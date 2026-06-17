from __future__ import annotations

import logging
import os
import secrets
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services import CandidateLead, RenderedEmail, ReplyAnalysis

_logger = logging.getLogger("medbot.db")


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

            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                permissions TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (role_id) REFERENCES roles(id)
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

        # Seed default admin role and user (idempotent).
        # Admin gets the full wildcard so newly added permissions are picked up
        # automatically without a migration.
        import json
        all_perms = json.dumps(["*"])
        now = _now()
        row = connection.execute("SELECT id FROM roles WHERE name = 'admin'").fetchone()
        if not row:
            connection.execute(
                "INSERT INTO roles (name, permissions, created_at) VALUES ('admin', ?, ?)",
                (all_perms, now),
            )
        row = connection.execute(
            "SELECT id FROM users WHERE username = 'microport_admin'"
        ).fetchone()
        if not row:
            role_id = connection.execute(
                "SELECT id FROM roles WHERE name = 'admin'"
            ).fetchone()[0]

            # Generate or read admin password — never use a hardcoded default.
            admin_password = os.getenv("MEDBOT_ADMIN_PASSWORD")
            if not admin_password:
                admin_password = secrets.token_urlsafe(10)
                # Print to stdout so the operator can capture it on first run.
                print(
                    f"\n{'='*60}\n"
                    f"  FIRST RUN: Created admin user 'microport_admin'\n"
                    f"  Password: {admin_password}\n"
                    f"  Set MEDBOT_ADMIN_PASSWORD env var to override on next run.\n"
                    f"{'='*60}\n"
                )

            # Late import to avoid circular dependency with auth module
            from app.auth import hash_password as _hash_pw
            password_hash = _hash_pw(admin_password)
            connection.execute(
                "INSERT INTO users (username, password_hash, role_id, created_at) VALUES (?, ?, ?, ?)",
                (
                    "microport_admin",
                    password_hash,
                    role_id,
                    now,
                ),
            )


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
    limit: int | None = None,
    offset: int = 0,
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
                (SELECT COUNT(*) FROM reply_analyses WHERE lead_id = l.id) AS reply_count,
                (SELECT COUNT(*) FROM outreach_events WHERE lead_id = l.id AND status = 'draft') AS draft_count
            FROM leads l
            {where} ORDER BY {sort_col} {sort_dir}, l.id DESC
            {"LIMIT :__limit" if limit is not None else ""}
            {"OFFSET :__offset" if limit is not None else ""}""",
            {**params, **({"__limit": limit, "__offset": offset} if limit is not None else {})},
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def count_leads(
    *,
    region: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> int:
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
    with connect() as connection:
        row = connection.execute(f"SELECT COUNT(*) FROM leads {where}", params).fetchone()
    return int(row[0]) if row else 0


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
    company_name: str | None = None,
    region: str | None = None,
    country: str | None = None,
    website: str | None = None,
    contact_name: str | None = None,
    email: str | None = None,
    category: str | None = None,
    match_reason: str | None = None,
    source: str | None = None,
    score: int | None = None,
    status: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    current = get_lead(lead_id)
    if current is None:
        return None

    fields: dict[str, Any] = {
        "company_name": company_name,
        "region": region,
        "country": country,
        "website": website,
        "contact_name": contact_name,
        "email": email,
        "category": category,
        "match_reason": match_reason,
        "source": source,
        "score": score,
        "status": status,
        "notes": notes,
    }

    setters: list[str] = []
    params: list[Any] = []
    for col, val in fields.items():
        if val is not None:
            setters.append(f"{col} = ?")
            params.append(val)

    if not setters:
        return current

    params.extend([_now(), lead_id])
    with connect() as connection:
        connection.execute(
            f"UPDATE leads SET {', '.join(setters)}, updated_at = ? WHERE id = ?",
            params,
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

# ── Users ──────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT u.*, r.permissions FROM users u JOIN roles r ON u.role_id = r.id WHERE u.username = ?",
            (username,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT u.id, u.username, u.role_id, r.name AS role_name, u.created_at "
            "FROM users u JOIN roles r ON u.role_id = r.id ORDER BY u.id"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def create_user(username: str, password_hash: str, role_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        try:
            connection.execute(
                "INSERT INTO users (username, password_hash, role_id, created_at) VALUES (?, ?, ?, ?)",
                (username, password_hash, role_id, _now()),
            )
        except sqlite3.IntegrityError:
            return None  # duplicate username
        row = connection.execute(
            "SELECT u.id, u.username, u.role_id, r.name AS role_name, u.created_at "
            "FROM users u JOIN roles r ON u.role_id = r.id WHERE u.username = ?",
            (username,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def update_user(user_id: int, *, username: str | None = None,
                password_hash: str | None = None,
                role_id: int | None = None) -> dict[str, Any] | None:
    setters: list[str] = []
    params: list[Any] = []
    if username is not None:
        setters.append("username = ?")
        params.append(username)
    if password_hash is not None:
        setters.append("password_hash = ?")
        params.append(password_hash)
    if role_id is not None:
        setters.append("role_id = ?")
        params.append(role_id)
    if not setters:
        row = connection.execute(
            "SELECT u.id, u.username, u.role_id, r.name AS role_name, u.created_at "
            "FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = ?",
            (user_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    params.append(user_id)
    with connect() as connection:
        connection.execute(f"UPDATE users SET {', '.join(setters)} WHERE id = ?", params)
        row = connection.execute(
            "SELECT u.id, u.username, u.role_id, r.name AS role_name, u.created_at "
            "FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = ?",
            (user_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def delete_user(user_id: int) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return cursor.rowcount > 0


# ── Roles ──────────────────────────────────────────────────────────

def list_roles() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT r.*, (SELECT COUNT(*) FROM users WHERE role_id = r.id) AS user_count "
            "FROM roles r ORDER BY r.id"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def create_role(name: str, permissions: list[str]) -> dict[str, Any] | None:
    import json
    with connect() as connection:
        try:
            connection.execute(
                "INSERT INTO roles (name, permissions, created_at) VALUES (?, ?, ?)",
                (name, json.dumps(permissions), _now()),
            )
        except sqlite3.IntegrityError:
            return None
        row = connection.execute("SELECT * FROM roles WHERE name = ?", (name,)).fetchone()
    return _row_to_dict(row) if row else None


def update_role(role_id: int, *, name: str | None = None,
                permissions: list[str] | None = None) -> dict[str, Any] | None:
    import json
    setters: list[str] = []
    params: list[Any] = []
    if name is not None:
        setters.append("name = ?")
        params.append(name)
    if permissions is not None:
        setters.append("permissions = ?")
        params.append(json.dumps(permissions))
    if not setters:
        return None
    params.append(role_id)
    with connect() as connection:
        connection.execute(f"UPDATE roles SET {', '.join(setters)} WHERE id = ?", params)
        row = connection.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
    return _row_to_dict(row) if row else None


def delete_role(role_id: int) -> bool:
    with connect() as connection:
        # Reassign users to admin role first
        admin = connection.execute("SELECT id FROM roles WHERE name = 'admin'").fetchone()
        if admin:
            connection.execute("UPDATE users SET role_id = ? WHERE role_id = ?", (admin[0], role_id))
        cursor = connection.execute("DELETE FROM roles WHERE id = ? AND name != 'admin'", (role_id,))
    return cursor.rowcount > 0


def _now() -> str:
    return datetime.now(UTC).isoformat()
