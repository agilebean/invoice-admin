"""Golden LLM-style JSON fixtures under ``tests/fixtures/llm_responses/``."""
from __future__ import annotations

from pathlib import Path

from invoice_admin.core.pdf import extract_html_invoice_data


def _fixture(name: str) -> Path:
    root = Path(__file__).resolve().parents[1]
    return root / "fixtures" / "llm_responses" / name


def test_extraction_valid_min_fixture_round_trip() -> None:
    """Reserved ``llm_responses`` tree: extraction JSON matches ``extract_html_invoice_data`` contract."""
    raw = _fixture("extraction_valid_min.json").read_text(encoding="utf-8").strip()

    class FakeLLM:
        def complete(self, prompt: str, **kwargs: object) -> str:
            assert "HTML" in prompt
            return raw

    out = extract_html_invoice_data("<html><body>fixture</body></html>", FakeLLM())
    assert out.vendor == "Fixture Vendor LLC"
    assert out.invoice_date == "2026-01-15"
    assert abs((out.amount or 0) - 99.99) < 1e-6
    assert out.currency == "EUR"
    assert out.verwendungszweck == "INV-001"
