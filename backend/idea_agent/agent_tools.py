"""
Agent tools for Idea Agent: ExtractKeywords, SearchArxiv, EvaluatePapers, FilterPapers,
AnalyzePapers, RefineIdea, ValidateRefinedIdea, FinishIdea, ListSkills, LoadSkill, ReadSkillFile.
OpenAI function-calling format. Used when ideaAgentMode=True.
"""

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import orjson
from loguru import logger

from shared.constants import TEMP_ANALYSIS, TEMP_EXTRACT
from shared.llm_client import chat_completion, merge_phase_config
from shared.utils import extract_codeblock
from shared.skill_utils import list_skills as _list_skills, load_skill as _load_skill, read_skill_file as _read_skill_file

from .literature import search_literature
from .llm import extract_keywords, refine_idea_from_papers
from .llm.executor import _build_papers_context

try:
    from .rag_engine import get_rag_engine
except ImportError:
    get_rag_engine = None

from .tool_schemas import get_idea_agent_tools

_IDEA_SKILLS_DIR = os.environ.get("MAARS_IDEA_SKILLS_DIR")
IDEA_SKILLS_ROOT = (
    Path(_IDEA_SKILLS_DIR).resolve()
    if _IDEA_SKILLS_DIR
    else Path(__file__).resolve().parent / "skills"
)


def _idea_agent_list_skills() -> str:
    """List Idea Agent skills. Returns JSON string of [{name, description}, ...]."""
    return _list_skills(IDEA_SKILLS_ROOT)


def _idea_agent_load_skill(name: str) -> str:
    """Load Idea Agent skill SKILL.md content."""
    return _load_skill(IDEA_SKILLS_ROOT, name)


def _idea_agent_read_skill_file(skill: str, path: str) -> str:
    """Read file from Idea Agent skill directory."""
    return _read_skill_file(IDEA_SKILLS_ROOT, skill, path)


def _parse_json_block(text: str) -> Optional[Dict]:
    """Extract JSON from ```json...``` or raw JSON."""
    cleaned = extract_codeblock(text) or (text or "").strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None


async def _eval_papers_llm(
    idea: str, papers_summary: str, api_config: dict, abort_event: Optional[Any] = None
) -> Dict:
    """LLM call for EvaluatePapers. Returns {score, should_retry, suggestion}."""
    prompt = f"""Evaluate whether these papers are relevant to the user's research idea.

**User's idea:** {idea}

**Papers summary:**
{papers_summary}

Output JSON only:
{{"score": 1-5, "should_retry": bool, "suggestion": "string"}}
- score: 1=irrelevant, 5=highly relevant
- should_retry: true if score < 3 and you suggest trying different keywords
- suggestion: brief advice for retry or next step"""
    messages = [{"role": "user", "content": prompt}]
    cfg = merge_phase_config(api_config, "idea")
    try:
        resp = await chat_completion(
            messages, cfg, stream=False, temperature=TEMP_EXTRACT, abort_event=abort_event
        )
        text = resp if isinstance(resp, str) else str(resp)
        data = _parse_json_block(text)
        if data:
            return {
                "score": int(data.get("score", 3)),
                "should_retry": bool(data.get("should_retry", False)),
                "suggestion": str(data.get("suggestion", "")),
            }
    except Exception as e:
        logger.warning("EvaluatePapers LLM call failed: %s", e)
    return {"score": 2, "should_retry": True, "suggestion": "LLM evaluation failed; retry with different keywords recommended."}


async def _validate_refined_llm(
    refined_idea: str, api_config: dict, abort_event: Optional[Any] = None
) -> Dict:
    """LLM call for ValidateRefinedIdea. Returns {score, comment, should_rewrite}."""
    prompt = f"""Assess this refined research idea for executability and specificity.

**Refined idea:**
{refined_idea or ""}

Output JSON only:
{{"score": 1-5, "comment": "string", "should_rewrite": bool}}
- score: 1=too vague, 5=concrete and decomposable
- should_rewrite: true if score < 4"""
    messages = [{"role": "user", "content": prompt}]
    cfg = merge_phase_config(api_config, "idea")
    try:
        resp = await chat_completion(
            messages, cfg, stream=False, temperature=TEMP_EXTRACT, abort_event=abort_event
        )
        text = resp if isinstance(resp, str) else str(resp)
        data = _parse_json_block(text)
        if data:
            return {
                "score": int(data.get("score", 4)),
                "comment": str(data.get("comment", "")),
                "should_rewrite": bool(data.get("should_rewrite", False)),
            }
    except Exception as e:
        logger.warning("ValidateRefinedIdea LLM call failed: %s", e)
    return {"score": 3, "comment": "LLM validation failed; consider rewriting for clarity.", "should_rewrite": True}


async def execute_idea_agent_tool(
    name: str,
    arguments: str,
    idea_state: Dict[str, Any],
    *,
    on_thinking: Optional[Callable] = None,
    abort_event: Optional[Any] = None,
    api_config: Optional[Dict] = None,
    limit: int = 10,
) -> Tuple[bool, str]:
    """
    Execute an Idea Agent tool. Returns (is_finish, result_str).
    is_finish: True when FinishIdea is called.
    """
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
    except json.JSONDecodeError as e:
        return False, f"Error: invalid tool arguments: {e}"

    idea = idea_state.get("idea", "")
    api_config = api_config or {}

    if name == "ExtractKeywords":
        kw_idea = args.get("idea") or idea
        if not kw_idea:
            return False, "Error: idea required"
        keywords = await extract_keywords(kw_idea, api_config, abort_event=abort_event)
        if not keywords:
            keywords = ["research"]
        idea_state["keywords"] = keywords
        return False, orjson.dumps({"keywords": keywords}).decode("utf-8")

    if name == "SearchArxiv":
        keywords = args.get("keywords") or idea_state.get("keywords") or ["research"]
        lim = args.get("limit") or limit
        cat = (args.get("cat") or "").strip() or None
        query = "+".join(str(k).replace(" ", "+") for k in keywords)[:100]
        if not query:
            query = "research"
        source, papers = await search_literature(
            query,
            limit=lim,
            cat=cat,
            source=(api_config or {}).get("literatureSource"),
        )
        idea_state["papers"] = papers
        summary = [
            f"[{i+1}] {p.get('title','')[:80]}..."
            for i, p in enumerate(papers[:15])
        ]
        return False, orjson.dumps(
            {"count": len(papers), "source": source, "titles": summary}, option=orjson.OPT_INDENT_2
        ).decode("utf-8")

    if name == "EvaluatePapers":
        papers = idea_state.get("papers") or []
        papers_summary = args.get("papers_summary") or _build_papers_context(papers, 2000)
        result = await _eval_papers_llm(
            args.get("idea") or idea, papers_summary, api_config, abort_event
        )
        return False, orjson.dumps(result, option=orjson.OPT_INDENT_2).decode("utf-8")

    if name == "FilterPapers":
        papers = idea_state.get("papers") or []
        indices = args.get("indices") or []
        if not indices:
            filtered = papers[:8]
        else:
            filtered = []
            for i in indices:
                if 1 <= i <= len(papers):
                    filtered.append(papers[i - 1])
        idea_state["filtered_papers"] = filtered
        return False, orjson.dumps(
            {"count": len(filtered), "indices": indices}, option=orjson.OPT_INDENT_2
        ).decode("utf-8")

    if name == "IndexPapers":
        if not api_config.get("ideaUseRAG"):
            logger.info("Idea RAG: IndexPapers called but disabled (ideaUseRAG=False)")
            return False, "Error: RAG not enabled (ideaUseRAG=False)"
        engine = get_rag_engine() if get_rag_engine else None
        if not engine:
            logger.info("Idea RAG: IndexPapers called but dependencies unavailable")
            return False, "Error: RAG dependencies not available"
        papers = idea_state.get("filtered_papers") or []
        logger.info("Idea RAG: IndexPapers start papers=%d", len(papers))
        result = await engine.index_papers(papers)
        logger.info("Idea RAG: IndexPapers done result=%s", (result or "")[:200])
        return False, result

    if name == "QueryKnowledgeBase":
        if not api_config.get("ideaUseRAG"):
            logger.info("Idea RAG: QueryKnowledgeBase called but disabled (ideaUseRAG=False)")
            return False, "Error: RAG not enabled (ideaUseRAG=False)"
        engine = get_rag_engine() if get_rag_engine else None
        if not engine:
            logger.info("Idea RAG: QueryKnowledgeBase called but dependencies unavailable")
            return False, "Error: RAG dependencies not available"
        q = (args.get("query") or "").strip()
        if not q:
            return False, "Error: query required"
        logger.info("Idea RAG: QueryKnowledgeBase start query=%r", q[:200])
        result = await engine.query(q, limit=30)
        idea_state["rag_context"] = result
        logger.info(
            "Idea RAG: QueryKnowledgeBase done chars=%d preview=%r",
            len(result or ""),
            (result or "")[:120],
        )
        return False, result

    if name == "IndexConceptKB":
        if not api_config.get("ideaUseRAG"):
            logger.info("Idea RAG: IndexConceptKB called but disabled (ideaUseRAG=False)")
            return False, "Error: RAG not enabled (ideaUseRAG=False)"
        engine = get_rag_engine() if get_rag_engine else None
        if not engine:
            logger.info("Idea RAG: IndexConceptKB called but dependencies unavailable")
            return False, "Error: RAG dependencies not available"
        result = await engine.index_concepts()
        logger.info("Idea RAG: IndexConceptKB done result=%s", (result or "")[:200])
        return False, result

    if name == "QueryConceptKB":
        if not api_config.get("ideaUseRAG"):
            logger.info("Idea RAG: QueryConceptKB called but disabled (ideaUseRAG=False)")
            return False, "Error: RAG not enabled (ideaUseRAG=False)"
        engine = get_rag_engine() if get_rag_engine else None
        if not engine:
            logger.info("Idea RAG: QueryConceptKB called but dependencies unavailable")
            return False, "Error: RAG dependencies not available"
        q = (args.get("query") or "").strip()
        if not q:
            return False, "Error: query required"
        logger.info("Idea RAG: QueryConceptKB start query=%r", q[:200])
        result = await engine.query_concepts(q, limit=30)
        idea_state["concept_kb_context"] = result
        logger.info(
            "Idea RAG: QueryConceptKB done chars=%d preview=%r",
            len(result or ""),
            (result or "")[:120],
        )
        return False, result

    if name == "AnalyzePapers":
        papers_ctx = args.get("papers_context") or _build_papers_context(
            idea_state.get("filtered_papers") or idea_state.get("papers") or []
        )
        prompt = f"""Analyze how these papers relate to the user's idea.

**User's idea:** {args.get("idea") or idea}

**Papers:**
{papers_ctx}

Output 2-4 sentences: relationship, insights, preliminary research gap."""
        messages = [{"role": "user", "content": prompt}]
        cfg = merge_phase_config(api_config, "idea")
        try:
            resp = await chat_completion(
                messages, cfg, stream=False, temperature=TEMP_ANALYSIS, abort_event=abort_event
            )
            analysis = resp if isinstance(resp, str) else str(resp)
        except Exception:
            analysis = "Papers provide context for the idea."
        idea_state["analysis"] = analysis
        return False, orjson.dumps({"analysis": analysis}).decode("utf-8")

    if name == "RefineIdea":
        papers = idea_state.get("filtered_papers") or idea_state.get("papers") or []
        analysis = args.get("analysis") or idea_state.get("analysis") or ""
        extra_parts: list[str] = []
        if (idea_state.get("rag_context") or "").strip():
            extra_parts.append(f"Paper KB retrieval:\n{idea_state.get('rag_context')}")
        if (idea_state.get("concept_kb_context") or "").strip():
            extra_parts.append(f"Concept KB retrieval:\n{idea_state.get('concept_kb_context')}")
        kb_context = "\n\n".join(extra_parts).strip() if extra_parts else None

        refined = await refine_idea_from_papers(
            args.get("idea") or idea,
            papers,
            api_config,
            abort_event=abort_event,
            analysis=analysis or None,
            kb_context=kb_context,
        )
        idea_state["refined_idea"] = refined
        return False, refined

    if name == "ValidateRefinedIdea":
        refined = args.get("refined_idea") or idea_state.get("refined_idea") or ""
        result = await _validate_refined_llm(refined, api_config, abort_event)
        return False, orjson.dumps(result, option=orjson.OPT_INDENT_2).decode("utf-8")

    if name == "FinishIdea":
        keywords = args.get("keywords") or idea_state.get("keywords") or []
        papers = args.get("papers") or idea_state.get("papers") or []
        refined = args.get("refined_idea") or idea_state.get("refined_idea") or ""
        return True, orjson.dumps(
            {"keywords": keywords, "papers": papers, "refined_idea": refined},
            option=orjson.OPT_INDENT_2,
        ).decode("utf-8")

    if name == "ListSkills":
        return False, _idea_agent_list_skills()

    if name == "LoadSkill":
        return False, _idea_agent_load_skill(args.get("name", ""))

    if name == "ReadSkillFile":
        return False, _idea_agent_read_skill_file(
            args.get("skill", ""), args.get("path", "")
        )

    return False, f"Error: unknown tool '{name}'"
