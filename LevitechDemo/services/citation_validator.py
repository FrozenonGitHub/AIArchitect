"""
Citation validation service with 4-check verification.

All citations must pass:
1. ID exists in source cache
2. URL matches stored URL
3. Domain is whitelisted
4. Excerpt appears in stored source text (critical!)
"""
import re
from typing import Optional
from urllib.parse import urlparse

import config
from models.schemas import Citation, LegalSource
from services import legal_cache_service, document_index_service


class CitationValidationError(Exception):
    """Raised when citation validation fails."""
    def __init__(self, citation: Citation, reason: str):
        self.citation = citation
        self.reason = reason
        super().__init__(f"Citation validation failed: {reason}")


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace for comparison."""
    # Replace all whitespace sequences with single space
    return re.sub(r'\s+', ' ', text.strip().lower())


def validate_legal_citation(citation: Citation) -> tuple[bool, str]:
    """
    Validate a legal source citation with 4 checks.

    Args:
        citation: The Citation object to validate

    Returns:
        Tuple of (is_valid, reason)
    """
    # Check 1: ID exists
    source = legal_cache_service.get_source(citation.id)
    if source is None:
        return False, f"Unknown citation ID: {citation.id}"

    # Check 2: URL matches
    if citation.url and citation.url != source.url:
        return False, f"URL mismatch: cited '{citation.url}' but source has '{source.url}'"

    # Check 3: Domain is whitelisted
    domain = urlparse(source.url).netloc.lower()
    is_whitelisted = any(
        domain == d or domain.endswith("." + d)
        for d in config.WHITELIST_DOMAINS
    )
    if not is_whitelisted:
        return False, f"Domain not whitelisted: {domain}"

    # Check 4: EXCERPT VERIFICATION (Critical!)
    if not citation.excerpt:
        return False, "Citation has no excerpt"

    normalized_excerpt = _normalize_whitespace(citation.excerpt)
    normalized_source = _normalize_whitespace(source.text)

    if normalized_excerpt not in normalized_source:
        # Try fuzzy match for minor differences
        if not _fuzzy_excerpt_match(citation.excerpt, source.text):
            return False, "Excerpt not found in source text"

    return True, "Valid"


def validate_client_citation(case_id: str, citation: Citation) -> tuple[bool, str]:
    """
    Validate a client document citation.

    Args:
        case_id: The case identifier
        citation: The Citation object to validate

    Returns:
        Tuple of (is_valid, reason)
    """
    if not citation.file_name:
        return False, "Client citation has no file_name"

    # Get the raw text for the cited location
    chunk_text = None

    if citation.id:
        # Try to get by chunk ID
        chunk_text = document_index_service.get_chunk_text(case_id, citation.id)

    if chunk_text is None and citation.file_name:
        # Try to get by file + page
        chunk_text = document_index_service.get_raw_text(
            case_id,
            citation.file_name,
            citation.page_num,
        )

    if chunk_text is None:
        return False, f"Source document not found: {citation.file_name}"

    # Check excerpt exists in source
    if not citation.excerpt:
        return False, "Citation has no excerpt"

    normalized_excerpt = _normalize_whitespace(citation.excerpt)
    normalized_source = _normalize_whitespace(chunk_text)

    if normalized_excerpt not in normalized_source:
        if not _fuzzy_excerpt_match(citation.excerpt, chunk_text):
            return False, f"Excerpt not found in {citation.file_name}"

    return True, "Valid"


def _fuzzy_excerpt_match(excerpt: str, source_text: str, threshold: float = 0.8) -> bool:
    """
    Attempt fuzzy matching for excerpts that may have minor differences.

    Args:
        excerpt: The quoted excerpt
        source_text: The source text to search in
        threshold: Minimum similarity for a match

    Returns:
        True if a fuzzy match is found
    """
    # Normalize
    excerpt_words = _normalize_whitespace(excerpt).split()
    source_words = _normalize_whitespace(source_text).split()

    if len(excerpt_words) < 3:
        # Too short for fuzzy match, require exact
        return False

    # Sliding window search
    window_size = len(excerpt_words)

    for i in range(len(source_words) - window_size + 1):
        window = source_words[i:i + window_size]

        # Calculate word overlap
        matches = sum(1 for e, w in zip(excerpt_words, window) if e == w)
        similarity = matches / window_size

        if similarity >= threshold:
            return True

    return False


def validate_citation(case_id: str, citation: Citation) -> tuple[bool, str]:
    """
    Validate a citation based on its source type.

    Args:
        case_id: The case identifier
        citation: The Citation object to validate

    Returns:
        Tuple of (is_valid, reason)
    """
    if citation.source_type == "legal":
        return validate_legal_citation(citation)
    elif citation.source_type == "client":
        return validate_client_citation(case_id, citation)
    else:
        return False, f"Unknown source type: {citation.source_type}"


def validate_all_citations(
    case_id: str,
    citations: list[Citation],
) -> list[tuple[Citation, bool, str]]:
    """
    Validate all citations and return results.

    Args:
        case_id: The case identifier
        citations: List of Citation objects

    Returns:
        List of (citation, is_valid, reason) tuples
    """
    results = []
    for citation in citations:
        is_valid, reason = validate_citation(case_id, citation)
        results.append((citation, is_valid, reason))
    return results


def all_citations_valid(case_id: str, citations: list[Citation]) -> tuple[bool, list[str]]:
    """
    Check if all citations are valid.

    Args:
        case_id: The case identifier
        citations: List of Citation objects

    Returns:
        Tuple of (all_valid, list_of_errors)
    """
    results = validate_all_citations(case_id, citations)
    errors = []

    for citation, is_valid, reason in results:
        if not is_valid:
            source_desc = citation.url if citation.source_type == "legal" else citation.file_name
            errors.append(f"{source_desc}: {reason}")

    return len(errors) == 0, errors


def get_validation_summary(case_id: str, citations: list[Citation]) -> dict:
    """
    Get a detailed validation summary.

    Args:
        case_id: The case identifier
        citations: List of Citation objects

    Returns:
        Dict with validation summary
    """
    results = validate_all_citations(case_id, citations)

    valid_count = sum(1 for _, v, _ in results if v)
    invalid_count = len(results) - valid_count

    invalid_details = []
    for citation, is_valid, reason in results:
        if not is_valid:
            invalid_details.append({
                "source_type": citation.source_type,
                "id": citation.id,
                "url": citation.url,
                "file_name": citation.file_name,
                "excerpt_preview": citation.excerpt[:50] + "..." if len(citation.excerpt) > 50 else citation.excerpt,
                "reason": reason,
            })

    return {
        "total": len(citations),
        "valid": valid_count,
        "invalid": invalid_count,
        "all_valid": invalid_count == 0,
        "invalid_details": invalid_details,
    }
