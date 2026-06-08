# ── 认证 ──
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=128)


class SetupRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)
    setup_token: str = Field(..., min_length=1, max_length=64)
