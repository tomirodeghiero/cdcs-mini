"""Fixtures for the TypeScript-side language tests.

Every test in this package spawns the ``ts-runtime/`` Node helper as a
subprocess. If Node + ``npm install`` haven't been run we skip the whole
module cleanly so the broader Python suite still passes on a minimal
checkout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cdcs_mini.language.typescript._runtime import ts_runtime_available

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "ts"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip TS-side tests when the Node runtime isn't installed."""
    _ = config
    if ts_runtime_available():
        return
    skip = pytest.mark.skip(reason="ts-runtime not installed (run `make ts-install`)")
    for item in items:
        item.add_marker(skip)


@pytest.fixture(scope="module")
def ts_fixtures_dir() -> Path:
    return FIXTURES_DIR
