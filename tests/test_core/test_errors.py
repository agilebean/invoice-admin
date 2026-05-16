"""Tests for invoice_admin.core.errors."""
from __future__ import annotations

import json

from invoice_admin.core.errors import (
    ClassificationLowConfidence,
    ConfigError,
    ExtractionError,
    HandlerError,
    IdempotencyViolation,
    InvoiceError,
    NotifyError,
    SepaGuardrailError,
    TrackerError,
    tracker_error_blob,
)


def test_exception_hierarchy() -> None:
    assert issubclass(ConfigError, InvoiceError)
    assert issubclass(TrackerError, InvoiceError)
    assert issubclass(ClassificationLowConfidence, InvoiceError)
    assert issubclass(ExtractionError, InvoiceError)
    assert issubclass(HandlerError, InvoiceError)
    assert issubclass(IdempotencyViolation, InvoiceError)
    assert issubclass(SepaGuardrailError, HandlerError)
    assert issubclass(NotifyError, InvoiceError)


def test_tracker_error_blob_round_trip() -> None:
    exc = HandlerError("boom")
    raw = tracker_error_blob(exc)
    data = json.loads(raw)
    assert data == {"type": "HandlerError", "message": "boom"}
