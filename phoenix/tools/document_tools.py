import os
import logging
from google.api_core.exceptions import FailedPrecondition
from google.cloud import discoveryengine_v1 as discoveryengine

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
DATA_STORE_LOCATION = os.environ.get("DATA_STORE_LOCATION", "global")
EARNINGS_DATA_STORE_ID = os.environ.get("EARNINGS_DATA_STORE_ID", "")
COMPETITOR_DATA_STORE_ID = os.environ.get("COMPETITOR_DATA_STORE_ID", "")

# Optional search engines (apps) sitting over the data stores. Extractive
# answers/segments — and the page numbers the citation format depends on — are
# Enterprise-edition features that can only be enabled at the engine level, so
# querying the engine returns far richer text than the bare data store.
EARNINGS_SEARCH_ENGINE_ID = os.environ.get("EARNINGS_SEARCH_ENGINE_ID", "")
COMPETITOR_SEARCH_ENGINE_ID = os.environ.get("COMPETITOR_SEARCH_ENGINE_ID", "")

_ENGINE_FOR_STORE = {
    EARNINGS_DATA_STORE_ID: EARNINGS_SEARCH_ENGINE_ID,
    COMPETITOR_DATA_STORE_ID: COMPETITOR_SEARCH_ENGINE_ID,
}


def _serving_config(data_store_id: str) -> str:
    """Prefers the engine serving config, falling back to the data store."""
    base = (
        f"projects/{PROJECT_ID}/locations/{DATA_STORE_LOCATION}"
        f"/collections/default_collection"
    )
    engine_id = _ENGINE_FOR_STORE.get(data_store_id, "")
    if engine_id:
        return f"{base}/engines/{engine_id}/servingConfigs/default_serving_config"
    return f"{base}/dataStores/{data_store_id}/servingConfigs/default_serving_config"


def _content_spec(extractive: bool):
    """Asks the API for the text shapes this module knows how to parse.

    Without a content_search_spec the API returns only document metadata —
    title and link — and every extraction path below silently finds nothing.
    """
    if not extractive:
        return discoveryengine.SearchRequest.ContentSearchSpec(
            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                return_snippet=True
            ),
        )
    return discoveryengine.SearchRequest.ContentSearchSpec(
        snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
            return_snippet=True
        ),
        extractive_content_spec=(
            discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                max_extractive_answer_count=1,
                max_extractive_segment_count=2,
            )
        ),
    )


# Result size caps. Extractive answers and segments are far richer than the
# snippets this module used to get, and the extractors issue dozens of searches
# per run — uncapped, a single 60-search plan exceeded the model's context and
# the run stopped partway through with no report. Cap per document and per
# search so a large search plan stays affordable.
MAX_CHARS_PER_DOC = 1200
MAX_CHARS_PER_SEARCH = 6000


def _clean(text: str) -> str:
    """Strips the HTML the snippet API embeds (<b> tags, &#39; entities)."""
    import html
    import re

    return html.unescape(re.sub(r"<[^>]+>", "", str(text))).strip()


def _document_text(derived_data, doc) -> str:
    """Best available text for one document, bounded in size.

    Sources are tried in order of information density rather than concatenated:
    the same passage is usually present as an extractive answer, an extractive
    segment AND a snippet, so appending all three tripled the payload for no
    extra information.
    """
    def _collect(entries, key):
        out = []
        for entry in entries or []:
            item = dict(entry)
            text = _clean(item.get(key, ""))
            if not text:
                continue
            page = item.get("pageNumber", "")
            out.append(f"[Page {page}] {text}" if page else text)
        return out

    parts = []
    if derived_data:
        # Extractive answers carry page numbers and are the densest form.
        parts = _collect(derived_data.get("extractive_answers"), "content")
        if not parts:
            parts = _collect(derived_data.get("extractive_segments"), "content")
        if not parts:
            parts = _collect(derived_data.get("snippets"), "snippet")
        if not parts:
            parts = _collect(derived_data.get("chunks"), "content")
        if not parts:
            for key in ("content", "text", "snippet", "htmlSnippet"):
                value = derived_data.get(key, "")
                if value and isinstance(value, str):
                    parts = [_clean(value)]
                    break

    if not parts and getattr(doc, "struct_data", None):
        for key in ("content", "text", "snippet", "body"):
            value = doc.struct_data.get(key, "")
            if value and isinstance(value, str):
                parts = [_clean(value)]
                break

    text = "\n".join(parts)
    if len(text) > MAX_CHARS_PER_DOC:
        text = text[:MAX_CHARS_PER_DOC].rsplit(" ", 1)[0] + " …[truncated]"
    return text


def _search_data_store(query: str, data_store_id: str) -> str:
    """Internal helper to query a Vertex AI Search data store."""
    try:
        client = discoveryengine.SearchServiceClient()
        serving_config = _serving_config(data_store_id)

        def _run(extractive: bool):
            return client.search(
                discoveryengine.SearchRequest(
                    serving_config=serving_config,
                    query=query,
                    page_size=5,
                    content_search_spec=_content_spec(extractive),
                )
            )

        try:
            response = _run(extractive=True)
        except FailedPrecondition:
            # Standard-edition store: extractive answers are unavailable, but
            # snippets still are. Degrade rather than returning nothing.
            logger.info(
                "Extractive content unavailable for %s; using snippets only.",
                data_store_id,
            )
            response = _run(extractive=False)

        results = []

        for result in response.results:
            doc = result.document
            derived_data = doc.derived_struct_data

            doc_title = ""
            if derived_data:
                doc_title = (
                    derived_data.get("title", "")
                    or derived_data.get("link", "")
                    or ""
                )

            doc_text = _document_text(derived_data, doc)
            if doc_text:
                header = f"[Document: {doc_title or doc.name}]"
                results.append(f"{header}\n{doc_text}")
            else:
                # Last resort: log all available keys so we can fix parsing
                avail_keys = list(derived_data.keys()) if derived_data else []
                struct_keys = list(doc.struct_data.keys()) if doc.struct_data else []
                logger.warning(
                    "No text extracted from %s. "
                    "derived_struct_data keys: %s, struct_data keys: %s",
                    doc.name, avail_keys, struct_keys,
                )

        if not results:
            return "No relevant information found in the data store for this query."

        joined = "\n\n---\n\n".join(results)
        if len(joined) > MAX_CHARS_PER_SEARCH:
            joined = (
                joined[:MAX_CHARS_PER_SEARCH].rsplit("\n\n---\n\n", 1)[0]
                + "\n\n---\n\n[Additional results omitted — narrow the query to see more.]"
            )
        return joined
    except Exception as e:
        logger.error("Failed to search data store %s: %s", data_store_id, e)
        return "Error searching documents. Check server logs for details."


def search_historical_documents(query: str) -> str:
    """Searches the company's own historical earnings data store.

    Contains past earnings call transcripts (Q1-Q3), 10-Ks, 10-Qs,
    and other company filings.

    Args:
        query: Natural language search query (e.g., "What did analysts ask
               about operating margins?", "management guidance for Q3").

    Returns:
        str: Relevant snippets from matching documents, or an error message.
    """
    return _search_data_store(query, EARNINGS_DATA_STORE_ID)


def search_competitor_documents(query: str) -> str:
    """Searches the competitor earnings data store.

    Contains earnings call transcripts and filings for the competitors
    configured in the active company profile. Scope the query by naming
    the competitor you want.

    Args:
        query: Natural language search query naming a competitor (e.g.,
               "<competitor> operating margin",
               "What did analysts ask <competitor> about pricing?",
               "<competitor> guidance for 2025").

    Returns:
        str: Relevant snippets from competitor documents, or an error message.
    """
    return _search_data_store(query, COMPETITOR_DATA_STORE_ID)
