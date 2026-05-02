import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    ci = os.environ.get("CI", "").lower() in ("1", "true", "yes")
    github = str(os.environ.get("GITHUB_ACTIONS", "")).lower() in ("1", "true", "yes")
    run_e2e = os.environ.get("RUN_E2E", "") == "1"
    if ci or github or not run_e2e:
        skip = pytest.mark.skip(
            reason="e2e: set RUN_E2E=1 and install Chrome/Chromium (see README); skipped in CI",
        )
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip)
