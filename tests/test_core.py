# SPDX-License-Identifier: GPL-3.0-or-later
from PySide6.QtWidgets import QMainWindow, QToolBar

from igz_pdf3d import _core
from core.scene import Scene


class FakeApp:
    def __init__(self, window):
        self.window = window
        self.viewport = None
        self.scene = Scene()
        self.menu_actions = []

    def add_menu_action(self, text, fn, shortcut=None, tip=None):
        self.menu_actions.append((text, fn, shortcut, tip))
        return object()


def test_setup_installs_toolbar_and_menu(qapp):
    win = QMainWindow()
    app = FakeApp(win)
    _core.setup(app)
    tb = win.findChild(QToolBar, _core.TOOLBAR_NAME)
    assert tb is not None
    assert [a.text() for a in tb.actions()] == ["3D PDF"]
    assert [t for t, *_ in app.menu_actions] == ["Export 3D PDF…"]
    _core.setup(app)                                  # idempotent
    assert len(win.findChildren(QToolBar, _core.TOOLBAR_NAME)) == 1


def test_setup_survives_a_window_without_toolbars(qapp):
    app = FakeApp(window=None)
    _core.setup(app)
    assert [t for t, *_ in app.menu_actions] == ["Export 3D PDF…"]


def test_icons_load(qapp):
    win = QMainWindow()
    assert not _core.load_icon("tb_pdf3d", win).isNull()
