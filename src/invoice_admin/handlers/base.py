"""Handler Protocol and common helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from invoice_admin.core.config import InvoiceConfig
from invoice_admin.core.naming import build_invoice_pdf_filename_with_vendor_slug
from invoice_admin.core.notify import Notifier
from invoice_admin.core.tracker import InvoiceRow, Tracker


@runtime_checkable
class Handler(Protocol):
    """Protocol for all invoice handlers."""

    @property
    def invoice_type(self) -> str:
        """The invoice_type string this handler processes (e.g. 'foyer_claim')."""
        ...

    def execute(
        self,
        row: InvoiceRow,
        tracker: Tracker,
        llm_provider: Any,
        config: InvoiceConfig,
        notifier: Notifier,
    ) -> None:
        """Process an invoice row; update tracker and notify on failure."""
        ...


def prepare_invoice_pdf(row: InvoiceRow, config: InvoiceConfig) -> Path:
    """Locate the PDF file for a given tracker row."""
    if not row.pdf_path:
        raise FileNotFoundError("invoice row has no pdf_path")
    path = Path(row.pdf_path).expanduser()
    if not path.is_absolute():
        path = (config.paths.invoices_root / path).resolve()
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path


def rename_invoice_pdf(row: InvoiceRow, config: InvoiceConfig, vendor_slug: str) -> Path:
    """Rename stored PDF to YYYY-MM-DD_<vendor-slug>_<amount><CCY>.pdf (same directory)."""
    src = prepare_invoice_pdf(row, config)
    name = build_invoice_pdf_filename_with_vendor_slug(
        invoice_date=row.invoice_date,
        vendor_slug=vendor_slug,
        amount=row.amount,
        currency=row.currency,
    )
    dest = src.with_name(name)
    if dest.resolve() == src.resolve():
        return src
    if dest.exists():
        dest.unlink()
    return src.rename(dest)
