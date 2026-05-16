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
    document_topic: str | None = None
    raw_json: str = ""


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
    amount_f = _safe_float(data.get("amount"))
    extracted = ExtractedInvoiceData(
        vendor=vendor_s,
        invoice_date=_str_field(data.get("invoice_date")),
        due_date=_str_field(data.get("due_date")),
        amount=amount_f,
        currency=_str_field(data.get("currency")),
        iban=_str_field(data.get("iban")),
        bic=_str_field(data.get("bic")),
        verwendungszweck=_str_field(data.get("verwendungszweck")),
        document_topic=_str_field(data.get("document_topic")),
        raw_json=raw_json,
    )
    if vendor_s is None and amount_f is None:
        raise ExtractionError("Extraction missing vendor and amount")
    return extracted


def extract_pdf_data(
    pdf_path: Path,
    llm_provider: Any,
    model_alias: str = "smart",
) -> ExtractedInvoiceData:
    """Extract structured invoice fields from a PDF.

    Tries pypdf text extraction first; falls back to sending raw PDF
    bytes (multimodal) when pypdf cannot parse the file.
    """
    pdf_bytes = pdf_path.read_bytes()

    try:
        raw_text = _extract_via_pypdf_text(pdf_bytes, llm_provider, model_alias)
    except Exception:
        raw_text = llm_provider.complete_with_pdf(
            EXTRACTION_PROMPT,
            pdf_bytes,
            model_alias=model_alias,
            purpose="pdf_extraction",
        )

    data, raw_json = _json_object_from_llm_text(raw_text)
    return _extracted_from_dict(data, raw_json)


def _extract_via_pypdf_text(
    pdf_bytes: bytes,
    llm_provider: Any,
    model_alias: str,
) -> str:
    """Extract text with pypdf, then ask the LLM to parse it."""
    import pypdf
    from io import BytesIO

    reader = pypdf.PdfReader(BytesIO(pdf_bytes))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            parts.append(f"--- page {i + 1} ---\n{text}")
    pdf_text = "\n\n".join(parts)
    if not pdf_text.strip():
        raise ExtractionError("pypdf returned no extractable text")
    capped = pdf_text[:500_000]
    prompt = EXTRACTION_PROMPT + "\n\nPDF text:\n" + capped
    return llm_provider.complete(
        prompt,
        model_alias=model_alias,
        purpose="pdf_extraction",
    )


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
