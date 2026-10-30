from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.security import (
    check_login_lockout,
    create_access_token,
    generate_totp_secret,
    get_current_user,
    record_failed_login,
    reset_login_lockout,
    revoke_access_token,
    verify_password,
    verify_totp_code,
)
from app.models.entities import User

router = APIRouter(prefix="/auth", tags=["auth"])

_login_attempts: dict[str, list[float]] = {}


class LoginRequest(BaseModel):
    email: str
    password: str
    totp_code: str | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    totp_enabled: bool = False


class TOTPSetupResponse(BaseModel):
    secret: str
    totp_uri: str


class TOTPVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


@router.post("/login", response_model=UserResponse)
async def login(
    req: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    # 1. Check account lockout (6.1)
    check_login_lockout(req.email)

    # 2. IP rate limit: max 10 failed attempts per 60 seconds per IP
    now = time.time()
    client_ip = request.client.host if request.client else "unknown"
    attempts = _login_attempts.get(client_ip, [])
    attempts = [t for t in attempts if now - t < 60]
    if len(attempts) >= 10:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts from this IP. Please try again later.",
        )

    stmt = select(User).where(User.email == req.email.lower().strip())
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(user.password_hash, req.password):
        attempts.append(now)
        _login_attempts[client_ip] = attempts
        record_failed_login(req.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated",
        )

    # 3. Two-factor TOTP verification if enabled
    if user.totp_enabled and user.totp_secret:
        if not req.totp_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="2FA TOTP code required",
            )
        if not verify_totp_code(user.totp_secret, req.totp_code):
            record_failed_login(req.email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 2FA TOTP code",
            )

    # Clear rate limit and lockout on success
    if client_ip in _login_attempts:
        del _login_attempts[client_ip]
    reset_login_lockout(req.email)

    token = create_access_token(user.id, user.role)
    is_production = settings.ENVIRONMENT == "production"

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=is_production,
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
    )

    return UserResponse(
        id=str(user.id),
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
    )


@router.post("/logout")
async def logout(
    response: Response,
    access_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    token_str: str | None = None
    if isinstance(access_token, str):
        token_str = access_token
    elif isinstance(authorization, str) and authorization.startswith("Bearer "):
        token_str = authorization.split(" ")[1]

    if token_str and isinstance(user, User) and isinstance(db, AsyncSession):
        await revoke_access_token(db, token_str, user.id)

    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)) -> Any:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
    )


@router.post("/totp/setup", response_model=TOTPSetupResponse)
async def setup_totp(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    secret = generate_totp_secret()
    user.totp_secret = secret
    await db.commit()
    uri = f"otpauth://totp/InvoiceFlow:{user.email}?secret={secret}&issuer=InvoiceFlow"
    return TOTPSetupResponse(secret=secret, totp_uri=uri)


@router.post("/totp/verify")
async def verify_and_enable_totp(
    req: TOTPVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP setup not initiated",
        )
    if not verify_totp_code(user.totp_secret, req.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code",
        )
    user.totp_enabled = True
    await db.commit()
    return {"message": "2FA TOTP successfully activated", "totp_enabled": True}


@router.post("/totp/disable")
async def disable_totp(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    user.totp_enabled = False
    user.totp_secret = None
    await db.commit()
    return {"message": "2FA TOTP disabled", "totp_enabled": False}
