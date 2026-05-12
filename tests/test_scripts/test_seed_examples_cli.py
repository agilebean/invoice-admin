"""Smoke tests for ``scripts/seed_examples.py``."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "seed_examples.py"


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(REPO / "src")}


def test_seed_examples_help_exits_zero() -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=str(REPO),
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert "--invoice-type" in r.stdout


def test_seed_examples_missing_pdf_exits_nonzero(tmp_path: Path) -> None:
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--invoice-type",
            "unknown",
            str(tmp_path / "nope.pdf"),
        ],
        cwd=str(REPO),
        env={**_env(), "INVOICE_ADMIN_REPO_ROOT": str(REPO)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 2
