"""Invoice classifier using LLM."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from invoice_admin.classify.example_store import build_classification_few_shot_section
from invoice_admin.classify.prompts import CLASSIFICATION_PROMPT
from invoice_admin.classify.taxonomy import INVOICE_TYPE_LABELS
from invoice_admin.core.errors import ClassifierError
from invoice_admin.core.pdf import ExtractedInvoiceData, extract_pdf_data


@dataclass(frozen=True)
class ClassificationResult:
    """LLM classification output plus extracted PDF/HTML fields."""

    invoice_type: str
    confidence: float
    reasoning: str
    extracted_data: ExtractedInvoiceData
    original_invoice_type: str | None = None
    original_confidence: float | None = None

    def review_notes_json(self) -> str | None:
        """JSON for tracker `notes` when invoice_type is needs_review."""
        if self.invoice_type != "needs_review":
            return None
        if self.original_invoice_type is None or self.original_confidence is None:
            return None
        return json.dumps(
            {
                "original_type": self.original_invoice_type,
                "original_confidence": self.original_confidence,
            }
        )


_ALLOWED_TYPES = INVOICE_TYPE_LABELS


def _parse_classification_json(text: str) -> tuple[str, float, str]:
    raw = text.strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ClassifierError(f"Invalid classification JSON: {e}") from e
    if not isinstance(data, dict):
        raise ClassifierError("Classification JSON must be an object")
    inv_type = str(data.get("invoice_type", "unknown")).strip()
    if inv_type not in _ALLOWED_TYPES:
        inv_type = "unknown"
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    reasoning = str(data.get("reasoning", "")).strip()
    return inv_type, confidence, reasoning


def classify_invoice(
    extracted: ExtractedInvoiceData,
    llm_provider: Any,
    min_confidence: float = 0.7,
    *,
    classifier_examples_path: Path | None = None,
) -> ClassificationResult:
    """Classify extracted invoice data; low confidence maps to needs_review (no exception)."""
    extracted_blob = json.dumps(
        {
            "vendor": extracted.vendor,
            "invoice_date": extracted.invoice_date,
            "due_date": extracted.due_date,
            "amount": extracted.amount,
            "currency": extracted.currency,
            "iban": extracted.iban,
            "bic": extracted.bic,
            "verwendungszweck": extracted.verwendungszweck,
        },
        indent=2,
        sort_keys=True,
    )
    few_block = ""
    if classifier_examples_path is not None:
        few_block = build_classification_few_shot_section(classifier_examples_path)
    prompt = CLASSIFICATION_PROMPT.format(
        few_shot_block=few_block,
        extracted_data=extracted_blob,
    )
    raw = llm_provider.complete(
        prompt,
        model_alias="fast",
        purpose="classification",
    )
    inv_type, confidence, reasoning = _parse_classification_json(raw)

    original_type: str | None = None
    original_conf: float | None = None
    final_type = inv_type
    if confidence < min_confidence:
        original_type = inv_type
        original_conf = confidence
        final_type = "needs_review"

    return ClassificationResult(
        invoice_type=final_type,
        confidence=confidence,
        reasoning=reasoning,
        extracted_data=extracted,
        original_invoice_type=original_type,
        original_confidence=original_conf,
    )


def extract_and_classify(
    pdf_path: Any,
    llm_provider: Any,
    min_confidence: float = 0.7,
    *,
    classifier_examples_path: Path | None = None,
) -> ClassificationResult:
    """Full pipeline: extract PDF data, then classify."""
    extracted = extract_pdf_data(pdf_path, llm_provider)
    return classify_invoice(
        extracted,
        llm_provider,
        min_confidence,
        classifier_examples_path=classifier_examples_path,
    )
