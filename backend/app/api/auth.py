from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.security import create_access_token, get_current_user, verify_password
from app.models.entities import User

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory simple login attempt tracking for rate-limiting
_login_attempts: dict[str, list[float]] = {}


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool


@router.post("/login", response_model=UserResponse)
async def login(
    req: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    # Rate limiting: max 10 failed attempts per 60 seconds per IP
    import time

    now = time.time()
    client_ip = request.client.host if request.client else "unknown"
    attempts = _login_attempts.get(client_ip, [])
    # Keep only last 60s
    attempts = [t for t in attempts if now - t < 60]
    if len(attempts) >= 10:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
        )

    stmt = select(User).where(User.email == req.email.lower().strip())
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(user.password_hash, req.password):
        attempts.append(now)
        _login_attempts[client_ip] = attempts
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated",
        )

    # Clear rate limit on success
    if client_ip in _login_attempts:
        del _login_attempts[client_ip]

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
    )


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)) -> Any:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        role=user.role,
        is_active=user.is_active,
    )
