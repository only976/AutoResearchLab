"""
arXiv API 请求与解析。
"""

import time
import xml.etree.ElementTree as ET
from typing import List, Optional

import httpx
from loguru import logger

ARXiv_API_BASE = "https://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


async def search_arxiv(
    query: str, limit: int = 10, cat: Optional[str] = None
) -> List[dict]:
    """
    检索 arXiv API，解析 Atom XML，返回文献列表。

    Args:
        query: 检索词，多个词用 + 连接（如 Python+JavaScript+backend）
        limit: 返回数量上限
        cat: 可选 arXiv 分类，如 cs.AI, cs.LG, math.NA

    Returns:
        [{title, abstract, url, authors, published}, ...]
    """
    if not query or not isinstance(query, str):
        return []
    query = query.strip()
    if not query:
        return []
    limit = min(max(1, int(limit) if isinstance(limit, (int, float)) else 10), 50)

    search_query = f"cat:{cat}+all:{query}" if (cat and cat.strip()) else f"all:{query}"
    url = f"{ARXiv_API_BASE}?search_query={search_query}&max_results={limit}"
    started = time.perf_counter()
    logger.info("arXiv search start query='{}' cat='{}' limit={}", query, cat or "", limit)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            logger.info(
                "arXiv search response query='{}' status={} bytes={} elapsed_ms={}",
                query,
                resp.status_code,
                len(resp.content or b""),
                int((time.perf_counter() - started) * 1000),
            )
    except httpx.HTTPStatusError as e:
        logger.warning("arXiv API HTTP error for query '{}': {}", query, e)
        raise RuntimeError(f"arXiv HTTP error for query '{query}': {e}") from e
    except httpx.RequestError as e:
        logger.warning("arXiv API request error for query '{}': {}", query, e)
        raise RuntimeError(f"arXiv request error for query '{query}': {e}") from e

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        logger.warning("arXiv API XML parse error for query '{}': {}", query, e)
        raise RuntimeError(f"arXiv XML parse error for query '{query}': {e}") from e

    results = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        paper = _parse_entry(entry)
        if paper:
            results.append(paper)
    logger.info(
        "arXiv search complete query='{}' papers={} elapsed_ms={}",
        query,
        len(results),
        int((time.perf_counter() - started) * 1000),
    )
    return results


def _parse_entry(entry: ET.Element) -> dict | None:
    """解析单条 Atom entry。"""
    title_el = entry.find(f"{ATOM_NS}title")
    title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""

    summary_el = entry.find(f"{ATOM_NS}summary")
    abstract = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""

    link_el = entry.find(f"{ATOM_NS}link[@rel='alternate']")
    url = link_el.get("href", "") if link_el is not None else ""

    authors = []
    for author in entry.findall(f"{ATOM_NS}author"):
        name_el = author.find(f"{ATOM_NS}name")
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    published_el = entry.find(f"{ATOM_NS}published")
    updated_el = entry.find(f"{ATOM_NS}updated")
    date_str = ""
    if published_el is not None and published_el.text:
        date_str = published_el.text[:10]
    elif updated_el is not None and updated_el.text:
        date_str = updated_el.text[:10]

    if not title:
        return None
    return {
        "title": title,
        "abstract": abstract,
        "url": url,
        "authors": authors,
        "published": date_str,
    }
