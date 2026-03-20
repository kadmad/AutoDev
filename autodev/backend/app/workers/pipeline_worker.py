"""
rq worker entry point for pipeline jobs.
Run with: rq worker pipeline:default pipeline:agents
"""
import asyncio

# Import all models so SQLAlchemy can resolve relationship strings
import app.models.user  # noqa: F401
import app.models.project  # noqa: F401
import app.models.pipeline_run  # noqa: F401
import app.models.plan  # noqa: F401
import app.models.agent_run  # noqa: F401
import app.models.test_result  # noqa: F401
import app.models.merge_request  # noqa: F401
import app.models.git_config  # noqa: F401

from app.agents.orchestrator import run_pipeline as _run_pipeline


def run_pipeline(run_id: str, project_id: str):
    """Synchronous wrapper for rq — runs the async orchestrator."""
    asyncio.run(_run_pipeline(run_id, project_id))


def start_worker():
    """Start rq worker programmatically (optional helper)."""
    from redis import Redis
    from rq import Worker
    from app.config import settings

    conn = Redis.from_url(settings.REDIS_URL)
    queues = ["pipeline:default", "pipeline:agents"]
    worker = Worker(queues, connection=conn)
    worker.work()


if __name__ == "__main__":
    start_worker()
