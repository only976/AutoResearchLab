from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from loguru import logger

from idea_agent.literature import search_literature
from shared.constants import TEMP_CREATIVE
from shared.llm_client import chat_completion, merge_phase_config
from shared.vector_store import VectorRecord, create_vector_store


def _embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")


def _generate_query(input_payload: dict[str, Any]) -> str:
    query = " ".join(
        [
            str(input_payload.get("broad_topic") or ""),
            str(input_payload.get("research_style") or ""),
            str(input_payload.get("depth_level") or ""),
        ]
    ).strip()
    return query


def _chunk_text(text: str, *, chunk_chars: int = 900) -> list[str]:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_chars:
        return [cleaned]
    out: list[str] = []
    step = max(300, int(chunk_chars * 0.7))
    for i in range(0, len(cleaned), step):
        out.append(cleaned[i : i + chunk_chars])
        if i + chunk_chars >= len(cleaned):
            break
    return out


def _generate_index_name() -> str:
    return (os.getenv("CF_VECTORIZE_GENERATE_INDEX") or "generate_chunks").strip()


async def _ingest_generate_rag(
    input_payload: dict[str, Any],
    *,
    paper_limit: int = 20,
) -> dict[str, Any]:
    query = _generate_query(input_payload)
    if not query:
        return {"query": "", "provider": "", "papers": 0, "chunks": 0}

    source = str(input_payload.get("literature_source") or "").strip() or None
    try:
        provider, papers = await search_literature(query, limit=paper_limit, cat=None, source=source)
    except Exception as e:
        logger.warning("Generate RAG search failed: {}", e)
        return {"query": query, "provider": "", "papers": 0, "chunks": 0}

    if not papers:
        return {"query": query, "provider": provider, "papers": 0, "chunks": 0}

    encoder = _embedder()
    store = create_vector_store()
    index_name = _generate_index_name()
    records: list[VectorRecord] = []
    for paper in papers:
        title = str(paper.get("title") or "").strip()
        abstract = str(paper.get("abstract") or "").strip()
        url = str(paper.get("url") or "").strip()
        published = str(paper.get("published") or "").strip()
        if not title and not abstract:
            continue
        content = f"{title}\n\n{abstract}".strip()
        for chunk_idx, chunk in enumerate(_chunk_text(content)):
            vector = encoder.encode(chunk).tolist()
            rid = hashlib.md5(f"{query}|{url}|{chunk_idx}|{chunk[:80]}".encode("utf-8")).hexdigest()
            records.append(
                VectorRecord(
                    id=rid,
                    vector=vector,
                    payload={
                        "title": title or "Unknown",
                        "text": chunk,
                        "url": url,
                        "published": published,
                        "provider": provider,
                    },
                )
            )

    if not records:
        return {"query": query, "provider": provider, "papers": len(papers), "chunks": 0}

    try:
        store.ensure_collection(index_name, 384)
        store.upsert(index_name, records)
        logger.info(
            "Generate RAG ingest ok: index={} provider={} papers={} chunks={}",
            index_name,
            provider,
            len(papers),
            len(records),
        )
    except Exception as e:
        logger.warning("Generate RAG ingest failed: {}", e)
    return {"query": query, "provider": provider, "papers": len(papers), "chunks": len(records)}


def _query_generate_rag(input_payload: dict[str, Any], *, limit: int = 30) -> str:
    query = _generate_query(input_payload)
    if not query:
        return ""
    encoder = _embedder()
    vector = encoder.encode(query).tolist()
    store = create_vector_store()
    index_name = _generate_index_name()
    try:
        store.ensure_collection(index_name, 384)
        rows = store.query(index_name, vector, limit)
    except Exception as e:
        logger.warning("Generate RAG query failed: {}", e)
        return ""

    lines: list[str] = []
    for i, r in enumerate(rows):
        payload = r.get("payload") or {}
        title = payload.get("title", "Unknown")
        text = payload.get("text", "")
        lines.append(f"[Source ID: {i}] (Title: {title})\n{text}")
    return "\n\n".join(lines)


def _build_prompt(input_payload: dict[str, Any], rag_context: str) -> list[dict]:
    system = (
        "You are a senior research proposal writer.\n"
        "Return JSON only.\n"
        "Generate final research idea output with fields: metadata and idea.\n"
        "Keep content concrete, experiment-ready, and compatible with master-level traditional ML workflow."
    )
    user = (
        "Generate final idea JSON from input.\n\n"
        f"Input JSON:\n{json.dumps(input_payload, ensure_ascii=False, indent=2)}\n\n"
        f"RAG context:\n{rag_context or '(none)'}\n"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def generate_idea_output(input_payload: dict[str, Any], api_config: dict, max_retries: int = 2) -> dict[str, Any]:
    # RAG-2 full loop: online retrieve papers -> upsert generate index -> query context.
    await _ingest_generate_rag(input_payload, paper_limit=int((api_config or {}).get("generateRagSearchLimit", 20) or 20))
    rag_context = _query_generate_rag(input_payload, limit=40)
    messages = _build_prompt(input_payload, rag_context)
    cfg = merge_phase_config(api_config, "idea")
    for i in range(max_retries + 1):
        response = await chat_completion(
            messages,
            cfg,
            stream=False,
            temperature=TEMP_CREATIVE,
            response_format={"type": "json_object"},
        )
        text = response if isinstance(response, str) else str(response)
        try:
            return json.loads(text)
        except Exception:
            if i >= max_retries:
                raise ValueError("generate_idea returned non-JSON output")
            messages.append({"role": "user", "content": "Output must be valid JSON only. Retry."})
    raise ValueError("unreachable")
