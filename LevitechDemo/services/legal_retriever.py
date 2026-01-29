"""
Legal source retrieval service with domain whitelist enforcement.
"""
import re
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import config
from models.schemas import LegalSource
from services import legal_cache_service


class DomainNotAllowedError(Exception):
    """Raised when attempting to fetch from a non-whitelisted domain."""
    pass


class FetchError(Exception):
    """Raised when source fetching fails."""
    pass


def is_domain_whitelisted(url: str) -> bool:
    """
    Check if a URL's domain is in the whitelist.

    Args:
        url: The URL to check

    Returns:
        True if domain is whitelisted
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    for allowed in config.WHITELIST_DOMAINS:
        if domain == allowed or domain.endswith("." + allowed):
            return True

    return False


def fetch_legal_source(url: str, force_refresh: bool = False) -> LegalSource:
    """
    Fetch a legal source from a whitelisted domain.

    Args:
        url: The source URL
        force_refresh: If True, bypass cache and refetch

    Returns:
        LegalSource object with content

    Raises:
        DomainNotAllowedError: If domain is not whitelisted
        FetchError: If fetching fails
    """
    # CRITICAL: Validate domain BEFORE any network request
    if not is_domain_whitelisted(url):
        domain = urlparse(url).netloc
        raise DomainNotAllowedError(
            f"Domain '{domain}' is not in the whitelist. "
            f"Allowed domains: {', '.join(config.WHITELIST_DOMAINS)}"
        )

    # Check cache first
    if not force_refresh:
        cached = legal_cache_service.get_source_by_url(url)
        if cached:
            return cached

    # Fetch the URL
    try:
        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; LevitechBot/1.0; legal research)",
            },
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise FetchError(f"Failed to fetch URL: {e}")

    # Parse HTML
    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text().strip()

    # Extract main text content
    text = _extract_text(soup)

    # Store in cache
    source = legal_cache_service.store_source(
        url=url,
        html=html,
        text=text,
        title=title,
    )

    return source


def _extract_text(soup: BeautifulSoup) -> str:
    """
    Extract clean text content from HTML.

    Args:
        soup: BeautifulSoup object

    Returns:
        Cleaned text content
    """
    # Remove script and style elements
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    # Try to find main content
    main_content = None

    # Common main content selectors
    for selector in ["main", "article", "[role='main']", ".content", "#content"]:
        main_content = soup.select_one(selector)
        if main_content:
            break

    if main_content:
        text = main_content.get_text(separator="\n")
    else:
        text = soup.get_text(separator="\n")

    # Clean up whitespace
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)

    # Remove excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text


def search_gov_uk(query: str, max_results: int = 5) -> list[dict]:
    """
    Search GOV.UK for relevant pages.

    Note: This is a simple implementation. For production,
    consider using the GOV.UK Search API.

    Args:
        query: Search query
        max_results: Maximum results to return

    Returns:
        List of dicts with url, title, snippet
    """
    # Simple search URL construction
    search_url = f"https://www.gov.uk/search/all?keywords={requests.utils.quote(query)}"

    try:
        response = requests.get(
            search_url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LevitechBot/1.0)"},
        )
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    # Parse search results (GOV.UK specific)
    for item in soup.select(".gem-c-document-list__item")[:max_results]:
        link = item.select_one("a")
        if link and link.get("href"):
            url = link.get("href")
            if not url.startswith("http"):
                url = "https://www.gov.uk" + url

            title = link.get_text().strip()
            snippet = ""
            desc = item.select_one(".gem-c-document-list__item-description")
            if desc:
                snippet = desc.get_text().strip()

            results.append({
                "url": url,
                "title": title,
                "snippet": snippet,
            })

    return results


def search_caselaw(query: str, max_results: int = 5) -> list[dict]:
    """
    Search caselaw.nationalarchives.gov.uk for judgments.

    Args:
        query: Search query
        max_results: Maximum results to return

    Returns:
        List of dicts with url, title, snippet
    """
    search_url = f"https://caselaw.nationalarchives.gov.uk/judgments/search?query={requests.utils.quote(query)}"

    try:
        response = requests.get(
            search_url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LevitechBot/1.0)"},
        )
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    # Parse search results (caselaw specific structure)
    for item in soup.select(".judgment-listing__judgment")[:max_results]:
        link = item.select_one("a.judgment-listing__title")
        if link and link.get("href"):
            url = link.get("href")
            if not url.startswith("http"):
                url = "https://caselaw.nationalarchives.gov.uk" + url

            title = link.get_text().strip()
            snippet = ""
            meta = item.select_one(".judgment-listing__meta")
            if meta:
                snippet = meta.get_text().strip()

            results.append({
                "url": url,
                "title": title,
                "snippet": snippet,
            })

    return results


def get_legal_sources_for_query(query: str) -> list[LegalSource]:
    """
    Search and fetch legal sources relevant to a query.

    Args:
        query: The search query

    Returns:
        List of fetched LegalSource objects
    """
    sources = []

    # Search GOV.UK
    gov_results = search_gov_uk(query, max_results=3)
    for result in gov_results:
        try:
            source = fetch_legal_source(result["url"])
            sources.append(source)
        except (DomainNotAllowedError, FetchError) as e:
            print(f"Warning: Failed to fetch {result['url']}: {e}")

    # Search caselaw
    case_results = search_caselaw(query, max_results=2)
    for result in case_results:
        try:
            source = fetch_legal_source(result["url"])
            sources.append(source)
        except (DomainNotAllowedError, FetchError) as e:
            print(f"Warning: Failed to fetch {result['url']}: {e}")

    return sources
