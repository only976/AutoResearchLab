"""Pydantic request/response schemas for API."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PlanRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    idea: Optional[str] = None
    skip_quality_assessment: bool = Field(default=False, alias="skipQualityAssessment")


class PlanLayoutRequest(BaseModel):
    """Request for plan execution layout (execution graph)."""
    model_config = ConfigDict(populate_by_name=True)
    execution: dict = Field(..., description="Execution data with tasks")
    plan_id: str = Field(default="test", alias="planId")


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    plan_id: str = Field(default="test", alias="planId")


class ExecutionRunRequest(BaseModel):
    """Request for starting execution. planId optional; if provided, validated against runner layout.
    resumeFromTaskId: when set, only reset that task and downstream to undone, then run (resume from task)."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    plan_id: Optional[str] = Field(default=None, alias="planId")
    resume_from_task_id: Optional[str] = Field(default=None, alias="resumeFromTaskId")


class ExecutionRetryRequest(BaseModel):
    """Request for retrying a single failed task."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    plan_id: Optional[str] = Field(default=None, alias="planId")
    task_id: str = Field(..., alias="taskId")
