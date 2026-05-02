"""Tests for Chrome download options (no browser required)."""

from pathlib import Path

from googleads_invoice.browser_download import (
    build_chrome_options,
    build_chrome_options_for_remote_debugging,
)


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


def test_build_chrome_options_for_remote_debugging_sets_debugger_address(
    tmp_path: Path,
) -> None:
    opts = build_chrome_options_for_remote_debugging(
        debugger_address="127.0.0.1:9222",
        download_dir=tmp_path / "dl",
    )
    assert opts.experimental_options.get("debuggerAddress") == "127.0.0.1:9222"
    prefs = opts.experimental_options.get("prefs", {})
    assert "download.default_directory" in prefs


def test_build_chrome_options_for_remote_debugging_no_download_dir() -> None:
    opts = build_chrome_options_for_remote_debugging(
        debugger_address=" localhost:9222 ",
    )
    assert opts.experimental_options.get("debuggerAddress") == "localhost:9222"
    assert "prefs" not in opts.experimental_options
