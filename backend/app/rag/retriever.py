"""
Trinity — RAG Retriever
Query ChromaDB collections for relevant code and documentation.
"""

import logging
from typing import Optional
from dataclasses import dataclass, field

import chromadb

from app.rag.indexer import get_chroma_client, CODE_COLLECTION, DOCS_COLLECTION

logger = logging.getLogger("triageforge.rag.retriever")


@dataclass
class RetrievalResult:
    """A single retrieval result from ChromaDB."""
    content: str
    file_path: str
    relevance_score: float
    metadata: dict = field(default_factory=dict)


async def search_code(
    query: str,
    n_results: int = 5,
    chroma_client: Optional[chromadb.HttpClient] = None,
) -> list[RetrievalResult]:
    """
    Search the Saleor code collection for relevant source code.
    
    Args:
        query: Natural language query (e.g., "checkout total None error")
        n_results: Maximum number of results to return
        chroma_client: Optional pre-configured ChromaDB client
        
    Returns:
        List of RetrievalResult sorted by relevance
    """
    if chroma_client is None:
        chroma_client = get_chroma_client()

    try:
        collection = chroma_client.get_collection(name=CODE_COLLECTION)
    except Exception as e:
        logger.warning("Code collection not found: %s", e)
        return []

    if collection.count() == 0:
        logger.warning("Code collection is empty")
        return []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        logger.error("ChromaDB query failed: %s", e)
        return []

    retrieval_results = []
    if results and results["documents"] and results["documents"][0]:
        for doc, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB returns L2 distance; convert to similarity score (0-1)
            # Lower distance = more similar
            similarity = max(0.0, 1.0 - (distance / 2.0))
            retrieval_results.append(RetrievalResult(
                content=doc,
                file_path=meta.get("file_path", "unknown"),
                relevance_score=round(similarity, 4),
                metadata=meta,
            ))

    return retrieval_results


async def search_docs(
    query: str,
    n_results: int = 5,
    chroma_client: Optional[chromadb.HttpClient] = None,
) -> list[RetrievalResult]:
    """
    Search the Saleor documentation collection for relevant docs and runbooks.
    
    Args:
        query: Natural language query (e.g., "payment timeout runbook")
        n_results: Maximum number of results to return
        chroma_client: Optional pre-configured ChromaDB client
        
    Returns:
        List of RetrievalResult sorted by relevance
    """
    if chroma_client is None:
        chroma_client = get_chroma_client()

    try:
        collection = chroma_client.get_collection(name=DOCS_COLLECTION)
    except Exception as e:
        logger.warning("Docs collection not found: %s", e)
        return []

    if collection.count() == 0:
        logger.warning("Docs collection is empty")
        return []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        logger.error("ChromaDB query failed: %s", e)
        return []

    retrieval_results = []
    if results and results["documents"] and results["documents"][0]:
        for doc, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            similarity = max(0.0, 1.0 - (distance / 2.0))
            retrieval_results.append(RetrievalResult(
                content=doc,
                file_path=meta.get("file_path", "unknown"),
                relevance_score=round(similarity, 4),
                metadata=meta,
            ))

    return retrieval_results


async def search_all(
    query: str,
    n_code_results: int = 5,
    n_doc_results: int = 5,
    chroma_client: Optional[chromadb.HttpClient] = None,
) -> dict:
    """
    Search both code and documentation collections.
    
    Returns dict with 'code' and 'docs' keys, each containing a list of results.
    """
    if chroma_client is None:
        chroma_client = get_chroma_client()

    code_results = await search_code(query, n_code_results, chroma_client)
    doc_results = await search_docs(query, n_doc_results, chroma_client)

    return {
        "code": code_results,
        "docs": doc_results,
    }
