"""
Document processing service for PDF and Word extraction with OCR support.
"""
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from docx import Document

import config
from models.schemas import ChunkProvenance, DocumentChunk


def extract_pdf(file_path: Path) -> list[tuple[str, int]]:
    """
    Extract text from a PDF file, preserving page numbers.

    Args:
        file_path: Path to the PDF file

    Returns:
        List of (text, page_num) tuples, one per page (1-indexed)
    """
    pages = []
    doc = fitz.open(str(file_path))

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if text.strip():
            pages.append((text, page_num))

    doc.close()
    return pages


def extract_docx(file_path: Path) -> list[tuple[str, int]]:
    """
    Extract text from a Word document, preserving paragraph indices.

    Args:
        file_path: Path to the .docx file

    Returns:
        List of (text, para_idx) tuples, one per paragraph (1-indexed)
    """
    doc = Document(str(file_path))
    paragraphs = []

    for para_idx, para in enumerate(doc.paragraphs, start=1):
        text = para.text.strip()
        if text:
            paragraphs.append((text, para_idx))

    return paragraphs


def detect_scanned_pdf(file_path: Path) -> bool:
    """
    Detect if a PDF is likely scanned (image-based) by checking text yield.

    Args:
        file_path: Path to the PDF file

    Returns:
        True if PDF appears to be scanned (low text extraction)
    """
    doc = fitz.open(str(file_path))
    total_chars = 0
    page_count = len(doc)

    for page in doc:
        text = page.get_text("text")
        total_chars += len(text.strip())

    doc.close()

    if page_count == 0:
        return False

    chars_per_page = total_chars / page_count
    return chars_per_page < config.OCR_TEXT_THRESHOLD


def ocr_pdf(file_path: Path) -> Path:
    """
    Run OCR on a PDF file to create a searchable version.

    Args:
        file_path: Path to the input PDF

    Returns:
        Path to the OCR'd PDF (same location with _ocr suffix)

    Raises:
        RuntimeError: If OCR fails
    """
    output_path = file_path.with_stem(file_path.stem + "_ocr")

    try:
        result = subprocess.run(
            [
                "ocrmypdf",
                "--skip-text",  # Don't re-OCR pages that have text
                "--optimize", "1",
                str(file_path),
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode != 0 and result.returncode != 6:
            # Return code 6 means "no OCR needed" which is fine
            raise RuntimeError(f"OCR failed: {result.stderr}")

        return output_path if output_path.exists() else file_path

    except subprocess.TimeoutExpired:
        raise RuntimeError("OCR timed out")
    except FileNotFoundError:
        raise RuntimeError("ocrmypdf not installed. Run: brew install tesseract ghostscript && pip install ocrmypdf")


def chunk_text(
    text: str,
    file_name: str,
    page_num: Optional[int] = None,
    para_idx: Optional[int] = None,
    ocr: bool = False,
) -> list[DocumentChunk]:
    """
    Split text into overlapping chunks suitable for embedding.

    Args:
        text: The text to chunk
        file_name: Source file name
        page_num: Page number (for PDFs)
        para_idx: Paragraph index (for Word docs)
        ocr: Whether text was extracted via OCR

    Returns:
        List of DocumentChunk objects
    """
    # Simple word-based chunking
    # Target: 500-800 tokens (~400-640 words assuming 1.25 words/token)
    target_words = 500
    overlap_words = 80

    words = text.split()
    chunks = []

    if len(words) <= target_words:
        # Text fits in one chunk
        chunk_id = str(uuid.uuid4())[:8]
        chunks.append(DocumentChunk(
            text=text.strip(),
            provenance=ChunkProvenance(
                chunk_id=chunk_id,
                file_name=file_name,
                page_num=page_num,
                para_idx=para_idx,
                char_start=0,
                char_end=len(text),
                ocr=ocr,
            ),
        ))
        return chunks

    # Split into overlapping chunks
    start = 0
    char_pos = 0

    while start < len(words):
        end = min(start + target_words, len(words))
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)

        # Calculate character positions (approximate)
        chunk_start = char_pos
        chunk_end = chunk_start + len(chunk_text)

        chunk_id = str(uuid.uuid4())[:8]
        chunks.append(DocumentChunk(
            text=chunk_text,
            provenance=ChunkProvenance(
                chunk_id=chunk_id,
                file_name=file_name,
                page_num=page_num,
                para_idx=para_idx,
                char_start=chunk_start,
                char_end=chunk_end,
                ocr=ocr,
            ),
        ))

        # Move start with overlap
        start = end - overlap_words if end < len(words) else len(words)
        char_pos = chunk_end - (overlap_words * 6)  # Approximate char position

    return chunks


def process_document(file_path: Path) -> list[DocumentChunk]:
    """
    Process a document (PDF or Word) into chunks with provenance.

    Args:
        file_path: Path to the document

    Returns:
        List of DocumentChunk objects

    Raises:
        ValueError: If file type is not supported
    """
    suffix = file_path.suffix.lower()
    file_name = file_path.name
    all_chunks = []

    if suffix == ".pdf":
        # Check if scanned
        is_scanned = detect_scanned_pdf(file_path)
        ocr_applied = False

        if is_scanned:
            try:
                file_path = ocr_pdf(file_path)
                ocr_applied = True
            except RuntimeError as e:
                print(f"Warning: OCR failed for {file_name}: {e}")

        # Extract text
        pages = extract_pdf(file_path)

        for text, page_num in pages:
            chunks = chunk_text(
                text=text,
                file_name=file_name,
                page_num=page_num,
                ocr=ocr_applied,
            )
            all_chunks.extend(chunks)

    elif suffix in (".docx", ".doc"):
        if suffix == ".doc":
            raise ValueError(".doc format not supported. Please convert to .docx")

        paragraphs = extract_docx(file_path)

        # Combine consecutive paragraphs for better chunks
        combined_text = ""
        start_para = 1

        for text, para_idx in paragraphs:
            if len(combined_text.split()) + len(text.split()) > 600:
                # Chunk the accumulated text
                if combined_text.strip():
                    chunks = chunk_text(
                        text=combined_text,
                        file_name=file_name,
                        para_idx=start_para,
                    )
                    all_chunks.extend(chunks)
                combined_text = text
                start_para = para_idx
            else:
                combined_text += "\n\n" + text

        # Don't forget the last batch
        if combined_text.strip():
            chunks = chunk_text(
                text=combined_text,
                file_name=file_name,
                para_idx=start_para,
            )
            all_chunks.extend(chunks)

    else:
        raise ValueError(f"Unsupported file type: {suffix}. Supported: .pdf, .docx")

    return all_chunks


def get_supported_extensions() -> list[str]:
    """Get list of supported file extensions."""
    return [".pdf", ".docx"]
