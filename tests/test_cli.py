from pathlib import Path

import pytest

from googleads_invoice.cli import main


def test_cli_dry_run_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    root = Path(__file__).resolve().parent
    mail = root / "fixtures" / "gmail" / "billing_mail_happy.html"
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(
        [
            "dry-run",
            "--mail-html",
            str(mail),
            "--invoice-pdf",
            str(pdf),
            "--month-label",
            "March 2026",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "payments.google.com" in out
    assert "Gmail send skipped" in out


def test_cli_requires_subcommand() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code != 0
