"""CLI entrypoint for monthly Google Ads invoice workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from googleads_invoice.pipeline import format_dry_run_report, run_dry_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="googleads-invoice")
    sub = parser.add_subparsers(dest="command", required=True)

    dry = sub.add_parser(
        "dry-run",
        help="Print billing URL, parsed PDF fields, and Jack email artifacts (no send).",
    )
    dry.add_argument(
        "--mail-html",
        type=Path,
        required=True,
        help="Path to saved Gmail-style HTML (e.g. redacted export or fixture).",
    )
    dry.add_argument(
        "--invoice-pdf",
        type=Path,
        required=True,
        help="Path to invoice PDF (downloaded or synthetic fixture).",
    )
    dry.add_argument(
        "--month-label",
        required=True,
        help='Human month label for the email, e.g. "March 2026".',
    )

    args = parser.parse_args(argv)
    if args.command == "dry-run":
        report = run_dry_run(
            mail_html_path=args.mail_html,
            invoice_pdf_path=args.invoice_pdf,
            month_label=args.month_label,
        )
        print(format_dry_run_report(report), end="")
        return 0
    return 2
