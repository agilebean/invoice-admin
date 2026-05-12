"""Tests for invoice_admin.core.config."""
from __future__ import annotations

from pathlib import Path

import pytest

from invoice_admin.core.config import InvoiceConfig, load_config, repo_root
from invoice_admin.core.errors import ConfigError


def _write_repo_layout(root: Path) -> None:
    (root / "pyproject.toml").write_text('[project]\nname = "t"\n', encoding="utf-8")
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "default.yaml").write_text(
        "\n".join(
            [
                "dry_run: true",
                "max_auto_amount_eur: 1500",
                "classifier_min_confidence: 0.8",
                "models:",
                "  fast: my-fast",
                "notify:",
                "  ntfy_topic: yaml-topic",
                "paths:",
                f"  state_dir: {root / 'state'}",
                f"  invoices_root: {root / 'Invoices'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    handlers = cfg / "handlers"
    handlers.mkdir(parents=True)
    (handlers / "sepa_vr_landau.yaml").write_text(
        "dry_run: true\nblz: '54061170'\nfints_endpoint: 'https://example.invalid'\n",
        encoding="utf-8",
    )


def test_repo_root_respects_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_repo_layout(tmp_path)
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    assert repo_root() == tmp_path.resolve()


def test_load_config_paths_and_sepa_env_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_repo_layout(tmp_path)
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("INVOICE_ADMIN_IBAN_SELF", "DE00000000000000000000")
    monkeypatch.setenv("INVOICE_ADMIN_ACCOUNT_HOLDER", "Test User")
    monkeypatch.setenv("FINTS_PIN", "secret-pin")
    monkeypatch.setenv("NTFY_TOPIC", "env-topic")

    cfg = load_config(tmp_path)
    assert isinstance(cfg, InvoiceConfig)
    assert cfg.paths.invoices_root == (tmp_path / "Invoices").resolve()
    assert cfg.paths.tracker_path == (tmp_path / "state" / "tracker.sqlite").resolve()
    assert cfg.paths.classifier_examples_path == (tmp_path / "config" / "classifier_examples.jsonl").resolve()
    assert cfg.models.fast == "my-fast"
    assert cfg.max_auto_amount_eur == 1500
    assert cfg.classifier_min_confidence == 0.8
    assert cfg.notify.ntfy_topic == "env-topic"

    sepa = cfg.raw["handlers"]["sepa_vr_landau"]
    assert sepa["iban_self"] == "DE00000000000000000000"
    assert sepa["account_holder"] == "Test User"
    assert sepa["fints_pin"] == "secret-pin"


def test_load_config_classifier_examples_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_repo_layout(tmp_path)
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    custom = tmp_path / "custom" / "examples.jsonl"
    default_yaml = tmp_path / "config" / "default.yaml"
    lines = default_yaml.read_text(encoding="utf-8").splitlines()
    inserted: list[str] = []
    for line in lines:
        inserted.append(line)
        if "invoices_root:" in line:
            inserted.append(f"  classifier_examples: {custom}")
    default_yaml.write_text("\n".join(inserted) + "\n", encoding="utf-8")

    cfg = load_config(tmp_path)
    assert cfg.paths.classifier_examples_path == custom.resolve()


def test_load_config_missing_default_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname=x\n", encoding="utf-8")
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    with pytest.raises(ConfigError):
        load_config(tmp_path)
