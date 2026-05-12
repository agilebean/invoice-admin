#!/usr/bin/env python3
"""Append human-labeled rows to ``config/classifier_examples.jsonl`` for classifier tuning.

Each run calls the **smart** PDF extractor (LLM) for every PDF path, then appends one JSON
line per file. Requires the same API keys / env as normal ``invoice`` ingest extraction.

Usage::

    export INVOICE_ADMIN_REPO_ROOT=/path/to/invoice-admin   # optional if cwd is repo
    python scripts/seed_examples.py --invoice-type sepa_transfer path/to/a.pdf path/to/b.pdf

    python scripts/seed_examples.py --invoice-type foyer_claim --output /tmp/my.jsonl x.pdf

Default output path is ``paths.classifier_examples`` from ``config/default.yaml`` (by default
``<repo>/config/classifier_examples.jsonl``).

See ``invoice_admin.classify.example_store`` for the on-disk record shape.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from invoice_admin.classify.taxonomy import INVOICE_TYPE_LABELS
from invoice_admin.classify.example_store import append_jsonl_record, build_example_record
from invoice_admin.core.config import load_config, repo_root
from invoice_admin.core.errors import ConfigError
from invoice_admin.core.llm import LLMProvider
from invoice_admin.core.pdf import extract_pdf_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract PDF fields via LLM and append labeled rows to classifier_examples.jsonl",
    )
    parser.add_argument(
        "--invoice-type",
        required=True,
        choices=sorted(INVOICE_TYPE_LABELS),
        help="Ground-truth label for every PDF in this invocation",
    )
    parser.add_argument(
        "pdfs",
        nargs="+",
        type=Path,
        help="One or more invoice PDF paths",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSONL output path (default: paths.classifier_examples from config, usually <repo>/config/classifier_examples.jsonl)",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Optional note stored on each appended row (e.g. batch id)",
    )
    args = parser.parse_args(argv)

    try:
        root = repo_root()
        config = load_config(root)
    except (RuntimeError, ConfigError, OSError, ValueError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    out_path = args.output if args.output is not None else config.paths.classifier_examples_path
    llm = LLMProvider(log_path=config.paths.llm_calls_path)

    for pdf in args.pdfs:
        p = pdf.expanduser().resolve()
        if not p.is_file():
            print(f"not a file: {pdf}", file=sys.stderr)
            return 2
        try:
            extracted = extract_pdf_data(p, llm, model_alias="smart")
        except Exception as e:
            print(f"extract failed for {p}: {e}", file=sys.stderr)
            return 1
        record = build_example_record(
            str(p),
            args.invoice_type,
            extracted,
            notes=args.notes,
        )
        append_jsonl_record(out_path, record)
        print(f"appended {p.name} -> {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
