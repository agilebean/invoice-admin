"""Classification and extraction prompts."""
from __future__ import annotations

CLASSIFICATION_PROMPT = """\
You are an invoice classifier. Given the following extracted data from an invoice PDF, determine the invoice type.

{few_shot_block}Data:
{extracted_data}

Classify as ONE of:
- "foyer_claim" — health insurance claim for Foyer Global Health (medical bill, doctor visit, hospital)
- "sepa_transfer" — tradesman/handwerker bill requiring SEPA bank transfer (plumber, electrician, repair, craftsman)
- "outgoing_invoice" — an invoice that Chaehan needs to SEND to a client (not one he received)
- "unknown" — cannot confidently classify

Respond with ONLY a JSON object:
{{"invoice_type": "<type>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}}
"""


EXTRACTION_PROMPT = """\
Extract structured data from this invoice PDF. Return ONLY a JSON object.

{{
    "vendor": "Company or person who issued this invoice",
    "invoice_date": "YYYY-MM-DD or null",
    "due_date": "YYYY-MM-DD or null",
    "amount": <number or null>,
    "currency": "EUR/USD/etc or null",
    "iban": "IBAN string or null",
    "bic": "BIC/SWIFT string or null",
    "verwendungszweck": "Payment reference/purpose or null"
}}

Do not include any text outside the JSON object.
"""


HTML_EXTRACTION_PREFIX = """\
The following is HTML from an email body (not a PDF). Extract structured invoice data from visible text.
Follow the same JSON schema as for PDF invoices.

"""
