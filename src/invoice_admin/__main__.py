"""Entry point for python -m invoice_admin."""
from __future__ import annotations

import sys

from invoice_admin.cli import main

if __name__ == "__main__":
    sys.exit(main())
