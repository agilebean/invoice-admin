"""Extract invoice billing URLs from Gmail-style HTML snippets."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlparse


class BillingUrlNotFoundError(ValueError):
    """Raised when HTML does not contain a recognized Google billing invoice link."""


class _AnchorHrefCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(value.strip())


_BILLING_NETLOCS = frozenset({
    "payments.google.com",
    "pay.google.com",
    "c.gle",  # Google short links that redirect to the billing Documents page
})


def _is_billing_href(href: str) -> bool:
    parsed = urlparse(href)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return host in _BILLING_NETLOCS


def extract_billing_url(html: str) -> str:
    """Return the first anchor href that points at a known Google billing host."""
    collector = _AnchorHrefCollector()
    collector.feed(html)
    for href in collector.hrefs:
        if _is_billing_href(href):
            return href
    raise BillingUrlNotFoundError(
        "No Google billing invoice URL found in mail HTML "
        "(expected a link to payments.google.com or pay.google.com)."
    )
