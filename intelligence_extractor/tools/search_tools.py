"""Batch-optimized search tools for intelligence extraction.

These are higher-throughput versions of the Phoenix search tools,
returning more results per query (page_size=10 vs 5) since batch
extraction prioritizes completeness over latency.
"""

import os
import logging
from google.api_core.exceptions import FailedPrecondition
from google.cloud import discoveryengine_v1 as discoveryengine

# Serving-config and content-spec construction are shared with the Phoenix
# search tools; only the page size differs between batch and live search.
from phoenix.tools.document_tools import (
    MAX_CHARS_PER_SEARCH,
    _content_spec,
    _document_text,
    _serving_config,
)

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
DATA_STORE_LOCATION = os.environ.get("DATA_STORE_LOCATION", "global")
EARNINGS_DATA_STORE_ID = os.environ.get("EARNINGS_DATA_STORE_ID", "")
COMPETITOR_DATA_STORE_ID = os.environ.get("COMPETITOR_DATA_STORE_ID", "")

# Batch extraction uses larger page size for comprehensive coverage
BATCH_PAGE_SIZE = 10


def _search_data_store(query: str, data_store_id: str) -> str:
    """Internal helper to query a Vertex AI Search data store.

    Batch-optimized: returns up to 10 results per query (vs 5 for live).
    """
    try:
        client = discoveryengine.SearchServiceClient()
        serving_config = _serving_config(data_store_id)

        def _run(extractive: bool):
            return client.search(
                discoveryengine.SearchRequest(
                    serving_config=serving_config,
                    query=query,
                    page_size=BATCH_PAGE_SIZE,
                    content_search_spec=_content_spec(extractive),
                )
            )

        try:
            response = _run(extractive=True)
        except FailedPrecondition:
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
    """Searches the company's historical earnings data store (batch mode).

    Returns up to 10 results per query for comprehensive extraction.
    Contains past earnings call transcripts, 10-Ks, 10-Qs, and filings.

    Args:
        query: Natural language search query.

    Returns:
        str: Relevant snippets from matching documents, or an error message.
    """
    return _search_data_store(query, EARNINGS_DATA_STORE_ID)


def search_competitor_documents(query: str) -> str:
    """Searches the competitor earnings data store (batch mode).

    Returns up to 10 results per query for comprehensive extraction.
    Contains transcripts and filings for the competitors configured in
    the active company profile.

    Args:
        query: Natural language search query.

    Returns:
        str: Relevant snippets from competitor documents, or an error message.
    """
    return _search_data_store(query, COMPETITOR_DATA_STORE_ID)
