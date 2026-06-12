from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services import CandidateLead, RenderedEmail, ReplyAnalysis


def get_db_path() -> Path:
    configured = os.getenv("MEDBOT_DB_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "medbot-demo.db"


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(get_db_path(), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                region TEXT NOT NULL,
                country TEXT NOT NULL,
                website TEXT NOT NULL,
                contact_name TEXT NOT NULL,
                email TEXT NOT NULL,
                category TEXT NOT NULL,
                match_reason TEXT NOT NULL,
                source TEXT NOT NULL,
                score INTEGER NOT NULL,
                status TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS outreach_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                sent_to TEXT NOT NULL,
                region TEXT NOT NULL,
                status TEXT NOT NULL,
                message_id TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            );

            CREATE TABLE IF NOT EXISTS reply_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER,
                reply_text TEXT NOT NULL,
                intent TEXT NOT NULL,
                confidence REAL NOT NULL,
                summary TEXT NOT NULL,
                next_action TEXT NOT NULL,
                requires_human INTEGER NOT NULL,
                message_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            """
        )
        # Migration: add message_id column if upgrading from older schema
        try:
            connection.execute(
                "ALTER TABLE outreach_events ADD COLUMN message_id TEXT NOT NULL DEFAULT ''"
            )
        except Exception:
            pass  # column already exists
        try:
            connection.execute(
                "ALTER TABLE reply_analyses ADD COLUMN message_id TEXT NOT NULL DEFAULT ''"
            )
        except Exception:
            pass  # column already exists
        try:
            connection.execute(
                "ALTER TABLE outreach_events ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
            )
        except Exception:
            pass  # column already exists


def insert_lead(lead: CandidateLead) -> dict[str, Any]:
    now = _now()
    payload = asdict(lead) | {"created_at": now, "updated_at": now}
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO leads (
                company_name, region, country, website, contact_name, email, category,
                match_reason, source, score, status, notes, created_at, updated_at
            )
            VALUES (
                :company_name, :region, :country, :website, :contact_name, :email, :category,
                :match_reason, :source, :score, :status, :notes, :created_at, :updated_at
            )
            """,
            payload,
        )
        return get_lead(cursor.lastrowid, connection=connection)


_SORTABLE_COLUMNS = {
    "company_name", "score", "category", "email", "source",
    "country", "region", "status", "id",
}

def list_leads(
    *,
    region: str | None = None,
    status: str | None = None,
    q: str | None = None,
    sort: str = "id",
    order: str = "desc",
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: dict[str, Any] = {}
    if region:
        filters.append("region = :region")
        params["region"] = region
    if status:
        filters.append("status = :status")
        params["status"] = status
    if q:
        filters.append(
            "(company_name LIKE :q OR email LIKE :q OR country LIKE :q OR category LIKE :q)"
        )
        params["q"] = f"%{q}%"

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    sort_col = sort if sort in _SORTABLE_COLUMNS else "id"
    sort_dir = "DESC" if order.lower() == "desc" else "ASC"
    with connect() as connection:
        rows = connection.execute(
            f"""SELECT l.*,
                (SELECT COUNT(*) FROM reply_analyses WHERE lead_id = l.id) AS reply_count
            FROM leads l
            {where} ORDER BY {sort_col} {sort_dir}, l.id DESC""",
            params,
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_lead(
    lead_id: int,
    *,
    connection: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    owns_connection = connection is None
    if connection is None:
        connection = connect()
    try:
        row = connection.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        if owns_connection:
            connection.close()


def update_lead(
    lead_id: int,
    *,
    status: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    current = get_lead(lead_id)
    if current is None:
        return None

    updated_status = status if status is not None else current["status"]
    updated_notes = notes if notes is not None else current["notes"]
    with connect() as connection:
        connection.execute(
            """
            UPDATE leads
            SET status = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (updated_status, updated_notes, _now(), lead_id),
        )
        return get_lead(lead_id, connection=connection)


def insert_outreach_event(
    lead_id: int,
    email: RenderedEmail,
    *,
    status: str = "recorded",
    message_id: str = "",
    source: str = "manual",
) -> dict[str, Any]:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO outreach_events (lead_id, subject, body, sent_to, region, status, message_id, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (lead_id, email.subject, email.body, email.sent_to, email.region, status, message_id, source, _now()),
        )
        if status == "sent":
            connection.execute(
                "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
                ("emailed", _now(), lead_id),
            )
        row = connection.execute(
            "SELECT * FROM outreach_events WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return _row_to_dict(row)


def insert_reply_analysis(
    *,
    lead_id: int | None,
    reply_text: str,
    analysis: ReplyAnalysis,
    message_id: str = "",
) -> dict[str, Any]:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO reply_analyses (
                lead_id, reply_text, intent, confidence, summary, next_action,
                requires_human, message_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead_id,
                reply_text,
                analysis.intent,
                analysis.confidence,
                analysis.summary,
                analysis.next_action,
                int(analysis.requires_human),
                message_id,
                _now(),
            ),
        )
        row = connection.execute(
            "SELECT * FROM reply_analyses WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    result = _row_to_dict(row)
    result["requires_human"] = bool(result["requires_human"])
    return result


def list_outreach_events(lead_id: int) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM outreach_events WHERE lead_id = ? ORDER BY id DESC",
            (lead_id,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_reply_analyses(lead_id: int) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM reply_analyses WHERE lead_id = ? ORDER BY id DESC",
            (lead_id,),
        ).fetchall()
    results = [_row_to_dict(row) for row in rows]
    for r in results:
        r["requires_human"] = bool(r["requires_human"])
    return results


def list_draft_events() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT e.*, l.company_name, l.email AS lead_email, l.country
            FROM outreach_events e
            JOIN leads l ON e.lead_id = l.id
            WHERE e.status = 'draft'
            ORDER BY e.created_at DESC
            """
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def approve_outreach_event(event_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM outreach_events WHERE id = ? AND status = 'draft'",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        connection.execute(
            "UPDATE outreach_events SET status = ?, message_id = ? WHERE id = ?",
            ("sent", "", event_id),
        )
        connection.execute(
            "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
            ("emailed", _now(), row["lead_id"]),
        )
        updated = connection.execute(
            "SELECT * FROM outreach_events WHERE id = ?", (event_id,)
        ).fetchone()
        return _row_to_dict(updated)


def reject_outreach_event(event_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM outreach_events WHERE id = ? AND status = 'draft'",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        connection.execute(
            "UPDATE outreach_events SET status = 'rejected' WHERE id = ?",
            (event_id,),
        )
        updated = connection.execute(
            "SELECT * FROM outreach_events WHERE id = ?", (event_id,)
        ).fetchone()
        return _row_to_dict(updated)


def delete_lead(lead_id: int) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        if cursor.rowcount == 0:
            return False
        connection.execute("DELETE FROM outreach_events WHERE lead_id = ?", (lead_id,))
        connection.execute("DELETE FROM reply_analyses WHERE lead_id = ?", (lead_id,))
        return True


def metrics() -> dict[str, int]:
    with connect() as connection:
        total_leads = connection.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        interested = connection.execute(
            "SELECT COUNT(*) FROM leads WHERE status = 'interested'"
        ).fetchone()[0]
        sent = connection.execute("SELECT COUNT(*) FROM outreach_events").fetchone()[0]
        human_review = connection.execute(
            "SELECT COUNT(*) FROM leads WHERE status = 'human_review'"
        ).fetchone()[0]
    return {
        "total_leads": total_leads,
        "interested_leads": interested,
        "sent_emails": sent,
        "human_review": human_review,
    }


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


# ── Settings ───────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with connect() as connection:
        row = connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_all_settings() -> dict[str, str]:
    with connect() as connection:
        rows = connection.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


# ── Helpers ────────────────────────────────────────────

def _now() -> str:
    return datetime.now(UTC).isoformat()
