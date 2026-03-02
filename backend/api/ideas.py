from typing import Any, Dict
from datetime import datetime
from ..ideas.agent import ResearchIdeaEngine
from backend.config import LLM_MODEL, LLM_API_BASE, LLM_API_KEY
from fastapi import APIRouter, HTTPException

from backend.api.common import parse_json_text
from backend.ideas.agent import IdeaAgent
from backend.ideas.snapshots import load_snapshot, list_snapshots, save_snapshot
from backend.schemas.request_models import (
    IdeaGenerateRequest,
    IdeaRefineRequest,
    SnapshotSaveRequest,
)

router = APIRouter(prefix="/api/ideas")


def _normalize_generated_ideas(result: Any) -> Dict[str, Any]:
    """Normalize LLM output to a stable API shape.

    Frontend expects either `Idea[]` or `{ ideas: Idea[] }`.
    Some prompts/templates return a single idea dict (e.g. {title,gap,...}).
    We wrap that into `{ ideas: [result] }` for backward compatibility.
    """

    if isinstance(result, list):
        return {"ideas": result}

    if isinstance(result, dict):
        ideas = result.get("ideas")
        if isinstance(ideas, list):
            return result
        # Preserve parse/LLM error fields but ensure ideas exists.
        if "error" in result and "raw" in result:
            return {"ideas": [], **result}
        return {"ideas": [result]}

    if result is None:
        return {"ideas": []}

    return {"ideas": [{"content": result}]}


def _fallback_topic_from_scope(scope: str) -> Dict[str, Any]:
    cleaned = (scope or "").strip()
    if not cleaned:
        return {"title": "Idea Snapshot", "scope": ""}

    one_line = " ".join(cleaned.split())
    title = one_line[:80]
    return {"title": title, "scope": cleaned}


def _build_snapshot_name_with_llm(agent: IdeaAgent, refined_topic: Any, snapshot_results: Any) -> str:
    llm_title = agent.generate_snapshot_title(refined_topic, snapshot_results)
    if not llm_title:
        llm_title = "idea_snapshot"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{llm_title}"


@router.post("/refine")
def refine_ideas(payload: IdeaRefineRequest) -> Dict[str, Any]:
    agent = IdeaAgent()
    text = agent.refine_topic(payload.scope)
    return parse_json_text(text)


@router.post("/generate")
def generate_ideas(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    第二阶段：生成深度研究报告（适配云端 RAG 和自定义模板）
    接收包含 broad_topic, vram_gb, depth_level, language 的 JSON
    """
    # 初始化 RAG 引擎
    # 引擎内部会自动读取环境变量 QDRANT_URL 和 QDRANT_API_KEY 以连接云端数据库
    engine = ResearchIdeaEngine(
        model_config={
            "model_name": LLM_MODEL,
            "api_base": LLM_API_BASE,
            "api_key": LLM_API_KEY
        },
        db_path="./qdrant_local_cache"  # 云端连接失败时的本地备份路径
    )

    # 提取主题用于日志或快照
    topic = payload.get("broad_topic", "Untitled Research")

    try:
        # 核心：运行你在 agent.py 中修改好的 run_agent_workflow
        # 它会自动处理检索、Source ID 引用、VRAM 评估和召回率计算
        result = engine.run_agent_workflow(payload)

        # 检查是否有错误返回
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        # 自动保存快照 (Auto-save)
        try:
            # 构造快照数据结构，适配前端展示
            snapshot_data = {
                "refinement_data": {"title": topic},
                "results": result
            }
            save_snapshot(snapshot_data["refinement_data"], [result])
        except Exception as save_err:
            print(f"⚠️ Snapshot auto-save failed: {save_err}")

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")



@router.get("/snapshots")
def get_snapshots() -> Dict[str, Any]:
    """获取所有已保存的快照列表"""
    return {"files": list_snapshots()}


@router.post("/snapshots")
def save_snapshot_api(payload: SnapshotSaveRequest) -> Dict[str, Any]:
    agent = IdeaAgent()
    snapshot_name = _build_snapshot_name_with_llm(agent, payload.refinement_data, payload.results)
    filename = save_snapshot(payload.refinement_data, payload.results, custom_name=snapshot_name)
    return {"file": filename}


@router.get("/snapshots/{name}")
def load_snapshot_api(name: str) -> Dict[str, Any]:
    """加载特定的研究快照"""
    data = load_snapshot(name)
    if not data:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return data