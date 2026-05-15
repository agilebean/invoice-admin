"""Classification and extraction prompts."""
from __future__ import annotations

CLASSIFICATION_PROMPT = """\
You are a document classifier for an invoice admin system. Given extracted data from a document, determine the document type.

{few_shot_block}Data:
{extracted_data}

Classify as ONE of:
- "foyer_claim" — health insurance claim for Foyer Global Health. Includes:
  * medical bills, doctor visit receipts, hospital invoices (has provider name + amount)
  * medical certificates, attestations, doctor's letters (has provider name, no amount — these are supporting documents for claims)
  * any document from a doctor, hospital, or medical provider
- "sepa_transfer" — tradesman/handwerker bill requiring SEPA bank transfer (plumber, electrician, repair, craftsman)
- "outgoing_invoice" — an invoice that Chaehan needs to SEND to a client (not one he received)
- "unknown" — cannot confidently classify

Respond with ONLY a JSON object:
{{"invoice_type": "<type>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}}
"""


EXTRACTION_PROMPT = """\
Extract structured data from this document. Return ONLY a JSON object.

{
    "vendor": "The sending person or doctor who signed/issued this document (NOT the letterhead organization). For medical letters, use the doctor's name. For businesses, use the company name.",
    "invoice_date": "Date of document in YYYY-MM-DD format (e.g. 2026-05-05) or null if not found",
    "due_date": "YYYY-MM-DD or null",
    "amount": <number or null>,
    "currency": "EUR/USD/etc or null",
    "iban": "IBAN string or null",
    "bic": "BIC/SWIFT string or null",
    "verwendungszweck": "Payment reference/purpose or null",
    "document_topic": "Short topic (3-6 words max, e.g. 'medical certificate shoulder', 'plumbing repair invoice', 'insurance receipt') or null"
}

IMPORTANT: Convert all dates to YYYY-MM-DD format. Return ONLY JSON.
"""


HTML_EXTRACTION_PREFIX = """\
The following is HTML from an email body (not a PDF). Extract structured invoice data from visible text.
Follow the same JSON schema as for PDF invoices.

"""
