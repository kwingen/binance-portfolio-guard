"""
JWT 认证 + 密码哈希
- bcrypt 直接哈希密码
- python-jose JWT，带过期时间
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from server.config import settings

bearer_scheme = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    密码复杂性校验。
    返回 (是否通过, 错误信息)
    """
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
    payload = {
        "sub": "admin",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(int(time.time() * 1000)),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="无效或过期的令牌")


async def require_auth(
    token: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        jwt.decode(token.credentials, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    return True


def is_setup_needed() -> bool:
    """是否首次运行（未设置密码 + 有有效 setup token）"""
    return getattr(settings, '_setup_mode', False) or (
        not settings.auth_password_hash and bool(getattr(settings, '_setup_token', ''))
    )
