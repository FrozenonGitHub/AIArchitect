"""
Hybrid search service combining BM25 keyword and vector similarity search.
"""
from typing import Optional

import config
from models.schemas import SearchResult
from services import chroma_service, bm25_service


def search(
    case_id: str,
    query: str,
    top_k: int = None,
    bm25_weight: float = 0.5,
    vector_weight: float = 0.5,
) -> list[SearchResult]:
    """
    Perform hybrid search combining BM25 and vector similarity.

    Args:
        case_id: The case identifier
        query: The search query
        top_k: Number of results to return (default from config)
        bm25_weight: Weight for BM25 scores (default 0.5)
        vector_weight: Weight for vector scores (default 0.5)

    Returns:
        List of SearchResult objects with fused scores
    """
    if top_k is None:
        top_k = config.HYBRID_SEARCH_TOP_K

    # Fetch more results than needed for fusion
    fetch_k = top_k * 3

    # Get results from both sources
    bm25_results = bm25_service.search_keywords(case_id, query, top_k=fetch_k)
    vector_results = chroma_service.search_similar(case_id, query, top_k=fetch_k)

    # Normalize scores
    bm25_results = _normalize_scores(bm25_results)
    vector_results = _normalize_scores(vector_results)

    # Merge results by chunk_id
    merged: dict[str, SearchResult] = {}
    chunk_scores: dict[str, dict] = {}

    # Add BM25 results
    for result in bm25_results:
        chunk_id = result.chunk_id
        if chunk_id not in chunk_scores:
            chunk_scores[chunk_id] = {"bm25": 0, "vector": 0}
            merged[chunk_id] = result
        chunk_scores[chunk_id]["bm25"] = result.score

    # Add vector results
    for result in vector_results:
        chunk_id = result.chunk_id
        if chunk_id not in chunk_scores:
            chunk_scores[chunk_id] = {"bm25": 0, "vector": 0}
            merged[chunk_id] = result
        chunk_scores[chunk_id]["vector"] = result.score

    # Calculate fused scores
    fused_results = []
    for chunk_id, result in merged.items():
        scores = chunk_scores[chunk_id]
        fused_score = (
            bm25_weight * scores["bm25"] +
            vector_weight * scores["vector"]
        )
        # Create new result with fused score
        fused_result = SearchResult(
            chunk_id=result.chunk_id,
            text=result.text,
            score=fused_score,
            provenance=result.provenance,
            source_type=result.source_type,
        )
        fused_results.append(fused_result)

    # Sort by fused score
    fused_results.sort(key=lambda x: x.score, reverse=True)

    # Apply per-document cap
    fused_results = _apply_doc_cap(fused_results, config.MAX_CHUNKS_PER_DOC)

    # Deduplicate
    fused_results = bm25_service.dedupe_results(fused_results)

    return fused_results[:top_k]


def _normalize_scores(results: list[SearchResult]) -> list[SearchResult]:
    """
    Normalize scores to 0-1 range using min-max normalization.

    Args:
        results: List of SearchResult objects

    Returns:
        List with normalized scores
    """
    if not results:
        return results

    scores = [r.score for r in results]
    min_score = min(scores)
    max_score = max(scores)
    score_range = max_score - min_score

    if score_range == 0:
        # All scores are the same
        for result in results:
            result.score = 1.0 if max_score > 0 else 0.0
        return results

    for result in results:
        result.score = (result.score - min_score) / score_range

    return results


def _apply_doc_cap(
    results: list[SearchResult],
    max_per_doc: int,
) -> list[SearchResult]:
    """
    Apply per-document cap to results.

    Args:
        results: Sorted list of SearchResult objects
        max_per_doc: Maximum chunks per document

    Returns:
        Filtered list respecting the cap
    """
    doc_counts: dict[str, int] = {}
    filtered = []

    for result in results:
        file_name = result.provenance.file_name
        current_count = doc_counts.get(file_name, 0)

        if current_count < max_per_doc:
            doc_counts[file_name] = current_count + 1
            filtered.append(result)

    return filtered


def search_keyword_only(
    case_id: str,
    query: str,
    top_k: int = None,
) -> list[SearchResult]:
    """
    Search using only BM25 keyword matching (useful for names, dates, IDs).

    Args:
        case_id: The case identifier
        query: The search query
        top_k: Number of results to return

    Returns:
        List of SearchResult objects
    """
    if top_k is None:
        top_k = config.HYBRID_SEARCH_TOP_K

    results = bm25_service.search_keywords(case_id, query, top_k=top_k * 2)
    results = bm25_service.dedupe_results(results)
    return results[:top_k]


def search_vector_only(
    case_id: str,
    query: str,
    top_k: int = None,
) -> list[SearchResult]:
    """
    Search using only vector similarity (useful for narrative questions).

    Args:
        case_id: The case identifier
        query: The search query
        top_k: Number of results to return

    Returns:
        List of SearchResult objects
    """
    if top_k is None:
        top_k = config.HYBRID_SEARCH_TOP_K

    results = chroma_service.search_similar(case_id, query, top_k=top_k * 2)
    results = _apply_doc_cap(results, config.MAX_CHUNKS_PER_DOC)
    results = bm25_service.dedupe_results(results)
    return results[:top_k]
