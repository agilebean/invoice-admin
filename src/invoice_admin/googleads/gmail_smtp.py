"""Compatibility shim: Gmail SMTP send now lives in agentkit.

The implementation was ported to :mod:`agentkit.gmail._smtp`; this module only
re-exports it so existing imports (``invoice_admin.googleads.gmail_smtp``) and
call sites keep working. Do not add send logic here.
"""

from __future__ import annotations

from agentkit.gmail import SmtpGmailBackend, smtp_app_password, smtp_login_user


def _smtp_login_user() -> str:
    """SMTP login / From: user, resolved by agentkit."""
    return smtp_login_user()


def _smtp_app_password_from_env() -> str:
    """Gmail app password from the environment or password file, resolved by agentkit."""
    return smtp_app_password()


__all__ = [
    "SmtpGmailBackend",
    "_smtp_login_user",
    "_smtp_app_password_from_env",
]
