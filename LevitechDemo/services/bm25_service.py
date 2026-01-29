"""
BM25 keyword search service with per-document cap and deduplication.
"""
import re
from typing import Optional
from rank_bm25 import BM25Okapi

import config
from models.schemas import SearchResult, ChunkProvenance
from services import document_index_service


# In-memory BM25 indices per case
_indices: dict[str, dict] = {}


def _tokenize(text: str) -> list[str]:
    """Simple tokenization for BM25."""
    # Lowercase and split on non-alphanumeric
    text = text.lower()
    tokens = re.findall(r'\b\w+\b', text)
    return tokens


def build_index(case_id: str) -> int:
    """
    Build or rebuild the BM25 index for a case.

    Args:
        case_id: The case identifier

    Returns:
        Number of chunks indexed
    """
    # Get all chunks for the case
    chunk_ids = document_index_service.get_all_chunk_ids(case_id)
    chunks = document_index_service.get_chunks_by_ids(case_id, chunk_ids)

    if not chunks:
        _indices[case_id] = {"bm25": None, "chunks": [], "chunk_ids": []}
        return 0

    # Tokenize all documents
    tokenized_corpus = [_tokenize(chunk.text) for chunk in chunks]

    # Build BM25 index
    bm25 = BM25Okapi(tokenized_corpus)

    # Store index with chunk references
    _indices[case_id] = {
        "bm25": bm25,
        "chunks": chunks,
        "chunk_ids": [c.provenance.chunk_id for c in chunks],
    }

    return len(chunks)


def _ensure_index(case_id: str) -> None:
    """Ensure the BM25 index exists for a case, building if needed."""
    if case_id not in _indices:
        build_index(case_id)


def search_keywords(
    case_id: str,
    query: str,
    top_k: int = 10,
    max_per_doc: int = None,
) -> list[SearchResult]:
    """
    Search using BM25 keyword matching.

    Args:
        case_id: The case identifier
        query: The search query
        top_k: Number of results to return
        max_per_doc: Maximum chunks per document (default from config)

    Returns:
        List of SearchResult objects sorted by BM25 score
    """
    _ensure_index(case_id)

    index_data = _indices.get(case_id)
    if not index_data or index_data["bm25"] is None:
        return []

    bm25 = index_data["bm25"]
    chunks = index_data["chunks"]

    if max_per_doc is None:
        max_per_doc = config.MAX_CHUNKS_PER_DOC

    # Tokenize query
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # Get BM25 scores
    scores = bm25.get_scores(query_tokens)

    # Create scored results
    scored_results = []
    for i, score in enumerate(scores):
        if score > 0:
            scored_results.append((score, chunks[i]))

    # Sort by score descending
    scored_results.sort(key=lambda x: x[0], reverse=True)

    # Apply per-document cap
    doc_counts: dict[str, int] = {}
    filtered_results = []

    for score, chunk in scored_results:
        file_name = chunk.provenance.file_name
        current_count = doc_counts.get(file_name, 0)

        if current_count < max_per_doc:
            doc_counts[file_name] = current_count + 1
            filtered_results.append((score, chunk))

        if len(filtered_results) >= top_k * 2:  # Get extras for dedupe
            break

    # Convert to SearchResult
    results = []
    for score, chunk in filtered_results[:top_k]:
        results.append(SearchResult(
            chunk_id=chunk.provenance.chunk_id,
            text=chunk.text,
            score=score,
            provenance=chunk.provenance,
            source_type="client",
        ))

    return results


def invalidate_index(case_id: str) -> None:
    """
    Invalidate the cached index for a case (call after adding/removing docs).

    Args:
        case_id: The case identifier
    """
    if case_id in _indices:
        del _indices[case_id]


def dedupe_results(
    results: list[SearchResult],
    similarity_threshold: float = None,
) -> list[SearchResult]:
    """
    Remove near-duplicate results based on text overlap.

    Args:
        results: List of SearchResult objects
        similarity_threshold: Overlap threshold for deduplication

    Returns:
        Deduplicated list of results
    """
    if similarity_threshold is None:
        similarity_threshold = config.DEDUPE_SIMILARITY_THRESHOLD

    if len(results) <= 1:
        return results

    deduped = [results[0]]

    for result in results[1:]:
        is_duplicate = False
        result_tokens = set(_tokenize(result.text))

        for existing in deduped:
            existing_tokens = set(_tokenize(existing.text))

            # Calculate Jaccard similarity
            if not result_tokens or not existing_tokens:
                continue

            intersection = len(result_tokens & existing_tokens)
            union = len(result_tokens | existing_tokens)
            similarity = intersection / union if union > 0 else 0

            if similarity >= similarity_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            deduped.append(result)

    return deduped
