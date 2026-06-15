"""Authentication module: JWT tokens + password verification.

Accepts both user JWTs and a static service token (for agent-to-backend calls).
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

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

# Admin user credentials (hardcoded)
ADMIN_USERNAME = "microport_admin"
# bcrypt hash of "73Eyd7XtGL"
ADMIN_PASSWORD_HASH = "$2b$12$Aed2eJHU0yB9sYJA2VNdUe1HPfle.3QK.wL0dhyfopoEIy0TqW6aW"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(username: str) -> str:
    """Create a signed JWT for the given username."""
    payload = {
        "sub": username,
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


def verify_credentials(username: str, password: str) -> bool:
    """Check username and password against stored admin credentials."""
    if username != ADMIN_USERNAME:
        return False
    try:
        import bcrypt
        return bcrypt.checkpw(password.encode(), ADMIN_PASSWORD_HASH.encode())
    except Exception:
        return False


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
