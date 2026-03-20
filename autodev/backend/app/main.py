from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db
from app.api.v1.router import api_router
from app.api.task_assign import router as task_assign_router
from app.api.v1.websocket import router as ws_router
from app.api.github_webhook import router as github_webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown


app = FastAPI(
    title="AutoDev",
    description="Product Lifecycle Automation System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(task_assign_router, tags=["task-assign"])   # /task-assign at root
app.include_router(ws_router)                                  # /ws/pipeline/{run_id} at root
app.include_router(github_webhook_router, tags=["github"])     # /github-webhook at root


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
