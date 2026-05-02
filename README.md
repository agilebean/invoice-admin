# googleads-invoice-glugglejug

Skeleton repository for Gmail → billed Google Ads UI (headed Brave/Chromium) → PDF handling → emailing **[jack.copeland@theglugglejugfactory.com](mailto:jack.copeland@theglugglejugfactory.com)** from **`chaehan.so@gmail.com`**.

Iteration 1 adds a **`src/`** package layout and **pytest** baseline; further slices (Gmail, Selenium, PDF, CLI) live in **[`PLAN.md`](PLAN.md)**.

## Development

Requires **Python 3.12+**.

### venv + pip

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

### uv (optional)

```bash
uv venv --python 3.12
source .venv/bin/activate  # Windows: .venv\Scripts\activate.ps1
uv pip install -e ".[dev]"
pytest
```

CI runs the same install and **`pytest`** on push and pull requests (see `.github/workflows/ci.yml`). **`@pytest.mark.e2e`** browser tests are **skipped in CI** and **skipped locally** unless you set **`RUN_E2E=1`**.

### Browser / e2e (optional, local)

Requires **Chrome** or **Chromium** on `PATH` (Selenium 4 manages **ChromeDriver** automatically in most setups). For a **headless** run (no window), set **`HEADLESS_E2E=1`**. To match production **Brave**, pass **`binary_location=`** into **`build_chrome_options`** from your install path.

```bash
RUN_E2E=1 pytest -m e2e
# or headless:
HEADLESS_E2E=1 RUN_E2E=1 pytest -m e2e
```

**Manual fallback:** if automated download is flaky (corporate policies, `file:` restrictions), use the headed browser yourself: open the billing URL with the same **download directory** and **user-data-dir** policy as in **`PLAN.md`**, then place the saved PDF where the CLI expects it once Iteration 7 wires paths.

## Repository

**Remote:** [`https://github.com/SoHu-Labs/googleads-invoice-glugglejug.git`](https://github.com/SoHu-Labs/googleads-invoice-glugglejug.git)

## Contents

| Item | Purpose |
|------|---------|
| `README.md` | Repo overview + local/CI run instructions |
| `PLAN.md` | Goal, backlog, agile iterations, strict TDD + regression posture |
| `pyproject.toml` | Package + pytest config |
| `src/googleads_invoice/` | Application package (Iteration 1: layout + version) |
| `tests/` | Fast pytest suite |
| `.github/workflows/ci.yml` | GitHub Actions — pytest |
| `LICENSE` | MIT (SoHu-Labs, 2026) |
| `.gitignore` | Python / env / tooling cruft |

## License

[MIT License](LICENSE) — Copyright (c) 2026 SoHu-Labs.
