"""Tests for Chrome download options (no browser required)."""

from pathlib import Path

from googleads_invoice.browser_download import build_chrome_options


def test_build_chrome_options_sets_download_prefs(tmp_path: Path) -> None:
    dl = tmp_path / "downloads"
    opts = build_chrome_options(download_dir=dl)
    prefs = opts.experimental_options.get("prefs", {})
    assert prefs["download.default_directory"] == str(dl.resolve())
    assert prefs["download.prompt_for_download"] is False
    assert prefs.get("plugins.always_open_pdf_externally") is True


def test_build_chrome_options_user_data_dir(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    dl = tmp_path / "downloads"
    opts = build_chrome_options(download_dir=dl, user_data_dir=profile)
    args = opts.arguments
    assert any(str(profile.resolve()) in a for a in args if a.startswith("--user-data-dir="))


def test_build_chrome_options_binary_location_passthrough(tmp_path: Path) -> None:
    opts = build_chrome_options(
        download_dir=tmp_path / "dl",
        binary_location="/usr/bin/chromium",
    )
    assert opts.binary_location == "/usr/bin/chromium"
