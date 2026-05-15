from __future__ import annotations

import os
from typing import Any

import requests
from pydantic import ValidationError

from app.schemas import AgentChatResponse


class AgentProxyError(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def get_agent_base_url() -> str:
    return os.getenv("AGENT_BASE_URL", "http://localhost:8011").rstrip("/")


def get_agent_headers() -> dict[str, str]:
    token = os.getenv("AGENT_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def forward_agent_chat(
    payload: dict[str, Any],
    *,
    http: Any = requests,
    timeout: float = 90.0,
) -> dict[str, Any]:
    url = f"{get_agent_base_url()}/agent/chat"
    post_kwargs: dict[str, Any] = {"json": payload, "timeout": timeout}
    headers = get_agent_headers()
    if headers:
        post_kwargs["headers"] = headers

    try:
        response = http.post(url, **post_kwargs)
    except requests.Timeout as exc:
        raise AgentProxyError(status_code=504, detail=f"Agent sidecar timed out at {url}") from exc
    except requests.RequestException as exc:
        raise AgentProxyError(status_code=503, detail=f"Agent sidecar unavailable at {url}") from exc

    if response.status_code >= 500:
        raise AgentProxyError(status_code=502, detail=f"Agent sidecar failed with {response.status_code}")
    if response.status_code >= 400:
        raise AgentProxyError(status_code=response.status_code, detail=response.text)

    try:
        data = response.json()
    except ValueError as exc:
        raise AgentProxyError(status_code=502, detail="Agent sidecar returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise AgentProxyError(status_code=502, detail="Agent sidecar returned an invalid chat payload")
    data = {**data, "events": data.get("events", [])}
    try:
        return AgentChatResponse.model_validate(data).model_dump()
    except ValidationError as exc:
        raise AgentProxyError(status_code=502, detail="Agent sidecar returned an invalid chat payload") from exc


def forward_agent_chat_stream(
    payload: dict[str, Any],
    *,
    http: Any = requests,
    timeout: float = 90.0,
) -> Any:
    url = f"{get_agent_base_url()}/agent/chat/stream"
    post_kwargs: dict[str, Any] = {"json": payload, "timeout": timeout, "stream": True}
    headers = get_agent_headers()
    if headers:
        post_kwargs["headers"] = headers

    try:
        response = http.post(url, **post_kwargs)
    except requests.Timeout as exc:
        raise AgentProxyError(status_code=504, detail=f"Agent sidecar timed out at {url}") from exc
    except requests.RequestException as exc:
        raise AgentProxyError(status_code=503, detail=f"Agent sidecar unavailable at {url}") from exc

    if response.status_code >= 500:
        response.close()
        raise AgentProxyError(status_code=502, detail=f"Agent sidecar failed with {response.status_code}")
    if response.status_code >= 400:
        detail = response.text
        response.close()
        raise AgentProxyError(status_code=response.status_code, detail=detail)

    def chunks() -> Any:
        try:
            try:
                for chunk in response.iter_content(chunk_size=None):
                    if chunk:
                        yield chunk
            except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError):
                return
        finally:
            response.close()

    return chunks()
