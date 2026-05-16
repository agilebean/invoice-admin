"""Deprecated shim — use ``from invoice_admin.googleads import ...`` instead.

A ``sys.meta_path`` finder redirects ``googleads_invoice.<sub>`` imports to
``invoice_admin.googleads.<sub>``.  Only **one** module object exists, so
``@patch`` / ``monkeypatch`` on either import path works identically.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys

__version__ = "0.0.0"
__all__: list[str] = []

_PREFIX = "googleads_invoice."
_TARGET = "invoice_admin.googleads."
_TAG = "_googleads_invoice_shim_v5"
# Submodule names that live in *this* package directory (not redirected).
_SELF_MODULES: frozenset[str] = frozenset({"__main__", "__init__"})


class _RedirectFinder(importlib.abc.MetaPathFinder):
    """Intercept ``googleads_invoice.<sub>`` → ``invoice_admin.googleads.<sub>``."""

    _tag = _TAG

    def find_spec(self, fullname: str, path, target=None):
        if fullname == "googleads_invoice" or not fullname.startswith(_PREFIX):
            return None
        sub = fullname[len(_PREFIX) :]
        if sub in _SELF_MODULES:
            return None
        redirected = _TARGET + sub
        try:
            real_mod = importlib.import_module(redirected)
        except ImportError:
            return None
        sys.modules[fullname] = real_mod

        loader = _AliasLoader(real_mod)
        spec = importlib.machinery.ModuleSpec(fullname, loader, is_package=_is_package(real_mod))
        spec.submodule_search_locations = getattr(real_mod, "__path__", None)
        return spec


def _is_package(mod):
    return getattr(getattr(mod, "__spec__", None), "submodule_search_locations", None) is not None


class _AliasLoader(importlib.abc.Loader):
    """Loader that returns the already-imported real module in ``create_module``."""

    def __init__(self, real_mod):
        self._real_mod = real_mod

    def create_module(self, spec):
        # Return the real module so importlib does NOT create a new empty one.
        return self._real_mod

    def exec_module(self, module):
        # Module was already executed during the real import above.
        pass


if not any(getattr(f, "_tag", None) == _TAG for f in sys.meta_path):
    sys.meta_path.insert(0, _RedirectFinder())
