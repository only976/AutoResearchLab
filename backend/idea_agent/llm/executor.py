"""
Idea Agent 单轮 LLM 实现 - 关键词提取 + Refined Idea 生成。
与 Plan 对齐：Mock 模式依赖 test/mock-ai/refine.json、refine-idea.json，使用 mock_chat_completion 流式输出。
Refine 流程：Keywords（关键词提取）→ arXiv 检索 → Refine（基于文献生成可执行 idea）。
"""

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import orjson

from shared.llm_client import chat_completion, merge_phase_config
from test.mock_stream import mock_chat_completion

# 与 Plan/Task 统一的 on_thinking 签名：(chunk, task_id, operation, schedule_info)
OnThinkingCallback = Callable[[str, Optional[str], Optional[str], Optional[dict]], None]

IDEA_DIR = Path(__file__).resolve().parent.parent
MOCK_AI_DIR = IDEA_DIR.parent / "test" / "mock-ai"
RESPONSE_TYPE_KEYWORDS = "refine"
RESPONSE_TYPE_REFINE = "refine-idea"
MOCK_KEY = "_default"

_mock_cache: Dict[str, dict] = {}


def _get_mock_cached(response_type: str) -> dict:
    if response_type not in _mock_cache:
        path = MOCK_AI_DIR / f"{response_type}.json"
        try:
            _mock_cache[response_type] = orjson.loads(path.read_bytes())
        except (FileNotFoundError, orjson.JSONDecodeError):
            _mock_cache[response_type] = {}
    return _mock_cache[response_type]


def _load_mock_response(response_type: str, key: str) -> Optional[Dict]:
    """从 test/mock-ai/ 加载 mock，与 Plan 对齐。"""
    data = _get_mock_cached(response_type)
    entry = data.get(key) or data.get("_default")
    if not entry:
        return None
    content = entry.get("content")
    if isinstance(content, str):
        content_str = content
    else:
        content_str = orjson.dumps(content).decode("utf-8")
    return {"content": content_str, "reasoning": entry.get("reasoning", "")}


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
    cleaned = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if m:
        cleaned = m.group(1).strip()
    try:
        data = json.loads(cleaned)
        keywords = data.get("keywords")
        if isinstance(keywords, list):
            result = [str(k).strip() for k in keywords if k and str(k).strip()]
            return result[:10] if result else []
    except (json.JSONDecodeError, TypeError):
        pass
    return []


async def extract_keywords(idea: str, api_config: dict, abort_event: Optional[Any] = None) -> List[str]:
    """
    从模糊 idea 中提取 arXiv 检索关键词。
    Mock 模式：从 test/mock-ai/refine.json 加载并解析。
    """
    if not idea or not isinstance(idea, str):
        return []
    idea = idea.strip()
    if not idea:
        return []

    use_mock = api_config.get("useMock", True)
    if use_mock:
        mock = _load_mock_response(RESPONSE_TYPE_KEYWORDS, MOCK_KEY)
        if not mock:
            raise ValueError(f"No mock data for {RESPONSE_TYPE_KEYWORDS}/{MOCK_KEY}")
        return _parse_keywords_response(mock["content"])

    cfg = merge_phase_config(api_config, "idea")
    ai_mode = api_config.get("aiMode", "llm")
    mode_cfg = api_config.get("modeConfig", {}).get(ai_mode, {})
    temperature = mode_cfg.get("ideaLlmTemperature")
    if temperature is not None:
        temperature = float(temperature)
    else:
        temperature = 0.3
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": idea},
    ]
    try:
        # 不使用 response_format，以便 LLM 先输出 reasoning 再输出 JSON（流式时 Thinking 显示推理）
        response = await chat_completion(
            messages,
            cfg,
            stream=False,
            temperature=temperature,
            abort_event=abort_event,
        )
        text = response if isinstance(response, str) else str(response)
        return _parse_keywords_response(text)
    except Exception:
        return []


async def extract_keywords_stream(
    idea: str,
    api_config: dict,
    on_chunk: Optional[OnThinkingCallback] = None,
    abort_event: Optional[Any] = None,
) -> List[str]:
    """
    流式从模糊 idea 中提取 arXiv 检索关键词。
    Mock 模式：从 test/mock-ai/refine.json 加载，通过 mock_chat_completion 流式输出 reasoning。
    """
    if not idea or not isinstance(idea, str):
        return []
    idea = idea.strip()
    if not idea:
        return []

    use_mock = api_config.get("useMock", True)
    if use_mock:
        mock = _load_mock_response(RESPONSE_TYPE_KEYWORDS, MOCK_KEY)
        if not mock:
            raise ValueError(f"No mock data for {RESPONSE_TYPE_KEYWORDS}/{MOCK_KEY}")
        stream = on_chunk is not None

        def stream_chunk(chunk: str):
            if on_chunk and chunk:
                return on_chunk(chunk, None, "Keywords", None)

        effective_on_thinking = stream_chunk if stream else None
        content = await mock_chat_completion(
            mock["content"],
            mock["reasoning"],
            effective_on_thinking,
            stream=stream,
            abort_event=abort_event,
        )
        return _parse_keywords_response(content or "")

    cfg = merge_phase_config(api_config, "idea")
    ai_mode = api_config.get("aiMode", "llm")
    mode_cfg = api_config.get("modeConfig", {}).get(ai_mode, {})
    temperature = mode_cfg.get("ideaLlmTemperature")
    if temperature is not None:
        temperature = float(temperature)
    else:
        temperature = 0.3
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": idea},
    ]

    def _stream_cb(chunk: str):
        if on_chunk:
            return on_chunk(chunk, None, "Keywords", None)

    try:
        # 不使用 response_format，以便 LLM 先输出 reasoning 再输出 JSON（流式时 Thinking 显示推理）
        full_content = await chat_completion(
            messages,
            cfg,
            on_chunk=_stream_cb,
            stream=True,
            temperature=temperature,
            abort_event=abort_event,
        )
        text = full_content if isinstance(full_content, str) else str(full_content)
        return _parse_keywords_response(text)
    except Exception:
        return []


# --- Refined Idea 生成 ---

_REFINE_IDEA_SYSTEM_PROMPT = """You are a research assistant. Given the user's fuzzy research idea and retrieved papers, produce a structured, executable research idea.

Output in two parts:

1. **Reasoning** (2-4 sentences): First, analyze how the papers relate to the user's idea, what insights you draw, and what research gap you identify. Write this as plain text. This will be shown as your thinking process.

2. **JSON**: Then output a JSON block wrapped in ```json and ``` with exactly these fields:
{
  "description": "A clear, expanded research description (2-4 sentences) that can guide task decomposition",
  "research_questions": ["RQ1: ...", "RQ2: ..."],
  "research_gap": "Brief statement of existing work's limitations and this study's contribution",
  "method_approach": "Suggested methodology or technical approach (optional, can be empty string)"
}

Requirements:
- Reasoning: Must appear first; explain your analysis before the JSON
- description: Must be concrete and actionable; expand vague ideas using insights from papers
- research_questions: 1-3 questions; use "RQ1:", "RQ2:" prefix
- research_gap: 1-2 sentences
- If no papers provided, infer from the user's idea alone
- The JSON block must be the last part of your response"""


def _parse_refined_idea_response(text: str) -> Dict:
    """解析 LLM 返回的 JSON，提取 refined_idea 结构。支持 reasoning + ```json...``` 或纯 JSON。"""
    default = {
        "description": "",
        "research_questions": [],
        "research_gap": "",
        "method_approach": "",
    }
    cleaned = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if m:
        cleaned = m.group(1).strip()
    # 若无 ```json``` 块，尝试整体解析（兼容仅输出 JSON 的旧行为）
    try:
        data = json.loads(cleaned)
        desc = data.get("description")
        rqs = data.get("research_questions")
        gap = data.get("research_gap")
        method = data.get("method_approach")
        return {
            "description": str(desc).strip() if desc else "",
            "research_questions": [str(q).strip() for q in (rqs if isinstance(rqs, list) else []) if q],
            "research_gap": str(gap).strip() if gap else "",
            "method_approach": str(method).strip() if method else "",
        }
    except (json.JSONDecodeError, TypeError):
        pass
    return default


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


async def refine_idea_from_papers(
    idea: str,
    papers: List[dict],
    api_config: dict,
    abort_event: Optional[Any] = None,
) -> Dict:
    """
    基于用户 idea 与检索到的 papers，生成结构化的可执行 refined idea。
    非流式版本，用于无 on_thinking 时。
    """
    if not idea or not isinstance(idea, str):
        idea = ""
    idea = idea.strip()
    papers = papers or []

    use_mock = api_config.get("useMock", True)
    if use_mock:
        mock = _load_mock_response(RESPONSE_TYPE_REFINE, MOCK_KEY)
        if not mock:
            return _parse_refined_idea_response("{}")
        return _parse_refined_idea_response(mock["content"])

    cfg = merge_phase_config(api_config, "idea")
    ai_mode = api_config.get("aiMode", "llm")
    mode_cfg = api_config.get("modeConfig", {}).get(ai_mode, {})
    temperature = mode_cfg.get("ideaLlmTemperature")
    if temperature is not None:
        temperature = float(temperature)
    else:
        temperature = 0.5  # Refine 稍高以鼓励创意
    papers_ctx = _build_papers_context(papers)
    user_content = f"**User's idea:** {idea}\n\n**Retrieved papers:**\n{papers_ctx}\n\n**Output:**"
    messages = [
        {"role": "system", "content": _REFINE_IDEA_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        # 不使用 response_format，以便 LLM 先输出 reasoning 再输出 JSON（流式时 Thinking 显示推理）
        response = await chat_completion(
            messages,
            cfg,
            stream=False,
            temperature=temperature,
            abort_event=abort_event,
        )
        text = response if isinstance(response, str) else str(response)
        return _parse_refined_idea_response(text)
    except Exception:
        return _parse_refined_idea_response("{}")


async def refine_idea_from_papers_stream(
    idea: str,
    papers: List[dict],
    api_config: dict,
    on_chunk: Optional[OnThinkingCallback] = None,
    abort_event: Optional[Any] = None,
) -> Dict:
    """
    流式基于用户 idea 与检索到的 papers，生成结构化的可执行 refined idea。
    Thinking 区域 operation 为 "Refine"。
    """
    if not idea or not isinstance(idea, str):
        idea = ""
    idea = idea.strip()
    papers = papers or []

    use_mock = api_config.get("useMock", True)
    if use_mock:
        mock = _load_mock_response(RESPONSE_TYPE_REFINE, MOCK_KEY)
        if not mock:
            return _parse_refined_idea_response("{}")
        stream = on_chunk is not None

        def stream_chunk(c: str):
            if on_chunk and c:
                return on_chunk(c, None, "Refine", None)

        effective_on_thinking = stream_chunk if stream else None
        content = await mock_chat_completion(
            mock["content"],
            mock.get("reasoning", ""),
            effective_on_thinking,
            stream=stream,
            abort_event=abort_event,
        )
        return _parse_refined_idea_response(content or "{}")

    cfg = merge_phase_config(api_config, "idea")
    ai_mode = api_config.get("aiMode", "llm")
    mode_cfg = api_config.get("modeConfig", {}).get(ai_mode, {})
    temperature = mode_cfg.get("ideaLlmTemperature")
    if temperature is not None:
        temperature = float(temperature)
    else:
        temperature = 0.5
    papers_ctx = _build_papers_context(papers)
    user_content = f"**User's idea:** {idea}\n\n**Retrieved papers:**\n{papers_ctx}\n\n**Output:**"
    messages = [
        {"role": "system", "content": _REFINE_IDEA_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    def _stream_cb(chunk: str):
        if on_chunk:
            return on_chunk(chunk, None, "Refine", None)

    try:
        # 不使用 response_format，以便 LLM 先输出 reasoning 再输出 JSON（流式时 Thinking 显示推理）
        full_content = await chat_completion(
            messages,
            cfg,
            on_chunk=_stream_cb,
            stream=True,
            temperature=temperature,
            abort_event=abort_event,
        )
        text = full_content if isinstance(full_content, str) else str(full_content)
        return _parse_refined_idea_response(text)
    except Exception:
        return _parse_refined_idea_response("{}")
