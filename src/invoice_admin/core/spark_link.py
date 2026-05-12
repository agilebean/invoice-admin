"""Spark deep-link generator."""
from __future__ import annotations

from urllib.parse import parse_qs, quote, unquote, urlparse


def spark_deep_link(message_id: str) -> str:
    """Generate a readdle-spark:// deep-link for a given RFC822 Message-ID."""
    encoded = quote(message_id, safe="")
    return f"readdle-spark://openmessage?messageId={encoded}"


def spark_link_with_fallback(
    message_id: str,
    sender: str,
    subject: str,
    date_str: str,
) -> str:
    """Return Spark deep-link + plain text fallback for when the scheme doesn't fire."""
    deep_link = spark_deep_link(message_id)
    return f"[Open in Spark]({deep_link})\n\n{sender} — {subject} — {date_str}"


def message_id_from_spark_open_url(url: str) -> str:
    """Parse RFC822 Message-ID from ``readdle-spark://openmessage?messageId=...``."""
    raw = url.strip()
    if not raw.lower().startswith("readdle-spark://"):
        raise ValueError("URL must start with readdle-spark://")
    qs = urlparse(raw).query
    params = parse_qs(qs, keep_blank_values=False)
    for key in ("messageId", "messageid"):
        if key in params and params[key] and params[key][0]:
            return unquote(params[key][0])
    raise ValueError("Spark URL has no messageId query parameter")
