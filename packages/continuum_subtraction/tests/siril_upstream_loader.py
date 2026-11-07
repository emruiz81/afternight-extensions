"""Load an upstream Siril script for parity tests, with sirilpy and the GUI toolkits stubbed out.

Set ``SIRIL_SCRIPTS_CHECKOUT`` to a local clone of https://gitlab.com/free-astro/siril-scripts.git; otherwise the
sibling ``../siril-scripts`` of this repository is used. Tests skip when the script is missing.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHECKOUT = REPO_ROOT.parent / "siril-scripts"
STUBBED_MODULES = (
    "sirilpy",
    "PyQt6",
    "PyQt6.QtWidgets",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "matplotlib",
    "matplotlib.pyplot",
    "matplotlib.backends",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.figure",
)
# Stubbed only when not installed: the ports never use upstream's FITS file I/O.
OPTIONAL_STUBBED_MODULES = ("astropy", "astropy.io", "astropy.io.fits")


class _Dummy:
    """Stands in for any GUI class, instance, enum or function; subclassable and callable."""

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return _Dummy()

    def __getattr__(self, _name):
        return _Dummy()

    def __or__(self, _other):
        return self

    __ror__ = __or__

    def __bool__(self):
        return False


class _DummyModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Dummy


class _SirilConnectionError(Exception):
    pass


def checkout():
    return Path(os.environ.get("SIRIL_SCRIPTS_CHECKOUT", DEFAULT_CHECKOUT))


def load_upstream_script(relative_path, module_name):
    """Import ``relative_path`` from the checkout with stubs in place, or raise SkipTest when it is absent."""

    source = checkout() / relative_path
    if not source.is_file():
        raise unittest.SkipTest(f"Missing upstream Siril script: {source}; set SIRIL_SCRIPTS_CHECKOUT")

    stubbed = list(STUBBED_MODULES)
    if importlib.util.find_spec("astropy") is None:
        stubbed.extend(OPTIONAL_STUBBED_MODULES)
    originals = {name: sys.modules.get(name) for name in stubbed}
    sirilpy = types.ModuleType("sirilpy")
    sirilpy.ensure_installed = lambda *args, **kwargs: None
    sirilpy.check_module_version = lambda *args, **kwargs: True
    sirilpy.SirilInterface = _Dummy
    sirilpy.SirilConnectionError = _SirilConnectionError
    sirilpy.SirilError = _SirilConnectionError
    sirilpy.NoImageError = _SirilConnectionError
    sirilpy.LogColor = types.SimpleNamespace(GREEN="green", RED="red", BLUE="blue", YELLOW="yellow", DEFAULT="default")
    sys.modules["sirilpy"] = sirilpy
    for name in stubbed[1:]:
        sys.modules[name] = _DummyModule(name)
    try:
        spec = importlib.util.spec_from_file_location(module_name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
    return module
