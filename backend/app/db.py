from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services import CandidateLead, RenderedEmail, ReplyAnalysis, infer_lead_type


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
                lead_type TEXT NOT NULL DEFAULT '',
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

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                is_superadmin INTEGER NOT NULL DEFAULT 0,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                permissions TEXT NOT NULL DEFAULT '[]',
                is_system INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (role_id) REFERENCES roles(id)
            );

            CREATE TABLE IF NOT EXISTS suppressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                reason TEXT NOT NULL DEFAULT 'unsubscribe',
                source TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL,
                target_type TEXT NOT NULL DEFAULT '',
                target_id TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
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
        try:
            connection.execute(
                "ALTER TABLE leads ADD COLUMN lead_type TEXT NOT NULL DEFAULT ''"
            )
        except Exception:
            pass  # column already exists
        try:
            connection.execute(
                "ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # column already exists
        try:
            connection.execute(
                "ALTER TABLE outreach_events ADD COLUMN sent_at TEXT NOT NULL DEFAULT ''"
            )
        except Exception:
            pass  # column already exists

    seed_auth()


def insert_lead(lead: CandidateLead) -> dict[str, Any]:
    now = _now()
    payload = asdict(lead) | {"created_at": now, "updated_at": now}
    # Resolve and persist lead_type at insert time instead of leaving it blank
    # and re-inferring on every email render — the classification needs to be
    # a stable, queryable column for filtering/dashboards/scoring-rule choice.
    if not str(payload.get("lead_type") or "").strip():
        payload["lead_type"] = infer_lead_type(lead)
    # Every lead-creation path constructs a CandidateLead with the "new"
    # default; apply the configured score thresholds here so a lead's initial
    # status actually reflects its score instead of always starting at "new".
    if payload["status"] == "new":
        payload["status"] = status_for_score(int(payload["score"]), lead_type=payload.get("lead_type"))
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO leads (
                company_name, region, country, website, contact_name, email, category,
                match_reason, source, score, status, notes, lead_type, created_at, updated_at
            )
            VALUES (
                :company_name, :region, :country, :website, :contact_name, :email, :category,
                :match_reason, :source, :score, :status, :notes, :lead_type, :created_at, :updated_at
            )
            """,
            payload,
        )
        return get_lead(cursor.lastrowid, connection=connection)


# Whitelist of external sort keys → SQL expressions. Values are hard-coded
# server strings, so string-interpolating them into ORDER BY is safe.
_SORT_EXPRS = {
    "id": "l.id",
    "score": "l.score",
    "company_name": "l.company_name",
    "country": "l.country",
    "region": "l.region",
    "status": "l.status",
    "category": "l.category",
    "created_at": "l.created_at",
    "updated_at": "l.updated_at",
    "reply_count": "reply_count",  # derived column, present in SELECT
}

def list_leads(
    *,
    region: str | None = None,
    status: str | None = None,
    lead_type: str | None = None,
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
    if lead_type:
        filters.append("lead_type = :lead_type")
        params["lead_type"] = lead_type
    if q:
        filters.append(
            "(company_name LIKE :q OR email LIKE :q OR country LIKE :q OR category LIKE :q)"
        )
        params["q"] = f"%{q}%"

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    sort_key = sort if sort in _SORT_EXPRS else "id"
    sort_expr = _SORT_EXPRS[sort_key]
    sort_dir = "ASC" if str(order).lower() == "asc" else "DESC"
    # Automatic secondary sort: keep results deterministic and surface newer
    # entries within ties (unless the user is already sorting by created_at/id).
    tiebreakers: list[str] = []
    if sort_key != "created_at":
        tiebreakers.append("l.created_at DESC")
    if sort_key != "id":
        tiebreakers.append("l.id DESC")
    order_clause = f"{sort_expr} {sort_dir}"
    if tiebreakers:
        order_clause += ", " + ", ".join(tiebreakers)
    with connect() as connection:
        rows = connection.execute(
            f"""SELECT l.*,
                (SELECT COUNT(*) FROM reply_analyses WHERE lead_id = l.id) AS reply_count
            FROM leads l
            {where} ORDER BY {order_clause}""",
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
    lead_type: str | None = None,
) -> dict[str, Any] | None:
    current = get_lead(lead_id)
    if current is None:
        return None

    updated_status = status if status is not None else current["status"]
    updated_notes = notes if notes is not None else current["notes"]
    updated_lead_type = lead_type if lead_type is not None else current["lead_type"]
    with connect() as connection:
        connection.execute(
            """
            UPDATE leads
            SET status = ?, notes = ?, lead_type = ?, updated_at = ?
            WHERE id = ?
            """,
            (updated_status, updated_notes, updated_lead_type, _now(), lead_id),
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


def enqueue_outreach(lead_id: int, email: RenderedEmail, *, source: str = "manual") -> dict[str, Any]:
    """Queue an email for throttled background delivery (status 'queued')."""
    return insert_outreach_event(lead_id, email, status="queued", source=source)


def list_queued_events(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM outreach_events WHERE status = 'queued' ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def count_queued() -> int:
    with connect() as connection:
        return int(connection.execute(
            "SELECT COUNT(*) FROM outreach_events WHERE status = 'queued'"
        ).fetchone()[0])


def count_sent_since(iso_since: str, *, domain: str | None = None) -> int:
    sql = "SELECT COUNT(*) FROM outreach_events WHERE status = 'sent' AND sent_at >= ?"
    params: list[Any] = [iso_since]
    if domain:
        sql += " AND lower(sent_to) LIKE ?"
        params.append(f"%@{domain.lower()}")
    with connect() as connection:
        return int(connection.execute(sql, params).fetchone()[0])


def last_sent_at() -> str:
    with connect() as connection:
        row = connection.execute(
            "SELECT MAX(sent_at) FROM outreach_events WHERE status = 'sent'"
        ).fetchone()
    return row[0] or ""


def mark_outreach_sent(event_id: int, *, message_id: str = "") -> dict[str, Any] | None:
    now = _now()
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM outreach_events WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        connection.execute(
            "UPDATE outreach_events SET status = 'sent', message_id = ?, sent_at = ? WHERE id = ?",
            (message_id, now, event_id),
        )
        connection.execute(
            "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
            ("emailed", now, row["lead_id"]),
        )
        updated = connection.execute(
            "SELECT * FROM outreach_events WHERE id = ?", (event_id,)
        ).fetchone()
    return _row_to_dict(updated)


def mark_outreach_status(event_id: int, status: str, *, error: str = "") -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE outreach_events SET status = ? WHERE id = ?", (status, event_id)
        )


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
        distributor_leads = connection.execute(
            "SELECT COUNT(*) FROM leads WHERE lead_type = 'distributor'"
        ).fetchone()[0]
        kol_leads = connection.execute(
            "SELECT COUNT(*) FROM leads WHERE lead_type = 'kol'"
        ).fetchone()[0]
        distributor_qualified = connection.execute(
            "SELECT COUNT(*) FROM leads WHERE lead_type = 'distributor' AND status = 'qualified'"
        ).fetchone()[0]
        kol_qualified = connection.execute(
            "SELECT COUNT(*) FROM leads WHERE lead_type = 'kol' AND status = 'qualified'"
        ).fetchone()[0]
    return {
        "total_leads": total_leads,
        "interested_leads": interested,
        "sent_emails": sent,
        "human_review": human_review,
        "distributor_leads": distributor_leads,
        "kol_leads": kol_leads,
        "distributor_qualified": distributor_qualified,
        "kol_qualified": kol_qualified,
    }


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


# ── Auth: users, roles, RBAC ───────────────────────────

def seed_auth() -> None:
    """Seed default roles and a superadmin on first run (idempotent)."""
    from app.auth import (
        DEFAULT_ADMIN_PASSWORD,
        DEFAULT_ADMIN_USERNAME,
        DEFAULT_ROLES,
        hash_password,
    )

    with connect() as connection:
        existing_roles = {
            row["name"] for row in connection.execute("SELECT name FROM roles").fetchall()
        }
        for role in DEFAULT_ROLES:
            if role["name"] in existing_roles:
                continue
            connection.execute(
                """
                INSERT INTO roles (name, description, permissions, is_system, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (
                    role["name"],
                    role["description"],
                    json.dumps(role["permissions"]),
                    _now(),
                    _now(),
                ),
            )

        user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            connection.execute(
                """
                INSERT INTO users (username, password_hash, display_name, is_active, is_superadmin, must_change_password, created_at, updated_at)
                VALUES (?, ?, ?, 1, 1, 1, ?, ?)
                """,
                (
                    DEFAULT_ADMIN_USERNAME,
                    hash_password(DEFAULT_ADMIN_PASSWORD),
                    "系统管理员",
                    _now(),
                    _now(),
                ),
            )
            admin_id = connection.execute(
                "SELECT id FROM users WHERE username = ?", (DEFAULT_ADMIN_USERNAME,)
            ).fetchone()["id"]
            admin_role = connection.execute(
                "SELECT id FROM roles WHERE name = ?", ("管理员",)
            ).fetchone()
            if admin_role:
                connection.execute(
                    "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
                    (admin_id, admin_role["id"]),
                )


def _role_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    try:
        data["permissions"] = json.loads(data.get("permissions") or "[]")
    except (ValueError, TypeError):
        data["permissions"] = []
    data["is_system"] = bool(data.get("is_system"))
    return data


def list_roles() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT r.*, (SELECT COUNT(*) FROM user_roles WHERE role_id = r.id) AS user_count
            FROM roles r ORDER BY r.id
            """
        ).fetchall()
    return [_role_to_dict(row) for row in rows]


def get_role(role_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
    return _role_to_dict(row) if row else None


def get_role_by_name(name: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM roles WHERE name = ?", (name,)).fetchone()
    return _role_to_dict(row) if row else None


def create_role(*, name: str, description: str, permissions: list[str]) -> dict[str, Any]:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO roles (name, description, permissions, is_system, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (name, description, json.dumps(permissions), _now(), _now()),
        )
        row = connection.execute(
            "SELECT * FROM roles WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return _role_to_dict(row)


def update_role(
    role_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    permissions: list[str] | None = None,
) -> dict[str, Any] | None:
    current = get_role(role_id)
    if current is None:
        return None
    new_name = name if name is not None else current["name"]
    new_desc = description if description is not None else current["description"]
    new_perms = permissions if permissions is not None else current["permissions"]
    with connect() as connection:
        connection.execute(
            "UPDATE roles SET name = ?, description = ?, permissions = ?, updated_at = ? WHERE id = ?",
            (new_name, new_desc, json.dumps(new_perms), _now(), role_id),
        )
    return get_role(role_id)


def delete_role(role_id: int) -> bool:
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM roles WHERE id = ? AND is_system = 0", (role_id,)
        )
        if cursor.rowcount == 0:
            return False
        connection.execute("DELETE FROM user_roles WHERE role_id = ?", (role_id,))
        return True


def _user_to_dict(row: sqlite3.Row, *, roles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    data = dict(row)
    data.pop("password_hash", None)
    data["is_active"] = bool(data.get("is_active"))
    data["is_superadmin"] = bool(data.get("is_superadmin"))
    data["must_change_password"] = bool(data.get("must_change_password"))
    if roles is not None:
        data["roles"] = [{"id": r["id"], "name": r["name"]} for r in roles]
        if data["is_superadmin"]:
            from app.auth import PERMISSION_KEYS

            data["permissions"] = sorted(PERMISSION_KEYS)
        else:
            perms: set[str] = set()
            for r in roles:
                perms.update(r["permissions"])
            data["permissions"] = sorted(perms)
    return data


def _roles_for_user(connection: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT r.* FROM roles r
        JOIN user_roles ur ON ur.role_id = r.id
        WHERE ur.user_id = ? ORDER BY r.id
        """,
        (user_id,),
    ).fetchall()
    return [_role_to_dict(row) for row in rows]


def list_users() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [
            _user_to_dict(row, roles=_roles_for_user(connection, row["id"])) for row in rows
        ]


def get_user(user_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return _user_to_dict(row, roles=_roles_for_user(connection, user_id))


def get_user_auth_row(username: str) -> dict[str, Any] | None:
    """Return the raw user row (including password_hash) for login verification."""
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    return dict(row) if row else None


def get_user_principal(user_id: int):
    """Build an auth.Principal for an active user, or None if missing/inactive."""
    from app.auth import Principal

    with connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not row["is_active"]:
            return None
        roles = _roles_for_user(connection, user_id)

    perms: set[str] = set()
    for r in roles:
        perms.update(r["permissions"])
    return Principal(
        user_id=int(row["id"]),
        username=str(row["username"]),
        permissions=frozenset(perms),
        is_superadmin=bool(row["is_superadmin"]),
    )


def create_user(
    *,
    username: str,
    password: str,
    display_name: str = "",
    is_active: bool = True,
    is_superadmin: bool = False,
    role_ids: list[int] | None = None,
    must_change_password: bool = True,
) -> dict[str, Any]:
    from app.auth import hash_password

    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (username, password_hash, display_name, is_active, is_superadmin, must_change_password, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                hash_password(password),
                display_name,
                int(is_active),
                int(is_superadmin),
                int(must_change_password),
                _now(),
                _now(),
            ),
        )
        user_id = cursor.lastrowid
        for rid in role_ids or []:
            connection.execute(
                "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
                (user_id, rid),
            )
    return get_user(user_id)


def update_user(
    user_id: int,
    *,
    display_name: str | None = None,
    is_active: bool | None = None,
    is_superadmin: bool | None = None,
    role_ids: list[int] | None = None,
) -> dict[str, Any] | None:
    current = get_user(user_id)
    if current is None:
        return None
    new_name = display_name if display_name is not None else current["display_name"]
    new_active = is_active if is_active is not None else current["is_active"]
    new_super = is_superadmin if is_superadmin is not None else current["is_superadmin"]
    with connect() as connection:
        connection.execute(
            "UPDATE users SET display_name = ?, is_active = ?, is_superadmin = ?, updated_at = ? WHERE id = ?",
            (new_name, int(new_active), int(new_super), _now(), user_id),
        )
        if role_ids is not None:
            connection.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
            for rid in role_ids:
                connection.execute(
                    "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
                    (user_id, rid),
                )
    return get_user(user_id)


def set_user_password(user_id: int, password: str, *, must_change: bool = False) -> bool:
    from app.auth import hash_password

    with connect() as connection:
        cursor = connection.execute(
            "UPDATE users SET password_hash = ?, must_change_password = ?, updated_at = ? WHERE id = ?",
            (hash_password(password), int(must_change), _now(), user_id),
        )
        return cursor.rowcount > 0


def delete_user(user_id: int) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        if cursor.rowcount == 0:
            return False
        connection.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
        return True


def count_active_superadmins(exclude_user_id: int | None = None) -> int:
    with connect() as connection:
        if exclude_user_id is None:
            row = connection.execute(
                "SELECT COUNT(*) FROM users WHERE is_superadmin = 1 AND is_active = 1"
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT COUNT(*) FROM users WHERE is_superadmin = 1 AND is_active = 1 AND id != ?",
                (exclude_user_id,),
            ).fetchone()
    return int(row[0])


# ── Suppression list (do-not-email) ────────────────────

def add_suppression(email: str, *, reason: str = "unsubscribe", source: str = "", notes: str = "") -> dict[str, Any]:
    norm = email.strip().lower()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO suppressions (email, reason, source, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET reason = excluded.reason, source = excluded.source
            """,
            (norm, reason, source, notes, _now()),
        )
        row = connection.execute("SELECT * FROM suppressions WHERE email = ?", (norm,)).fetchone()
    return _row_to_dict(row)


def is_suppressed(email: str) -> bool:
    norm = email.strip().lower()
    if not norm:
        return False
    with connect() as connection:
        row = connection.execute(
            "SELECT 1 FROM suppressions WHERE email = ? LIMIT 1", (norm,)
        ).fetchone()
    return row is not None


def list_suppressions(q: str | None = None) -> list[dict[str, Any]]:
    with connect() as connection:
        if q:
            rows = connection.execute(
                "SELECT * FROM suppressions WHERE email LIKE ? ORDER BY id DESC",
                (f"%{q.strip().lower()}%",),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM suppressions ORDER BY id DESC"
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def remove_suppression(email: str) -> bool:
    norm = email.strip().lower()
    with connect() as connection:
        cursor = connection.execute("DELETE FROM suppressions WHERE email = ?", (norm,))
        return cursor.rowcount > 0


# ── Audit log ──────────────────────────────────────────

def add_audit(
    *,
    actor: str,
    action: str,
    target_type: str = "",
    target_id: str | int = "",
    detail: str = "",
) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO audit_log (actor, action, target_type, target_id, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (actor, action, target_type, str(target_id), detail, _now()),
        )


def list_audit(*, limit: int = 200, action: str | None = None, actor: str | None = None) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if action:
        filters.append("action = ?")
        params.append(action)
    if actor:
        filters.append("actor = ?")
        params.append(actor)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(max(1, min(limit, 1000)))
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ?", params
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


# ── Settings ───────────────────────────────────────────

# Settings whose values are encrypted at rest (transparently de/encrypted here).
_SECRET_SETTING_KEYS = {"agent_key", "email_password"}


def get_setting(key: str, default: str = "") -> str:
    with connect() as connection:
        row = connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return default
    value = row["value"]
    if key in _SECRET_SETTING_KEYS:
        from app.crypto import decrypt_secret

        return decrypt_secret(value)
    return value


def set_setting(key: str, value: str) -> None:
    if key in _SECRET_SETTING_KEYS and value:
        from app.crypto import encrypt_secret

        value = encrypt_secret(value)
    with connect() as connection:
        connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_all_settings() -> dict[str, str]:
    with connect() as connection:
        rows = connection.execute("SELECT key, value FROM settings").fetchall()
    from app.crypto import decrypt_secret

    result: dict[str, str] = {}
    for row in rows:
        key, value = row["key"], row["value"]
        result[key] = decrypt_secret(value) if key in _SECRET_SETTING_KEYS else value
    return result


# ── Lead scoring rules ───────────────────────────────────
# Stored as a JSON blob per lead_type under the settings table. Defaults
# mirror the overseas-distributor-prospecting SKILL.md Step 5 rules verbatim,
# so behavior is unchanged until an admin actually customizes them.
#
# "scoring_rules" is the legacy single-set key (pre-dates the distributor/KOL
# split) and is kept as the distributor key so any rules an admin already
# customized are not silently discarded.

_SCORING_RULES_SETTING_KEYS = {
    "distributor": "scoring_rules",
    "kol": "scoring_rules_kol",
}

DEFAULT_SCORING_RULES: dict[str, Any] = {
    "weights": [
        {"key": "channel_fit", "label": "渠道匹配度", "percent": 40},
        {"key": "market_priority", "label": "目标市场战略优先级", "percent": 25},
        {"key": "academic_brand", "label": "学术/品牌公开资历", "percent": 20},
        {"key": "contact_availability", "label": "联系方式可用性", "percent": 10},
        {"key": "kol_hospital_evidence", "label": "公开KOL/医院合作记录（加分项）", "percent": 5},
    ],
    "positive_rules": [
        {"points": 25, "description": "官网确认从事医疗器械分销、进口或渠道销售"},
        {"points": 20, "description": "明确的骨科植入物/关节置换/膝关节置换/手术设备/机器人/导航/OR资本设备相关性"},
        {"points": 15, "description": "有可见的商务邮箱或官方联系表单"},
        {"points": 15, "description": "公司所在国家/区域覆盖匹配目标市场"},
        {"points": 10, "description": "有具名的商务拓展/销售/产品/经销联系人"},
        {"points": 10, "description": "出现在厂商合作伙伴页、官方展商名录、监管/进口商目录，或医疗器械协会目录中"},
        {"points": 5, "description": "具备与目标区域相关的多国覆盖"},
    ],
    "negative_rules": [
        {"points": -20, "description": "来源证据薄弱或不完整"},
        {"points": -20, "description": "仅有LinkedIn/社交媒体/贸易目录证据，无官网确认"},
        {"points": -30, "description": "与医疗机器人、骨科器械、医疗分销、手术设备或医院设备无关"},
        {"points": -30, "description": "疑似仅为医院、媒体、咨询公司、招聘网站、消费品，或无关的工业机器人公司"},
        {"points": -40, "description": "确认为重复线索"},
    ],
    "thresholds": [
        {"min": 80, "max": 100, "status": "qualified", "label": "强匹配"},
        {"min": 60, "max": 79, "status": "new", "label": "中度匹配"},
        {"min": 40, "max": 59, "status": "human_review", "label": "需人工核验"},
        {"min": 0, "max": 39, "status": "rejected", "label": "弱匹配/建议拒绝"},
    ],
}

# Mirrors SKILL.md Step 5 "KOL-specific scoring" — distinct from the
# distributor rules above because the evidence that matters for a surgeon
# (case volume, robotic experience, academic output) is nothing like what
# matters for a distribution company.
DEFAULT_KOL_SCORING_RULES: dict[str, Any] = {
    "weights": [
        {"key": "clinical_volume_fit", "label": "临床/手术量匹配度", "percent": 40},
        {"key": "market_priority", "label": "目标市场战略优先级", "percent": 25},
        {"key": "academic_brand", "label": "学术/品牌公开资历", "percent": 20},
        {"key": "contact_availability", "label": "联系方式可用性", "percent": 10},
        {"key": "mentorship_evidence", "label": "带教/机构合作证据（加分项）", "percent": 5},
    ],
    "positive_rules": [
        {"points": 25, "description": "手术量证据充分（约150+ TKA/年）或有机器人/导航手术经验"},
        {"points": 20, "description": "有'首例'类里程碑成就（本国/本地区首例机器人或导航手术等）"},
        {"points": 15, "description": "有学术产出：骨科期刊发表论文，或具名教授/研究职称"},
        {"points": 15, "description": "有会议/同行影响力：AAOS/AAHKS/CAOS 或区域关节置换学会演讲者，或学会任职"},
        {"points": 10, "description": "任职于教学医院、学术医学中心或专科培训项目"},
        {"points": 10, "description": "有带教、培训同行或接待观摩医生的记录"},
        {"points": 10, "description": "有可见的商务/专业邮箱或官方联系方式"},
        {"points": 5, "description": "所在机构或职务覆盖战略优先目标市场"},
    ],
    "negative_rules": [
        {"points": -20, "description": "来源证据薄弱或间接（仅医院人员名录，无手术/学术细节）"},
        {"points": -30, "description": "无手术量、机器人/导航经验或学术产出证据，缺乏可个性化的信息"},
        {"points": -40, "description": "确认为重复线索"},
    ],
    "thresholds": [
        {"min": 80, "max": 100, "status": "qualified", "label": "强匹配"},
        {"min": 60, "max": 79, "status": "new", "label": "中度匹配"},
        {"min": 40, "max": 59, "status": "human_review", "label": "需人工核验"},
        {"min": 0, "max": 39, "status": "rejected", "label": "弱匹配/建议拒绝"},
    ],
}

DEFAULT_SCORING_RULES_BY_TYPE: dict[str, dict[str, Any]] = {
    "distributor": DEFAULT_SCORING_RULES,
    "kol": DEFAULT_KOL_SCORING_RULES,
}


def _normalize_scoring_lead_type(lead_type: str | None) -> str:
    return "kol" if str(lead_type or "").strip().lower() == "kol" else "distributor"


def get_scoring_rules(lead_type: str | None = None) -> dict[str, Any]:
    normalized = _normalize_scoring_lead_type(lead_type)
    setting_key = _SCORING_RULES_SETTING_KEYS[normalized]
    defaults = DEFAULT_SCORING_RULES_BY_TYPE[normalized]
    raw = get_setting(setting_key, "")
    if not raw:
        return {**defaults, "updated_at": ""}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {**defaults, "updated_at": ""}
    parsed.setdefault("updated_at", "")
    return parsed


def status_for_score(score: int, lead_type: str | None = None) -> str:
    """Map a lead score to its initial status using the admin-configured
    thresholds for that lead type, falling back to defaults if none/invalid
    are configured."""
    normalized = _normalize_scoring_lead_type(lead_type)
    thresholds = get_scoring_rules(normalized).get("thresholds") or DEFAULT_SCORING_RULES_BY_TYPE[normalized]["thresholds"]
    for rule in thresholds:
        try:
            lo, hi = int(rule["min"]), int(rule["max"])
        except (KeyError, TypeError, ValueError):
            continue
        if lo <= score <= hi:
            status = str(rule.get("status") or "").strip()
            if status:
                return status
    return "new"


def set_scoring_rules(rules: dict[str, Any], lead_type: str | None = None) -> dict[str, Any]:
    normalized = _normalize_scoring_lead_type(lead_type)
    setting_key = _SCORING_RULES_SETTING_KEYS[normalized]
    payload = {**rules, "updated_at": _now()}
    set_setting(setting_key, json.dumps(payload))
    return payload


# ── Helpers ────────────────────────────────────────────

def _now() -> str:
    return datetime.now(UTC).isoformat()
