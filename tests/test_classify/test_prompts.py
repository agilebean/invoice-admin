"""Tests for classification and extraction prompt strings."""
from __future__ import annotations

import json

from invoice_admin.classify.prompts import (
    CLASSIFICATION_PROMPT,
    EXTRACTION_PROMPT,
    HTML_EXTRACTION_PREFIX,
)


def test_classification_prompt_formats_and_contains_schema_instruction() -> None:
    blob = json.dumps({"vendor": "Test Clinic", "amount": 42.5}, sort_keys=True)
    out = CLASSIFICATION_PROMPT.format(few_shot_block="", extracted_data=blob)
    assert blob in out
    assert '"foyer_claim"' in out or "foyer_claim" in out
    assert "sepa_transfer" in out
    assert "outgoing_invoice" in out
    assert "unknown" in out
    assert "invoice_type" in out
    assert "{few_shot_block}" not in out
    assert "{extracted_data}" not in out


def test_classification_prompt_inserts_few_shot_before_data() -> None:
    few = "FEW_SHOT_MARKER\n"
    out = CLASSIFICATION_PROMPT.format(few_shot_block=few, extracted_data="{}")
    assert out.index(few) < out.index("Data:")


def test_extraction_prompt_is_single_brace_json_template() -> None:
    assert "{{" not in EXTRACTION_PROMPT
    assert '"vendor"' in EXTRACTION_PROMPT
    assert "verwendungszweck" in EXTRACTION_PROMPT
    assert "\n{\n" in EXTRACTION_PROMPT


def test_html_prefix_plus_extraction_mentions_html() -> None:
    combo = HTML_EXTRACTION_PREFIX + EXTRACTION_PROMPT
    assert "HTML" in HTML_EXTRACTION_PREFIX
    assert "email body" in HTML_EXTRACTION_PREFIX.lower() or "HTML" in HTML_EXTRACTION_PREFIX
    assert EXTRACTION_PROMPT in combo
