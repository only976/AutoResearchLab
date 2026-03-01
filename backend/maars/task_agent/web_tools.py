"""
Web tools for Task Agent: WebSearch, WebFetch.
Requires: duckduckgo-search (or ddgs), httpx. Set MAARS_TASK_WEB_ENABLED=0 to disable.
"""

import asyncio
from typing import List, Optional
from urllib.parse import urlparse

_WEB_ENABLED: Optional[bool] = None
_WEB_FETCH_MAX_BYTES = 100_000  # ~25k tokens
_WEB_FETCH_TIMEOUT = 15
_WEB_SEARCH_MAX_RESULTS = 5


def _is_web_enabled() -> bool:
    global _WEB_ENABLED
    if _WEB_ENABLED is None:
        val = (__import__("os").environ.get("MAARS_TASK_WEB_ENABLED", "1")).lower()
        _WEB_ENABLED = val in ("1", "true", "yes", "on")
    return _WEB_ENABLED


def _is_safe_url(url: str) -> bool:
    """Reject localhost, file:, and non-http(s) URLs."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return False
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return False
        if host.endswith(".local"):
            return False
        return True
    except Exception:
        return False


async def run_web_search(query: str, max_results: int = _WEB_SEARCH_MAX_RESULTS) -> str:
    """Search the web via DuckDuckGo. Returns JSON string of results."""
    if not _is_web_enabled():
        return "Error: Web search is disabled (set MAARS_TASK_WEB_ENABLED=1 to enable)."
    if not query or not isinstance(query, str):
        return "Error: query must be a non-empty string"
    query = query.strip()[:500]
    max_results = min(max(1, int(max_results) if isinstance(max_results, (int, float)) else 5), 10)

    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "Error: duckduckgo-search not installed. Run: pip install duckduckgo-search"

    def _search() -> List[dict]:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))

    try:
        results = await asyncio.to_thread(_search)
    except Exception as e:
        return f"Error: Search failed: {e}"

    if not results:
        return "No results found."
    out = []
    for i, r in enumerate(results, 1):
        title = r.get("title") or ""
        href = r.get("href") or r.get("link") or ""
        body = r.get("body") or ""
        out.append({"rank": i, "title": title, "url": href, "snippet": body[:400]})
    import orjson
    return orjson.dumps(out, option=orjson.OPT_INDENT_2).decode("utf-8")


async def run_web_fetch(url: str) -> str:
    """Fetch URL content. Returns text (HTML or plain). Truncated for token limits."""
    if not _is_web_enabled():
        return "Error: Web fetch is disabled (set MAARS_TASK_WEB_ENABLED=1 to enable)."
    if not _is_safe_url(url):
        return "Error: Invalid or disallowed URL (only http/https, no localhost)."

    try:
        import httpx
    except ImportError:
        return "Error: httpx not installed. Run: pip install httpx"

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=_WEB_FETCH_TIMEOUT,
            headers={"User-Agent": "MAARS-TaskAgent/1.0 (research)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.text
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except httpx.RequestError as e:
        return f"Error: Request failed: {e}"
    except Exception as e:
        return f"Error: {e}"

    if len(content) > _WEB_FETCH_MAX_BYTES:
        content = content[:_WEB_FETCH_MAX_BYTES] + "\n\n[... content truncated ...]"
    return content
