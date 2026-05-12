"""Tests for invoice_admin.core.errors."""
from __future__ import annotations

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
