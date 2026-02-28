import os
import json
from typing import Any, Dict
from fastapi import APIRouter, HTTPException

# 1. 导入核心组件和配置
from backend.ideas.agent import IdeaAgent, ResearchIdeaEngine
from backend.api.common import parse_json_text
from backend.config import LLM_MODEL, LLM_API_BASE, LLM_API_KEY
from backend.schemas.request_models import IdeaRefineRequest, SnapshotSaveRequest
from backend.ideas.snapshots import save_snapshot, list_snapshots, load_snapshot

router = APIRouter(prefix="/api/ideas")


@router.post("/refine")
def refine_ideas(payload: IdeaRefineRequest) -> Dict[str, Any]:
    """
    第一阶段：精炼研究主题
    保持原样，使用 IdeaAgent 进行初步的方向发散
    """
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
    """手动保存当前研究成果快照"""
    filename = save_snapshot(payload.refinement_data, payload.results)
    return {"file": filename}


@router.get("/snapshots/{name}")
def load_snapshot_api(name: str) -> Dict[str, Any]:
    """加载特定的研究快照"""
    data = load_snapshot(name)
    if not data:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return data