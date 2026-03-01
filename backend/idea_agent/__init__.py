"""
Idea Agent - 从模糊 idea 收集 arXiv 文献并生成可执行 refined idea。
"""

from typing import Any, Optional

from . import arxiv
from .llm import (
    extract_keywords,
    extract_keywords_stream,
    refine_idea_from_papers,
    refine_idea_from_papers_stream,
)
from .llm.executor import OnThinkingCallback  # 统一 on_thinking 签名


async def collect_literature(
    idea: str,
    api_config: dict,
    limit: int = 10,
    on_thinking: Optional[OnThinkingCallback] = None,
    abort_event: Optional[Any] = None,
) -> dict:
    """
    根据模糊 idea 收集 arXiv 文献并生成可执行 refined idea。

    流程：Keywords（LLM 提取关键词）-> arXiv 检索 -> Refine（LLM 基于文献生成 refined idea）。

    Args:
        idea: 用户输入的模糊研究想法
        api_config: API 配置
        limit: 返回文献数量上限
        on_thinking: 可选，流式时每收到 LLM token 调用，用于 Thinking 区域展示（Keywords、Refine 两阶段）

    Returns:
        {keywords: [...], papers: [...], refined_idea: {description, research_questions, research_gap, method_approach}}
    """
    # 1. Keywords：提取检索关键词
    if on_thinking is not None:
        keywords = await extract_keywords_stream(idea, api_config, on_chunk=on_thinking, abort_event=abort_event)
    else:
        keywords = await extract_keywords(idea, api_config, abort_event=abort_event)
    if not keywords:
        keywords = ["research"]
    # 2. arXiv 检索
    query = "+".join(str(k).replace(" ", "+") for k in keywords)[:100]
    if not query:
        query = "research"
    papers = await arxiv.search_arxiv(query, limit=limit)
    # 3. Refine：基于 idea + papers 生成可执行 refined idea
    if on_thinking is not None:
        refined_idea = await refine_idea_from_papers_stream(
            idea, papers, api_config, on_chunk=on_thinking, abort_event=abort_event
        )
    else:
        refined_idea = await refine_idea_from_papers(idea, papers, api_config, abort_event=abort_event)
    return {"keywords": keywords, "papers": papers, "refined_idea": refined_idea}
