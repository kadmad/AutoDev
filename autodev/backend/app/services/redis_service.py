import json
import redis
from datetime import datetime
from app.config import settings

# Synchronous redis client for rq
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

# How long to keep the log buffer after pipeline finishes (2 hours)
LOG_BUFFER_TTL = 7200


def enqueue_pipeline(run_id: str, project_id: str):
    """Enqueue a pipeline job."""
    from rq import Queue
    q = Queue("pipeline:default", connection=redis_client)
    q.enqueue(
        "app.workers.pipeline_worker.run_pipeline",
        run_id=run_id,
        project_id=project_id,
        job_timeout=3600,
    )


def publish_log(run_id: str, line: str, agent: str = "system"):
    """Publish a log line to Redis pub/sub AND append to persistent buffer."""
    message = json.dumps({
        "type": "log",
        "line": line,
        "agent": agent,
        "ts": datetime.utcnow().isoformat(),
    })
    buf_key = f"pipeline:logbuf:{run_id}"
    pipe = redis_client.pipeline()
    pipe.rpush(buf_key, message)
    pipe.expire(buf_key, LOG_BUFFER_TTL)
    pipe.publish(f"pipeline:logs:{run_id}", message)
    pipe.execute()


def publish_stage(run_id: str, stage: str):
    """Publish a stage transition event AND buffer it."""
    message = json.dumps({
        "type": "stage",
        "stage": stage,
        "ts": datetime.utcnow().isoformat(),
    })
    buf_key = f"pipeline:logbuf:{run_id}"
    pipe = redis_client.pipeline()
    pipe.rpush(buf_key, message)
    pipe.expire(buf_key, LOG_BUFFER_TTL)
    pipe.publish(f"pipeline:status:{run_id}", message)
    pipe.execute()


def get_log_buffer(run_id: str) -> list[str]:
    """Return all buffered log lines for a run (for WS replay on connect)."""
    return redis_client.lrange(f"pipeline:logbuf:{run_id}", 0, -1)


def publish_pipeline_event(user_id: str, run_id: str, status: str, stage: str):
    """Publish a pipeline state change to the user-level channel for Dashboard WebSocket."""
    message = json.dumps({
        "type": "pipeline_update",
        "run_id": run_id,
        "status": status,
        "stage": stage,
        "ts": datetime.utcnow().isoformat(),
    })
    redis_client.publish(f"user:pipelines:{user_id}", message)


def get_redis():
    return redis_client
