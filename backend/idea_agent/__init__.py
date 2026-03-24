"""Idea Agent - collect papers and generate refined idea."""

from typing import Any, Optional

from loguru import logger

from . import arxiv
from .agent import run_idea_agent
from .llm import (
    extract_keywords,
    extract_keywords_stream,
    refine_idea_from_papers,
    refine_idea_from_papers_stream,
)
from .llm.executor import OnThinkingCallback  # 统一 on_thinking 签名
from .literature import search_literature
from .rag_engine import get_rag_engine

__all__ = [
    "collect_literature",
    "run_idea_agent",
    "arxiv",
    "extract_keywords",
    "extract_keywords_stream",
    "refine_idea_from_papers",
    "refine_idea_from_papers_stream",
]


async def collect_literature(
    idea: str,
    api_config: dict,
    limit: int = 10,
    on_thinking: Optional[OnThinkingCallback] = None,
    abort_event: Optional[Any] = None,
) -> dict:
    """
    根据模糊 idea 收集文献并生成可执行 refined idea。

    流程：Keywords（LLM 提取关键词）-> 文献检索（OpenAlex/arXiv）-> Refine（LLM 基于文献生成 refined idea）。

    Args:
        idea: 用户输入的模糊研究想法
        api_config: API 配置
        limit: 返回文献数量上限
        on_thinking: 可选，流式时每收到 LLM token 调用，用于 Thinking 区域展示（Keywords、Refine 两阶段）

    Returns:
        {keywords: [...], papers: [...], refined_idea: "..."}  # refined_idea is Markdown string
    """
    logger.info("Idea collect start idea_chars={} limit={}", len((idea or "").strip()), limit)
    # 1. Keywords：提取检索关键词
    if on_thinking is not None:
        keywords = await extract_keywords_stream(idea, api_config, on_chunk=on_thinking, abort_event=abort_event)
    else:
        keywords = await extract_keywords(idea, api_config, abort_event=abort_event)
    if not keywords:
        keywords = ["research"]
    logger.info("Idea collect keywords extracted count={} keywords={}", len(keywords), keywords)
    # 2. 文献检索（默认 OpenAlex，可切换 arXiv）
    query = "+".join(str(k).replace(" ", "+") for k in keywords)[:100]
    if not query:
        query = "research"
    source, papers = await search_literature(
        query,
        limit=limit,
        cat=None,
        source=(api_config or {}).get("literatureSource"),
    )
    logger.info("Idea collect search source={} query='{}'", source, query)
    if not papers:
        logger.warning("Idea collect blocked: no papers retrieved for query='{}'", query)
        raise ValueError(
            f"No papers retrieved from {source} for query '{query}'. Refine stage is blocked; please adjust the idea/keywords or retry later."
        )
    logger.info("Idea collect papers retrieved count={} first_title='{}'", len(papers), (papers[0].get("title") or "")[:120])
    if api_config.get("ideaUseRAG") and api_config.get("ideaAutoIndexPapers", True):
        try:
            engine = get_rag_engine()
            if engine:
                await engine.index_papers(papers)
        except Exception as e:
            logger.warning("Idea collect auto-index papers failed: {}", e)
    # 3. Refine：基于 idea + papers 生成可执行 refined idea
    used_streaming_refine = on_thinking is not None
    if used_streaming_refine:
        refined_idea = await refine_idea_from_papers_stream(
            idea, papers, api_config, on_chunk=on_thinking, abort_event=abort_event
        )
    else:
        refined_idea = await refine_idea_from_papers(idea, papers, api_config, abort_event=abort_event)

    if used_streaming_refine and not (refined_idea or "").strip():
        logger.warning(
            "Idea collect refine returned empty in streaming mode; retrying non-streaming refine query='{}' papers={}",
            query,
            len(papers),
        )
        refined_idea = await refine_idea_from_papers(
            idea,
            papers,
            api_config,
            abort_event=abort_event,
        )

    if not (refined_idea or "").strip():
        logger.warning("Idea collect blocked: refine returned empty output for query='{}' papers={}", query, len(papers))
        raise ValueError("Refine stage produced empty refined idea. Pipeline is blocked to avoid low-quality downstream planning.")

    logger.info("Idea collect complete keywords={} papers={} refined_chars={}", len(keywords), len(papers), len(refined_idea))

    return {"keywords": keywords, "papers": papers, "refined_idea": refined_idea}
