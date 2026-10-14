# SPDX-License-Identifier: GPL-3.0-or-later
"""Extension wiring: the toolbar button, the Extensions menu entry and the
one dialog instance per application window."""
from __future__ import annotations

import logging
import os

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPalette
from PySide6.QtWidgets import QToolBar

log = logging.getLogger("ingetrazo.plugins.igz_pdf3d")

TOOLBAR_NAME = "igz_pdf3d_toolbar"
BUTTON_TEXT = "3D PDF"
MENU_TEXT = "Export 3D PDF…"
TIP = "Export the selection or the whole visible model as a 3D PDF."
_ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
_SESSIONS: dict = {}


def _deferred(fn):
    """A slot that runs ``fn`` on the next event-loop turn and ignores the
    ``checked`` bool Qt may pass to a triggered handler."""
    return lambda _checked=False, f=fn: QTimer.singleShot(0, f)


def load_icon(name: str, window) -> QIcon:
    """icons/<name>.svg (light strokes) for a dark palette, <name>_light.svg
    for a light one; either file serves as the fallback for the other."""
    dark = True
    try:
        dark = window.palette().color(QPalette.Window).lightness() < 128
    except Exception:  # noqa: BLE001
        pass
    order = [f"{name}.svg", f"{name}_light.svg"] if dark else [f"{name}_light.svg", f"{name}.svg"]
    for fn in order:
        path = os.path.join(_ICONS, fn)
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()


class Session:
    def __init__(self, app) -> None:
        self.app = app
        self.dialog = None

    def open_dialog(self) -> None:
        from ._dialog import ExportDialog
        if self.dialog is None:
            self.dialog = ExportDialog(self.app, parent=getattr(self.app, "window", None))
        self.dialog.refresh_scope()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()


def _install_toolbar(app, session: Session):
    win = getattr(app, "window", None)
    if win is None or not hasattr(win, "addToolBar"):
        return None
    if win.findChild(QToolBar, TOOLBAR_NAME) is not None:
        return None
    tb = None
    maker = getattr(win, "_new_toolbar", None)
    if callable(maker):
        try:
            tb = maker(BUTTON_TEXT, TOOLBAR_NAME)
        except Exception:  # noqa: BLE001 — fall back to a plain toolbar
            tb = None
    if tb is None:
        tb = QToolBar(BUTTON_TEXT, win)
        tb.setObjectName(TOOLBAR_NAME)
        tb.setMovable(True)
        tb.setFloatable(True)
        px = 24
        try:
            from views.icons import toolbar_icon_px
            px = toolbar_icon_px()
        except Exception:  # noqa: BLE001
            pass
        tb.setIconSize(QSize(px, px))
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        win.addToolBar(Qt.TopToolBarArea, tb)
    act = QAction(load_icon("tb_pdf3d", win), BUTTON_TEXT, win)
    act.setToolTip(TIP)
    act.setStatusTip(TIP)
    act.triggered.connect(_deferred(session.open_dialog))
    tb.addAction(act)
    tb._igz_pdf3d_refs = [act]
    return tb


def setup(app) -> None:
    session = _SESSIONS.get(id(app))
    if session is None:
        session = _SESSIONS[id(app)] = Session(app)
    try:
        _install_toolbar(app, session)
    except Exception:  # noqa: BLE001 — the menu entry still works
        log.exception("igz_pdf3d: toolbar install failed")
    try:
        app.add_menu_action(MENU_TEXT, session.open_dialog, None, tip=TIP)
    except Exception:  # noqa: BLE001
        log.exception("igz_pdf3d: menu entry failed")
