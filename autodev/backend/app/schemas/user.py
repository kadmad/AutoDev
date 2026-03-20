from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ZohoConfigCreate(BaseModel):
    """Used during setup — email is fetched from Zoho userinfo after OAuth."""
    zoho_email: Optional[str] = None
    zoho_user_id: Optional[str] = None
    portal_name: str
    project_id: str
    webhook_secret: Optional[str] = None
    poll_interval_seconds: int = 60


class ZohoConfigUpdate(BaseModel):
    zoho_email: Optional[str] = None
    zoho_user_id: Optional[str] = None
    portal_name: Optional[str] = None
    project_id: Optional[str] = None
    webhook_secret: Optional[str] = None
    poll_interval_seconds: Optional[int] = None


class ZohoConfigResponse(BaseModel):
    id: UUID
    user_id: UUID
    zoho_email: Optional[str]
    zoho_user_id: Optional[str]
    portal_name: str
    project_id: str
    webhook_secret: Optional[str]
    poll_interval_seconds: int
    token_expired: bool
    is_connected: bool   # True when we have a valid/unexpired access token
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_status(cls, config) -> "ZohoConfigResponse":
        return cls(
            id=config.id,
            user_id=config.user_id,
            zoho_email=config.zoho_email,
            zoho_user_id=config.zoho_user_id,
            portal_name=config.portal_name,
            project_id=config.project_id,
            webhook_secret=config.webhook_secret,
            poll_interval_seconds=config.poll_interval_seconds,
            token_expired=config.token_expired,
            is_connected=bool(config.access_token) and not config.token_expired,
            created_at=config.created_at,
        )


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class SetupRequest(BaseModel):
    user: UserCreate
    zoho: ZohoConfigCreate
