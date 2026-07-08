"""Shared test setup: point the app at a disposable PostgreSQL and reset it
before every test so each case starts from a clean, freshly-seeded schema.

Provide the connection string via MEDBOT_TEST_DATABASE_URL; the default matches
the throwaway Postgres the CI/dev helper spins up on port 5433.
"""
import os

import pytest

TEST_DB_URL = os.getenv(
    "MEDBOT_TEST_DATABASE_URL",
    "postgresql://medbot:medbot@localhost:5433/medbot_test",
)


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    # Bind the app to the test database and isolate the Pi sidecar env so the
    # AI-content fallback can't resolve a real key from the project's agent/.env.
    monkeypatch.setenv("MEDBOT_DATABASE_URL", TEST_DB_URL)
    monkeypatch.setenv("AGENT_ENV_PATH", str(tmp_path / "agent.env"))
    # Legacy env some per-file fixtures still set; harmless but keep it unset so
    # nothing accidentally depends on a SQLite path.
    monkeypatch.delenv("MEDBOT_DB_PATH", raising=False)

    from app import db

    db.reset_for_tests()
    yield
