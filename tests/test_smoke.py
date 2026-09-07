"""Baseline smoke: package importable (Iteration 1 + P1)."""

import importlib
import importlib.metadata


def test_invoice_admin_googleads_importable() -> None:
    """P1: ``import invoice_admin.googleads`` resolves the merged package."""
    mod = importlib.import_module("invoice_admin.googleads")
    assert hasattr(mod, "__all__")


def test_invoice_admin_version_matches_distribution_metadata() -> None:
    """§5.1 S2: ``invoice_admin.__version__`` matches installed ``invoice-admin`` dist version."""
    mod = importlib.import_module("invoice_admin")
    dist_ver = importlib.metadata.version("invoice-admin")
    assert dist_ver == mod.__version__


def test_googleads_invoice_shim_removed() -> None:
    """The legacy ``googleads_invoice`` shim package is gone."""
    import pytest

    with pytest.raises(ImportError):
        importlib.import_module("googleads_invoice")
