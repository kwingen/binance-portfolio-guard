"""
JWT 认证 + 密码哈希 + 会话黑名单 + Cookie 安全
- bcrypt 直接哈希密码
- JWT 存储在 httpOnly Secure SameSite=Strict Cookie
- XSS 无法窃取 token, HTTPS 加密传输
- 兼容 Bearer header (SSE 等场景)
"""
import time
import threading
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from server.config import settings

bearer_scheme = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"
COOKIE_NAME = "sl_token"
CSRF_COOKIE = "sl_csrf"

_jti_blacklist: set[str] = set()
_blacklist_lock = threading.Lock()


def revoke_token(jti: str):
    with _blacklist_lock:
        _jti_blacklist.add(jti)


def is_revoked(jti: str) -> bool:
    with _blacklist_lock:
        return jti in _jti_blacklist


# ── Cookie 工具 ──

COOKIE_KWARGS = dict(
    httponly=True, secure=True, samesite="strict", path="/",
    max_age=15 * 60,  # 15 分钟
)


def set_auth_cookie(response: Response, token: str):
    """设置认证 cookie + CSRF cookie"""
    response.set_cookie(COOKIE_NAME, token, **COOKIE_KWARGS)
    # CSRF token: 可被 JS 读取的 cookie，前端拿到后放入 X-CSRF-Token header
    csrf = secrets.token_hex(16)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=True, samesite="strict", path="/", max_age=15*60)


def clear_auth_cookie(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _extract_token(request: Request) -> Optional[str]:
    """优先从 cookie 读，再从 Authorization header 读"""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        # CSRF 防护：有 cookie 时必须带自定义 header
        if request.headers.get("X-CSRF-Token") != request.cookies.get(CSRF_COOKIE):
            raise HTTPException(403, "CSRF 验证失败")
        return token
    # 回退到 Bearer header
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


# ── 密码 ──

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def validate_password_strength(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "密码至少 8 位"
    if not any(c.isupper() for c in password):
        return False, "需要至少一个大写字母"
    if not any(c.islower() for c in password):
        return False, "需要至少一个小写字母"
    if not any(c.isdigit() for c in password):
        return False, "需要至少一个数字"
    if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/`~" for c in password):
        return False, "需要至少一个特殊字符 (!@#$%^&* 等)"
    return True, ""


# ── JWT ──

def create_access_token(expires_minutes: Optional[int] = None) -> str:
    expire_minutes = expires_minutes or settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    jti = str(int(time.time() * 1000000))
    payload = {
        "sub": "admin", "exp": expire,
        "iat": datetime.now(timezone.utc), "jti": jti,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_sse_token() -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {
        "sub": "sse", "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(int(time.time() * 1000000)),
        "scope": "sse_only",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if is_revoked(payload.get("jti", "")):
            raise HTTPException(401, "令牌已被吊销")
        return payload
    except JWTError:
        raise HTTPException(401, "无效或过期的令牌")


# ── 认证依赖 ──

async def require_auth(request: Request):
    token = _extract_token(request)
    if not token:
        raise HTTPException(401, "请先登录")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if is_revoked(payload.get("jti", "")):
            raise HTTPException(401, "令牌已被吊销")
        if payload.get("scope") == "sse_only":
            raise HTTPException(401, "无效的令牌类型")
    except JWTError:
        raise HTTPException(401, "令牌无效或已过期")
    return True


def is_setup_needed() -> bool:
    return getattr(settings, '_setup_mode', False) or (
        not settings.auth_password_hash and bool(getattr(settings, '_setup_token', ''))
    )
