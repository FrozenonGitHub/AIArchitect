"""
ChromaDB service for vector storage and similarity search.
"""
from typing import Optional
import chromadb
from chromadb.config import Settings

import config
from models.schemas import DocumentChunk, SearchResult
from services import embedding_service


# Global client instance
_client: Optional[chromadb.PersistentClient] = None


def _get_client() -> chromadb.PersistentClient:
    """Get or create the ChromaDB client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=str(config.CHROMA_DB_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def _get_collection_name(case_id: str) -> str:
    """Generate collection name for a case."""
    # ChromaDB collection names must be 3-63 chars, alphanumeric with underscores
    safe_name = "".join(c if c.isalnum() else "_" for c in case_id)
    return f"case_{safe_name}"[:63]


def get_or_create_collection(case_id: str):
    """Get or create a collection for a case."""
    client = _get_client()
    collection_name = _get_collection_name(case_id)
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"case_id": case_id},
    )


def add_chunks(case_id: str, chunks: list[DocumentChunk]) -> int:
    """
    Add document chunks to the vector database.

    Args:
        case_id: The case identifier
        chunks: List of DocumentChunk objects (will generate embeddings)

    Returns:
        Number of chunks added
    """
    if not chunks:
        return 0

    collection = get_or_create_collection(case_id)

    # Generate embeddings for all chunks
    texts = [chunk.text for chunk in chunks]
    embeddings = embedding_service.embed_batch(texts)

    # Prepare data for ChromaDB
    ids = [chunk.provenance.chunk_id for chunk in chunks]
    documents = texts
    metadatas = [
        {
            "file_name": chunk.provenance.file_name,
            "page_num": chunk.provenance.page_num or -1,
            "para_idx": chunk.provenance.para_idx or -1,
            "char_start": chunk.provenance.char_start,
            "char_end": chunk.provenance.char_end,
            "ocr": chunk.provenance.ocr,
        }
        for chunk in chunks
    ]

    # Add to collection
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    return len(chunks)


def search_similar(
    case_id: str,
    query: str,
    top_k: int = 10,
) -> list[SearchResult]:
    """
    Search for similar chunks using vector similarity.

    Args:
        case_id: The case identifier
        query: The search query
        top_k: Number of results to return

    Returns:
        List of SearchResult objects sorted by similarity
    """
    collection = get_or_create_collection(case_id)

    # Check if collection has any documents
    if collection.count() == 0:
        return []

    # Generate query embedding
    query_embedding = embedding_service.embed_text(query)

    # Search
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    # Convert to SearchResult objects
    search_results = []
    if results["ids"] and results["ids"][0]:
        for i, chunk_id in enumerate(results["ids"][0]):
            # Convert distance to similarity score (ChromaDB uses L2 distance)
            distance = results["distances"][0][i] if results["distances"] else 0
            score = 1 / (1 + distance)  # Convert distance to similarity

            metadata = results["metadatas"][0][i] if results["metadatas"] else {}

            from models.schemas import ChunkProvenance
            provenance = ChunkProvenance(
                chunk_id=chunk_id,
                file_name=metadata.get("file_name", ""),
                page_num=metadata.get("page_num") if metadata.get("page_num", -1) != -1 else None,
                para_idx=metadata.get("para_idx") if metadata.get("para_idx", -1) != -1 else None,
                char_start=metadata.get("char_start", 0),
                char_end=metadata.get("char_end", 0),
                ocr=metadata.get("ocr", False),
            )

            search_results.append(SearchResult(
                chunk_id=chunk_id,
                text=results["documents"][0][i] if results["documents"] else "",
                score=score,
                provenance=provenance,
                source_type="client",
            ))

    return search_results


def delete_collection(case_id: str) -> bool:
    """
    Delete the collection for a case.

    Args:
        case_id: The case identifier

    Returns:
        True if deleted, False if not found
    """
    client = _get_client()
    collection_name = _get_collection_name(case_id)

    try:
        client.delete_collection(collection_name)
        return True
    except ValueError:
        return False


def get_collection_count(case_id: str) -> int:
    """Get the number of chunks in a case's collection."""
    collection = get_or_create_collection(case_id)
    return collection.count()


def delete_chunks(case_id: str, chunk_ids: list[str]) -> int:
    """
    Delete specific chunks from the collection.

    Args:
        case_id: The case identifier
        chunk_ids: List of chunk IDs to delete

    Returns:
        Number of chunks deleted
    """
    if not chunk_ids:
        return 0

    collection = get_or_create_collection(case_id)
    collection.delete(ids=chunk_ids)
    return len(chunk_ids)
