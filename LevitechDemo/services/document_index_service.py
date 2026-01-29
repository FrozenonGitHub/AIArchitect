"""
Document index service for storing chunk provenance and raw text.
Separate from vector DB for direct lookups.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.schemas import DocumentChunk, ChunkProvenance, DocumentInfo
from services.path_validator import validate_case_path, ensure_case_exists


INDEX_FILE = "document_index.json"
RAW_TEXT_DIR = "raw_text"


def _get_index_path(case_id: str) -> Path:
    """Get path to the document index file for a case."""
    case_path = ensure_case_exists(case_id)
    return case_path / INDEX_FILE


def _get_raw_text_dir(case_id: str) -> Path:
    """Get path to raw text storage directory for a case."""
    case_path = ensure_case_exists(case_id)
    raw_dir = case_path / RAW_TEXT_DIR
    raw_dir.mkdir(exist_ok=True)
    return raw_dir


def _load_index(case_id: str) -> dict:
    """Load the document index for a case."""
    index_path = _get_index_path(case_id)
    if index_path.exists():
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {"documents": {}, "chunks": {}}
    return {"documents": {}, "chunks": {}}


def _save_index(case_id: str, index: dict) -> None:
    """Save the document index for a case."""
    index_path = _get_index_path(case_id)
    temp_path = index_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, default=str)
    temp_path.replace(index_path)


def index_document(case_id: str, file_name: str, chunks: list[DocumentChunk]) -> DocumentInfo:
    """
    Index a document's chunks and store provenance.

    Args:
        case_id: The case identifier
        file_name: Name of the source document
        chunks: List of chunks from document_processor

    Returns:
        DocumentInfo with indexing metadata
    """
    index = _load_index(case_id)
    raw_text_dir = _get_raw_text_dir(case_id)

    # Store document info
    doc_info = {
        "file_name": file_name,
        "chunk_count": len(chunks),
        "chunk_ids": [],
        "ocr_applied": any(c.provenance.ocr for c in chunks),
        "indexed_at": datetime.utcnow().isoformat(),
    }

    # Store each chunk's provenance
    for chunk in chunks:
        chunk_id = chunk.provenance.chunk_id
        doc_info["chunk_ids"].append(chunk_id)

        # Store provenance in index
        index["chunks"][chunk_id] = {
            "file_name": chunk.provenance.file_name,
            "page_num": chunk.provenance.page_num,
            "para_idx": chunk.provenance.para_idx,
            "char_start": chunk.provenance.char_start,
            "char_end": chunk.provenance.char_end,
            "ocr": chunk.provenance.ocr,
            "text_preview": chunk.text[:100] + "..." if len(chunk.text) > 100 else chunk.text,
        }

        # Store raw text in separate file (for retrieval/validation)
        text_path = raw_text_dir / f"{chunk_id}.txt"
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(chunk.text)

    index["documents"][file_name] = doc_info
    _save_index(case_id, index)

    return DocumentInfo(
        file_name=file_name,
        file_size=0,  # Not tracked here
        chunk_count=len(chunks),
        ocr_applied=doc_info["ocr_applied"],
        indexed_at=datetime.fromisoformat(doc_info["indexed_at"]),
    )


def get_chunk_provenance(case_id: str, chunk_id: str) -> Optional[ChunkProvenance]:
    """
    Get provenance information for a specific chunk.

    Args:
        case_id: The case identifier
        chunk_id: The chunk identifier

    Returns:
        ChunkProvenance if found, None otherwise
    """
    index = _load_index(case_id)
    chunk_data = index["chunks"].get(chunk_id)

    if not chunk_data:
        return None

    return ChunkProvenance(
        chunk_id=chunk_id,
        file_name=chunk_data["file_name"],
        page_num=chunk_data.get("page_num"),
        para_idx=chunk_data.get("para_idx"),
        char_start=chunk_data.get("char_start", 0),
        char_end=chunk_data.get("char_end", 0),
        ocr=chunk_data.get("ocr", False),
    )


def get_chunk_text(case_id: str, chunk_id: str) -> Optional[str]:
    """
    Get the raw text for a specific chunk.

    Args:
        case_id: The case identifier
        chunk_id: The chunk identifier

    Returns:
        Chunk text if found, None otherwise
    """
    raw_text_dir = _get_raw_text_dir(case_id)
    text_path = raw_text_dir / f"{chunk_id}.txt"

    if text_path.exists():
        with open(text_path, "r", encoding="utf-8") as f:
            return f.read()

    return None


def get_chunks_by_ids(case_id: str, chunk_ids: list[str]) -> list[DocumentChunk]:
    """
    Get full DocumentChunk objects for a list of chunk IDs.

    Args:
        case_id: The case identifier
        chunk_ids: List of chunk IDs to retrieve

    Returns:
        List of DocumentChunk objects (without embeddings)
    """
    chunks = []
    for chunk_id in chunk_ids:
        provenance = get_chunk_provenance(case_id, chunk_id)
        text = get_chunk_text(case_id, chunk_id)

        if provenance and text:
            chunks.append(DocumentChunk(
                text=text,
                provenance=provenance,
            ))

    return chunks


def get_raw_text(case_id: str, file_name: str, page_num: Optional[int] = None) -> Optional[str]:
    """
    Get concatenated raw text for a file (optionally filtered by page).

    Args:
        case_id: The case identifier
        file_name: The document file name
        page_num: Optional page number filter

    Returns:
        Concatenated text from matching chunks
    """
    index = _load_index(case_id)
    doc_data = index["documents"].get(file_name)

    if not doc_data:
        return None

    texts = []
    for chunk_id in doc_data["chunk_ids"]:
        chunk_data = index["chunks"].get(chunk_id, {})

        # Filter by page if specified
        if page_num is not None and chunk_data.get("page_num") != page_num:
            continue

        text = get_chunk_text(case_id, chunk_id)
        if text:
            texts.append(text)

    return "\n\n".join(texts) if texts else None


def list_documents(case_id: str) -> list[DocumentInfo]:
    """
    List all indexed documents for a case.

    Args:
        case_id: The case identifier

    Returns:
        List of DocumentInfo objects
    """
    index = _load_index(case_id)
    docs = []

    for file_name, doc_data in index["documents"].items():
        docs.append(DocumentInfo(
            file_name=file_name,
            file_size=0,
            chunk_count=doc_data["chunk_count"],
            ocr_applied=doc_data.get("ocr_applied", False),
            indexed_at=datetime.fromisoformat(doc_data["indexed_at"]) if "indexed_at" in doc_data else datetime.utcnow(),
        ))

    return docs


def get_all_chunk_ids(case_id: str) -> list[str]:
    """
    Get all chunk IDs for a case.

    Args:
        case_id: The case identifier

    Returns:
        List of all chunk IDs
    """
    index = _load_index(case_id)
    return list(index["chunks"].keys())


def delete_document(case_id: str, file_name: str) -> bool:
    """
    Delete a document and its chunks from the index.

    Args:
        case_id: The case identifier
        file_name: The document to delete

    Returns:
        True if deleted, False if not found
    """
    index = _load_index(case_id)

    if file_name not in index["documents"]:
        return False

    doc_data = index["documents"][file_name]
    raw_text_dir = _get_raw_text_dir(case_id)

    # Delete chunk files and index entries
    for chunk_id in doc_data["chunk_ids"]:
        # Remove from index
        if chunk_id in index["chunks"]:
            del index["chunks"][chunk_id]

        # Remove raw text file
        text_path = raw_text_dir / f"{chunk_id}.txt"
        if text_path.exists():
            text_path.unlink()

    # Remove document entry
    del index["documents"][file_name]
    _save_index(case_id, index)

    return True
