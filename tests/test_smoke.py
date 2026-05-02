"""Baseline smoke: package importable (Iteration 1)."""


def test_googleads_invoice_package_importable() -> None:
    import importlib

    mod = importlib.import_module("googleads_invoice")
    assert mod.__version__ == "0.0.0"
