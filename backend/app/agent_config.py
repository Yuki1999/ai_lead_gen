from __future__ import annotations

import os
import time
from pathlib import Path

import requests


PROVIDER_API_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

PROVIDER_API_BASE = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
}

DEFAULT_MODEL_BY_PROVIDER = {
    "openai": "gpt-5-mini",
    "deepseek": "deepseek-v4-pro",
}


def agent_config_status(*, restart_required: bool = False) -> dict[str, object]:
    values = _read_env_values(_agent_env_path())
    provider_name = _provider_name(values)
    api_key_env = _api_key_env_name(provider_name)
    api_key = values.get(api_key_env, "")
    openai_api_key = values.get("OPENAI_API_KEY", "")
    backend_base_url = (values.get("BACKEND_BASE_URL") or "http://localhost:8000").rstrip("/")
    api_base_url = values.get("PI_API_BASE_URL", "").strip().rstrip("/")

    return {
        "provider_name": provider_name,
        "has_api_key": bool(api_key.strip()),
        "api_key_preview": _mask_secret(api_key),
        "has_openai_api_key": bool(openai_api_key.strip()),
        "openai_api_key_preview": _mask_secret(openai_api_key),
        "model_name": values.get("PI_MODEL") or DEFAULT_MODEL_BY_PROVIDER.get(provider_name, "gpt-5-mini"),
        "api_base_url": api_base_url,
        "backend_base_url": backend_base_url,
        "agent_env_path": str(_agent_env_path()),
        "restart_required": restart_required,
    }


def update_agent_config(
    *,
    provider_name: str | None = None,
    api_key: str | None = None,
    openai_api_key: str | None = None,
    model_name: str | None = None,
    api_base_url: str | None = None,
    backend_base_url: str | None = None,
) -> dict[str, object]:
    updates: dict[str, str] = {}
    current_values = _read_env_values(_agent_env_path())
    provider = _normalize_provider(provider_name) or _provider_name(current_values)

    if provider_name is not None and provider_name.strip():
        updates["PI_PROVIDER"] = provider
    if api_key is not None and api_key.strip():
        updates[_api_key_env_name(provider)] = api_key.strip()
    elif openai_api_key is not None and openai_api_key.strip():
        provider = "openai"
        updates["PI_PROVIDER"] = provider
        updates["OPENAI_API_KEY"] = openai_api_key.strip()
    if model_name is not None and model_name.strip():
        updates["PI_MODEL"] = model_name.strip()
    if api_base_url is not None:
        updates["PI_API_BASE_URL"] = api_base_url.strip().rstrip("/")
    if backend_base_url is not None and backend_base_url.strip():
        updates["BACKEND_BASE_URL"] = backend_base_url.strip().rstrip("/")

    if updates:
        _write_env_updates(_agent_env_path(), updates)

    return agent_config_status(restart_required=True)


def _provider_name(values: dict[str, str]) -> str:
    configured = _normalize_provider(values.get("PI_PROVIDER"))
    if configured:
        return configured

    model_name = values.get("PI_MODEL", "")
    if model_name.startswith("deepseek") or values.get("DEEPSEEK_API_KEY"):
        return "deepseek"

    return "openai"


def _normalize_provider(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    return normalized or None


def _api_key_env_name(provider_name: str) -> str:
    return PROVIDER_API_KEY_ENV.get(
        provider_name,
        f"{provider_name.upper().replace('-', '_')}_API_KEY",
    )


def _agent_env_path() -> Path:
    configured_path = os.getenv("AGENT_ENV_PATH")
    if configured_path:
        return Path(configured_path).expanduser().resolve()

    project_root = Path(__file__).resolve().parents[2]
    return project_root / "agent" / ".env"


def _read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf8").splitlines():
        key, value = _parse_env_line(raw_line)
        if key:
            values[key] = value
    return values


def _write_env_updates(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf8").splitlines() if path.exists() else []
    seen: set[str] = set()
    next_lines: list[str] = []

    for line in lines:
        key, _ = _parse_env_line(line)
        if key in updates:
            next_lines.append(f"{key}={_format_env_value(updates[key])}")
            seen.add(key)
        else:
            next_lines.append(line)

    for key in updates:
        if key not in seen:
            next_lines.append(f"{key}={_format_env_value(updates[key])}")

    path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf8")


def _parse_env_line(line: str) -> tuple[str | None, str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None, ""
    if stripped.startswith("export "):
        stripped = stripped[7:].strip()

    separator = stripped.find("=")
    if separator <= 0:
        return None, ""

    key = stripped[:separator].strip()
    value = stripped[separator + 1 :].strip()
    if not key.replace("_", "").isalnum() or key[0].isdigit():
        return None, ""

    return key, _parse_env_value(value)


def _parse_env_value(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    comment_index = value.find(" #")
    return value[:comment_index].rstrip() if comment_index >= 0 else value


def _format_env_value(value: str) -> str:
    if not value or any(character.isspace() for character in value) or "#" in value:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _mask_secret(value: str) -> str | None:
    secret = value.strip()
    if not secret:
        return None
    if len(secret) <= 7:
        return "***"
    return f"{secret[:3]}...{secret[-4:]}"


def test_agent_connection(
    *,
    provider_name: str,
    api_key: str,
    model_name: str,
    api_base_url: str | None = None,
) -> dict[str, object]:
    """Test the AI provider connection directly by sending a minimal chat request."""
    provider = provider_name.strip().lower()
    custom_base = (api_base_url or "").strip().rstrip("/") if api_base_url else ""
    api_base = custom_base or PROVIDER_API_BASE.get(provider)
    if not api_base:
        return {
            "ok": False,
            "latency_ms": 0,
            "provider": provider,
            "model": model_name.strip(),
            "message": f"Unsupported provider: {provider_name}",
            "error": f"Supported providers: {', '.join(PROVIDER_API_BASE.keys())}",
        }

    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model_name.strip(),
        "messages": [
            {"role": "user", "content": "Hi, respond with just 'ok'."},
        ],
        "max_tokens": 5,
        "temperature": 0,
    }

    start = time.monotonic()
    try:
        response = requests.post(url, json=body, headers=headers, timeout=15.0)
        latency_ms = int((time.monotonic() - start) * 1000)

        if response.status_code == 200:
            return {
                "ok": True,
                "latency_ms": latency_ms,
                "provider": provider,
                "model": model_name.strip(),
                "message": "连接成功",
                "error": None,
            }

        # Try to extract error detail from response
        error_detail = ""
        try:
            error_body = response.json()
            error_detail = error_body.get("error", {}).get("message", "") or response.text[:300]
        except Exception:
            error_detail = response.text[:300]

        return {
            "ok": False,
            "latency_ms": latency_ms,
            "provider": provider,
            "model": model_name.strip(),
            "message": f"API 返回 {response.status_code}",
            "error": error_detail or f"HTTP {response.status_code}",
        }
    except requests.Timeout:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "provider": provider,
            "model": model_name.strip(),
            "message": "连接超时",
            "error": "Request timed out after 15 seconds",
        }
    except requests.ConnectionError:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "provider": provider,
            "model": model_name.strip(),
            "message": "无法连接到 API 服务器",
            "error": "Connection failed — check network or API base URL",
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "provider": provider,
            "model": model_name.strip(),
            "message": "测试失败",
            "error": str(exc),
        }
