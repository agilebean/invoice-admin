"""Domain exceptions for invoice-admin."""
from __future__ import annotations

import json

from agentkit.core import AgentError


class InvoiceError(AgentError):
    """Base exception for all invoice-admin errors."""


class ConfigError(InvoiceError):
    """Configuration is missing or invalid."""


class TrackerError(InvoiceError):
    """Database operation failed."""


class ClassifierError(InvoiceError):
    """Classification or extraction failed."""


class HandlerError(InvoiceError):
    """A handler failed to process an invoice."""


class IdempotencyViolation(InvoiceError):
    """Duplicate message-ID or file hash detected."""


class ExtractionError(ClassifierError):
    """LLM could not extract structured data from invoice."""


class ClassificationLowConfidence(ClassifierError):
    """Classifier confidence below threshold."""


class SepaGuardrailError(HandlerError):
    """Transfer exceeds MAX_AUTO_AMOUNT_EUR or IBAN validation failed."""


class NotifyError(InvoiceError):
    """Notification delivery failed."""


class FoyerAuthError(HandlerError):
    """Foyer portal authentication failed."""


def tracker_error_blob(exc: BaseException) -> str:
    """Serialize an exception for the tracker ``error`` column (JSON object)."""
    return json.dumps({"type": type(exc).__name__, "message": str(exc)}, indent=2)
