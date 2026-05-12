"""Parity: OutgoingInvoiceHandler dry-run path matches pipeline.run_dry_run."""
from __future__ import annotations

from pathlib import Path

from googleads_invoice.pipeline import run_dry_run

from invoice_admin.core.config import repo_root
from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler


def test_dry_run_output_matches_pipeline() -> None:
    """Handler delegates to the same ``run_dry_run`` used by the legacy CLI dry-run."""
    root = repo_root()
    mail = root / "tests" / "fixtures" / "gmail" / "billing_mail_happy.html"
    pdf = root / "tests" / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    month_label = "March 2026"

    direct = run_dry_run(
        mail_html_path=mail,
        invoice_pdf_path=pdf,
        month_label=month_label,
    )
    handler = OutgoingInvoiceHandler({})
    wrapped = handler.dry_run_from_paths(mail, pdf, month_label=month_label)
    assert wrapped == direct
