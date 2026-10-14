# SPDX-License-Identifier: GPL-3.0-or-later
"""Put the host stubs on sys.path (only when the real host is absent) and
provide an offscreen QApplication for Qt tests."""
import os
import sys
from pathlib import Path

import pytest

STUBS = Path(__file__).parent / "stubs"
DATA = Path(__file__).parent / "data"
try:
    import core.mesh  # noqa: F401  (real IngeTrazo present?)
except ImportError:
    sys.path.insert(0, str(STUBS))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def data_dir():
    return DATA
