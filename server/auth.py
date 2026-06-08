"""
JWT 认证 + 密码哈希 + 会话黑名单
- bcrypt 直接哈希密码
- python-jose JWT，15 分钟过期 + jti 黑名单
- SSE 专用短时效 token（仅 5 分钟，仅用于 /api/events）
"""
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from server.config import settings

bearer_scheme = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"

# ── JTI 黑名单（内存，重启清空）──
_jti_blacklist: set[str] = set()
_blacklist_lock = threading.Lock()


def revoke_token(jti: str):
    with _blacklist_lock:
        _jti_blacklist.add(jti)


def is_revoked(jti: str) -> bool:
    with _blacklist_lock:
        return jti in _jti_blacklist


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


def create_access_token(expires_minutes: Optional[int] = None) -> str:
    expire_minutes = expires_minutes or settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    jti = str(int(time.time() * 1000000))  # 微秒级唯一
    payload = {
        "sub": "admin",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": jti,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_sse_token() -> str:
    """SSE 专用短时效 token（仅 5 分钟，仅限 /api/events 使用）"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {
        "sub": "sse",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(int(time.time() * 1000000)),
        "scope": "sse_only",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if is_revoked(payload.get("jti", "")):
            raise HTTPException(status_code=401, detail="令牌已被吊销")
        # SSE token 只能用于 SSE 端点
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="无效或过期的令牌")


async def require_auth(
    token: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        payload = jwt.decode(token.credentials, settings.secret_key, algorithms=[ALGORITHM])
        if is_revoked(payload.get("jti", "")):
            raise HTTPException(status_code=401, detail="令牌已被吊销")
        # SSE token 不能用于普通 API
        if payload.get("scope") == "sse_only":
            raise HTTPException(status_code=401, detail="无效的令牌类型")
    except JWTError:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    return True


def is_setup_needed() -> bool:
    return getattr(settings, '_setup_mode', False) or (
        not settings.auth_password_hash and bool(getattr(settings, '_setup_token', ''))
    )
