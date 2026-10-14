# SPDX-License-Identifier: GPL-3.0-or-later
"""The export dialog and its worker thread.

The scene is read on the main thread (``_collect``) into plain data; the
worker only encodes (U3D, views, PDF) and hands bytes back through a queued
``Signal(object)`` to a bound method, per the host's threading rule.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from ._collect import NothingToExport, collect, describe_selection
from ._pdf import write_pdf
from ._u3d import write_u3d
from ._views import make_views

log = logging.getLogger("ingetrazo.plugins.igz_pdf3d")

UNITS = [("Imperial (inches)", "in", "inches"), ("Metric (metres)", "m", "metres")]
PAGES = [("Letter landscape", "letter"), ("A4 landscape", "a4")]
POSTER_WIDTH_PX = 1600
UNTITLED = "Untitled model"


def document_path(app):
    win = getattr(app, "window", None)
    path = getattr(win, "_current_path", None) if win is not None else None
    return str(path) if path else None


class ExportWorker(QThread):
    progress = Signal(str)
    done = Signal(object)

    def __init__(self, scene_data: dict, options: dict, parent=None) -> None:
        super().__init__(parent)
        self.scene_data = scene_data
        self.options = options
        self.cancelled = False

    def run(self) -> None:
        try:
            self.progress.emit("Encoding 3D model…")
            u3d = write_u3d(self.scene_data)
            if self.cancelled:
                self.done.emit({"cancelled": True})
                return
            self.progress.emit("Writing PDF…")
            views = make_views(self.scene_data.get("camera"), self.scene_data["bbox"])
            pdf = write_pdf(self.options, u3d, views, self.scene_data.get("poster"),
                            self.scene_data.get("poster_size"))
            self.done.emit({"pdf": pdf, "fallbacks": list(self.scene_data.get("fallbacks") or [])})
        except Exception as ex:  # noqa: BLE001 — reported to the user, never raised across threads
            log.exception("igz_pdf3d: export failed")
            self.done.emit({"error": f"{type(ex).__name__}: {ex}"})


class ExportDialog(QDialog):
    def __init__(self, app, parent=None) -> None:
        super().__init__(parent)
        self.app = app
        self.worker = None
        self._written = None
        self.setWindowTitle("Export 3D PDF")
        self.setModal(False)

        self.scope = QLabel()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_scope)
        scope_row = QHBoxLayout()
        scope_row.addWidget(self.scope, 1)
        scope_row.addWidget(refresh)

        self.title = QLineEdit()
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional note shown under the title")
        self.units = QComboBox()
        for label, _code, _name in UNITS:
            self.units.addItem(label)
        self.page = QComboBox()
        for label, _key in PAGES:
            self.page.addItem(label)
        self.output = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output, 1)
        out_row.addWidget(browse)

        form = QFormLayout()
        form.addRow("Export", scope_row)
        form.addRow("Title", self.title)
        form.addRow("Note", self.note)
        form.addRow("Units", self.units)
        form.addRow("Page", self.page)
        form.addRow("Save as", out_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.status = QLabel()
        self.status.setWordWrap(True)

        self.export_button = QPushButton("Export")
        self.export_button.setDefault(True)
        self.export_button.clicked.connect(self.start_export)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.hide()
        self.open_button = QPushButton("Open PDF")
        self.open_button.clicked.connect(self._open_pdf)
        self.open_button.hide()
        self.folder_button = QPushButton("Show in folder")
        self.folder_button.clicked.connect(self._show_folder)
        self.folder_button.hide()
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.folder_button)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.export_button)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        self._inputs = [self.title, self.note, self.units, self.page, self.output, browse, refresh]

        self._apply_defaults()
        self.refresh_scope()

    # ---- defaults and options -------------------------------------------------
    def _apply_defaults(self) -> None:
        path = document_path(self.app)
        if path:
            p = Path(path)
            self.title.setText(p.stem or UNTITLED)
            self.output.setText(str(p.with_suffix(".pdf")))
        else:
            self.title.setText(UNTITLED)
            self.output.setText(str(Path.home() / f"{UNTITLED}.pdf"))

    def refresh_scope(self) -> None:
        try:
            self.scope.setText(describe_selection(self.app.scene))
        except Exception as ex:  # noqa: BLE001
            self.scope.setText(f"Cannot read the model: {ex}")

    def output_path(self) -> str:
        return self.output.text().strip()

    def options(self) -> dict:
        _label, code, name = UNITS[max(self.units.currentIndex(), 0)]
        _plabel, page = PAGES[max(self.page.currentIndex(), 0)]
        return {"title": self.title.text().strip() or UNTITLED, "note": self.note.text().strip(),
                "date": _dt.date.today().isoformat(), "units": code, "units_label": name,
                "page": page}

    # ---- export ----------------------------------------------------------------
    def start_export(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        options = self.options()
        target = self.output_path()
        if not target:
            self.status.setText("Choose a file to save to.")
            return
        self._set_busy(True, "Collecting geometry…")
        try:
            poster_size = (POSTER_WIDTH_PX, None)     # the PDF letterboxes the snapshot
            data = collect(self.app.scene, options["units"], getattr(self.app, "viewport", None),
                           poster_size)
        except NothingToExport as ex:
            self._set_busy(False, str(ex))
            return
        except Exception as ex:  # noqa: BLE001 — reading the model failed
            log.exception("igz_pdf3d: collect failed")
            self._set_busy(False, f"Could not read the model: {type(ex).__name__}: {ex}")
            return
        self._written = None
        self.worker = ExportWorker(data, options, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.start()

    def _cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancelled = True
            self.status.setText("Cancelling…")

    def _on_progress(self, text: str) -> None:
        self.status.setText(text)

    def _on_done(self, result) -> None:
        result = result or {}
        if result.get("cancelled"):
            self._set_busy(False, "Export cancelled.")
            return
        if "error" in result:
            self._set_busy(False, f"Export failed: {result['error']} (see IngeTrazo's log folder).")
            return
        target = self.output_path()
        try:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(result["pdf"])
        except Exception as ex:  # noqa: BLE001 — disk full, locked file, bad path
            log.exception("igz_pdf3d: write failed")
            try:
                if os.path.exists(target):
                    os.remove(target)
            except OSError:
                pass
            self._set_busy(False, f"Could not write {target}: {ex}")
            return
        self._written = target
        note = ""
        if result.get("fallbacks"):
            note = " Textures not exported (colour used instead): " + "; ".join(result["fallbacks"])
        self._set_busy(False, f"Saved {target}.{note}")
        self.open_button.show()
        self.folder_button.show()
        vp = getattr(self.app, "viewport", None)
        flash = getattr(vp, "flash_status", None)
        if callable(flash):
            try:
                flash(f"3D PDF saved: {target}", 4000)
            except Exception:  # noqa: BLE001
                pass

    def _set_busy(self, busy: bool, text: str) -> None:
        for w in self._inputs:
            w.setEnabled(not busy)
        self.export_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.progress.setVisible(busy)
        if busy:
            self.open_button.hide()
            self.folder_button.hide()
        self.status.setText(text)

    # ---- buttons ---------------------------------------------------------------
    def _browse(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Save 3D PDF", self.output_path(),
                                                    "PDF files (*.pdf)")
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self.output.setText(path)

    def _open_pdf(self) -> None:
        if self._written:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._written))

    def _show_folder(self) -> None:
        if self._written:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self._written).parent)))
