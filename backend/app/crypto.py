"""Symmetric encryption for secrets at rest (LLM key, email password).

Keyed off the same server secret used for JWTs (MEDBOT_AUTH_SECRET or the
auto-generated settings secret), so there is no extra key to manage. This
protects against casual leakage of the database; it is not a substitute
for filesystem permissions or a real KMS.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    from app.auth import _secret

    key = base64.urlsafe_b64encode(hashlib.sha256(b"settings-enc:" + _secret()).digest())
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _PREFIX + _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    """Decrypt a stored value. Returns legacy plaintext unchanged (pre-encryption rows)."""
    if not value or not value.startswith(_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
