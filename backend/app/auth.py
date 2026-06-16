"""Authentication module: JWT tokens + password verification + RBAC.

Accepts both user JWTs and a static service token (for agent-to-backend calls).
User JWTs embed permissions from their assigned role.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

# ---- Constants ----
_SECRET_KEY = os.getenv("MEDBOT_JWT_SECRET", "medbot-dev-secret-change-in-production")
_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 24

# Service token for agent-to-backend communication.
# Override via MEDBOT_SERVICE_TOKEN env var in production.
SERVICE_TOKEN = os.getenv("MEDBOT_SERVICE_TOKEN", "medbot-agent-service-token-dev")

security_scheme = HTTPBearer(auto_error=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(*, user_id: int, username: str, permissions: list[str]) -> str:
    """Create a signed JWT with embedded permissions."""
    payload = {
        "sub": username,
        "uid": user_id,
        "perms": permissions,
        "iat": _now(),
        "exp": _now() + timedelta(hours=_TOKEN_EXPIRE_HOURS),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, object] | None:
    """Decode and validate a JWT. Returns the payload or None."""
    try:
        return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError:
        return None


def hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, password_hash: str) -> bool:
    try:
        import bcrypt
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


def verify_credentials(username: str, password: str) -> dict[str, object] | None:
    """Check username/password against the users table. Returns user dict with permissions."""
    from app.db import get_user_by_username
    user = get_user_by_username(username)
    if user is None:
        return None
    if not check_password(password, str(user.get("password_hash", ""))):
        return None
    try:
        permissions = json.loads(str(user.get("permissions", "[]")))
    except (json.JSONDecodeError, TypeError):
        permissions = []
    return {
        "user_id": user["id"],
        "username": user["username"],
        "role_id": user["role_id"],
        "permissions": permissions,
    }


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> str:
    """FastAPI dependency – returns username if token is valid, raises 401 otherwise.

    Accepts either:
    - A valid user JWT (via login)
    - The static service token (for agent-to-backend communication)
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Check service token first (for agent-to-backend calls)
    if token == SERVICE_TOKEN:
        return "agent-service"

    # Check JWT
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if not isinstance(username, str) or not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    return username


def require_permission(permission: str) -> Callable:
    """FastAPI dependency factory – checks the JWT payload for a specific permission.

    Usage:
        @app.get("/settings")
        def get_settings(user=Depends(require_permission("settings:read"))):
            ...
    """
    async def _check(
        credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    ) -> str:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = credentials.credentials

        # Service token bypasses all permission checks
        if token == SERVICE_TOKEN:
            return "agent-service"

        payload = decode_access_token(token)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        username = payload.get("sub")
        if not isinstance(username, str):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        perms: list = payload.get("perms", [])
        if permission not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )

        return username
    return _check
