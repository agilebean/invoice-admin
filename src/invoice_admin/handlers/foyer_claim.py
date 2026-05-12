"""Foyer Global Health claim submission via Playwright."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from invoice_admin.core.config import InvoiceConfig
from invoice_admin.core.errors import FoyerAuthError, HandlerError
from invoice_admin.core.notify import Notification, Notifier
from invoice_admin.core.tracker import InvoiceRow, Tracker
from invoice_admin.handlers.base import prepare_invoice_pdf

logger = logging.getLogger(__name__)

SyncPlaywrightFactory = Callable[[], Any]


def _default_playwright_factory() -> Any:
    from playwright.sync_api import sync_playwright

    return sync_playwright()


def _error_blob(exc: BaseException) -> str:
    return json.dumps(
        {"type": type(exc).__name__, "message": str(exc)},
        indent=2,
    )


class FoyerClaimHandler:
    """Submits health insurance claims to Foyer Global Health portal."""

    invoice_type = "foyer_claim"

    def __init__(
        self,
        handler_config: dict[str, Any],
        *,
        playwright_factory: SyncPlaywrightFactory | None = None,
    ) -> None:
        self._portal_url = str(handler_config["portal_url"])
        self._timeout_ms = int(handler_config.get("timeout_ms", 30_000))
        self._locators: dict[str, str] = dict(handler_config.get("locators") or {})
        self._playwright_factory: SyncPlaywrightFactory = (
            playwright_factory or _default_playwright_factory
        )
        sp = handler_config.get("session_path")
        self._session_path: Path | None = (
            Path(str(sp)).expanduser().resolve() if sp else None
        )
        ad = handler_config.get("artifacts_dir")
        self._artifacts_dir: Path | None = (
            Path(str(ad)).expanduser().resolve() if ad else None
        )

    def execute(
        self,
        row: InvoiceRow,
        tracker: Tracker,
        llm_provider: Any,
        config: InvoiceConfig,
        notifier: Notifier,
    ) -> None:
        """Submit claim to Foyer portal (Playwright)."""
        if row.status in ("submitted", "reimbursed"):
            return
        pdf_path = prepare_invoice_pdf(row, config)
        tracker.update_status(row.id, "submitting")
        try:
            self._submit_with_playwright(row, tracker, notifier, pdf_path)
        except FoyerAuthError as e:
            tracker.update_status(row.id, "failed", error=_error_blob(e))
            notifier.send(
                Notification(
                    title="Foyer claim failed (auth)",
                    body=str(e)[:4000],
                    priority="urgent",
                    click_url=None,
                )
            )
            raise
        except Exception as e:
            tracker.update_status(row.id, "failed", error=_error_blob(e))
            notifier.send(
                Notification(
                    title="Foyer claim failed",
                    body=str(e)[:4000],
                    priority="urgent",
                    click_url=None,
                )
            )
            raise HandlerError(str(e)) from e

    def _submit_with_playwright(
        self,
        row: InvoiceRow,
        tracker: Tracker,
        notifier: Notifier,
        pdf_path: Path,
    ) -> None:
        pw = self._playwright_factory()
        headless = os.environ.get("FOYER_PLAYWRIGHT_HEADLESS", "1").strip() != "0"
        with pw as p:
            browser = p.chromium.launch(headless=headless)
            context: Any | None = None
            try:
                storage: str | None = None
                if self._session_path and self._session_path.is_file():
                    storage = str(self._session_path)
                context = (
                    browser.new_context(storage_state=storage)
                    if storage
                    else browser.new_context()
                )
                page = context.new_page()
                page.set_default_timeout(self._timeout_ms)
                page.goto(self._portal_url, wait_until="domcontentloaded")

                auth = self._authenticate(page)
                if auth == "2fa":
                    tracker.update_status(
                        row.id,
                        "needs_review",
                        notes="2FA required — please complete login manually",
                    )
                    notifier.send(
                        Notification(
                            title="Foyer login needs 2FA",
                            body="Complete login manually, then retry.",
                            priority="high",
                            click_url=None,
                        )
                    )
                    return
                if auth == "failed":
                    raise FoyerAuthError("Foyer portal login failed")

                self._navigate_to_claim_form(page)
                self._fill_claim_form(page, row)
                self._upload_pdf(page, pdf_path)
                self._submit_claim(page)

                confirmation = self._capture_confirmation(page)
                self._maybe_screenshot(page, row.id, success=True)

                now = datetime.now(timezone.utc).isoformat()
                note_bits = [row.notes or "", f"foyer_confirmation={confirmation}".strip()]
                new_notes = "\n".join(b for b in note_bits if b).strip() or None
                tracker.update_status(
                    row.id,
                    "submitted",
                    submitted_at=now,
                    notes=new_notes,
                )
                self._persist_storage(context)
            finally:
                if context is not None:
                    context.close()
                browser.close()

    def _login_visible(self, page: Any) -> bool:
        sel = self._locators.get("login_username", "input[name='username']")
        try:
            loc = page.locator(sel).first
            return bool(loc.is_visible(timeout=min(1_500, self._timeout_ms)))
        except Exception:
            return False

    def _twofa_hint_visible(self, page: Any) -> bool:
        try:
            return (
                page.get_by_text(
                    re.compile(
                        r"verification code|two[- ]factor|authenticator|sms code",
                        re.I,
                    )
                ).count()
                > 0
            )
        except Exception:
            return False

    def _authenticate(self, page: Any) -> Literal["ok", "2fa", "failed"]:
        """Attempt interactive login using env credentials when the login form is visible."""
        if not self._login_visible(page):
            return "ok"
        user = os.environ.get("FOYER_USERNAME", "").strip()
        pwd = os.environ.get("FOYER_PASSWORD", "").strip()
        if not user or not pwd:
            raise FoyerAuthError("Missing FOYER_USERNAME / FOYER_PASSWORD for Foyer login")

        user_sel = self._locators.get("login_username", "input[name='username']")
        pwd_sel = self._locators.get("login_password", "input[name='password']")
        page.locator(user_sel).first.fill(user)
        page.locator(pwd_sel).first.fill(pwd)
        submit_sel = self._locators.get("login_submit", "button[type='submit']")
        page.locator(submit_sel).first.click()

        time.sleep(0.8)
        if self._twofa_hint_visible(page):
            return "2fa"
        if self._login_visible(page):
            return "failed"
        return "ok"

    def _navigate_to_claim_form(self, page: Any) -> None:
        """Open claims UI using roles/labels first, YAML locators as hints."""
        try:
            page.get_by_role("link", name=re.compile(r"claim", re.I)).first.click(
                timeout=self._timeout_ms
            )
        except Exception:
            hint = self._locators.get("claims_tab", "text=Claims")
            page.locator(hint).first.click(timeout=self._timeout_ms)
        try:
            page.get_by_role("button", name=re.compile(r"new claim|submit new", re.I)).click(
                timeout=self._timeout_ms
            )
        except Exception:
            hint = self._locators.get("new_claim_button", "text=Submit New Claim")
            page.locator(hint).first.click(timeout=self._timeout_ms)

    def _fill_claim_form(self, page: Any, row: InvoiceRow) -> None:
        service_date = (row.invoice_date or "")[:10]
        if not service_date:
            raise HandlerError("invoice_date is required for Foyer claims")
        vendor = row.vendor or ""
        amount = row.amount
        if amount is None:
            raise HandlerError("amount is required for Foyer claims")

        try:
            page.get_by_label(re.compile(r"service|date", re.I)).first.fill(
                service_date, timeout=self._timeout_ms
            )
        except Exception:
            sel = self._locators.get("claim_form_date", "input[name='service_date']")
            page.locator(sel).first.fill(service_date, timeout=self._timeout_ms)

        try:
            page.get_by_label(re.compile(r"provider|vendor|doctor", re.I)).first.fill(
                vendor, timeout=self._timeout_ms
            )
        except Exception:
            sel = self._locators.get("claim_form_vendor", "input[name='provider_name']")
            page.locator(sel).first.fill(vendor, timeout=self._timeout_ms)

        amt_str = str(int(amount)) if float(amount).is_integer() else str(float(amount))
        try:
            page.get_by_label(re.compile(r"amount|claim", re.I)).first.fill(
                amt_str, timeout=self._timeout_ms
            )
        except Exception:
            sel = self._locators.get("claim_form_amount", "input[name='claim_amount']")
            page.locator(sel).first.fill(amt_str, timeout=self._timeout_ms)

    def _upload_pdf(self, page: Any, pdf_path: Path) -> None:
        try:
            page.get_by_label(re.compile(r"upload|document|file", re.I)).set_input_files(
                str(pdf_path), timeout=self._timeout_ms
            )
        except Exception:
            sel = self._locators.get("claim_form_upload", "input[type='file']")
            page.locator(sel).first.set_input_files(str(pdf_path), timeout=self._timeout_ms)

    def _submit_claim(self, page: Any) -> None:
        try:
            page.get_by_role("button", name=re.compile(r"submit", re.I)).first.click(
                timeout=self._timeout_ms
            )
        except Exception:
            sel = self._locators.get("claim_submit", "button:has-text('Submit')")
            page.locator(sel).first.click(timeout=self._timeout_ms)

    def _capture_confirmation(self, page: Any) -> str:
        try:
            txt = page.get_by_text(re.compile(r"confirmation|reference", re.I)).first.inner_text(
                timeout=self._timeout_ms
            )
            return txt.strip()[:500]
        except Exception:
            pass
        try:
            sel = self._locators.get("confirmation_number", ".confirmation-number")
            return page.locator(sel).first.inner_text(timeout=self._timeout_ms).strip()[:500]
        except Exception:
            return ""

    def _maybe_screenshot(self, page: Any, row_id: int, *, success: bool) -> None:
        if self._artifacts_dir is None:
            return
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        name = f"{row_id}_{'ok' if success else 'err'}.png"
        path = self._artifacts_dir / name
        try:
            page.screenshot(path=str(path), full_page=True)
        except Exception:
            logger.warning("Foyer screenshot failed for row %s", row_id)

    def _persist_storage(self, context: Any) -> None:
        if self._session_path is None:
            return
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(self._session_path))
