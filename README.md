# googleads-invoice-glugglejug

Skeleton repository for Gmail → billed Google Ads UI (headed Brave/Chromium) → PDF handling → emailing **[jack.copeland@theglugglejugfactory.com](mailto:jack.copeland@theglugglejugfactory.com)** from **`chaehan.so@gmail.com`**.

Iteration 1 adds a **`src/`** package layout and **pytest** baseline; further slices (Gmail, Selenium, PDF, CLI) live in **[`PLAN.md`](PLAN.md)**.

## Development

Requires **Python 3.12+**. **Use [mamba](https://mamba.readthedocs.io/)** (conda-forge); do **not** use a project-local **`python -m venv`**.

### mamba environment

From the repo root:

```bash
mamba env create -f environment.yml   # first time
# or refresh after editing environment.yml:
mamba env update -f environment.yml --prune

mamba activate googleads-invoice-glugglejug
pip install -e ".[dev]"
pytest
```

Python packaging dependencies stay in **`pyproject.toml`**; **`environment.yml`** only pins the **Python + pip** base from conda-forge.

### Daily use (bash)

**`gig`** = same pattern as **`swim`**: **`export gig=<this-repo>`** and **`alias gig='mamba activate googleads-invoice-glugglejug && cd "$gig"'`** in **`~/.bash_aliases`**—no separate **`.bash`** file.
The **`export`** is **`cd`**’s path; single-quoted **`alias`** so **`"$gig"`** expands when you **run** **`gig`**, not when the alias is defined. **macOS:** load **`~/.bash_aliases`** from **`~/.bash_profile`** (see **`~/.cursor/rules/shell-bash-aliases.mdc`**).

```bash
export gig=/path/to/googleads-invoice-glugglejug
alias gig='mamba activate googleads-invoice-glugglejug && cd "$gig"'
```
CI runs **GitHub Actions** **`setup-python`** + **`pip install -e ".[dev]"`** + **`pytest`** (see `.github/workflows/ci.yml`). **`@pytest.mark.e2e`** browser tests are **skipped in CI** and **skipped locally** unless you set **`RUN_E2E=1`**.

### CLI (`dry-run`)

After **`pip install -e ".[dev]"`** in the active mamba env, print **billing URL**, **parsed PDF fields**, and **email/filename** artifacts (no browser, no Gmail):

```bash
googleads-invoice dry-run \
  --mail-html tests/fixtures/gmail/billing_mail_happy.html \
  --invoice-pdf tests/fixtures/pdf/invoice_eur_dot_decimal.pdf \
  --month-label "March 2026"
```

Equivalent: **`python -m googleads_invoice dry-run ...`** (works whenever the package is installed).

**`googleads-invoice: command not found`:** run **`mamba activate googleads-invoice-glugglejug`**, then **`pip install -e ".[dev]"`** again if entry points changed. The script is under **`$CONDA_PREFIX/bin/googleads-invoice`** on Unix; you can call **`python -m googleads_invoice ...`** if **`PATH`** is wrong.

### Browser / e2e (optional, local)

Requires **Chrome** or **Chromium** on `PATH` (Selenium 4 manages **ChromeDriver** automatically in most setups). For a **headless** run (no window), set **`HEADLESS_E2E=1`**. To match production **Brave**, pass **`binary_location=`** into **`build_chrome_options`** from your install path.

```bash
RUN_E2E=1 pytest -m e2e
# or headless:
HEADLESS_E2E=1 RUN_E2E=1 pytest -m e2e
```

**Manual fallback:** if automated download is flaky (corporate policies, `file:` restrictions), use the headed browser yourself: open the billing URL with the same **download directory** and **user-data-dir** policy as in **`PLAN.md`**, then pass the saved PDF path to **`googleads-invoice dry-run --invoice-pdf ...`**.

## Repository

**Remote:** [`https://github.com/SoHu-Labs/googleads-invoice-glugglejug.git`](https://github.com/SoHu-Labs/googleads-invoice-glugglejug.git)

## Contents

| Item | Purpose |
|------|---------|
| `README.md` | Repo overview + local/CI run instructions |
| `environment.yml` | **mamba** env (Python 3.12 + pip); app deps via **`pip install -e ".[dev]"`** |
| `PLAN.md` | Goal, backlog, agile iterations, strict TDD + regression posture |
| `pyproject.toml` | Package + pytest config |
| `src/googleads_invoice/` | Application package |
| `tests/` | Fast pytest suite |
| `.github/workflows/ci.yml` | GitHub Actions — pytest |
| `LICENSE` | MIT (SoHu-Labs, 2026) |
| `.gitignore` | Python / env / tooling cruft |

## License

[MIT License](LICENSE) — Copyright (c) 2026 SoHu-Labs.
