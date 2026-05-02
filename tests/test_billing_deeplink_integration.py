"""Optional real-world HTTP checks (not CI fixtures). See PLAN Iteration 9.1."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from urllib.parse import urlparse

import pytest

_TEST_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _final_url_after_redirects(url: str, *, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _TEST_UA},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.geturl()


@pytest.mark.integration
@pytest.mark.skipif(
    not (os.environ.get("GOOGLEADS_BILLING_DEEPLINK") or "").strip(),
    reason="Set GOOGLEADS_BILLING_DEEPLINK to the monthly c.gle (or equivalent) URL from mail",
)
def test_billing_mail_deeplink_reaches_google_ads() -> None:
    """Follow the real short link from billing mail; assert we end in Google's Ads/sign-in funnel.

    This uses plain HTTP (no Selenium). It does not use your Brave cookie jar — unauthenticated
    clients often land on accounts.google.com, which still proves the redirect chain from mail works.
    """
    deeplink = os.environ["GOOGLEADS_BILLING_DEEPLINK"].strip()
    parsed = urlparse(deeplink)
    assert parsed.scheme in ("http", "https"), "Deeplink must be an http(s) URL"
    try:
        final = _final_url_after_redirects(deeplink)
    except urllib.error.HTTPError as e:
        pytest.fail(f"Deeplink HTTP error: {e.code} {e.reason} from {e.url}")
    except urllib.error.URLError as e:
        pytest.fail(f"Deeplink network error: {e.reason}")

    host = urlparse(final).hostname or ""
    assert host.endswith("google.com") or host.endswith(
        "googleusercontent.com"
    ), f"Expected Google host after redirects, got: {final!r}"
    path_lower = (urlparse(final).path or "").lower()
    combined = f"{final.lower()}"
    assert (
        "ads.google.com" in combined
        or "service=adwords" in combined
        or "signin" in path_lower
        or "/nav/login" in combined
    ), f"Redirect chain did not resemble Ads login/documents flow: {final!r}"
