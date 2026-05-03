#!/usr/bin/env python3
"""One-time OAuth token generator for Google APIs (Gmail + Google Ads).

Usage
-----
    pip install -e ".[oauth]"           # if you haven't already
    python scripts/get_oauth_token.py

1. Go to https://console.cloud.google.com/
2. Enable **Gmail API** and **Google Ads API**
3. Add both scopes to OAuth consent screen:
   - ``https://www.googleapis.com/auth/gmail.readonly``
   - ``https://www.googleapis.com/auth/adwords``
4. Create OAuth credentials → **Desktop app** → download JSON
5. Run this script, paste the path to that JSON when prompted

The token grants:
- Gmail read-only access (search inbox, download messages)
- Google Ads billing access
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/adwords",
]


def _resolve_path(prompt: str, *, must_exist: bool, default: str | None = None) -> Path:
    while True:
        raw = input(prompt).strip()
        if not raw:
            if default is not None:
                p = Path(default).expanduser().resolve()
                if must_exist and not p.is_file():
                    print(f"  Not a file: {p}", file=sys.stderr)
                    continue
                return p
            continue
        p = Path(raw).expanduser().resolve()
        if must_exist and not p.is_file():
            print(f"  Not a file: {p}", file=sys.stderr)
            continue
        return p


def main() -> int:
    print("=" * 60)
    print("Google API OAuth token generator (Gmail + Google Ads)")
    print("=" * 60)
    print()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "Missing google-auth-oauthlib. Install it with:\n"
            "  pip install -e \".[oauth]\"",
            file=sys.stderr,
        )
        return 1

    secrets = _resolve_path(
        "Path to client_secret.json (from Google Cloud Console):\n"
        "  (default: ~/Downloads/client_secret.json)\n> ",
        must_exist=True,
        default="~/Downloads/client_secret.json",
    )

    default_token = Path.home() / ".google" / "oauth_token.json"
    print()
    print(
        f"Token output path (default: {default_token}):"
    )
    token_out = _resolve_path("> ", must_exist=False, default=str(default_token))
    if not token_out:
        token_out = default_token
    token_out.parent.mkdir(parents=True, exist_ok=True)

    print()
    print(f"Opening browser for {secrets} ...")
    for s in SCOPES:
        print(f"  Scope: {s}")
    print("Log in as chaehan.so@gmail.com and click Allow.")
    print()

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
        creds = flow.run_local_server(port=0)
    except Exception as e:
        print(f"OAuth flow failed: {e}", file=sys.stderr)
        return 1

    token_out.write_text(creds.to_json(), encoding="utf-8")
    token_out.chmod(0o600)

    print()
    print("✅ Token saved!")
    print(f"   File: {token_out}")
    print()
    print("Export this in your shell profile (~/.bash_profile, ~/.zshrc, etc.):")
    print(f'   export GOOGLE_OAUTH_TOKEN="{token_out}"')
    print()
    print("Then verify it works:")
    print("   googleads-invoice list-billing-mail")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
