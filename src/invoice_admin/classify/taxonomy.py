"""Shared invoice-type labels for classification and example JSONL."""
from __future__ import annotations

INVOICE_TYPE_LABELS: frozenset[str] = frozenset(
    {"foyer_claim", "sepa_transfer", "outgoing_invoice", "unknown", "needs_review"}
)
