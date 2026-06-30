"""Authentication and RBAC for the Medbot overseas pipeline.

Self-contained (stdlib only) so it adds no install friction:

- Passwords: PBKDF2-HMAC-SHA256 with a per-user salt.
- Tokens: compact JWT-style HS256 tokens signed with an auto-generated secret
  persisted in the settings table.
- Authorization: operation-level permissions (see PERMISSIONS) grouped into
  custom roles. A user's effective permissions are the union of their roles'
  permissions; superadmins implicitly hold every permission.

A service token (env MEDBOT_SERVICE_TOKEN) lets trusted backend callers — the
Pi agent sidecar — authenticate as a service principal with all permissions,
without a user account.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field

from fastapi import Header, HTTPException

# ── Permission catalog ────────────────────────────────────────────────────────
# The fixed set of operation-level permissions. Custom roles are built by
# selecting a subset of these keys. Keep in sync with the frontend admin UI.

PERMISSIONS: list[dict[str, str]] = [
    {"key": "leads.view", "group": "线索", "label": "查看线索", "description": "浏览线索库、线索历史与指标"},
    {"key": "leads.search", "group": "线索", "label": "搜索入库", "description": "实时网页搜索、抓取并入库线索"},
    {"key": "leads.edit", "group": "线索", "label": "新增/编辑线索", "description": "手动添加、修改状态或备注"},
    {"key": "leads.delete", "group": "线索", "label": "删除线索", "description": "删除单条或批量删除线索"},
    {"key": "outreach.view", "group": "触达", "label": "查看触达/草稿", "description": "预览邮件、查看草稿列表"},
    {"key": "outreach.create", "group": "触达", "label": "生成触达记录", "description": "为线索生成邮件草稿/记录"},
    {"key": "outreach.send", "group": "触达", "label": "发送/批准邮件", "description": "批准草稿并真实发送邮件"},
    {"key": "replies.analyze", "group": "回复", "label": "分析回复/同步", "description": "理解回复意向、同步收件箱"},
    {"key": "agent.use", "group": "Agent", "label": "使用 Agent", "description": "与 Agent 对话并调用业务工具"},
    {"key": "agent.config", "group": "Agent", "label": "配置 Agent", "description": "设置 provider、模型与 API key"},
    {"key": "settings.manage", "group": "系统", "label": "系统设置", "description": "邮箱、同步、自动发送等配置"},
    {"key": "users.manage", "group": "系统", "label": "用户与角色管理", "description": "管理用户、自定义角色与权限"},
]

PERMISSION_KEYS: frozenset[str] = frozenset(p["key"] for p in PERMISSIONS)


# ── Default roles seeded on first run (editable, not deletable) ───────────────

DEFAULT_ROLES: list[dict[str, object]] = [
    {
        "name": "管理员",
        "description": "全部权限",
        "permissions": sorted(PERMISSION_KEYS),
    },
    {
        "name": "操作员",
        "description": "日常获客与触达，不含系统/用户配置",
        "permissions": [
            "leads.view", "leads.search", "leads.edit", "leads.delete",
            "outreach.view", "outreach.create", "outreach.send",
            "replies.analyze", "agent.use",
        ],
    },
    {
        "name": "只读",
        "description": "仅查看线索与触达",
        "permissions": ["leads.view", "outreach.view"],
    },
]

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


# ── Principal ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Principal:
    """The authenticated caller for a request."""

    user_id: int | None
    username: str
    permissions: frozenset[str]
    is_superadmin: bool = False
    is_service: bool = False

    def has(self, permission: str) -> bool:
        return self.is_superadmin or self.is_service or permission in self.permissions


# ── Password hashing (PBKDF2-HMAC-SHA256) ─────────────────────────────────────

_PBKDF2_ROUNDS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds_s, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        rounds = int(rounds_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


# ── Tokens (compact JWT, HS256) ───────────────────────────────────────────────

TOKEN_TTL_SECONDS = 12 * 3600


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _secret() -> bytes:
    """Return the signing secret, generating and persisting one on first use."""
    from app.db import get_setting, set_setting

    env_secret = os.getenv("MEDBOT_AUTH_SECRET", "").strip()
    if env_secret:
        return env_secret.encode("utf-8")
    stored = get_setting("auth_secret", "")
    if not stored:
        stored = secrets.token_hex(32)
        set_setting("auth_secret", stored)
    return stored.encode("utf-8")


def create_token(*, user_id: int, username: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"sub": user_id, "username": username, "iat": now, "exp": now + ttl}
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    segments.append(_b64url(signature))
    return ".".join(segments)


def decode_token(token: str) -> dict | None:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


# ── Service token ─────────────────────────────────────────────────────────────

def _service_token() -> str:
    return os.getenv("MEDBOT_SERVICE_TOKEN", "").strip()


def _service_principal() -> Principal:
    return Principal(
        user_id=None,
        username="service",
        permissions=PERMISSION_KEYS,
        is_superadmin=False,
        is_service=True,
    )


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def _principal_from_headers(authorization: str | None, x_service_token: str | None) -> Principal | None:
    svc = _service_token()
    if svc and x_service_token and hmac.compare_digest(x_service_token, svc):
        return _service_principal()
    if svc and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if hmac.compare_digest(token, svc):
            return _service_principal()

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        payload = decode_token(token)
        if payload is None:
            return None
        from app.db import get_user_principal

        return get_user_principal(int(payload["sub"]))
    return None


def get_current_principal(
    authorization: str | None = Header(default=None),
    x_service_token: str | None = Header(default=None),
) -> Principal:
    """FastAPI dependency: resolve and require an authenticated principal."""
    principal = _principal_from_headers(authorization, x_service_token)
    if principal is None:
        raise HTTPException(status_code=401, detail="未认证或登录已过期，请重新登录")
    return principal


# ── Login brute-force protection (in-memory) ──────────────────────────────────

_LOGIN_MAX_FAILURES = 5
_LOGIN_WINDOW_SECONDS = 900  # 15 min
_login_failures: dict[str, list[float]] = {}


def _prune(key: str, now: float) -> list[float]:
    recent = [t for t in _login_failures.get(key, []) if now - t < _LOGIN_WINDOW_SECONDS]
    if recent:
        _login_failures[key] = recent
    else:
        _login_failures.pop(key, None)
    return recent


def login_locked_out(key: str) -> int:
    """Return seconds remaining in lockout, or 0 if not locked out."""
    now = time.time()
    recent = _prune(key, now)
    if len(recent) >= _LOGIN_MAX_FAILURES:
        return max(1, int(_LOGIN_WINDOW_SECONDS - (now - recent[0])))
    return 0


def record_login_failure(key: str) -> None:
    now = time.time()
    recent = _prune(key, now)
    recent.append(now)
    _login_failures[key] = recent


def clear_login_failures(key: str) -> None:
    _login_failures.pop(key, None)


def require(*permissions: str):
    """Return a dependency that requires ALL of the given permissions."""

    def _dep(
        authorization: str | None = Header(default=None),
        x_service_token: str | None = Header(default=None),
    ) -> Principal:
        principal = _principal_from_headers(authorization, x_service_token)
        if principal is None:
            raise HTTPException(status_code=401, detail="未认证或登录已过期，请重新登录")
        for perm in permissions:
            if not principal.has(perm):
                raise HTTPException(status_code=403, detail=f"缺少权限：{perm}")
        return principal

    return _dep
