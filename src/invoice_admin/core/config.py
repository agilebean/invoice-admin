"""Config loader — frozen dataclass from YAML."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from invoice_admin.core.errors import ConfigError

_HANDLERS_DIR = "handlers"


@dataclass(frozen=True)
class PathsConfig:
    """Resolved filesystem paths for all invoice operations."""

    invoices_root: Path
    inbox_dir: Path
    foyer_claims_dir: Path
    sepa_transfers_dir: Path
    outgoing_dir: Path
    failures_dir: Path
    tracker_path: Path
    log_path: Path
    llm_calls_path: Path
    classifier_examples_path: Path


@dataclass(frozen=True)
class ModelConfig:
    """LLM model aliases."""

    fast: str
    smart: str
    cheap: str
    local: str


@dataclass(frozen=True)
class NotifyConfig:
    """Notification channel settings."""

    ntfy_topic: str | None
    pushover_user: str | None
    pushover_token: str | None


@dataclass(frozen=True)
class InvoiceConfig:
    """Full resolved config."""

    paths: PathsConfig
    models: ModelConfig
    notify: NotifyConfig
    dry_run: bool
    max_auto_amount_eur: int
    classifier_min_confidence: float
    raw: dict[str, Any]


def repo_root() -> Path:
    """Find repository root. Mirrors swim/common.py:repo_root()."""
    env = os.environ.get("INVOICE_ADMIN_REPO_ROOT")
    if env:
        return Path(env).resolve()

    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent

    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent

    raise RuntimeError(
        "Cannot find repo root: no pyproject.toml found. "
        "Set INVOICE_ADMIN_REPO_ROOT env var or run from within the repo."
    )


def _expand_path(value: str | Path | None, default: Path) -> Path:
    if value is None or value == "":
        return default
    p = Path(value).expanduser()
    if not p.is_absolute():
        return (Path.cwd() / p).resolve()
    return p.resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be a mapping: {path}")
    return data


def _merge_sepa_with_env(sepa: dict[str, Any]) -> dict[str, Any]:
    """Overlay secrets from env; YAML must never store these values."""
    merged = dict(sepa)
    merged["iban_self"] = os.environ.get("INVOICE_ADMIN_IBAN_SELF", "")
    merged["account_holder"] = os.environ.get("INVOICE_ADMIN_ACCOUNT_HOLDER", "")
    merged["fints_pin"] = os.environ.get("FINTS_PIN", "")
    return merged


def load_config(root: Path | None = None) -> InvoiceConfig:
    """Load default.yaml, handler YAMLs, overlay env vars, return frozen InvoiceConfig."""
    base = root if root is not None else repo_root()
    default_path = base / "config" / "default.yaml"
    cfg = _load_yaml(default_path)

    paths_block = cfg.get("paths") or {}
    if not isinstance(paths_block, dict):
        raise ConfigError("paths must be a mapping in default.yaml")

    home = Path.home()
    state_default = home / ".local/state/invoice_admin"
    state_dir = _expand_path(paths_block.get("state_dir"), state_default)
    invoices_default = home / "Documents" / "Invoices"
    env_root = os.environ.get("INVOICE_ADMIN_ROOT")
    invoices_root = _expand_path(
        env_root or paths_block.get("invoices_root"),
        invoices_default,
    )

    tracker_rel = paths_block.get("tracker_path")
    log_rel = paths_block.get("log_path")
    llm_calls_rel = paths_block.get("llm_calls_path")
    classifier_examples_rel = paths_block.get("classifier_examples")
    classifier_examples_default = base / "config" / "classifier_examples.jsonl"
    paths_cfg = PathsConfig(
        invoices_root=invoices_root,
        inbox_dir=invoices_root / "_inbox",
        foyer_claims_dir=invoices_root / "foyer_claims",
        sepa_transfers_dir=invoices_root / "sepa_transfers",
        outgoing_dir=invoices_root / "outgoing",
        failures_dir=invoices_root / "_failures",
        tracker_path=_expand_path(tracker_rel, state_dir / "tracker.sqlite"),
        log_path=_expand_path(log_rel, state_dir / "log.jsonl"),
        llm_calls_path=_expand_path(llm_calls_rel, state_dir / "llm_calls.sqlite"),
        classifier_examples_path=_expand_path(
            classifier_examples_rel,
            classifier_examples_default,
        ),
    )

    models_block = cfg.get("models") or {}
    if not isinstance(models_block, dict):
        raise ConfigError("models must be a mapping in default.yaml")
    models_cfg = ModelConfig(
        fast=str(models_block.get("fast", "claude-haiku-4-5")),
        smart=str(models_block.get("smart", "claude-opus-4-7")),
        cheap=str(models_block.get("cheap", "deepseek/deepseek-chat")),
        local=str(models_block.get("local", "ollama/llama3.1:70b")),
    )

    notify_block = cfg.get("notify") or {}
    if not isinstance(notify_block, dict):
        raise ConfigError("notify must be a mapping in default.yaml")
    notify_cfg = NotifyConfig(
        ntfy_topic=os.environ.get("NTFY_TOPIC") or notify_block.get("ntfy_topic"),
        pushover_user=os.environ.get("PUSHOVER_USER") or notify_block.get("pushover_user"),
        pushover_token=os.environ.get("PUSHOVER_TOKEN") or notify_block.get("pushover_token"),
    )

    dry_run = bool(cfg.get("dry_run", True))
    max_auto = int(cfg.get("max_auto_amount_eur", 2000))
    min_conf = float(cfg.get("classifier_min_confidence", 0.7))

    handlers_dir = base / "config" / _HANDLERS_DIR
    raw_handlers: dict[str, Any] = {}
    if handlers_dir.is_dir():
        for yml in sorted(handlers_dir.glob("*.yaml")):
            name = yml.stem
            loaded = _load_yaml(yml)
            if name == "sepa_vr_landau":
                loaded = _merge_sepa_with_env(loaded)
            raw_handlers[name] = loaded

    raw: dict[str, Any] = {"handlers": raw_handlers, "defaults": dict(cfg)}

    return InvoiceConfig(
        paths=paths_cfg,
        models=models_cfg,
        notify=notify_cfg,
        dry_run=dry_run,
        max_auto_amount_eur=max_auto,
        classifier_min_confidence=min_conf,
        raw=raw,
    )
