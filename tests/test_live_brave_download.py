"""Tests for live_brave_download module (pure logic + CLI wiring; WebDriver mocked in CI)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from invoice_admin.googleads.live_brave_download import (
    LiveBraveDownloadError,
    _find_download_on_documents_page,
    _new_completed_pdf,
    live_brave_download_pdf,
)


# ── _find_download_on_documents_page ────────────────────────────────────


def make_mock_element(displayed: bool = True) -> MagicMock:
    el = MagicMock()
    el.is_displayed.return_value = displayed
    el.tag_name = "button"
    return el


class TestFindDownloadOnDocumentsPage:
    def test_finds_by_aria_label_starting_with_download(self) -> None:
        driver = MagicMock()
        el = make_mock_element()
        # Return empty list for all selectors except the first aria-label one
        driver.find_elements.side_effect = lambda by, sel: {
            '//*[starts-with(@aria-label, "Download")]': [el],
        }.get(sel, [])
        result = _find_download_on_documents_page(driver)
        assert result is el

    def test_finds_by_link_text_download(self) -> None:
        driver = MagicMock()
        el = make_mock_element()
        driver.find_elements.side_effect = lambda by, sel: {
            '//*[starts-with(@aria-label, "Download")]': [],
            '//a[contains(text(), "Download")]': [el],
        }.get(sel, [])
        result = _find_download_on_documents_page(driver)
        assert result is el

    def test_finds_button_with_download_text(self) -> None:
        driver = MagicMock()
        el = make_mock_element()
        driver.find_elements.side_effect = lambda by, sel: {
            '//*[starts-with(@aria-label, "Download")]': [],
            '//a[contains(text(), "Download")]': [],
            '//button[contains(text(), "Download")]': [el],
        }.get(sel, [])
        result = _find_download_on_documents_page(driver)
        assert result is el

    def test_raises_live_brave_download_error_when_nothing_found(self) -> None:
        driver = MagicMock()
        driver.find_elements.return_value = []
        driver.execute_script.return_value = None  # JS fallback returns nothing
        with pytest.raises(
            LiveBraveDownloadError,
            match="No download button found",
        ):
            _find_download_on_documents_page(driver)

    def test_uses_visible_elements_over_hidden(self) -> None:
        driver = MagicMock()
        hidden = make_mock_element(displayed=False)
        visible = make_mock_element(displayed=True)
        # Return both hidden and visible for the aria-label selector
        driver.find_elements.return_value = [hidden, visible]
        result = _find_download_on_documents_page(driver)
        # Should pick the visible one (first visible in the returned list)
        assert result is visible

    def test_skips_hidden_elements(self) -> None:
        driver = MagicMock()
        hidden = make_mock_element(displayed=False)
        driver.find_elements.return_value = [hidden]
        driver.execute_script.return_value = None  # JS fallback returns nothing
        with pytest.raises(LiveBraveDownloadError):
            _find_download_on_documents_page(driver)

    def test_finds_by_span_with_download_text(self) -> None:
        driver = MagicMock()
        el = make_mock_element()
        driver.find_elements.side_effect = lambda by, sel: {
            '//*[starts-with(@aria-label, "Download")]': [],
            '//a[contains(text(), "Download")]': [],
            '//button[contains(text(), "Download")]': [],
            '//span[contains(text(), "Download")]': [el],
        }.get(sel, [])
        result = _find_download_on_documents_page(driver)
        assert result is el

    def test_finds_by_role_button_with_download_label(self) -> None:
        driver = MagicMock()
        el = make_mock_element()
        driver.find_elements.side_effect = lambda by, sel: {
            '//*[starts-with(@aria-label, "Download")]': [],
            '//a[contains(text(), "Download")]': [],
            '//button[contains(text(), "Download")]': [],
            '//span[contains(text(), "Download")]': [],
            '//*[@role="button" and contains(@aria-label, "Download")]': [el],
        }.get(sel, [])
        result = _find_download_on_documents_page(driver)
        assert result is el


# ── _new_completed_pdf ─────────────────────────────────────────────────


class TestNewCompletedPdf:
    def _snap(self, p: Path) -> tuple[Path, tuple[int, float]]:
        st = p.stat()
        return (p.resolve(), (st.st_size, st.st_mtime))

    def test_ignores_pre_existing_unchanged_pdf(self, tmp_path: Path) -> None:
        """A PDF that existed at click time with the same size must not be picked.

        Regression: the old wait loop compared st_mtime (wall clock) against
        ``time.monotonic()``, so any old PDF matched and was returned immediately.
        """
        old = tmp_path / "old_report.pdf"
        old.write_bytes(b"%PDF-1.4 stale")
        before = dict([self._snap(old)])
        assert _new_completed_pdf(tmp_path, before=before) is None

    def test_returns_new_pdf(self, tmp_path: Path) -> None:
        old = tmp_path / "old_report.pdf"
        old.write_bytes(b"%PDF-1.4 stale")
        before = dict([self._snap(old)])
        new = tmp_path / "invoice.pdf"
        new.write_bytes(b"%PDF-1.4 fresh")
        assert _new_completed_pdf(tmp_path, before=before) == new.resolve()

    def test_returns_pdf_that_grew_since_snapshot(self, tmp_path: Path) -> None:
        growing = tmp_path / "invoice.pdf"
        growing.write_bytes(b"partial")
        before = dict([self._snap(growing)])
        growing.write_bytes(b"partial but now complete")
        assert _new_completed_pdf(tmp_path, before=before) == growing.resolve()

    def test_returns_overwritten_pdf_with_same_size_and_newer_mtime(
        self, tmp_path: Path
    ) -> None:
        """A re-download that overwrites the file with identical bytes must still count.

        Regression: ``invoice send`` re-downloads the same monthly invoice, which
        overwrites the file in place (same path, same size, newer mtime). The old
        path+size comparison classified it as the pre-existing file, so the wait
        loop stalled at [5/6] until the 120s timeout.
        """
        import os
        import time

        invoice = tmp_path / "5678778429.pdf"
        invoice.write_bytes(b"%PDF-1.4 same invoice bytes")
        before = dict([self._snap(invoice)])
        time.sleep(0.02)
        os.utime(invoice, None)  # newer mtime, same path and size
        assert _new_completed_pdf(tmp_path, before=before) == invoice.resolve()

    def test_pending_crdownload_blocks_selection(self, tmp_path: Path) -> None:
        new = tmp_path / "invoice.pdf"
        new.write_bytes(b"%PDF-1.4 fresh")
        (tmp_path / "invoice.pdf.crdownload").write_bytes(b"")
        assert _new_completed_pdf(tmp_path, before={}) is None

    def test_picks_newest_among_multiple_new(self, tmp_path: Path) -> None:
        import os
        import time

        first = tmp_path / "a.pdf"
        first.write_bytes(b"%PDF-1.4 one")
        newest = tmp_path / "b.pdf"
        newest.write_bytes(b"%PDF-1.4 two")
        now = time.time()
        os.utime(first, (now - 10, now - 10))
        os.utime(newest, (now - 5, now - 5))
        assert _new_completed_pdf(tmp_path, before={}) == newest.resolve()


# ── live_brave_download_pdf ────────────────────────────────────────────


class TestLiveBraveDownloadPdf:
    def test_happy_path_downloads_pdf(self, tmp_path: Path) -> None:
        """Full happy path: attach, navigate, find button, click, PDF appears."""
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()

        fixture_pdf = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "pdf"
            / "invoice_eur_dot_decimal.pdf"
        )

        mock_driver = MagicMock()
        mock_driver.current_url = "https://ads.google.com/aw/billing/documents"
        mock_driver.window_handles = ["main"]

        mock_el = make_mock_element()
        mock_driver.find_elements.return_value = [mock_el]
        mock_driver.execute_cdp_cmd = MagicMock()

        with (
            patch(
                "invoice_admin.googleads.live_brave_download.chrome_driver_attach",
                return_value=mock_driver,
            ) as mock_attach,
        ):
            def _simulate_click(*args: object, **kwargs: object) -> None:
                # Copy the real fixture PDF into download dir (passes parse_invoice_pdf)
                import shutil
                shutil.copy2(fixture_pdf, download_dir / fixture_pdf.name)

            mock_el.click.side_effect = _simulate_click

            result_path = live_brave_download_pdf(
                debugger_address="127.0.0.1:9222",
                deeplink_url="https://c.gle/abc123",
                download_dir=download_dir,
                navigation_timeout_s=5,
                download_timeout_s=30,
            )

        mock_attach.assert_called_once_with(
            debugger_address="127.0.0.1:9222",
            download_dir=download_dir,
        )
        mock_driver.get.assert_called_once_with("https://c.gle/abc123")
        mock_driver.set_page_load_timeout.assert_called_once_with(5)
        mock_el.click.assert_called_once()
        assert result_path.suffix == ".pdf"
        assert result_path.stat().st_size > 0
        # Should be renamed to the final format
        assert "GoogleAds" in result_path.name or "google" in result_path.name.lower()

    def test_navigation_timeout_raises_and_saves_trace(self, tmp_path: Path) -> None:
        """If billing/documents doesn't appear, error includes trace paths."""
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()

        mock_driver = MagicMock()
        mock_driver.current_url = "https://accounts.google.com/signin"
        mock_driver.page_source = "<html>sign-in</html>"
        mock_driver.save_screenshot = MagicMock()

        with (
            patch(
                "invoice_admin.googleads.live_brave_download.chrome_driver_attach",
                return_value=mock_driver,
            ),
            patch(
                "invoice_admin.googleads.live_brave_download.save_live_brave_trace",
                return_value=(tmp_path / "trace.html", tmp_path / "trace.png"),
            ) as mock_save,
        ):
            with pytest.raises(LiveBraveDownloadError, match="Trace saved"):
                live_brave_download_pdf(
                    debugger_address="127.0.0.1:9222",
                    deeplink_url="https://c.gle/nope",
                    download_dir=download_dir,
                    navigation_timeout_s=0.1,
                )
        mock_save.assert_called_once()

    def test_page_load_timeout_raises_instead_of_hanging(self, tmp_path: Path) -> None:
        """A page load that never completes must surface as an error, not hang silently.

        Regression: ``driver.get`` had no page-load timeout, so a c.gle redirect into
        the ads.google.com documents SPA blocked for Selenium's 300s default with no
        output (run_month prints nothing between [3/7] and [4/7]).
        """
        from selenium.common.exceptions import TimeoutException

        download_dir = tmp_path / "downloads"
        download_dir.mkdir()

        mock_driver = MagicMock()
        mock_driver.current_url = "https://ads.google.com/aw/billing/documents"
        mock_driver.page_source = "<html>stuck</html>"
        mock_driver.save_screenshot = MagicMock()
        mock_driver.get.side_effect = TimeoutException("page load timed out")

        with (
            patch(
                "invoice_admin.googleads.live_brave_download.chrome_driver_attach",
                return_value=mock_driver,
            ),
            patch(
                "invoice_admin.googleads.live_brave_download.save_live_brave_trace",
                return_value=(tmp_path / "trace.html", tmp_path / "trace.png"),
            ) as mock_save,
        ):
            with pytest.raises(LiveBraveDownloadError, match="Trace saved"):
                live_brave_download_pdf(
                    debugger_address="127.0.0.1:9222",
                    deeplink_url="https://c.gle/hangs",
                    download_dir=download_dir,
                    navigation_timeout_s=45,
                )
        mock_driver.set_page_load_timeout.assert_called_once_with(45)
        mock_save.assert_called_once()

    def test_no_download_button_raises_and_saves_trace(self, tmp_path: Path) -> None:
        """If no download element found, error includes trace paths."""
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()

        mock_driver = MagicMock()
        mock_driver.current_url = "https://ads.google.com/aw/billing/documents"
        mock_driver.page_source = "<html>no download</html>"
        mock_driver.save_screenshot = MagicMock()
        mock_driver.find_elements.return_value = []  # no Download element
        mock_driver.execute_script.return_value = None  # JS fallback returns nothing

        with (
            patch(
                "invoice_admin.googleads.live_brave_download.chrome_driver_attach",
                return_value=mock_driver,
            ),
            patch(
                "invoice_admin.googleads.live_brave_download.save_live_brave_trace",
                return_value=(tmp_path / "trace.html", tmp_path / "trace.png"),
            ) as mock_save,
        ):
            with pytest.raises(
                LiveBraveDownloadError, match="couldn't locate the Download"
            ):
                live_brave_download_pdf(
                    debugger_address="127.0.0.1:9222",
                    deeplink_url="https://c.gle/nope",
                    download_dir=download_dir,
                    navigation_timeout_s=5,
                )
        mock_save.assert_called_once()

    def test_download_timeout_raises(self, tmp_path: Path) -> None:
        """If PDF never appears after click, error includes trace paths."""
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()

        mock_driver = MagicMock()
        mock_driver.current_url = "https://ads.google.com/aw/billing/documents"
        mock_driver.page_source = "<html>timeout</html>"
        mock_driver.save_screenshot = MagicMock()
        mock_el = make_mock_element()
        mock_driver.find_elements.return_value = [mock_el]

        with (
            patch(
                "invoice_admin.googleads.live_brave_download.chrome_driver_attach",
                return_value=mock_driver,
            ),
            patch(
                "invoice_admin.googleads.live_brave_download.save_live_brave_trace",
                return_value=(tmp_path / "trace.html", tmp_path / "trace.png"),
            ) as mock_save,
        ):
            with pytest.raises(LiveBraveDownloadError, match="No new PDF in"):
                live_brave_download_pdf(
                    debugger_address="127.0.0.1:9222",
                    deeplink_url="https://c.gle/nope",
                    download_dir=download_dir,
                    navigation_timeout_s=5,
                    download_timeout_s=0.1,
                )
        mock_save.assert_called_once()

    def test_download_dir_resolves_explicit_path(self) -> None:
        """download_dir is resolved before being passed to chrome_driver_attach."""
        download_dir = Path("/tmp/nonexistent-googleads-test")

        mock_driver = MagicMock()
        mock_driver.current_url = "https://ads.google.com/aw/billing/documents"
        mock_driver.page_source = "<html/>"
        mock_driver.find_elements.return_value = []
        # Return a string with "Download" so the 15s innerText wait passes immediately,
        # then return None for the JS fallback in _find_download_on_documents_page
        mock_driver.execute_script.side_effect = ["Page has Download here", None]

        with (
            patch(
                "invoice_admin.googleads.live_brave_download.chrome_driver_attach",
                return_value=mock_driver,
            ) as mock_attach,
            patch(
                "invoice_admin.googleads.live_brave_download.save_live_brave_trace",
                return_value=(Path("/tmp/t.html"), Path("/tmp/t.png")),
            ),
        ):
            with pytest.raises(LiveBraveDownloadError):
                live_brave_download_pdf(
                    debugger_address="127.0.0.1:9222",
                    deeplink_url="https://c.gle/x",
                    download_dir=download_dir,
                    navigation_timeout_s=0.1,
                )
            # The resolved path was passed to chrome_driver_attach
            call_dl_dir = mock_attach.call_args.kwargs["download_dir"]
            assert call_dl_dir.is_absolute()
