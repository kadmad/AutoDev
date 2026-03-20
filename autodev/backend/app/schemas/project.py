from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, List


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    monolithic_dir: Optional[str] = None
    frontend_dir: Optional[str] = None
    backend_dir: Optional[str] = None
    frontend_tech: Optional[str] = None
    backend_tech: Optional[str] = None
    test_command: Optional[str] = None
    gitlab_repo_url: Optional[str] = None
    gitlab_project_id: Optional[str] = None
    gitlab_token: Optional[str] = None
    base_branch: str = "develop"
    pr_checklist: Optional[List[str]] = None
    git_provider: Optional[str] = None
    repo_full_name: Optional[str] = None
    zoho_portal_name: Optional[str] = None
    zoho_project_id: Optional[str] = None
    server_start_command: Optional[str] = None
    server_port: Optional[int] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    monolithic_dir: Optional[str] = None
    frontend_dir: Optional[str] = None
    backend_dir: Optional[str] = None
    frontend_tech: Optional[str] = None
    backend_tech: Optional[str] = None
    test_command: Optional[str] = None
    gitlab_repo_url: Optional[str] = None
    gitlab_project_id: Optional[str] = None
    gitlab_token: Optional[str] = None
    base_branch: Optional[str] = None
    pr_checklist: Optional[List[str]] = None
    git_provider: Optional[str] = None
    repo_full_name: Optional[str] = None
    zoho_portal_name: Optional[str] = None
    zoho_project_id: Optional[str] = None
    server_start_command: Optional[str] = None
    server_port: Optional[int] = None


class ProjectResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: Optional[str]
    monolithic_dir: Optional[str]
    frontend_dir: Optional[str]
    backend_dir: Optional[str]
    frontend_tech: Optional[str]
    backend_tech: Optional[str]
    test_command: Optional[str]
    gitlab_repo_url: Optional[str]
    gitlab_project_id: Optional[str]
    base_branch: str
    pr_checklist: Optional[List[str]]
    git_provider: Optional[str]
    repo_full_name: Optional[str]
    zoho_portal_name: Optional[str]
    zoho_project_id: Optional[str]
    server_start_command: Optional[str]
    server_port: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


TECH_STACKS = {
    "frontend": [
        {"id": "react", "name": "React", "description": "React.js SPA"},
        {"id": "next", "name": "Next.js", "description": "Next.js with SSR"},
        {"id": "vue", "name": "Vue.js", "description": "Vue 3 SPA"},
        {"id": "angular", "name": "Angular", "description": "Angular SPA"},
    ],
    "backend": [
        {"id": "fastapi", "name": "FastAPI", "description": "Python FastAPI"},
        {"id": "django", "name": "Django", "description": "Django + DRF"},
        {"id": "express", "name": "Express.js", "description": "Node.js Express"},
        {"id": "rails", "name": "Rails", "description": "Ruby on Rails"},
    ],
}
