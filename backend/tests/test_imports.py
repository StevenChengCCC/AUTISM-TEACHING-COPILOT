"""Regression guard: every module under ``app`` must import without error.

This catches import-time crashes (e.g. a method named ``list`` shadowing the
builtin so a later ``list[...]`` annotation raises at class-definition time)
automatically, instead of relying on manual discovery.
"""

import importlib
import pkgutil

import pytest

import app


def _all_app_modules() -> list[str]:
    names: list[str] = []
    for module in pkgutil.walk_packages(app.__path__, prefix="app."):
        names.append(module.name)
    return sorted(names)


@pytest.mark.parametrize("module_name", _all_app_modules())
def test_app_module_imports(module_name: str):
    importlib.import_module(module_name)
