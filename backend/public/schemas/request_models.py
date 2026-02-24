from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class IdeaRefineRequest(BaseModel):
    scope: str = Field(min_length=1)

class IdeaGenerateRequest(BaseModel):
    scope: str = Field(min_length=1)

class ExperimentCreateRequest(BaseModel):
    idea: Dict[str, Any]
    topic: Optional[Dict[str, Any]] = None

class ExperimentPlanRequest(BaseModel):
    idea: Dict[str, Any]
    topic: Optional[Dict[str, Any]] = None

class ExperimentRunRequest(BaseModel):
    max_iterations: Optional[int] = None

class FeedbackRequest(BaseModel):
    type: str = Field(min_length=1)
    message: str = Field(min_length=1)

class SnapshotSaveRequest(BaseModel):
    refinement_data: Optional[Dict[str, Any]] = None
    results: Optional[Any] = None

class DraftRequest(BaseModel):
    format: str = Field(min_length=1)
