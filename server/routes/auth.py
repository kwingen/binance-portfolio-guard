"""认证路由"""
from fastapi import APIRouter, HTTPException, Depends

from server.config import settings
from server.auth import hash_password, verify_password, create_access_token, require_auth, is_setup_needed
from server.models import LoginRequest, LoginResponse, PasswordChangeRequest

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.get("/status")
async def auth_status():
    """公开端点：返回系统认证状态（首次访问时用于判断是否需要 setup）"""
    return {
        "setup_needed": is_setup_needed(),
    }


@router.post("/setup")
async def setup_password(req: LoginRequest):
    """首次设置管理员密码（仅密码未设置时可调用）"""
    if not is_setup_needed():
        raise HTTPException(status_code=400, detail="密码已设置，请使用 /login")

    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")

    settings.auth_password_hash = hash_password(req.password)
    settings._setup_mode = False

    token = create_access_token()
    return LoginResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """密码登录，返回 JWT token"""
    if is_setup_needed():
        raise HTTPException(status_code=400, detail="请先设置管理员密码")

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
    return {"ok": True, "message": "密码已更改"}


@router.get("/me")
async def get_me(_=Depends(require_auth)):
    return {"authenticated": True}
