"""Tests for invoice_admin.classify.classifier."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from invoice_admin.classify.classifier import classify_invoice, extract_and_classify
from invoice_admin.classify.example_store import append_jsonl_record, build_example_record
from invoice_admin.core.errors import ClassifierError
from invoice_admin.core.pdf import ExtractedInvoiceData


def _extracted() -> ExtractedInvoiceData:
    return ExtractedInvoiceData(
        vendor="ACME",
        invoice_date="2026-01-01",
        due_date=None,
        amount=10.0,
        currency="EUR",
        iban=None,
        bic=None,
        verwendungszweck=None,
        raw_json="{}",
    )


def test_classify_invoice_low_confidence_maps_to_needs_review() -> None:
    llm = MagicMock()
    llm.complete.return_value = json.dumps(
        {"invoice_type": "sepa_transfer", "confidence": 0.4, "reasoning": "unsure"}
    )
    ext = _extracted()
    out = classify_invoice(ext, llm, min_confidence=0.7)
    assert out.invoice_type == "needs_review"
    assert out.confidence == 0.4
    assert out.original_invoice_type == "sepa_transfer"
    assert out.original_confidence == 0.4
    notes = out.review_notes_json()
    assert notes is not None
    payload = json.loads(notes)
    assert payload["original_type"] == "sepa_transfer"
    assert payload["original_confidence"] == 0.4


def test_classify_invoice_high_confidence_passthrough() -> None:
    llm = MagicMock()
    llm.complete.return_value = json.dumps(
        {"invoice_type": "foyer_claim", "confidence": 0.9, "reasoning": "ok"}
    )
    out = classify_invoice(_extracted(), llm, min_confidence=0.7)
    assert out.invoice_type == "foyer_claim"
    assert out.review_notes_json() is None


def test_classify_invoice_includes_few_shot_when_path_provided(tmp_path: Path) -> None:
    examples = tmp_path / "classifier_examples.jsonl"
    examples.parent.mkdir(parents=True, exist_ok=True)
    append_jsonl_record(
        examples,
        build_example_record("ref.pdf", "sepa_transfer", _extracted()),
    )
    prompts: list[str] = []

    def capture(prompt: str, **kwargs: object) -> str:
        prompts.append(prompt)
        return json.dumps(
            {"invoice_type": "sepa_transfer", "confidence": 0.9, "reasoning": "ok"}
        )

    llm = MagicMock()
    llm.complete.side_effect = capture
    classify_invoice(
        _extracted(),
        llm,
        min_confidence=0.7,
        classifier_examples_path=examples,
    )
    assert len(prompts) == 1
    assert "Prior labeled examples" in prompts[0]
    assert "sepa_transfer" in prompts[0]


def test_classify_invalid_json_raises() -> None:
    llm = MagicMock()
    llm.complete.return_value = "not-json"
    with pytest.raises(ClassifierError):
        classify_invoice(_extracted(), llm)


def test_extract_and_classify(tmp_path: Path) -> None:
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    class FakeLLM:
        def complete_with_pdf(self, prompt, pdf_bytes, **kwargs):
            return json.dumps(
                {
                    "vendor": "V",
                    "invoice_date": "2026-02-02",
                    "due_date": None,
                    "amount": 1,
                    "currency": "EUR",
                    "iban": None,
                    "bic": None,
                    "verwendungszweck": None,
                }
            )

        def complete(self, prompt, **kwargs):
            return json.dumps(
                {"invoice_type": "unknown", "confidence": 0.99, "reasoning": "x"}
            )

    llm = FakeLLM()
    res = extract_and_classify(pdf, llm, min_confidence=0.5)
    assert res.invoice_type == "unknown"
