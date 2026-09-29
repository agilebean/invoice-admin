#!/usr/bin/env python3
"""Re-consent the shared Google OAuth token (Gmail + Google Ads).

The procedure now lives in agentkit so both repos use one implementation:
:mod:`agentkit.gmail.oauth` and ``scripts/gmail_oauth_consent.py`` there.
This wrapper keeps the old invoice-admin command working.

    pip install -e ".[oauth]"        # google-auth-oauthlib
    python scripts/get_oauth_token.py

Writes ~/.google/oauth_token.json (0600), the single token location read by
both agentkit and invoice-admin.
"""

from agentkit.gmail.oauth import main

if __name__ == "__main__":
    raise SystemExit(main())
