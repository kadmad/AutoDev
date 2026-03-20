from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        from app.models import user, project, pipeline_run, plan, agent_run, test_result, merge_request  # noqa
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent column migrations — runs safely on every startup
        await conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS monolithic_dir TEXT;"
        ))
        await conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS zoho_portal_name VARCHAR(255);"
        ))
        await conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS zoho_project_id VARCHAR(255);"
        ))
        await conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS server_start_command TEXT;"
        ))
        await conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS server_port INTEGER;"
        ))
        await conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS zoho_project_name VARCHAR(255);"
        ))
        await conn.execute(text(
            "ALTER TABLE test_results ADD COLUMN IF NOT EXISTS scenarios TEXT;"
        ))
        await conn.execute(text(
            "ALTER TABLE test_results ADD COLUMN IF NOT EXISTS browser_test_output TEXT;"
        ))
        await conn.execute(text(
            "ALTER TABLE test_results ADD COLUMN IF NOT EXISTS browser_test_status VARCHAR(20);"
        ))
        await conn.execute(text(
            "ALTER TABLE zoho_configs ADD COLUMN IF NOT EXISTS api_domain VARCHAR(255);"
        ))
        await conn.execute(text(
            "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS zoho_task_number VARCHAR(100);"
        ))
        await conn.execute(text(
            "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT FALSE;"
        ))
        # Fix legacy pipeline runs that were created with status='pending' (old default)
        # Use lock_timeout so this never blocks startup if the worker holds row locks.
        try:
            await conn.execute(text("SET LOCAL lock_timeout = '2s';"))
            await conn.execute(text(
                "UPDATE pipeline_runs SET status='task_received', current_stage='task_received' "
                "WHERE status='pending' OR status IS NULL OR status='';"
            ))
        except Exception:
            pass  # Non-fatal — old records will just show as-is
