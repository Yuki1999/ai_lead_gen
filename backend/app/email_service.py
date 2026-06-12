"""
Email service for sending emails via Microsoft Exchange Web Services (EWS).

Uses exchangelib with Basic Auth to connect to an on-premises Exchange server.
Configuration is read from environment variables:

    MEDBOT_EMAIL_SERVER   – Exchange server hostname (default: mail.microport.com.cn)
    MEDBOT_EMAIL_USER     – sender email / login username
    MEDBOT_EMAIL_PASSWORD – login password

If email credentials are not configured the service reports is_configured() == False,
and callers should fall back to recording outreach events without actual delivery.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from exchangelib import (
    Account,
    Configuration,
    Credentials,
    DELEGATE,
    HTMLBody,
    Mailbox,
    Message,
)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class EmailConfig:
    server: str
    username: str
    password: str

    def is_valid(self) -> bool:
        return bool(self.server and self.username and self.password)


def _load_config() -> EmailConfig:
    return EmailConfig(
        server=_env("MEDBOT_EMAIL_SERVER", "mail.microport.com.cn"),
        username=_env("MEDBOT_EMAIL_USER", "OB_OSD@microport.com"),
        password=_env("MEDBOT_EMAIL_PASSWORD", "CDdeXHi9"),
    )


_config: EmailConfig | None = None
_account: Account | None = None


def get_config() -> EmailConfig:
    """Return the current email configuration (cached)."""
    global _config
    if _config is None:
        _config = _load_config()
    return _config


def reload_config() -> EmailConfig:
    """Re-read configuration from environment variables."""
    global _config, _account
    _config = None
    _account = None
    return get_config()


def is_configured() -> bool:
    """Return True if email credentials are available."""
    return get_config().is_valid()


def _get_account() -> Account:
    """Return a configured exchangelib Account (cached)."""
    global _account
    if _account is not None:
        return _account

    cfg = get_config()
    if not cfg.is_valid():
        raise EmailNotConfiguredError(
            "Email credentials not configured. "
            "Set MEDBOT_EMAIL_SERVER, MEDBOT_EMAIL_USER, and MEDBOT_EMAIL_PASSWORD."
        )

    creds = Credentials(cfg.username, cfg.password)
    config = Configuration(server=cfg.server, credentials=creds)

    _account = Account(
        primary_smtp_address=cfg.username,
        config=config,
        autodiscover=False,
        access_type=DELEGATE,
    )
    return _account


@dataclass
class SendResult:
    """Result of a single email send attempt."""

    sent_to: str
    subject: str
    success: bool
    message_id: str = ""
    error: str = ""


@dataclass
class BatchSendResult:
    """Aggregated result of sending multiple emails."""

    results: list[SendResult] = field(default_factory=list)

    @property
    def sent_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.success)


def send_email(
    *,
    to: str,
    subject: str,
    body: str,
    html: bool = False,
    cc: list[str] | None = None,
) -> SendResult:
    """Send a single email via Exchange EWS.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text or HTML body.
        html: If True, treat body as HTML.
        cc: Optional list of CC recipients.

    Returns:
        SendResult with success status and error details.
    """
    try:
        account = _get_account()

        kwargs: dict = {
            "account": account,
            "subject": subject,
            "to_recipients": [to],
        }

        if html:
            kwargs["body"] = HTMLBody(body)
        else:
            kwargs["body"] = body

        if cc:
            kwargs["cc_recipients"] = cc

        msg = Message(**kwargs)
        msg.send()

        return SendResult(
            sent_to=to,
            subject=subject,
            success=True,
            message_id=getattr(msg, "message_id", "") or "",
        )

    except EmailNotConfiguredError:
        raise
    except Exception as exc:
        return SendResult(
            sent_to=to,
            subject=subject,
            success=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def send_batch(
    *,
    recipients: list[dict[str, object]],
    subject: str,
    body: str,
    html: bool = False,
) -> BatchSendResult:
    """Send the same email to multiple recipients.

    Each recipient dict should have at least an "email" key.
    The recipient's "contact_name" key (if present) is used to
    personalize the greeting via {contact_name} placeholder replacement.

    Args:
        recipients: List of dicts with "email" and optional "contact_name".
        subject: Email subject (may contain {contact_name}).
        body: Email body (may contain {contact_name}).
        html: If True, treat body as HTML.

    Returns:
        BatchSendResult with per-recipient status.
    """
    result = BatchSendResult()
    for rcpt in recipients:
        email = str(rcpt.get("email", "")).strip()
        if not email:
            result.results.append(
                SendResult(sent_to="", subject=subject, success=False, error="Missing email address")
            )
            continue

        name = str(rcpt.get("contact_name", ""))
        personalized_subject = subject.replace("{contact_name}", name) if name else subject
        personalized_body = body.replace("{contact_name}", name) if name else body

        result.results.append(
            send_email(to=email, subject=personalized_subject, body=personalized_body, html=html)
        )
    return result


def test_connection() -> dict[str, object]:
    """Test Exchange connectivity and return status info.

    Returns:
        Dict with "ok", "server", "user", "version", and optional "error" keys.
    """
    cfg = get_config()
    if not cfg.is_valid():
        return {
            "ok": False,
            "server": cfg.server or "(not set)",
            "user": cfg.username or "(not set)",
            "version": "",
            "error": "Email credentials not configured.",
        }

    try:
        account = _get_account()
        return {
            "ok": True,
            "server": cfg.server,
            "user": cfg.username,
            "version": str(account.version) if account.version else "",
        }
    except Exception as exc:
        # Clear cached account so retry is possible after config fix
        global _account
        _account = None
        return {
            "ok": False,
            "server": cfg.server,
            "user": cfg.username,
            "version": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


@dataclass
class InboxReply:
    """A reply fetched from the Exchange inbox."""

    sender_email: str
    sender_name: str
    subject: str
    body: str
    received_at: str
    message_id: str


def fetch_inbox_replies(*, max_count: int = 30) -> list[InboxReply]:
    """Fetch recent replies from the Exchange inbox.

    Returns emails where the sender is NOT the configured user
    (i.e., replies from external contacts, not sent items or self-mail).

    Args:
        max_count: Maximum number of recent inbox items to scan.

    Returns:
        List of InboxReply objects sorted by most recent first.
    """
    try:
        account = _get_account()
    except EmailNotConfiguredError:
        raise

    cfg = get_config()
    own_email = cfg.username.lower()

    replies: list[InboxReply] = []
    for msg in account.inbox.all().order_by("-datetime_received")[:max_count]:
        sender_email = str(msg.sender.email_address).lower() if msg.sender else ""

        # Skip emails from ourselves
        if sender_email == own_email:
            continue

        body = ""
        if msg.text_body:
            body = msg.text_body.strip()
        elif msg.body:
            # HTML body — try to get text
            from bs4 import BeautifulSoup
            try:
                body = BeautifulSoup(str(msg.body), "html.parser").get_text(separator="\n").strip()
            except Exception:
                body = str(msg.body)[:2000]

        sender_name = str(msg.sender.name) if msg.sender and msg.sender.name else ""

        replies.append(
            InboxReply(
                sender_email=sender_email,
                sender_name=sender_name,
                subject=str(msg.subject) if msg.subject else "",
                body=body[:5000],
                received_at=msg.datetime_received.isoformat() if msg.datetime_received else "",
                message_id=str(msg.message_id) if msg.message_id else "",
            )
        )

    return replies


class EmailNotConfiguredError(RuntimeError):
    """Raised when email credentials are missing."""
