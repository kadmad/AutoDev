from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import bcrypt
from jose import jwt
from datetime import datetime, timedelta

from app.database import get_db
from app.models.user import User, ZohoConfig
from app.schemas.user import SetupRequest, TokenResponse, UserResponse, LoginRequest
from app.config import settings

router = APIRouter()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


async def _async_hash_password(password: str) -> str:
    return await run_in_threadpool(_hash_password, password)


async def _async_verify_password(plain: str, hashed: str) -> bool:
    return await run_in_threadpool(_verify_password, plain, hashed)


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


@router.post("/setup", response_model=TokenResponse)
async def setup(request: SetupRequest, db: AsyncSession = Depends(get_db)):
    count = await db.scalar(select(func.count()).select_from(User))
    if count and count > 0:
        raise HTTPException(status_code=409, detail="Setup already completed. Use /login instead.")

    user = User(
        name=request.user.name,
        email=request.user.email,
        password_hash=await _async_hash_password(request.user.password),
    )
    db.add(user)
    await db.flush()

    zoho = ZohoConfig(
        user_id=user.id,
        **request.zoho.model_dump(),
    )
    db.add(zoho)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    if not user or not await _async_verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/setup/status")
async def setup_status(db: AsyncSession = Depends(get_db)):
    count = await db.scalar(select(func.count()).select_from(User))
    return {"completed": bool(count and count > 0)}
