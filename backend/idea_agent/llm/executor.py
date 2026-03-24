"""
Idea Agent 单轮 LLM 实现 - 关键词提取 + Refined Idea 生成。
与 Plan 对齐：Mock 模式依赖 test/mock-ai/refine.json、refine-idea.json，使用 mock_chat_completion 流式输出。
Refine 流程：Keywords（关键词提取）→ arXiv 检索 → Refine（基于文献生成可执行 idea）。
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from shared.constants import TEMP_CREATIVE, TEMP_EXTRACT
from shared.llm_client import chat_completion, merge_phase_config
from shared.mock_utils import load_mock_entry
from shared.utils import extract_codeblock
from test.mock_stream import mock_chat_completion

# 与 Plan/Task 统一的 on_thinking 签名：(chunk, task_id, operation, schedule_info)
OnThinkingCallback = Callable[[str, Optional[str], Optional[str], Optional[dict]], None]

IDEA_DIR = Path(__file__).resolve().parent.parent
MOCK_AI_DIR = IDEA_DIR.parent / "test" / "mock-ai"
RESPONSE_TYPE_KEYWORDS = "refine"
RESPONSE_TYPE_REFINE = "refine-idea"
MOCK_KEY = "_default"


# LLM 提示词：用于 arXiv 检索，输出英文关键词
_SYSTEM_PROMPT = """You are a research assistant. Extract 3-5 concise keywords suitable for arXiv search from the user's fuzzy research idea.

Output in two parts:
1. **Reasoning** (1-2 sentences): Briefly explain why these keywords fit the idea. This will be shown as your thinking process.
2. **JSON**: Then output a JSON block in ```json and ``` with: {"keywords": ["keyword1", "keyword2", ...]}

Requirements:
- Keywords should be technical terms or domain nouns, no stop words (e.g. the, a, and)
- The JSON block must be the last part of your response"""


def _parse_keywords_response(text: str) -> List[str]:
    """解析 LLM 返回的 JSON，提取 keywords 列表。"""
    cleaned = extract_codeblock(text) or (text or "").strip()
    try:
        data = json.loads(cleaned)
        keywords = data.get("keywords")
        if isinstance(keywords, list):
            result = [str(k).strip() for k in keywords if k and str(k).strip()]
            return result[:10] if result else []
    except (json.JSONDecodeError, TypeError):
        pass
    return []


async def _keywords_via_mock(
    on_chunk: Optional[OnThinkingCallback] = None,
    abort_event: Optional[Any] = None,
) -> List[str]:
    mock = load_mock_entry(MOCK_AI_DIR, RESPONSE_TYPE_KEYWORDS, MOCK_KEY)
    if not mock:
        raise ValueError(f"No mock data for {RESPONSE_TYPE_KEYWORDS}/{MOCK_KEY}")
    if on_chunk:
        def stream_chunk(chunk: str):
            if chunk:
                return on_chunk(chunk, None, "Keywords", None)
        content = await mock_chat_completion(
            mock["content"], mock["reasoning"], stream_chunk,
            stream=True, abort_event=abort_event,
        )
        return _parse_keywords_response(content or "")
    return _parse_keywords_response(mock["content"])


async def _keywords_via_llm(
    idea: str,
    api_config: dict,
    on_chunk: Optional[OnThinkingCallback] = None,
    abort_event: Optional[Any] = None,
) -> List[str]:
    cfg = merge_phase_config(api_config, "idea")
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": idea},
    ]
    def _stream_cb(chunk: str):
        if on_chunk:
            return on_chunk(chunk, None, "Keywords", None)
    try:
        response = await chat_completion(
            messages, cfg,
            on_chunk=_stream_cb if on_chunk else None,
            stream=bool(on_chunk),
            temperature=TEMP_EXTRACT,
            abort_event=abort_event,
        )
        text = response if isinstance(response, str) else str(response)
        return _parse_keywords_response(text)
    except Exception:
        return []


async def extract_keywords(idea: str, api_config: dict, abort_event: Optional[Any] = None) -> List[str]:
    """从模糊 idea 中提取 arXiv 检索关键词。"""
    if not idea or not isinstance(idea, str):
        return []
    idea = idea.strip()
    if not idea:
        return []
    if api_config.get("ideaUseMock", True):
        return await _keywords_via_mock(abort_event=abort_event)
    return await _keywords_via_llm(idea, api_config, abort_event=abort_event)


async def extract_keywords_stream(
    idea: str,
    api_config: dict,
    on_chunk: Optional[OnThinkingCallback] = None,
    abort_event: Optional[Any] = None,
) -> List[str]:
    """流式从模糊 idea 中提取 arXiv 检索关键词。"""
    if not idea or not isinstance(idea, str):
        return []
    idea = idea.strip()
    if not idea:
        return []
    if api_config.get("ideaUseMock", True):
        return await _keywords_via_mock(on_chunk=on_chunk, abort_event=abort_event)
    return await _keywords_via_llm(idea, api_config, on_chunk=on_chunk, abort_event=abort_event)


# --- Refined Idea 生成 ---

_REFINE_IDEA_SYSTEM_PROMPT = """你是科研助手。请基于用户模糊想法、检索论文和可选知识库上下文，输出“可执行”的精炼研究方案。

默认研究域：传统机器学习（计算量可控、可在 Python 环境完成实验）。

创新点必须包含：
- 具体可改动的算法设计与细粒度优化项（损失/正则/特征/采样/超参数/训练策略等）
- 在有限算力下可落地的实验路径
- 清晰的消融/敏感性分析计划
- 相对已有工作的明确差异（不是综述复述）

输出要求（必须同时满足）：
1) 先输出中文 Markdown（结构可用：## 研究描述 / ## 研究问题 / ## 研究空白 / ## 方法 / ## 创新点 / ## 消融计划 / ## 可行性）。
2) 在最后追加一个 ```json 代码块，字段必须为：
{
  "broad_topic": "string",
  "research_style": "novelty_seeking",
  "depth_level": "master",
  "language": "zh",
  "compute": "cuda",
  "vram_gb": 24,
  "max_runtime_minutes": 60,
  "frameworks": ["pytorch", "numpy", "scikit-learn"]
}
3) JSON 必须可被直接解析，且是输出中的最后一个代码块。"""


def _build_papers_context(papers: List[dict], max_chars: int = 4000) -> str:
    """将 papers 转为 prompt 可用的文本，控制长度。"""
    if not papers:
        return "(No papers retrieved)"
    parts = []
    total = 0
    for i, p in enumerate(papers[:15]):
        title = (p.get("title") or "").strip()
        abstract = (p.get("abstract") or "").strip().replace("\n", " ")[:500]
        s = f"[{i + 1}] {title}\n  Abstract: {abstract}\n"
        if total + len(s) > max_chars:
            break
        parts.append(s)
        total += len(s)
    return "\n".join(parts) if parts else "(No papers)"


def _fallback_generate_input(idea: str) -> dict:
    topic = (idea or "").strip() or "传统机器学习方向的可执行研究课题"
    return {
        "broad_topic": topic[:300],
        "research_style": "novelty_seeking",
        "depth_level": "master",
        "language": "zh",
        "compute": "cuda",
        "vram_gb": 24,
        "max_runtime_minutes": 60,
        "frameworks": ["pytorch", "numpy", "scikit-learn"],
    }


def _ensure_generate_input_codeblock(text: str, idea: str) -> str:
    raw = (text or "").strip()
    if not raw:
        raw = "## 研究描述\n基于当前输入生成失败，已自动回退到保底方案。\n"
    parsed = None
    codeblock = extract_codeblock(raw)
    for candidate in [codeblock, raw]:
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                parsed = obj
                break
        except Exception:
            continue
    if parsed is None:
        parsed = _fallback_generate_input(idea)
        raw = raw.rstrip() + "\n\n```json\n" + json.dumps(parsed, ensure_ascii=False, indent=2) + "\n```"
    return raw.strip()


async def _refine_via_mock(
    on_chunk: Optional[OnThinkingCallback] = None,
    abort_event: Optional[Any] = None,
) -> str:
    mock = load_mock_entry(MOCK_AI_DIR, RESPONSE_TYPE_REFINE, MOCK_KEY)
    if not mock:
        return ""
    if on_chunk:
        def stream_chunk(c: str):
            if c:
                return on_chunk(c, None, "Refine", None)
        content = await mock_chat_completion(
            mock["content"], mock.get("reasoning", ""), stream_chunk,
            stream=True, abort_event=abort_event,
        )
        return (content or "").strip()
    return (mock["content"] or "").strip()


async def _refine_via_llm(
    idea: str,
    papers: List[dict],
    api_config: dict,
    on_chunk: Optional[OnThinkingCallback] = None,
    abort_event: Optional[Any] = None,
    analysis: Optional[str] = None,
    kb_context: Optional[str] = None,
) -> str:
    cfg = merge_phase_config(api_config, "idea")
    papers_ctx = _build_papers_context(papers)
    user_content = f"**User's idea:** {idea}\n\n**Retrieved papers:**\n{papers_ctx}\n"
    if analysis:
        user_content += f"\n**Prior analysis:**\n{analysis}\n"
    if kb_context:
        # Keep prompt bounded; KB retrieval can be long.
        kb_text = str(kb_context)
        if len(kb_text) > 6000:
            kb_text = kb_text[:6000] + "\n...[truncated]"
        user_content += f"\n**Knowledge base context (concept/KB retrieval):**\n{kb_text}\n"
    user_content += "\n**Output:**"
    messages = [
        {"role": "system", "content": _REFINE_IDEA_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    def _stream_cb(chunk: str):
        if on_chunk:
            return on_chunk(chunk, None, "Refine", None)
    try:
        response = await chat_completion(
            messages, cfg,
            on_chunk=_stream_cb if on_chunk else None,
            stream=bool(on_chunk),
            temperature=TEMP_CREATIVE,
            abort_event=abort_event,
        )
        text = response if isinstance(response, str) else str(response)
        return _ensure_generate_input_codeblock((text or "").strip(), idea)
    except Exception as e:
        logger.warning("Refine idea failed: {}", e)
        fallback = (
            "## 研究描述\n"
            "LLM 在本次 Refine 阶段未返回有效内容，系统已自动生成可继续下游流程的保底方案。\n\n"
            "## 方法\n"
            "- 先构建可复现实验基线\n"
            "- 再做 1-2 个轻量创新点对比与消融\n"
        )
        return _ensure_generate_input_codeblock(fallback, idea)


async def refine_idea_from_papers(
    idea: str,
    papers: List[dict],
    api_config: dict,
    abort_event: Optional[Any] = None,
    analysis: Optional[str] = None,
    kb_context: Optional[str] = None,
) -> str:
    """基于用户 idea 与检索到的 papers，生成可执行的 refined idea。"""
    idea = (idea or "").strip()
    papers = papers or []
    if api_config.get("ideaUseMock", True):
        return await _refine_via_mock(abort_event=abort_event)
    return await _refine_via_llm(
        idea,
        papers,
        api_config,
        abort_event=abort_event,
        analysis=analysis,
        kb_context=kb_context,
    )


async def refine_idea_from_papers_stream(
    idea: str,
    papers: List[dict],
    api_config: dict,
    on_chunk: Optional[OnThinkingCallback] = None,
    abort_event: Optional[Any] = None,
    analysis: Optional[str] = None,
    kb_context: Optional[str] = None,
) -> str:
    """流式基于用户 idea 与检索到的 papers，生成可执行的 refined idea。"""
    idea = (idea or "").strip()
    papers = papers or []
    if api_config.get("ideaUseMock", True):
        return await _refine_via_mock(on_chunk=on_chunk, abort_event=abort_event)
    return await _refine_via_llm(
        idea,
        papers,
        api_config,
        on_chunk=on_chunk,
        abort_event=abort_event,
        analysis=analysis,
        kb_context=kb_context,
    )
