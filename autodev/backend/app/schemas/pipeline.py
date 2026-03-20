from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, List


class PipelineTriggerRequest(BaseModel):
    project_id: UUID
    zoho_task_id: str
    zoho_task_number: Optional[str] = None
    zoho_task_title: Optional[str] = None
    zoho_task_description: Optional[str] = None


class AgentRunResponse(BaseModel):
    id: UUID
    agent_type: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    exit_code: Optional[int]
    error: Optional[str]

    model_config = {"from_attributes": True}


class PlanResponse(BaseModel):
    id: UUID
    pipeline_run_id: UUID
    content: str
    version: int
    approved_by: Optional[UUID]
    approved_at: Optional[datetime]
    user_edits: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class TestResultResponse(BaseModel):
    id: UUID
    pipeline_run_id: UUID
    total: int
    passed: int
    failed: int
    skipped: int
    html_report_path: Optional[str]
    raw_output: Optional[str]
    scenarios: Optional[str]  # JSON array of manual test scenarios
    browser_test_output: Optional[str] = None
    browser_test_status: Optional[str] = None
    approved_by: Optional[UUID]
    approved_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class MergeRequestResponse(BaseModel):
    id: UUID
    pipeline_run_id: UUID
    gitlab_mr_id: Optional[str]
    mr_url: Optional[str]
    title: Optional[str]
    source_branch: Optional[str]
    target_branch: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PipelineRunResponse(BaseModel):
    id: UUID
    project_id: UUID
    triggered_by_user_id: Optional[UUID]
    zoho_task_id: Optional[str]
    zoho_task_number: Optional[str]
    zoho_task_title: Optional[str]
    zoho_task_description: Optional[str]
    status: str
    current_stage: Optional[str]
    feature_branch: Optional[str]
    error_message: Optional[str]
    archived: bool = False
    created_at: datetime
    updated_at: datetime
    plans: List[PlanResponse] = []
    agent_runs: List[AgentRunResponse] = []
    test_results: List[TestResultResponse] = []
    merge_requests: List[MergeRequestResponse] = []

    model_config = {"from_attributes": True}


class PipelineRunSummary(BaseModel):
    id: UUID
    project_id: UUID
    zoho_task_id: Optional[str]
    zoho_task_number: Optional[str]
    zoho_task_title: Optional[str]
    zoho_task_description: Optional[str]
    status: str
    current_stage: Optional[str]
    feature_branch: Optional[str]
    error_message: Optional[str]
    archived: bool = False
    merge_requests: List[MergeRequestResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlanApproveRequest(BaseModel):
    user_edits: Optional[str] = None


class PlanReplanRequest(BaseModel):
    feedback: str


class TestScenario(BaseModel):
    id: str
    name: str
    steps: Optional[str] = None
    expected: Optional[str] = None
    status: str  # "pending" | "passed" | "failed"


class TestScenariosUpdateRequest(BaseModel):
    scenarios: List[TestScenario]


class TestApproveRequest(BaseModel):
    scenarios: List[TestScenario]


class TestReworkRequest(BaseModel):
    feedback: str
