"""Allow ``python -m googleads_invoice``."""

from invoice_admin.googleads.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
