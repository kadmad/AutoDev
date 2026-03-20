import json
import asyncio
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
from uuid import UUID
from jose import JWTError, jwt

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.redis_service import get_log_buffer

router = APIRouter()


@router.websocket("/ws/pipeline/{run_id}")
async def pipeline_websocket(websocket: WebSocket, run_id: str):
    await websocket.accept()

    # 1. Replay buffered logs so late-connecting clients see everything
    buffered = get_log_buffer(run_id)
    for msg in buffered:
        try:
            await websocket.send_text(msg)
        except Exception:
            return

    # 2. Subscribe to live pub/sub for new messages going forward
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    channels = [
        f"pipeline:logs:{run_id}",
        f"pipeline:status:{run_id}",
    ]
    await pubsub.subscribe(*channels)

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.close()
        await r.aclose()


@router.websocket("/ws/pipelines")
async def user_pipelines_ws(websocket: WebSocket, token: str = Query(...)):
    """User-level WebSocket: pushes pipeline_update events for all pipelines owned by user."""
    # Authenticate via query-param token (WebSocket can't send headers)
    user_id: str | None = None
    async with AsyncSessionLocal() as db:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            sub = payload.get("sub")
            if sub:
                result = await db.execute(select(User).where(User.id == UUID(sub)))
                user = result.scalar_one_or_none()
                if user:
                    user_id = str(user.id)
        except (JWTError, Exception):
            pass

    await websocket.accept()

    if not user_id:
        await websocket.close(code=4001)
        return

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    channel = f"user:pipelines:{user_id}"
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await r.aclose()
