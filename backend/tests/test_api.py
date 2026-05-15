import pytest
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app.main import create_app

    return TestClient(create_app())


def test_health_check(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_prospecting_persists_and_lists_leads(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Europe"],
                "product_keywords": ["surgical robot"],
                "max_results": 3,
                "real_search": False,
            },
        )
        listed = client.get("/leads", params={"region": "Europe"})

    assert created.status_code == 201
    assert created.json()["created_count"] == 3
    assert len(created.json()["leads"]) == 3
    assert listed.status_code == 200
    assert listed.json()["total"] == 3
    assert listed.json()["leads"][0]["region"] == "Europe"


def test_product_profile_endpoint_reads_root_assets(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/product/profile")

    payload = response.json()
    assert response.status_code == 200
    assert "SkyWalker" in payload["product_name"]
    assert payload["procedure"] == "total knee arthroplasty (TKA)"
    assert any(source.endswith(".pdf") for source in payload["source_files"])


def test_real_search_mode_uses_product_profile_and_web_search(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module
    from app.services import CandidateLead

    def fake_discover_real_prospects(**kwargs):
        assert kwargs["product_profile"].procedure == "total knee arthroplasty (TKA)"
        assert kwargs["require_email"] is True
        return [
            CandidateLead(
                company_name="Real Ortho Distribution",
                region="Europe",
                country="Europe",
                website="https://real-ortho.example",
                contact_name="Sales / Business Development",
                email="bd@real-ortho.example",
                category="orthopedic / medical device distributor",
                match_reason="Live web match for total knee arthroplasty distributor.",
                source="https://real-ortho.example",
                score=91,
            )
        ]

    monkeypatch.setattr(
        main_module,
        "discover_real_prospects",
        fake_discover_real_prospects,
        raising=False,
    )

    with TestClient(main_module.create_app()) as client:
        response = client.post(
            "/leads/search",
            json={
                "target_regions": ["Europe"],
                "product_keywords": [],
                "max_results": 1,
                "real_search": True,
                "require_email": True,
            },
        )

    payload = response.json()
    assert response.status_code == 201
    assert payload["created_count"] == 1
    assert payload["leads"][0]["company_name"] == "Real Ortho Distribution"
    assert payload["leads"][0]["email"] == "bd@real-ortho.example"
    assert payload["leads"][0]["source"] == "https://real-ortho.example"


def test_demo_email_send_records_events(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Middle East"],
                "product_keywords": ["minimally invasive robot"],
                "max_results": 1,
                "real_search": False,
            },
        )
        lead_id = created.json()["leads"][0]["id"]
        sent = client.post("/campaigns/send-demo", json={"lead_ids": [lead_id]})

    payload = sent.json()
    assert sent.status_code == 201
    assert payload["sent_count"] == 1
    assert payload["events"][0]["lead_id"] == lead_id
    assert "Middle East" in payload["events"][0]["subject"]
    assert "introductory product brief" in payload["events"][0]["body"].lower()


def test_demo_email_send_requires_discovered_email(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module
    from app.services import CandidateLead

    def fake_discover_real_prospects(**kwargs):
        return [
            CandidateLead(
                company_name="No Email Ortho",
                region="Europe",
                country="Europe",
                website="https://no-email.example",
                contact_name="Sales / Business Development",
                email="",
                category="orthopedic distributor",
                match_reason="Live web match without visible email.",
                source="https://no-email.example",
                score=71,
            )
        ]

    monkeypatch.setattr(
        main_module,
        "discover_real_prospects",
        fake_discover_real_prospects,
        raising=False,
    )

    with TestClient(main_module.create_app()) as client:
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Europe"],
                "max_results": 1,
                "real_search": True,
                "require_email": False,
            },
        )
        lead_id = created.json()["leads"][0]["id"]
        sent = client.post("/campaigns/send-demo", json={"lead_ids": [lead_id]})

    assert sent.status_code == 422
    assert "no discovered email" in sent.json()["detail"]


def test_reply_analysis_updates_lead_status(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Southeast Asia"],
                "product_keywords": ["hospital robotics"],
                "max_results": 1,
                "real_search": False,
            },
        )
        lead_id = created.json()["leads"][0]["id"]
        analysis = client.post(
            "/replies/analyze",
            json={
                "lead_id": lead_id,
                "reply_text": "We are interested. Please send product details and certificates.",
            },
        )
        listed = client.get("/leads")

    assert analysis.status_code == 201
    assert analysis.json()["intent"] == "interested"
    assert analysis.json()["requires_human"] is False
    assert listed.json()["leads"][0]["status"] == "interested"


def test_complex_reply_sets_human_review_status(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Latin America"],
                "product_keywords": ["surgical robot"],
                "max_results": 1,
                "real_search": False,
            },
        )
        lead_id = created.json()["leads"][0]["id"]
        analysis = client.post(
            "/replies/analyze",
            json={
                "lead_id": lead_id,
                "reply_text": "We need exclusive distribution, regulatory ownership, and contract review.",
            },
        )
        lead = client.get("/leads").json()["leads"][0]

    assert analysis.status_code == 201
    assert analysis.json()["requires_human"] is True
    assert lead["status"] == "human_review"


def test_update_lead_status_and_notes(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/leads/search",
            json={
                "target_regions": ["Europe"],
                "product_keywords": ["surgical robot"],
                "max_results": 1,
                "real_search": False,
            },
        )
        lead_id = created.json()["leads"][0]["id"]
        updated = client.patch(
            f"/leads/{lead_id}",
            json={"status": "qualified", "notes": "Owner confirmed channel fit."},
        )

    assert updated.status_code == 200
    assert updated.json()["status"] == "qualified"
    assert updated.json()["notes"] == "Owner confirmed channel fit."


def test_source_preview_endpoint_returns_page_text_and_email_match(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module

    def fake_fetch_source_preview(url: str, email: str):
        assert url == "https://source.example/contact"
        assert email == "sales@source.example"
        return {
            "url": url,
            "title": "Source Contact",
            "text": "Contact our sales team at sales@source.example for distribution inquiries.",
            "email": email,
            "emails": ["sales@source.example"],
            "email_found": True,
        }

    monkeypatch.setattr(
        main_module,
        "fetch_source_preview",
        fake_fetch_source_preview,
        raising=False,
    )

    with TestClient(main_module.create_app()) as client:
        response = client.get(
            "/sources/preview",
            params={"url": "https://source.example/contact", "email": "sales@source.example"},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["title"] == "Source Contact"
    assert payload["email_found"] is True
    assert "sales@source.example" in payload["text"]


def test_web_search_endpoint_returns_search_results(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module
    from app.web_search import SearchResult

    def fake_search_web(query: str, *, limit: int = 8):
        assert query == "orthopedic implant distributor India"
        assert limit == 2
        return [
            SearchResult(
                title="Ortho Distributor India",
                url="https://ortho.example",
                snippet="Orthopedic implant distributor in India.",
                query=query,
            )
        ]

    monkeypatch.setattr(main_module, "search_web", fake_search_web, raising=False)

    with TestClient(main_module.create_app()) as client:
        response = client.post(
            "/web/search",
            json={"query": "orthopedic implant distributor India", "max_results": 2},
        )

    assert response.status_code == 200
    assert response.json() == {
        "query": "orthopedic implant distributor India",
        "results": [
            {
                "title": "Ortho Distributor India",
                "url": "https://ortho.example",
                "snippet": "Orthopedic implant distributor in India.",
                "query": "orthopedic implant distributor India",
            }
        ],
    }


def test_web_fetch_endpoint_returns_page_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module

    def fake_fetch_source_preview(url: str, email: str):
        assert url == "https://ortho.example/contact"
        assert email == "sales@ortho.example"
        return {
            "url": url,
            "title": "Contact Ortho",
            "text": "Contact sales@ortho.example for distribution.",
            "email": email,
            "emails": [email],
            "email_found": True,
        }

    monkeypatch.setattr(
        main_module,
        "fetch_source_preview",
        fake_fetch_source_preview,
        raising=False,
    )

    with TestClient(main_module.create_app()) as client:
        response = client.post(
            "/web/fetch",
            json={"url": "https://ortho.example/contact", "email": "sales@ortho.example"},
        )

    assert response.status_code == 200
    assert response.json()["title"] == "Contact Ortho"
    assert response.json()["email_found"] is True


def test_agent_chat_proxy_forwards_to_sidecar(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module

    def fake_forward_agent_chat(payload):
        assert payload["message"] == "Find India SkyWalker TKA distributors"
        assert payload["session_id"] is None
        return {
            "message": "Found 3 candidate distributors.",
            "session_id": "test-session",
            "events": [{"type": "tool", "name": "search_leads"}],
        }

    monkeypatch.setattr(main_module, "forward_agent_chat", fake_forward_agent_chat, raising=False)

    with TestClient(main_module.create_app()) as client:
        response = client.post(
            "/agent/chat",
            json={"message": "Find India SkyWalker TKA distributors"},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Found 3 candidate distributors."
    assert response.json()["session_id"] == "test-session"
    assert response.json()["events"][0]["name"] == "search_leads"


def test_agent_chat_stream_proxy_forwards_sse(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module

    def fake_forward_agent_chat_stream(payload):
        assert payload["message"] == "Find India SkyWalker TKA distributors"
        yield b'event: start\ndata: {"session_id":"test-session"}\n\n'
        yield b'event: delta\ndata: {"text":"Found "}\n\n'
        yield b'event: done\ndata: {"message":"Found 3","session_id":"test-session","events":[]}\n\n'

    monkeypatch.setattr(
        main_module,
        "forward_agent_chat_stream",
        fake_forward_agent_chat_stream,
        raising=False,
    )

    with TestClient(main_module.create_app()) as client:
        with client.stream(
            "POST",
            "/agent/chat/stream",
            json={"message": "Find India SkyWalker TKA distributors"},
        ) as response:
            body = response.read().decode("utf8")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: start' in body
    assert '{"text":"Found "}' in body
    assert 'event: done' in body


def test_agent_chat_proxy_reports_sidecar_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDBOT_DB_PATH", str(tmp_path / "medbot-demo.db"))
    from app import main as main_module
    from app.agent_proxy import AgentProxyError

    def fake_forward_agent_chat(payload):
        raise AgentProxyError(status_code=503, detail="Agent sidecar unavailable at http://localhost:8011")

    monkeypatch.setattr(main_module, "forward_agent_chat", fake_forward_agent_chat, raising=False)

    with TestClient(main_module.create_app()) as client:
        response = client.post("/agent/chat", json={"message": "hello"})

    assert response.status_code == 503
    assert "Agent sidecar unavailable" in response.json()["detail"]


def test_agent_config_status_masks_key_and_reads_agent_env(tmp_path, monkeypatch):
    agent_env_path = tmp_path / "agent.env"
    agent_env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=sk-test-secret-123456",
                "PI_MODEL=gpt-5-mini",
                "BACKEND_BASE_URL=http://localhost:8020",
            ]
        ),
        encoding="utf8",
    )
    monkeypatch.setenv("AGENT_ENV_PATH", str(agent_env_path))

    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/agent/config")

    payload = response.json()
    assert response.status_code == 200
    assert payload["has_openai_api_key"] is True
    assert payload["openai_api_key_preview"] == "sk-...3456"
    assert payload["provider_name"] == "openai"
    assert payload["has_api_key"] is True
    assert payload["api_key_preview"] == "sk-...3456"
    assert "secret" not in str(payload)
    assert payload["model_name"] == "gpt-5-mini"
    assert payload["backend_base_url"] == "http://localhost:8020"
    assert payload["restart_required"] is False


def test_agent_config_status_reads_deepseek_key_without_leaking_secret(tmp_path, monkeypatch):
    agent_env_path = tmp_path / "agent.env"
    agent_env_path.write_text(
        "\n".join(
            [
                "PI_PROVIDER=deepseek",
                "DEEPSEEK_API_KEY=sk-deepseek-secret-123456",
                "PI_MODEL=deepseek-v4-pro",
            ]
        ),
        encoding="utf8",
    )
    monkeypatch.setenv("AGENT_ENV_PATH", str(agent_env_path))

    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/agent/config")

    payload = response.json()
    assert response.status_code == 200
    assert payload["provider_name"] == "deepseek"
    assert payload["has_api_key"] is True
    assert payload["api_key_preview"] == "sk-...3456"
    assert "secret" not in str(payload)
    assert payload["has_openai_api_key"] is False
    assert payload["model_name"] == "deepseek-v4-pro"


def test_agent_config_update_writes_agent_env_and_preserves_other_values(tmp_path, monkeypatch):
    agent_env_path = tmp_path / "agent.env"
    agent_env_path.write_text(
        "\n".join(
            [
                "# existing sidecar settings",
                "AGENT_PORT=8011",
                "OPENAI_API_KEY=old-key",
                "PI_MODEL=gpt-5-mini",
            ]
        )
        + "\n",
        encoding="utf8",
    )
    monkeypatch.setenv("AGENT_ENV_PATH", str(agent_env_path))

    with _client(tmp_path, monkeypatch) as client:
        response = client.put(
            "/agent/config",
            json={
                "openai_api_key": "sk-new-secret-abcdef",
                "model_name": "gpt-5.5",
                "backend_base_url": "http://localhost:8020/",
            },
        )

    payload = response.json()
    content = agent_env_path.read_text(encoding="utf8")
    assert response.status_code == 200
    assert payload["has_openai_api_key"] is True
    assert payload["openai_api_key_preview"] == "sk-...cdef"
    assert payload["model_name"] == "gpt-5.5"
    assert payload["backend_base_url"] == "http://localhost:8020"
    assert payload["restart_required"] is True
    assert "# existing sidecar settings" in content
    assert "AGENT_PORT=8011" in content
    assert "OPENAI_API_KEY=sk-new-secret-abcdef" in content
    assert "PI_MODEL=gpt-5.5" in content
    assert "BACKEND_BASE_URL=http://localhost:8020" in content


def test_agent_config_update_writes_deepseek_provider_key_and_model(tmp_path, monkeypatch):
    agent_env_path = tmp_path / "agent.env"
    agent_env_path.write_text("AGENT_PORT=8011\nOPENAI_API_KEY=old-openai-key\n", encoding="utf8")
    monkeypatch.setenv("AGENT_ENV_PATH", str(agent_env_path))

    with _client(tmp_path, monkeypatch) as client:
        response = client.put(
            "/agent/config",
            json={
                "provider_name": "deepseek",
                "api_key": "sk-deepseek-new-abcdef",
                "model_name": "deepseek-v4-pro",
                "backend_base_url": "http://localhost:8020/",
            },
        )

    payload = response.json()
    content = agent_env_path.read_text(encoding="utf8")
    assert response.status_code == 200
    assert payload["provider_name"] == "deepseek"
    assert payload["has_api_key"] is True
    assert payload["api_key_preview"] == "sk-...cdef"
    assert payload["model_name"] == "deepseek-v4-pro"
    assert payload["backend_base_url"] == "http://localhost:8020"
    assert "AGENT_PORT=8011" in content
    assert "OPENAI_API_KEY=old-openai-key" in content
    assert "PI_PROVIDER=deepseek" in content
    assert "DEEPSEEK_API_KEY=sk-deepseek-new-abcdef" in content
    assert "PI_MODEL=deepseek-v4-pro" in content
    assert "BACKEND_BASE_URL=http://localhost:8020" in content


def test_agent_config_update_can_change_model_without_resending_key(tmp_path, monkeypatch):
    agent_env_path = tmp_path / "agent.env"
    agent_env_path.write_text(
        "OPENAI_API_KEY=sk-existing-secret-0000\nPI_MODEL=gpt-5-mini\n",
        encoding="utf8",
    )
    monkeypatch.setenv("AGENT_ENV_PATH", str(agent_env_path))

    with _client(tmp_path, monkeypatch) as client:
        response = client.put("/agent/config", json={"model_name": "gpt-5.4"})

    content = agent_env_path.read_text(encoding="utf8")
    assert response.status_code == 200
    assert "OPENAI_API_KEY=sk-existing-secret-0000" in content
    assert "PI_MODEL=gpt-5.4" in content


@pytest.mark.parametrize(
    "payload",
    [
        {"message": None, "session_id": "s"},
        {"message": "ok", "session_id": "s", "events": "bad"},
    ],
)
def test_forward_agent_chat_rejects_malformed_sidecar_payload(payload, monkeypatch):
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    from app.agent_proxy import AgentProxyError, forward_agent_chat

    class FakeResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return payload

    class FakeHttp:
        def post(self, url, json, timeout):
            return FakeResponse()

    with pytest.raises(AgentProxyError) as exc_info:
        forward_agent_chat({"message": "hello"}, http=FakeHttp())

    assert exc_info.value.status_code == 502
    assert "invalid chat payload" in exc_info.value.detail


def test_forward_agent_chat_uses_default_url_and_defaults_events(monkeypatch):
    monkeypatch.delenv("AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    from app.agent_proxy import forward_agent_chat

    class FakeResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return {"message": "ok", "session_id": "s"}

    class FakeHttp:
        def __init__(self):
            self.calls = []

        def post(self, url, json, timeout):
            self.calls.append((url, json, timeout))
            return FakeResponse()

    fake_http = FakeHttp()
    result = forward_agent_chat({"message": "hello", "session_id": None}, http=fake_http, timeout=12.5)

    assert fake_http.calls == [
        ("http://localhost:8011/agent/chat", {"message": "hello", "session_id": None}, 12.5)
    ]
    assert result == {"message": "ok", "session_id": "s", "events": []}


def test_forward_agent_chat_sends_authorization_header_when_token_is_configured(monkeypatch):
    monkeypatch.setenv("AGENT_TOKEN", "sidecar-secret")
    from app.agent_proxy import forward_agent_chat

    class FakeResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return {"message": "ok", "session_id": "s", "events": []}

    class FakeHttp:
        def __init__(self):
            self.headers = None

        def post(self, url, json, timeout, headers=None):
            self.headers = headers
            return FakeResponse()

    fake_http = FakeHttp()
    forward_agent_chat({"message": "hello"}, http=fake_http)

    assert fake_http.headers == {"Authorization": "Bearer sidecar-secret"}


def test_forward_agent_chat_stream_uses_stream_endpoint_and_yields_chunks(monkeypatch):
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    from app.agent_proxy import forward_agent_chat_stream

    class FakeResponse:
        status_code = 200
        text = "ok"

        def iter_content(self, chunk_size=None):
            yield b"event: delta\n"
            yield b'data: {"text":"hi"}\n\n'

        def close(self):
            self.closed = True

    class FakeHttp:
        def __init__(self):
            self.calls = []
            self.response = FakeResponse()

        def post(self, url, json, timeout, stream=False):
            self.calls.append((url, json, timeout, stream))
            return self.response

    fake_http = FakeHttp()
    chunks = list(forward_agent_chat_stream({"message": "hello"}, http=fake_http, timeout=12.5))

    assert fake_http.calls == [
        ("http://localhost:8011/agent/chat/stream", {"message": "hello"}, 12.5, True)
    ]
    assert chunks == [b"event: delta\n", b'data: {"text":"hi"}\n\n']
    assert fake_http.response.closed is True


def test_forward_agent_chat_stream_stops_cleanly_when_upstream_disconnects(monkeypatch):
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    import requests

    from app.agent_proxy import forward_agent_chat_stream

    class FakeResponse:
        status_code = 200
        text = "ok"
        closed = False

        def iter_content(self, chunk_size=None):
            yield b"event: start\n\n"
            raise requests.exceptions.ChunkedEncodingError("broken stream")

        def close(self):
            self.closed = True

    class FakeHttp:
        def __init__(self):
            self.response = FakeResponse()

        def post(self, url, json, timeout, stream=False):
            return self.response

    fake_http = FakeHttp()
    chunks = list(forward_agent_chat_stream({"message": "hello"}, http=fake_http))

    assert chunks == [b"event: start\n\n"]
    assert fake_http.response.closed is True
