"""
Legal source cache service for storing and retrieving snapshots.
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import config
from models.schemas import LegalSource


def _url_to_hash(url: str) -> str:
    """Generate a safe hash from URL for filesystem storage."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _get_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc


def _get_cache_path(url: str) -> Path:
    """Get the cache directory path for a URL."""
    domain = _get_domain(url)
    url_hash = _url_to_hash(url)
    return config.LEGAL_CACHE_DIR / domain / url_hash


def store_source(url: str, html: str, text: str, title: str = "") -> LegalSource:
    """
    Store a fetched legal source in the cache.

    Args:
        url: The source URL
        html: Raw HTML content
        text: Extracted text content
        title: Page title (optional)

    Returns:
        LegalSource object with all metadata
    """
    domain = _get_domain(url)
    source_id = _url_to_hash(url)
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    fetched_at = datetime.utcnow()

    # Create cache directory
    cache_path = _get_cache_path(url)
    cache_path.mkdir(parents=True, exist_ok=True)

    # Store raw HTML
    html_path = cache_path / "source.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Store extracted text
    text_path = cache_path / "source.txt"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)

    # Store metadata
    meta = {
        "id": source_id,
        "url": url,
        "domain": domain,
        "title": title,
        "content_hash": content_hash,
        "fetched_at": fetched_at.isoformat(),
    }
    meta_path = cache_path / "meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    # Create short excerpt (first 500 chars of text)
    excerpt = text[:500].strip()
    if len(text) > 500:
        excerpt += "..."

    return LegalSource(
        id=source_id,
        url=url,
        domain=domain,
        title=title,
        excerpt=excerpt,
        text=text,
        html=html,
        content_hash=content_hash,
        fetched_at=fetched_at,
    )


def get_source(source_id: str) -> Optional[LegalSource]:
    """
    Get a cached legal source by its ID.

    Args:
        source_id: The source identifier (URL hash)

    Returns:
        LegalSource if found, None otherwise
    """
    # Search through all domain directories
    for domain_dir in config.LEGAL_CACHE_DIR.iterdir():
        if not domain_dir.is_dir():
            continue
        cache_path = domain_dir / source_id
        if cache_path.exists():
            return _load_source_from_path(cache_path)

    return None


def get_source_by_url(url: str) -> Optional[LegalSource]:
    """
    Get a cached legal source by its URL.

    Args:
        url: The source URL

    Returns:
        LegalSource if found in cache, None otherwise
    """
    cache_path = _get_cache_path(url)
    if cache_path.exists():
        return _load_source_from_path(cache_path)
    return None


def _load_source_from_path(cache_path: Path) -> Optional[LegalSource]:
    """Load a LegalSource from its cache directory."""
    meta_path = cache_path / "meta.json"
    text_path = cache_path / "source.txt"
    html_path = cache_path / "source.html"

    if not meta_path.exists():
        return None

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        text = ""
        if text_path.exists():
            with open(text_path, "r", encoding="utf-8") as f:
                text = f.read()

        html = ""
        if html_path.exists():
            with open(html_path, "r", encoding="utf-8") as f:
                html = f.read()

        excerpt = text[:500].strip()
        if len(text) > 500:
            excerpt += "..."

        return LegalSource(
            id=meta["id"],
            url=meta["url"],
            domain=meta["domain"],
            title=meta.get("title", ""),
            excerpt=excerpt,
            text=text,
            html=html,
            content_hash=meta.get("content_hash", ""),
            fetched_at=datetime.fromisoformat(meta["fetched_at"]) if "fetched_at" in meta else datetime.utcnow(),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Warning: Failed to load cached source from {cache_path}: {e}")
        return None


def source_exists(url: str) -> bool:
    """Check if a source is already cached."""
    cache_path = _get_cache_path(url)
    return cache_path.exists() and (cache_path / "meta.json").exists()


def get_source_text(source_id: str) -> Optional[str]:
    """
    Get just the text content of a cached source (for validation).

    Args:
        source_id: The source identifier

    Returns:
        Text content if found, None otherwise
    """
    source = get_source(source_id)
    return source.text if source else None


def list_cached_sources() -> list[dict]:
    """
    List all cached legal sources (metadata only).

    Returns:
        List of metadata dicts for all cached sources
    """
    sources = []
    for domain_dir in config.LEGAL_CACHE_DIR.iterdir():
        if not domain_dir.is_dir():
            continue
        for source_dir in domain_dir.iterdir():
            if not source_dir.is_dir():
                continue
            meta_path = source_dir / "meta.json"
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        sources.append(json.load(f))
                except json.JSONDecodeError:
                    pass
    return sources
