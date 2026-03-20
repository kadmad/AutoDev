from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, ZohoConfig
from app.schemas.user import UserUpdate, UserResponse, ZohoConfigCreate, ZohoConfigUpdate, ZohoConfigResponse

router = APIRouter()


@router.get("/users/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/users/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.name is not None:
        current_user.name = data.name
    if data.email is not None:
        current_user.email = data.email
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/users/me/zoho", response_model=ZohoConfigResponse)
async def get_zoho_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ZohoConfig).where(ZohoConfig.user_id == current_user.id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Zoho config not found")
    return ZohoConfigResponse.from_orm_with_status(config)


@router.put("/users/me/zoho", response_model=ZohoConfigResponse)
async def update_zoho_config(
    data: ZohoConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ZohoConfig).where(ZohoConfig.user_id == current_user.id))
    config = result.scalar_one_or_none()

    if not config:
        config = ZohoConfig(user_id=current_user.id, **data.model_dump(exclude_none=True))
        db.add(config)
    else:
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(config, field, value)

    await db.commit()
    await db.refresh(config)
    return ZohoConfigResponse.from_orm_with_status(config)
