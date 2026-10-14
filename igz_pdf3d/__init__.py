# SPDX-License-Identifier: GPL-3.0-or-later
"""igz_pdf3d — export the selection or the visible model as a 3D PDF.

Entry point only. IngeTrazo instantiates every ``Tool`` subclass defined in
this module with no arguments, so no Tool lives here: the wiring is in
``_core.py``.
"""
from __future__ import annotations

KEY = "igz_pdf3d"
EXT_VERSION = 1
__version__ = "1.0.1"


def setup(app):
    """Extension API v2 entry point, called once when the main window exists."""
    from ._core import setup as _setup
    _setup(app)
