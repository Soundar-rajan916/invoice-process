from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.models.entities import RevokedToken, User

ph = PasswordHasher()

# In-memory tracking for rate-limiting and lockout
_login_failures: dict[str, list[float]] = {}
_lockout_until: dict[str, float] = {}


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(hash_str: str, password: str) -> bool:
    try:
        return ph.verify(hash_str, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def validate_password_strength(password: str) -> None:
    """Enforces NIST-aligned password complexity: >=8 chars, upper, lower, digit, special."""
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters long",
        )
    if not re.search(r"[A-Z]", password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must contain at least one uppercase letter",
        )
    if not re.search(r"[a-z]", password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must contain at least one lowercase letter",
        )
    if not re.search(r"\d", password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must contain at least one number",
        )
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must contain at least one special character",
        )


def check_login_lockout(email: str) -> None:
    normalized = email.strip().lower()
    now = time.time()
    locked_until = _lockout_until.get(normalized, 0.0)
    if now < locked_until:
        remaining_secs = int(locked_until - now)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Account temporarily locked for {remaining_secs} seconds.",
        )


def record_failed_login(email: str) -> None:
    normalized = email.strip().lower()
    now = time.time()
    attempts = _login_failures.get(normalized, [])
    attempts = [t for t in attempts if now - t < 900]
    attempts.append(now)
    _login_failures[normalized] = attempts

    if len(attempts) >= 5:
        _lockout_until[normalized] = now + 900  # 15 minutes


def reset_login_lockout(email: str) -> None:
    normalized = email.strip().lower()
    _login_failures.pop(normalized, None)
    _lockout_until.pop(normalized, None)


# ---------------------------------------------------------------------------
# TOTP Two-Factor Authentication (RFC 6238)
# ---------------------------------------------------------------------------
def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8").rstrip("=")


def get_totp_code(secret: str, interval: int = 30, t: float | None = None) -> str:
    if t is None:
        t = time.time()
    pad = len(secret) % 8
    if pad != 0:
        secret += "=" * (8 - pad)
    key = base64.b32decode(secret, casefold=True)
    counter = int(t // interval)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % 1000000).zfill(6)


def verify_totp_code(secret: str, code: str, interval: int = 30, window: int = 1) -> bool:
    now = time.time()
    cleaned = code.strip()
    for offset in range(-window, window + 1):
        t = now + (offset * interval)
        expected = get_totp_code(secret, interval=interval, t=t)
        if hmac.compare_digest(expected, cleaned):
            return True
    return False


def create_access_token(user_id: uuid.UUID, role: str, jti: str | None = None) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": jti or str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from e


async def revoke_access_token(db: AsyncSession, token: str, user_id: uuid.UUID) -> None:
    try:
        payload = decode_access_token(token)
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            expires_at = datetime.fromtimestamp(exp, tz=UTC)
            revocation = RevokedToken(
                token_jti=jti,
                user_id=user_id,
                expires_at=expires_at,
            )
            db.add(revocation)
            await db.commit()
    except Exception:
        pass


async def get_current_user(
    access_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    token = access_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    payload = decode_access_token(token)
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    # Check revoked tokens
    jti = payload.get("jti")
    if jti:
        revoked = await db.scalar(select(RevokedToken).where(RevokedToken.token_jti == jti))
        if revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )

    user_id = uuid.UUID(user_id_str)
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User inactive or not found",
        )

    return user


async def require_reviewer(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("reviewer", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer or admin role required",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user


def verify_csrf_header(
    x_requested_with: str | None = Header(default=None),
) -> None:
    """CSRF guard for state-changing endpoints."""
    if settings.ENVIRONMENT != "test" and not x_requested_with:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required CSRF header (X-Requested-With)",
        )
