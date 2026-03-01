"""Status API - 用于前端按钮禁用逻辑：Plan Agent 需有 idea_id，Task Agent Execution 需有 idea_id 及 plan_id。"""

from fastapi import APIRouter

from db import list_idea_ids, list_recent_plans

router = APIRouter()


@router.get("")
async def get_status():
    """返回 db 中是否有合法 idea_id 及 plan_id。用于 Idea(Refine)/Plan/Task(Execute) 按钮启用判断。"""
    idea_ids = await list_idea_ids()
    plans = await list_recent_plans()
    has_idea = len(idea_ids) > 0
    has_plan = len(plans) > 0
    return {"hasIdea": has_idea, "hasPlan": has_plan}
