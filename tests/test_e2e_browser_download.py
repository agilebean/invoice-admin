import os
from pathlib import Path

import pytest
from selenium import webdriver

from invoice_admin.googleads.browser_download import (
    build_chrome_options,
    click_and_wait_for_pdf,
)


@pytest.mark.e2e
def test_e2e_download_pdf_via_local_file_link(tmp_path: Path) -> None:
    """Click a file:// PDF link and assert a .pdf lands in the download directory."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    fixture_pdf = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf"
        / "invoice_eur_dot_decimal.pdf"
    )
    assert fixture_pdf.is_file()
    page = tmp_path / "page.html"
    page.write_text(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>fixture</title></head><body>
<a id="invoice-dl" href="{fixture_pdf.as_uri()}" download>Download PDF</a>
</body></html>""",
        encoding="utf-8",
    )
    headless = os.environ.get("HEADLESS_E2E", "") == "1"
    opts = build_chrome_options(download_dir=download_dir, headless=headless)
    driver = webdriver.Chrome(options=opts)
    try:
        saved = click_and_wait_for_pdf(
            driver,
            page_url=page.as_uri(),
            link_id="invoice-dl",
            download_dir=download_dir,
            timeout_s=90,
        )
    finally:
        driver.quit()
    assert saved.suffix.lower() == ".pdf"
    assert saved.stat().st_size > 0
