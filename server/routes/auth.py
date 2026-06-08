"""认证路由"""
from fastapi import APIRouter, HTTPException, Depends

from server.config import settings
from server.auth import hash_password, verify_password, create_access_token, require_auth
from server.models import LoginRequest, LoginResponse, PasswordChangeRequest

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """密码登录，返回 JWT token"""
    if not settings.auth_password_hash:
        raise HTTPException(status_code=500, detail="服务器未配置密码")

    if not verify_password(req.password, settings.auth_password_hash):
        raise HTTPException(status_code=401, detail="密码错误")

    token = create_access_token()
    return LoginResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/change-password")
async def change_password(req: PasswordChangeRequest, _=Depends(require_auth)):
    """修改密码（需要已登录 + 旧密码验证）"""
    if not settings.auth_password_hash:
        raise HTTPException(status_code=500, detail="服务器未配置密码")

    if not verify_password(req.old_password, settings.auth_password_hash):
        raise HTTPException(status_code=403, detail="旧密码错误")

    settings.auth_password_hash = hash_password(req.new_password)
    return {"ok": True, "message": "密码已更改（重启后需重新设置环境变量 SL_PASSWORD）"}


@router.get("/me")
async def get_me(_=Depends(require_auth)):
    return {"authenticated": True}
