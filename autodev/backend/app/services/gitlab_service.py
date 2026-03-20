import httpx
from typing import Optional


class GitLabService:
    def __init__(self, base_url: str, token: str, project_id: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.project_id = project_id
        self.headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/api/v4/projects/{self.project_id}"

    async def create_branch(self, branch_name: str, ref: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.api_url}/repository/branches",
                headers=self.headers,
                json={"branch": branch_name, "ref": ref},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_branch(self, branch_name: str) -> Optional[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_url}/repository/branches/{branch_name}",
                headers=self.headers,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def create_merge_request(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str = "",
    ) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.api_url}/merge_requests",
                headers=self.headers,
                json={
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "title": title,
                    "description": description,
                    "remove_source_branch": True,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_merge_request(self, mr_iid: str) -> Optional[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_url}/merge_requests/{mr_iid}",
                headers=self.headers,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
