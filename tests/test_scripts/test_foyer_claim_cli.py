"""Tests for ``scripts/foyer_claim.py`` (pure helpers + CLI smoke)."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "foyer_claim.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("foyer_claim_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(REPO / "src")}


def test_help_exits_zero() -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=str(REPO),
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert "--verify-wait" in r.stdout
    assert "--verify-only" in r.stdout


def test_missing_pdf_exits_nonzero(tmp_path: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.pdf")],
        cwd=str(REPO),
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode != 0
    assert "not found" in (r.stdout + r.stderr).lower()


def test_dead_cdp_port_fails_fast(tmp_path: Path) -> None:
    pdf = tmp_path / "2026-09-17 clinic KRW 1.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(pdf),
            "--cdp-url",
            "http://127.0.0.1:9",
        ],
        cwd=str(REPO),
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert r.returncode != 0
    assert "Brave" in (r.stdout + r.stderr)


def test_detect_currency_from_filename() -> None:
    mod = _load_module()
    assert (
        mod.detect_currency("2026-09-17 IPL Gongdeok eye clinic 공덕안과 KRW 254860.pdf")
        == "KRW"
    )
    assert mod.detect_currency("2025-03-20 Dr. Frenkiell Shoulder AUD 165.94.pdf") == "AUD"
    assert mod.detect_currency("2025-02-20 Dr. Frenkiel Shoulder $$510.pdf") is None


def test_country_for_currency() -> None:
    mod = _load_module()
    assert mod.country_for_currency("KRW") == "KR"
    assert mod.country_for_currency("MXN") == "MX"
    assert mod.country_for_currency("AUD") == "AU"
    assert mod.country_for_currency("USD") == "US"
    assert mod.country_for_currency("EUR") is None


def test_is_login_url() -> None:
    mod = _load_module()
    assert mod.is_login_url(
        "https://auth.foyerglobalhealth.com/u/login/identifier?state=x"
    )
    assert not mod.is_login_url("https://myaccount.foyerglobalhealth.com/show")


CARD_OLD = """\
Schadenmeldung
Nummer
28000001916396
Versichert
Chaehan So
Einreichungsdatum
25/06/2026
Geforderter Betrag
643,00 MXN
Status
Akzeptiert
"""

CARD_NEW = """\
Nummer
28000001968192
Versichert
Chaehan So
Einreichungsdatum
17/09/2026
Geforderter Betrag
0,00
Status
• Gesendet
Logout
"""


def test_parse_claim_cards() -> None:
    mod = _load_module()
    cards = mod.parse_claim_cards(CARD_OLD + CARD_NEW)
    assert len(cards) == 2
    assert cards[0].number == "28000001916396"
    assert cards[0].date == "25/06/2026"
    assert cards[0].status == "Akzeptiert"
    assert cards[1].number == "28000001968192"
    assert cards[1].date == "17/09/2026"
    assert cards[1].status == "Gesendet"


def test_find_claim_for_date() -> None:
    mod = _load_module()
    cards = mod.parse_claim_cards(CARD_NEW)
    hit = mod.find_claim_for_date(cards, "17/09/2026")
    assert hit is not None and hit.number == "28000001968192"
    assert mod.find_claim_for_date(cards, "01/01/2020") is None
