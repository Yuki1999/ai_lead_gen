"""Authentication module: JWT tokens + password verification + RBAC.

Accepts both user JWTs and a static service token (for agent-to-backend calls).

Permissions are NOT embedded in the JWT — they are looked up from the database
on every request (with a short TTL cache) so role/permission changes take effect
without requiring users to re-login or wait for token expiry.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.permissions import matches as _perm_matches

_logger = logging.getLogger("medbot.auth")

# ---- Constants ----
_SECRET_KEY = os.getenv("MEDBOT_JWT_SECRET", "medbot-dev-secret-change-in-production")
_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 24

# Service token for agent-to-backend communication.
# Read dynamically via ``service_token()`` so tests can mutate the env after
# import. ``SERVICE_TOKEN`` is kept as a module-level cached value because some
# call sites (and tests) read it directly; treat ``service_token()`` as the
# source of truth in new code.
SERVICE_TOKEN = os.getenv("MEDBOT_SERVICE_TOKEN", "medbot-agent-service-token-dev")


def service_token() -> str:
    """Return the currently configured service token (re-read from env)."""
    return os.getenv("MEDBOT_SERVICE_TOKEN", "medbot-agent-service-token-dev")


def validate_secrets() -> None:
    """Log warnings when critical secrets are still set to dev defaults.

    Call once at startup. Does NOT crash — this is a demo system, but dev defaults
    in production are dangerous and the operator must be warned.
    """
    warnings: list[str] = []

    if _SECRET_KEY == "medbot-dev-secret-change-in-production":
        warnings.append(
            "MEDBOT_JWT_SECRET is using the hardcoded dev default — "
            "JWT tokens can be forged by anyone with source access."
        )
    if service_token() == "medbot-agent-service-token-dev":
        warnings.append(
            "MEDBOT_SERVICE_TOKEN is using the hardcoded dev default — "
            "the agent-to-backend channel is unprotected."
        )

    if warnings:
        _logger.warning("=" * 60)
        _logger.warning("SECURITY: %d critical secret(s) using dev defaults:", len(warnings))
        for w in warnings:
            _logger.warning("  • %s", w)
        _logger.warning("Set the corresponding env vars before deploying to production.")
        _logger.warning("=" * 60)
    else:
        _logger.info("Secrets validation passed — no dev defaults detected.")

security_scheme = HTTPBearer(auto_error=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(*, user_id: int, username: str) -> str:
    """Create a signed JWT containing only the user identity.

    Permissions are intentionally NOT embedded — they are looked up on every
    request via ``get_user_permissions(uid)``. Storing them in the token would
    mean role changes don't take effect until expiry (24h).
    """
    payload = {
        "sub": username,
        "uid": user_id,
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


# ── Permission cache ────────────────────────────────────────────────────────
#
# require_permission() runs on every request. We cache the (uid → perms) lookup
# for a short TTL so the per-request DB cost is amortized; cache is invalidated
# explicitly on user/role mutations (see app.db).

_PERM_CACHE_TTL_SECONDS = 30.0
_perm_cache: dict[int, tuple[float, list[str]]] = {}


def _load_user_permissions(user_id: int) -> list[str] | None:
    """Read fresh permissions from the database. Returns None if the user is gone."""
    from app.db import connect
    with connect() as connection:
        row = connection.execute(
            "SELECT r.permissions FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    try:
        result = json.loads(row["permissions"] or "[]")
        return [str(p) for p in result] if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def get_user_permissions(user_id: int) -> list[str] | None:
    """Return the current permission list for ``user_id`` (cached up to 30s).

    Returns ``None`` if the user has been deleted or has no role — callers
    should treat that as 401.
    """
    now = time.monotonic()
    cached = _perm_cache.get(user_id)
    if cached and (now - cached[0]) < _PERM_CACHE_TTL_SECONDS:
        return cached[1]
    perms = _load_user_permissions(user_id)
    if perms is None:
        # User is gone — drop any stale cache entry too.
        _perm_cache.pop(user_id, None)
        return None
    _perm_cache[user_id] = (now, perms)
    return perms


def invalidate_permission_cache(user_id: int | None = None) -> None:
    """Drop cached permissions for one user, or for all users if ``user_id`` is None.

    Called by ``app.db`` after role/user mutations so subsequent requests pick
    up the new state immediately rather than after the 30s TTL.
    """
    if user_id is None:
        _perm_cache.clear()
    else:
        _perm_cache.pop(user_id, None)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> str:
    """FastAPI dependency – returns username if token is valid, raises 401 otherwise.

    Accepts either:
    - A valid user JWT (via login)
    - The static service token (for agent-to-backend communication)
    """
    if os.getenv("MEDBOT_AUTH_DISABLED", "").lower() in ("1", "true", "yes"):
        return "auth-disabled"
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Check service token first (for agent-to-backend calls)
    if token == service_token():
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
    """FastAPI dependency factory — checks the JWT subject against fresh DB perms.

    Permissions are looked up via ``get_user_permissions(uid)`` (with a 30s
    cache) so role changes propagate without forcing the user to re-login.

    Usage:
        @app.get("/settings")
        def get_settings(user=Depends(require_permission("settings:read"))):
            ...
    """
    async def _check(
        credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    ) -> str:
        # Honor the test-mode auth bypass so route-level dependencies match
        # the middleware's MEDBOT_AUTH_DISABLED short-circuit.
        if os.getenv("MEDBOT_AUTH_DISABLED", "").lower() in ("1", "true", "yes"):
            return "auth-disabled"
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = credentials.credentials

        # Service token bypasses all permission checks
        if token == service_token():
            return "agent-service"

        payload = decode_access_token(token)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        username = payload.get("sub")
        uid = payload.get("uid")
        if not isinstance(username, str) or not isinstance(uid, int):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        perms = get_user_permissions(uid)
        if perms is None:
            # User was deleted — bounce them to login.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="账号不存在或已被删除",
            )
        if not _perm_matches(perms, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )

        return username
    return _check
