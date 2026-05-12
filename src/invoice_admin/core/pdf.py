"""PDF → structured data via Claude native PDF support."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from invoice_admin.classify.prompts import EXTRACTION_PROMPT, HTML_EXTRACTION_PREFIX
from invoice_admin.core.errors import ExtractionError


@dataclass(frozen=True)
class ExtractedInvoiceData:
    """Structured data extracted from an invoice PDF."""

    vendor: str | None
    invoice_date: str | None
    due_date: str | None
    amount: float | None
    currency: str | None
    iban: str | None
    bic: str | None
    verwendungszweck: str | None
    raw_json: str


def _str_field(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "null":
        return None
    return s


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", ".")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _json_object_from_llm_text(raw_text: str) -> tuple[dict[str, Any], str]:
    raw_json = raw_text.strip()
    m = re.search(r"\{[\s\S]*\}", raw_json)
    if m:
        raw_json = m.group(0)
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Invalid JSON from LLM: {e}") from e
    if not isinstance(data, dict) or not data:
        raise ExtractionError("LLM returned empty or non-object JSON")
    return data, raw_json


def _extracted_from_dict(data: dict[str, Any], raw_json: str) -> ExtractedInvoiceData:
    vendor_s = _str_field(data.get("vendor"))
    extracted = ExtractedInvoiceData(
        vendor=vendor_s,
        invoice_date=_str_field(data.get("invoice_date")),
        due_date=_str_field(data.get("due_date")),
        amount=_safe_float(data.get("amount")),
        currency=_str_field(data.get("currency")),
        iban=_str_field(data.get("iban")),
        bic=_str_field(data.get("bic")),
        verwendungszweck=_str_field(data.get("verwendungszweck")),
        raw_json=raw_json,
    )
    if extracted.vendor is None and extracted.amount is None:
        raise ExtractionError("Extraction missing vendor and amount")
    return extracted


def extract_pdf_data(
    pdf_path: Path,
    llm_provider: Any,
    model_alias: str = "smart",
) -> ExtractedInvoiceData:
    """Send PDF to Claude, get structured data back."""
    prompt = EXTRACTION_PROMPT
    pdf_bytes = pdf_path.read_bytes()
    raw_text = llm_provider.complete_with_pdf(
        prompt,
        pdf_bytes,
        model_alias=model_alias,
        purpose="pdf_extraction",
    )
    data, raw_json = _json_object_from_llm_text(raw_text)
    return _extracted_from_dict(data, raw_json)


def extract_html_invoice_data(
    html: str,
    llm_provider: Any,
    model_alias: str = "smart",
) -> ExtractedInvoiceData:
    """Extract structured invoice fields from HTML email body via LLM text completion."""
    capped = html[:500_000]
    prompt = HTML_EXTRACTION_PREFIX + EXTRACTION_PROMPT + "\n\nHTML:\n" + capped
    raw_text = llm_provider.complete(
        prompt,
        model_alias=model_alias,
        purpose="pdf_extraction",
    )
    data, raw_json = _json_object_from_llm_text(raw_text)
    return _extracted_from_dict(data, raw_json)
