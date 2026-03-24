"""
OpenAI function-calling tool schema definitions for the Idea Agent.
"""

from typing import Dict, List, Optional

try:
    from .rag_engine import get_rag_engine
except ImportError:
    get_rag_engine = None

# OpenAI function-calling tool definitions
IDEA_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ExtractKeywords",
            "description": "Extract 3-5 arXiv search keywords from the user's fuzzy research idea. Call this first, or again if EvaluatePapers suggests retry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "idea": {"type": "string", "description": "User's fuzzy research idea"},
                },
                "required": ["idea"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "SearchArxiv",
            "description": "Search arXiv with keywords. Call after ExtractKeywords.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keywords from ExtractKeywords",
                    },
                    "limit": {"type": "integer", "description": "Max papers to return", "default": 10},
                    "cat": {
                        "type": "string",
                        "description": "Optional arXiv category, e.g. cs.AI, cs.LG, math.NA",
                    },
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "EvaluatePapers",
            "description": "Evaluate whether retrieved papers are relevant to the idea. Returns score 1-5, should_retry, suggestion. Call after SearchArxiv. If score < 3 and retry_count < 1, call ExtractKeywords again with refined idea.",
            "parameters": {
                "type": "object",
                "properties": {
                    "idea": {"type": "string", "description": "User's idea"},
                    "papers_summary": {"type": "string", "description": "Brief summary of paper titles/abstracts"},
                },
                "required": ["idea", "papers_summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "FilterPapers",
            "description": "Select 5-8 most relevant papers from the retrieved list. Call after EvaluatePapers passes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "papers_summary": {"type": "string", "description": "Full papers list with indices"},
                    "idea": {"type": "string", "description": "User's idea for relevance"},
                    "indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Indices (1-based) of papers to keep, e.g. [1,3,5,7,8]",
                    },
                },
                "required": ["papers_summary", "idea", "indices"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "AnalyzePapers",
            "description": "Analyze how papers relate to the idea, what insights to draw, and preliminary research gap. CoT analysis before RefineIdea.",
            "parameters": {
                "type": "object",
                "properties": {
                    "idea": {"type": "string", "description": "User's idea"},
                    "papers_context": {"type": "string", "description": "Filtered papers context"},
                },
                "required": ["idea", "papers_context"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "RefineIdea",
            "description": "Generate refined idea as Markdown from idea and papers. Call after AnalyzePapers. Output concrete, actionable content decomposable into 3–10 tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "idea": {"type": "string", "description": "User's idea"},
                    "papers_context": {"type": "string", "description": "Filtered papers"},
                    "analysis": {"type": "string", "description": "Output from AnalyzePapers"},
                },
                "required": ["idea", "papers_context"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ValidateRefinedIdea",
            "description": "Self-assess refined_idea: executability and specificity (1-5). If score < 4, rewrite with RefineIdea.",
            "parameters": {
                "type": "object",
                "properties": {
                    "refined_idea": {"type": "string", "description": "The refined idea (Markdown) to validate"},
                },
                "required": ["refined_idea"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "FinishIdea",
            "description": "Submit final refined_idea and complete. Call when ValidateRefinedIdea passes or when satisfied.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "string"}, "description": "Final keywords used"},
                    "papers": {"type": "array", "description": "Final papers list (full objects)"},
                    "refined_idea": {"type": "string", "description": "Final refined idea (Markdown)"},
                },
                "required": ["keywords", "papers", "refined_idea"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ListSkills",
            "description": "List available Idea Agent Skills (keyword extraction, paper evaluation, research templates, topic refinement, rag-research-template, literature-grounding, refined-idea quality).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "LoadSkill",
            "description": "Load an Idea Agent skill's SKILL.md content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ReadSkillFile",
            "description": "Read a file from an Idea Agent skill directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "description": "Skill name"},
                    "path": {"type": "string", "description": "Path relative to skill dir"},
                },
                "required": ["skill", "path"],
            },
        },
    },
]

# RAG 工具：仅当 ideaUseRAG=True 时加入
RAG_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "IndexPapers",
            "description": "Index filtered papers (from FilterPapers) into PDF vector store for semantic retrieval. Call after FilterPapers when you need to query paper full-text for methodology or experimental details.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "QueryKnowledgeBase",
            "description": "Semantic search over indexed paper PDF content. Use when RefineIdea needs methodology, experimental setup, or specific details from paper body. Returns [Source ID: i] (Title)\ntext format.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for methodology, experiments, etc."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "IndexConceptKB",
            "description": "Index concept knowledge base PDFs into a dedicated vector store. Uses MAARS_CONCEPTS_PDFS_DIR env var (or default backend/db/concepts_pdfs). Call once before QueryConceptKB.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "QueryConceptKB",
            "description": "Semantic search over indexed concept knowledge base (traditional ML concepts, optimization techniques, experiment design). Use when RefineIdea needs concept-level methodology or fine-grained optimization knobs. Returns [Source ID: i] (Concept: Title)\ntext format.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for concept-level methodology, experiments, or optimization knobs."},
                },
                "required": ["query"],
            },
        },
    },
]


def get_idea_agent_tools(api_config: Optional[Dict] = None) -> List[dict]:
    """返回 Idea Agent 工具列表，ideaUseRAG=True 时包含 IndexPapers 与 QueryKnowledgeBase。"""
    tools = list(IDEA_AGENT_TOOLS)
    if api_config and api_config.get("ideaUseRAG") and get_rag_engine:
        engine = get_rag_engine()
        if engine is not None:
            tools = tools + RAG_TOOLS
    return tools
