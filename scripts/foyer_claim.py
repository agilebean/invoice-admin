#!/usr/bin/env python3
"""Submit a Foyer Global Health reimbursement claim for a receipt PDF on the live portal.

Usage::

    python scripts/foyer_claim.py path/to/receipt.pdf [--country KR] [--dry-run]
    python scripts/foyer_claim.py path/to/receipt.pdf --verify-only

The user's Brave must be running with ``--remote-debugging-port=9222``
(the ``brave`` shell alias does this). The script attaches to it over CDP,
so the logged-in portal session and the passkey stay in the real browser.
If the portal asks for login, the script brings the tab to the front, prints
a prompt, and waits while the passkey is completed there.

After submitting, the script waits ``--verify-wait`` seconds (default 60) and
checks the claim appears under Schadenmeldung with status ``Gesendet``.

Shell alias (``~/.bash_aliases``) picks the latest PDF from the claims folder,
asks for confirmation, then calls this script::

    foyerclaim
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PORTAL_URL = "https://myaccount.foyerglobalhealth.com/"
DEFAULT_CDP_URL = "http://127.0.0.1:9222"

CLAIMS_NAV = '[data-clickable-action="globalMenu.2.2.FghClientIconBar.Claims"]'
NEW_CLAIM_BUTTON = '[data-clickable-action="menu.submitClaim"]'
NEIN_LABEL = 'label[for$="moreThan24Hfalse"]'
COUNTRY_SELECT = 'select[name$="countryOfTreatment"]'
KRW_ACCOUNT_LABEL = 'label:has-text("KOOKMIN")'
EUR_ACCOUNT_LABEL = 'label:has-text("WISE")'
FILE_INPUT = "input[type=file]"
SUBMIT_BUTTON = 'button:has-text("Anfrage senden")'
SUBMITTED_TEXT = "Ihr Antrag wurde eingereicht"
AUTH_FORM = "input#username, input#password, input[name='username']"

_CURRENCY_COUNTRY = {"KRW": "KR", "MXN": "MX", "AUD": "AU", "USD": "US"}
_CURRENCY_RE = re.compile(r"\b(KRW|MXN|AUD|USD|EUR|GBP|TWD)\b", re.IGNORECASE)

_FORM_STATE_JS = """() => {
  const radios = Array.from(document.querySelectorAll('input[type=radio]')).map(r => ({
    name: r.name || '',
    label: (r.labels && r.labels[0] ? r.labels[0].innerText : '').trim().replace(/\\s+/g, ' '),
    checked: r.checked,
  }));
  const sel = document.querySelector('select[name$="countryOfTreatment"]');
  const f = document.querySelector('input[type=file]');
  return {radios, country: sel ? sel.value : null, inputFiles: f ? f.files.length : -1, body: document.body.innerText};
}"""


def detect_currency(filename: str) -> str | None:
    """Return the ISO currency code mentioned in a receipt filename, if any."""
    m = _CURRENCY_RE.search(filename)
    return m.group(1).upper() if m else None


def country_for_currency(currency: str) -> str | None:
    """Map a currency to the treatment country it implies (None when ambiguous)."""
    return _CURRENCY_COUNTRY.get(currency.upper())


def is_login_url(url: str) -> bool:
    """True when the browser is on the Foyer Auth0 login flow."""
    return "auth.foyerglobalhealth.com" in url or "/u/login" in url


@dataclass(frozen=True)
class ClaimCard:
    """One claim row from the Schadenmeldung list."""

    number: str
    date: str
    status: str


_NUMBER_RE = re.compile(r"Nummer\s*\n\s*(\d+)\s*\n")
_CARD_RE = re.compile(
    r"Nummer\s*\n\s*(\d+)\s*\n"
    r"\s*Versichert\s*\n.*?\n"
    r"\s*Einreichungsdatum\s*\n\s*(\d{2}/\d{2}/\d{4})\s*\n"
    r"\s*Geforderter Betrag\s*\n.*?\n"
    r"\s*Status\s*\n\s*([^\n]+)",
    re.DOTALL,
)


def parse_claim_cards(text: str) -> list[ClaimCard]:
    """Parse claim cards from the Schadenmeldung page text."""
    starts = [m.start() for m in _NUMBER_RE.finditer(text)]
    cards: list[ClaimCard] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        m = _CARD_RE.search(text, start, end)
        if m:
            status = m.group(3).strip().lstrip("\u2022").strip()
            cards.append(ClaimCard(number=m.group(1), date=m.group(2), status=status))
    return cards


def find_claim_for_date(cards: list[ClaimCard], date_str: str) -> ClaimCard | None:
    """Return the first claim submitted on ``date_str`` (DD/MM/YYYY)."""
    for card in cards:
        if card.date == date_str:
            return card
    return None


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _connect(pw, cdp_url: str):
    try:
        return pw.chromium.connect_over_cdp(cdp_url, timeout=10_000)
    except Exception as exc:  # noqa: BLE001 - surface any attach failure
        _fail(
            f"Cannot attach to Brave at {cdp_url}: {exc}\n"
            'Start Brave with: brave   (open -a "Brave Browser" --args --remote-debugging-port=9222)'
        )


def _portal_loaded(page) -> bool:
    try:
        return "Schadenmeldung" in page.inner_text("body")
    except Exception:  # noqa: BLE001 - page may be mid-navigation
        return False


def ensure_logged_in(page, timeout_s: int) -> None:
    """Wait for the portal session; prompt the user to complete the passkey if needed."""
    deadline = time.time() + timeout_s
    auth_since: float | None = None
    prompted = False
    while time.time() < deadline:
        if page.is_closed():
            _fail("The portal tab was closed while waiting; re-run the script.")
        if is_login_url(page.url):
            if auth_since is None:
                auth_since = time.time()
            auth_age = time.time() - auth_since
            try:
                auth_form_visible = page.locator(AUTH_FORM).first.is_visible()
            except Exception:  # noqa: BLE001 - best effort
                auth_form_visible = False
            if not prompted and ((auth_form_visible and auth_age >= 2) or auth_age >= 15):
                print(
                    "\n*** Login required: complete the Foyer passkey in Brave "
                    f"(the tab has been brought to the front). Waiting up to {timeout_s}s... ***\n",
                    flush=True,
                )
                try:
                    page.bring_to_front()
                except Exception:  # noqa: BLE001 - best effort
                    pass
                prompted = True
            time.sleep(2)
            continue
        auth_since = None
        if _portal_loaded(page):
            if prompted:
                print("Login completed.")
            return
        time.sleep(1)
    _fail(f"Portal login was not completed within {timeout_s}s.")


def go_to_claims(page) -> None:
    page.locator(CLAIMS_NAV).first.click(timeout=20_000)
    page.wait_for_selector(NEW_CLAIM_BUTTON, timeout=20_000)


def open_new_claim(page) -> None:
    page.locator(NEW_CLAIM_BUTTON).first.click(timeout=20_000)
    page.wait_for_selector(NEIN_LABEL, timeout=20_000)


def read_form_state(page) -> dict:
    return page.evaluate(_FORM_STATE_JS)


def fill_claim_form(page, pdf: Path, country: str, currency: str | None) -> dict:
    page.locator(NEIN_LABEL).click(timeout=20_000)
    page.wait_for_timeout(800)

    page.locator(COUNTRY_SELECT).select_option(country, timeout=20_000)
    page.wait_for_timeout(800)

    if currency == "KRW":
        page.locator(KRW_ACCOUNT_LABEL).first.click(timeout=20_000)
    else:
        wise_checked = any(
            "WISE" in r["label"].upper() and r["checked"] for r in read_form_state(page)["radios"]
        )
        if not wise_checked:
            page.locator(EUR_ACCOUNT_LABEL).first.click(timeout=20_000)
    page.wait_for_timeout(800)

    page.locator(FILE_INPUT).set_input_files(str(pdf), timeout=30_000)
    deadline = time.time() + 30
    while time.time() < deadline:
        if pdf.name in page.inner_text("body"):
            break
        time.sleep(1)
    else:
        _fail("The uploaded file never appeared as attached; aborting before submit.")

    state = read_form_state(page)
    problems: list[str] = []
    nein = [
        r for r in state["radios"]
        if r["name"].endswith("moreThan24H") and r["label"] == "Nein"
    ]
    if not (nein and nein[0]["checked"]):
        problems.append("'Nein' (more than 24h) is not selected")
    if state["country"] != country:
        problems.append(f"country is {state['country']!r}, expected {country!r}")
    kookmin = any(
        "KOOKMIN" in r["label"].upper() and r["checked"] for r in state["radios"]
    )
    wise = any("WISE" in r["label"].upper() and r["checked"] for r in state["radios"])
    if currency == "KRW":
        if not kookmin:
            problems.append("Kookmin Bank account is not selected for a KRW bill")
    elif not wise:
        problems.append("EUR (WISE) account is not selected")
    if pdf.name not in state["body"]:
        problems.append("uploaded file is not shown as attached")
    if problems:
        _fail("Form verification failed; aborting before submit:\n- " + "\n- ".join(problems))
    return state


def submit_and_confirm(page) -> None:
    page.locator(SUBMIT_BUTTON).first.click(timeout=20_000)
    deadline = time.time() + 30
    while time.time() < deadline:
        if SUBMITTED_TEXT in page.inner_text("body"):
            print("Portal confirmation: " + SUBMITTED_TEXT)
            return
        time.sleep(1)
    _fail("No submit confirmation seen. Do NOT resubmit blindly; check the portal.")


def verify_claim(
    page, today: str, wait_s: int, attempts: int, interval_s: int = 30
) -> ClaimCard | None:
    print(f"Waiting {wait_s}s before verifying the claim list...")
    time.sleep(wait_s)
    last: ClaimCard | None = None
    for _ in range(attempts):
        go_to_claims(page)
        last = find_claim_for_date(parse_claim_cards(page.inner_text("body")), today)
        if last and "Gesendet" in last.status:
            return last
        print(
            "Not verified yet: "
            + (f"claim {last.number} status {last.status!r}" if last else f"no claim dated {today}")
        )
        time.sleep(interval_s)
    return last


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path, nargs="?", help="receipt PDF to upload")
    ap.add_argument("--country", help="ISO country code of treatment (e.g. KR); defaults from currency")
    ap.add_argument("--cdp-url", default=os.environ.get("FOYER_CDP_URL", DEFAULT_CDP_URL))
    ap.add_argument("--login-timeout", type=int, default=300, help="seconds to wait for passkey login")
    ap.add_argument("--verify-wait", type=int, default=60, help="seconds to wait before verifying the claim list")
    ap.add_argument("--verify-attempts", type=int, default=3, help="verification retries after the wait")
    ap.add_argument("--dry-run", action="store_true", help="fill and verify the form but do not submit")
    ap.add_argument("--verify-only", action="store_true", help="only check today's claim on the portal")
    args = ap.parse_args(argv)

    if args.pdf is None:
        _fail("PDF argument is required.", 2)
    if not args.pdf.is_file():
        _fail(f"PDF not found: {args.pdf}", 2)

    today = time.strftime("%d/%m/%Y")
    currency = detect_currency(args.pdf.name)
    country = args.country or (country_for_currency(currency) if currency else None)
    if not args.verify_only and not country:
        try:
            country = input(f"Country code for {args.pdf.name} (e.g. KR): ").strip().upper()
        except EOFError:
            _fail("Country required; pass --country.")
        if not country:
            _fail("Country required; pass --country.")

    print(f"PDF:      {args.pdf}")
    print(f"Currency: {currency or 'unknown (EUR account will be used)'}")
    if not args.verify_only:
        print(f"Country:  {country}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = _connect(pw, args.cdp_url)
        contexts = browser.contexts
        if not contexts:
            _fail("Brave is running but exposes no browser context over CDP.")
        page = contexts[0].new_page()
        page.set_default_timeout(20_000)
        try:
            page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=40_000)
            ensure_logged_in(page, args.login_timeout)

            if args.verify_only:
                go_to_claims(page)
                card = find_claim_for_date(
                    parse_claim_cards(page.inner_text("body")), today
                )
                if card is None:
                    _fail(f"No claim dated {today} found.")
                print(f"Claim {card.number} — status {card.status}")
                return 0 if "Gesendet" in card.status else 1

            go_to_claims(page)
            existing = find_claim_for_date(
                parse_claim_cards(page.inner_text("body")), today
            )
            if existing:
                print(
                    f"WARNING: a claim from today already exists: {existing.number} "
                    f"(status {existing.status})."
                )
                try:
                    answer = input("Submit another one anyway? [y/N] ")
                except EOFError:
                    answer = ""
                if answer.strip().lower() != "y":
                    _fail("Aborted: a claim for today already exists.")

            open_new_claim(page)
            fill_claim_form(page, args.pdf, country, currency)
            if args.dry_run:
                print("Dry run: form filled and verified; not submitting.")
                return 0

            submit_and_confirm(page)
            card = verify_claim(page, today, args.verify_wait, args.verify_attempts)
            if card and "Gesendet" in card.status:
                print(f"SUCCESS: claim {card.number} submitted and visible with status Gesendet.")
                return 0
            if card:
                print(f"WARNING: claim {card.number} found but status is {card.status!r}.")
                return 1
            _fail(f"Claim for {today} not found after verification window.")
        finally:
            page.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
