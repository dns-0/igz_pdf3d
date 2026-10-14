# SPDX-License-Identifier: GPL-3.0-or-later
import io
import time
from pathlib import Path

import pytest
from pypdf import PdfReader
from PySide6.QtGui import QImage, QVector3D

from igz_pdf3d import _dialog as D
from core.camera import OrbitCamera
from core.group import Group
from core.scene import Scene


def V(x, y, z):
    return QVector3D(x, y, z)


def add_box(mesh, origin=(0, 0, 0), size=1.0, attrs=None):
    ox, oy, oz = origin
    s = size
    p = [V(ox, oy, oz), V(ox + s, oy, oz), V(ox + s, oy + s, oz), V(ox, oy + s, oz),
         V(ox, oy, oz + s), V(ox + s, oy, oz + s), V(ox + s, oy + s, oz + s), V(ox, oy + s, oz + s)]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return [mesh.add_face([p[i] for i in q], attrs=attrs) for q in quads]


class FakeViewport:
    def __init__(self):
        self.camera = OrbitCamera()
        self.flashed = []

    def render_image(self, w, h=None):
        img = QImage(int(w), int(h or w), QImage.Format_RGB888)
        img.fill(0xFFFFFFFF)
        return img

    def flash_status(self, text, msec=2500):
        self.flashed.append(text)


class FakeWindow:
    def __init__(self, path):
        self._current_path = path


class FakeApp:
    def __init__(self, path, scene=None):
        self.window = FakeWindow(path)
        self.viewport = FakeViewport()
        self.scene = scene or Scene()


def _scene_with_box():
    scene = Scene()
    g = Group(name="Beam")
    add_box(g.mesh)
    scene.groups.append(g)
    return scene


def _wait(dialog, qapp, timeout=20.0):
    deadline = time.time() + timeout
    while dialog.worker is not None and dialog.worker.isRunning() and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    for _ in range(20):
        qapp.processEvents()


def test_defaults_from_document(qapp, tmp_path):
    app = FakeApp(str(tmp_path / "job.igz"), _scene_with_box())
    d = D.ExportDialog(app)
    assert d.title.text() == "job"
    assert Path(d.output_path()) == tmp_path / "job.pdf"
    assert d.scope.text() == "Whole visible model: 1 groups, 0 loose faces"
    opts = d.options()
    assert opts["units"] == "in" and opts["units_label"] == "inches" and opts["page"] == "letter"
    assert opts["title"] == "job" and len(opts["date"]) == 10


def test_defaults_without_document(qapp):
    app = FakeApp(None, _scene_with_box())
    d = D.ExportDialog(app)
    assert d.title.text() == "Untitled model"
    assert d.output_path().endswith("Untitled model.pdf")


def test_metric_and_a4_options(qapp, tmp_path):
    d = D.ExportDialog(FakeApp(str(tmp_path / "job.igz"), _scene_with_box()))
    d.units.setCurrentIndex(1)
    d.page.setCurrentIndex(1)
    d.note.setText("Issued for review")
    opts = d.options()
    assert (opts["units"], opts["units_label"], opts["page"], opts["note"]) == ("m", "metres", "a4", "Issued for review")


def test_export_writes_a_3d_pdf(qapp, tmp_path):
    app = FakeApp(str(tmp_path / "job.igz"), _scene_with_box())
    d = D.ExportDialog(app)
    d.start_export()
    _wait(d, qapp)
    out = tmp_path / "job.pdf"
    assert out.exists()
    reader = PdfReader(io.BytesIO(out.read_bytes()))
    annot = reader.pages[0]["/Annots"][0].get_object()
    assert annot["/Subtype"] == "/3D"
    assert annot["/3DD"].get_object().get_data()[:4] == b"U3D\0"
    assert "/XObject" in annot["/AP"]["/N"].get_object()["/Resources"]      # poster present
    assert d.open_button.isVisible() or d.open_button.isEnabled()
    assert any("job.pdf" in t for t in app.viewport.flashed)
    assert d.export_button.isEnabled()


def test_refusal_shows_message_and_writes_nothing(qapp, tmp_path):
    scene = Scene()
    scene.selection.add(scene.mesh.add_edge(V(0, 0, 0), V(1, 0, 0)))
    app = FakeApp(str(tmp_path / "job.igz"), scene)
    d = D.ExportDialog(app)
    d.start_export()
    _wait(d, qapp)
    assert not (tmp_path / "job.pdf").exists()
    assert "edges" in d.status.text().lower()
    assert d.export_button.isEnabled()


def test_worker_error_is_reported_and_partial_file_removed(qapp, tmp_path, monkeypatch):
    app = FakeApp(str(tmp_path / "job.igz"), _scene_with_box())
    d = D.ExportDialog(app)

    def boom(_scene):
        raise RuntimeError("encoder exploded")
    monkeypatch.setattr(D, "write_u3d", boom)
    d.start_export()
    _wait(d, qapp)
    assert not (tmp_path / "job.pdf").exists()
    assert "encoder exploded" in d.status.text()
    assert d.export_button.isEnabled()


def test_document_path_helper(tmp_path):
    assert D.document_path(FakeApp(str(tmp_path / "x.igz"))) == str(tmp_path / "x.igz")
    assert D.document_path(FakeApp(None)) is None
    assert D.document_path(object()) is None


def test_poster_is_rendered_at_the_viewport_aspect(qapp, tmp_path):
    app = FakeApp(str(tmp_path / "job.igz"), _scene_with_box())
    calls = []
    original = app.viewport.render_image

    def record(w, h=None):
        calls.append((w, h))
        return original(w, h)
    app.viewport.render_image = record
    d = D.ExportDialog(app)
    d.start_export()
    _wait(d, qapp)
    assert calls == [(D.POSTER_WIDTH_PX, None)]
