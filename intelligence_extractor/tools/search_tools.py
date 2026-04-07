"""Batch-optimized search tools for intelligence extraction.

These are higher-throughput versions of the Phoenix search tools,
returning more results per query (page_size=10 vs 5) since batch
extraction prioritizes completeness over latency.
"""

import os
import logging
from google.cloud import discoveryengine_v1 as discoveryengine

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]
DATA_STORE_LOCATION = os.environ.get("DATA_STORE_LOCATION", "global")
EARNINGS_DATA_STORE_ID = os.environ["EARNINGS_DATA_STORE_ID"]
COMPETITOR_DATA_STORE_ID = os.environ["COMPETITOR_DATA_STORE_ID"]

# Batch extraction uses larger page size for comprehensive coverage
BATCH_PAGE_SIZE = 10


def _search_data_store(query: str, data_store_id: str) -> str:
    """Internal helper to query a Vertex AI Search data store.

    Batch-optimized: returns up to 10 results per query (vs 5 for live).
    """
    try:
        client = discoveryengine.SearchServiceClient()
        serving_config = (
            f"projects/{PROJECT_ID}/locations/{DATA_STORE_LOCATION}"
            f"/collections/default_collection/dataStores/{data_store_id}"
            f"/servingConfigs/default_serving_config"
        )

        request = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=query,
            page_size=BATCH_PAGE_SIZE,
        )

        response = client.search(request)
        results = []

        for result in response.results:
            doc = result.document
            derived_data = doc.derived_struct_data

            doc_snippets = []
            doc_title = ""

            if derived_data:
                doc_title = (
                    derived_data.get("title", "")
                    or derived_data.get("link", "")
                    or ""
                )

                # Method 1: snippets array
                for s in derived_data.get("snippets", []):
                    text = s.get("snippet", "") or s.get("htmlSnippet", "")
                    if text:
                        page = s.get("pageNumber", "")
                        prefix = f"[Page {page}] " if page else ""
                        doc_snippets.append(f"{prefix}{text}")

                # Method 2: extractive answers
                for ea in derived_data.get("extractive_answers", []):
                    text = ea.get("content", "")
                    if text:
                        page = ea.get("pageNumber", "")
                        prefix = f"[Page {page}] " if page else ""
                        doc_snippets.append(f"{prefix}{text}")

                # Method 3: extractive segments
                for seg in derived_data.get("extractive_segments", []):
                    text = seg.get("content", "")
                    if text:
                        page = seg.get("pageNumber", "")
                        prefix = f"[Page {page}] " if page else ""
                        doc_snippets.append(f"{prefix}{text}")

                # Method 4: direct content fields
                if not doc_snippets:
                    for key in ("content", "text", "snippet", "htmlSnippet"):
                        text = derived_data.get(key, "")
                        if text and isinstance(text, str):
                            doc_snippets.append(text)
                            break

                # Method 5: chunked content
                for chunk in derived_data.get("chunks", []):
                    text = chunk.get("content", "") or chunk.get("snippet", "")
                    if text:
                        page = chunk.get("pageNumber", "")
                        prefix = f"[Page {page}] " if page else ""
                        doc_snippets.append(f"{prefix}{text}")

            # Method 6: struct_data
            if not doc_snippets and doc.struct_data:
                for key in ("content", "text", "snippet", "body"):
                    text = doc.struct_data.get(key, "")
                    if text and isinstance(text, str):
                        doc_snippets.append(text)
                        break

            if doc_snippets:
                header = f"[Document: {doc_title or doc.name}]"
                results.append(f"{header}\n" + "\n".join(doc_snippets))
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

        return "\n\n---\n\n".join(results)
    except Exception as e:
        logger.error(f"Failed to search data store {data_store_id}: {e}")
        return f"Error searching documents: {e}"


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
    Currently contains Carrier Global transcripts and filings.

    Args:
        query: Natural language search query.

    Returns:
        str: Relevant snippets from competitor documents, or an error message.
    """
    return _search_data_store(query, COMPETITOR_DATA_STORE_ID)
