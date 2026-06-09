"""认证路由 — Cookie 模式"""
import secrets
import time as _time
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse

from server.config import settings
from server.auth import (
    hash_password, verify_password, validate_password_strength,
    create_access_token, require_auth, is_setup_needed,
    set_auth_cookie, clear_auth_cookie,
)
from server.models import LoginRequest, PasswordChangeRequest, SetupRequest

router = APIRouter(prefix="/api/auth", tags=["认证"])

_setup_attempts: dict[str, list[float]] = {}
SETUP_RATE_LIMIT = 5


def _check_setup_rate_limit(ip: str):
    now = _time.time()
    window = now - 60
    attempts = _setup_attempts.get(ip, [])
    attempts = [t for t in attempts if t > window]
    if len(attempts) >= SETUP_RATE_LIMIT:
        raise HTTPException(429, "尝试次数过多，请 1 分钟后再试")
    attempts.append(now)
    _setup_attempts[ip] = attempts


@router.get("/status")
async def auth_status():
    return {"setup_needed": is_setup_needed()}


@router.post("/setup")
async def setup_password(req: SetupRequest, request: Request):
    if not is_setup_needed():
        raise HTTPException(400, "密码已设置，请使用 /login")

    client_ip = request.client.host if request.client else "unknown"
    _check_setup_rate_limit(client_ip)

    expected = getattr(settings, '_setup_token', '')
    if not expected or not secrets.compare_digest(req.setup_token.strip(), expected):
        raise HTTPException(403, "Setup token 无效")

    ok, err = validate_password_strength(req.password)
    if not ok:
        raise HTTPException(400, err)

    settings.auth_password_hash = hash_password(req.password)
    settings._setup_mode = False
    settings._setup_token = ''

    token = create_access_token()
    resp = JSONResponse({"ok": True})
    set_auth_cookie(resp, token)
    return resp


@router.post("/login")
async def login(req: LoginRequest):
    if is_setup_needed():
        raise HTTPException(400, "请先设置管理员密码")

    if not verify_password(req.password, settings.auth_password_hash):
        raise HTTPException(401, "密码错误")

    token = create_access_token()
    resp = JSONResponse({"ok": True})
    set_auth_cookie(resp, token)
    return resp


@router.post("/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    clear_auth_cookie(resp)
    return resp


@router.post("/change-password")
async def change_password(req: PasswordChangeRequest, _=Depends(require_auth)):
    if not settings.auth_password_hash:
        raise HTTPException(500, "服务器未配置密码")

    if not verify_password(req.old_password, settings.auth_password_hash):
        raise HTTPException(403, "旧密码错误")

    ok, err = validate_password_strength(req.new_password)
    if not ok:
        raise HTTPException(400, err)

    settings.auth_password_hash = hash_password(req.new_password)
    return {"ok": True, "message": "密码已更改"}


@router.get("/me")
async def get_me(_=Depends(require_auth)):
    return {"authenticated": True}
