"""认证路由"""
import secrets
import time as _time
from fastapi import APIRouter, HTTPException, Depends, Request

from server.config import settings
from server.auth import (
    hash_password, verify_password, validate_password_strength,
    create_access_token, require_auth, is_setup_needed,
)
from server.models import LoginRequest, LoginResponse, PasswordChangeRequest, SetupRequest

router = APIRouter(prefix="/api/auth", tags=["认证"])

# setup 端点防暴力破解：每 IP 最多 5 次/分钟
_setup_attempts: dict[str, list[float]] = {}
SETUP_RATE_LIMIT = 5


def _check_setup_rate_limit(ip: str):
    now = _time.time()
    window = now - 60
    attempts = _setup_attempts.get(ip, [])
    attempts = [t for t in attempts if t > window]
    if len(attempts) >= SETUP_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="尝试次数过多，请 1 分钟后再试")
    attempts.append(now)
    _setup_attempts[ip] = attempts


@router.get("/status")
async def auth_status():
    return {"setup_needed": is_setup_needed()}


@router.post("/setup", response_model=LoginResponse)
async def setup_password(req: SetupRequest, request: Request):
    """首次设置管理员密码。需要 setup token + 符合复杂度要求的密码。"""
    if not is_setup_needed():
        raise HTTPException(status_code=400, detail="密码已设置，请使用 /login")

    client_ip = request.client.host if request.client else "unknown"
    _check_setup_rate_limit(client_ip)

    # 常数时间比较 setup token
    expected = getattr(settings, '_setup_token', '')
    if not expected or not secrets.compare_digest(req.setup_token.strip(), expected):
        raise HTTPException(status_code=403, detail="Setup token 无效，请检查服务器控制台输出")

    # 密码复杂度
    ok, err = validate_password_strength(req.password)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    # 设置密码，清除 setup 状态
    settings.auth_password_hash = hash_password(req.password)
    settings._setup_mode = False
    settings._setup_token = ''

    token = create_access_token()
    return LoginResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
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
    if not settings.auth_password_hash:
        raise HTTPException(status_code=500, detail="服务器未配置密码")

    if not verify_password(req.old_password, settings.auth_password_hash):
        raise HTTPException(status_code=403, detail="旧密码错误")

    ok, err = validate_password_strength(req.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    settings.auth_password_hash = hash_password(req.new_password)
    return {"ok": True, "message": "密码已更改"}


@router.get("/me")
async def get_me(_=Depends(require_auth)):
    return {"authenticated": True}
