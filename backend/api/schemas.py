"""Pydantic request/response schemas for API.

叙事口径：Idea、Plan、Task 为三个 Agent；Task Agent 含 Execution（执行）与 Validation（验证）两阶段。
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PlanRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    idea: Optional[str] = None
    idea_id: Optional[str] = Field(default=None, alias="ideaId")
    skip_quality_assessment: bool = Field(default=False, alias="skipQualityAssessment")


class PlanLayoutRequest(BaseModel):
    """Task Agent Execution 阶段可视化布局请求（execution graph）。"""
    model_config = ConfigDict(populate_by_name=True)
    execution: dict = Field(..., description="Execution data with tasks")
    idea_id: str = Field(default="test", alias="ideaId")
    plan_id: str = Field(default="test", alias="planId")


class ExecutionRequest(BaseModel):
    """Task Agent Execution 阶段通用请求（ideaId、planId）。"""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    idea_id: str = Field(default="test", alias="ideaId")
    plan_id: str = Field(default="test", alias="planId")


class ExecutionRunRequest(BaseModel):
    """Task Agent Execution 阶段启动请求。resumeFromTaskId：从该任务及下游恢复执行。"""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    idea_id: Optional[str] = Field(default=None, alias="ideaId")
    plan_id: Optional[str] = Field(default=None, alias="planId")
    resume_from_task_id: Optional[str] = Field(default=None, alias="resumeFromTaskId")


class ExecutionRetryRequest(BaseModel):
    """Task Agent Execution 阶段：重试单个失败任务。"""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    idea_id: Optional[str] = Field(default=None, alias="ideaId")
    plan_id: Optional[str] = Field(default=None, alias="planId")
    task_id: str = Field(..., alias="taskId")


class IdeaCollectRequest(BaseModel):
    """Idea Agent 文献收集请求。"""
    model_config = ConfigDict(populate_by_name=True)
    idea: Optional[str] = Field(default=None, description="Fuzzy research idea")
    limit: int = Field(default=10, ge=1, le=50, description="Max number of papers to return")
