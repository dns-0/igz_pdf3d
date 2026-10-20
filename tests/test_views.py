# SPDX-License-Identifier: GPL-3.0-or-later
import math

import pytest

from igz_pdf3d import _views as W

BBOX = ((0.0, 0.0, -20.0), (10.0, 4.0, 0.0))


def _axes(view):
    """``(left, up, forward, eye)``: the C2W columns. PDF 32000-1 13.6.5: the
    camera faces out along its positive z axis."""
    c = view["c2w"]
    return c[0:3], c[3:6], c[6:9], c[9:12]


def _orbit_centre(view):
    _left, _up, forward, pos = _axes(view)
    return [p + f * view["co"] for p, f in zip(pos, forward)]


def test_names_and_order_with_camera():
    cam = {"eye": (30.0, -30.0, 30.0), "target": (5.0, 2.0, -10.0), "up": (0.0, 0.0, 1.0),
           "fov": 45.0, "perspective": True}
    names = [v["name"] for v in W.make_views(cam, BBOX)]
    assert names == ["Exported view", "Iso", "Top", "Front", "Back", "Left", "Right"]


def test_names_without_camera():
    names = [v["name"] for v in W.make_views(None, BBOX)]
    assert names == ["Iso", "Top", "Front", "Back", "Left", "Right"]


def test_exported_view_matches_camera():
    cam = {"eye": (0.0, 0.0, 50.0), "target": (0.0, 0.0, 0.0), "up": (0.0, 1.0, 0.0),
           "fov": 40.0, "perspective": True}
    v = W.make_views(cam, BBOX)[0]
    left, up, forward, pos = _axes(v)
    assert [round(x, 6) + 0.0 for x in left] == [-1.0, 0.0, 0.0]
    assert [round(x, 6) + 0.0 for x in up] == [0.0, 1.0, 0.0]
    assert [round(x, 6) + 0.0 for x in forward] == [0.0, 0.0, -1.0]
    assert pos == [0.0, 0.0, 50.0]
    # The pivot is the point of the sight line nearest the box centre (5, 2, -10): z = -10, 60 away.
    assert v["co"] == 60.0 and v["fov"] == 40.0


def test_the_centre_of_orbit_is_on_the_model_in_front_of_the_camera():
    """David, 2026-10-20: a threaded-pipe export swung unpredictably when
    dragged in Acrobat. The C2W's z column was the back axis, so the centre
    of orbit sat behind the camera, two model distances from the pipe."""
    cam = {"eye": (-171.5, -272.1, 132.3), "target": (0.0, 0.0, 0.0), "up": (0.0, 0.0, 1.0),
           "fov": 45.0, "perspective": True}
    box = ((-44.0, -44.0, -15.0), (44.0, 44.0, 15.0))
    for v in W.make_views(cam, box):
        centre = _orbit_centre(v)
        assert all(lo - 1e-6 <= c <= hi + 1e-6 for c, lo, hi in zip(centre, *box)), v["name"]


def test_exported_view_pivot_falls_back_when_model_is_behind_camera():
    cam = {"eye": (0.0, 0.0, -50.0), "target": (0.0, 0.0, -100.0), "up": (0.0, 1.0, 0.0),
           "fov": 40.0, "perspective": True}
    v = W.make_views(cam, BBOX)[0]
    assert v["co"] == 50.0
    assert [round(x, 6) for x in _orbit_centre(v)] == [0.0, 0.0, -100.0]


def test_axes_are_orthonormal_and_right_handed_for_every_view():
    cam = {"eye": (30.0, -30.0, 30.0), "target": (5.0, 2.0, -10.0), "up": (0.0, 0.0, 1.0),
           "fov": 45.0, "perspective": True}
    for v in W.make_views(cam, BBOX):
        left, up, forward, _pos = _axes(v)
        for a in (left, up, forward):
            assert abs(math.sqrt(sum(x * x for x in a)) - 1.0) < 1e-6, v["name"]
        assert abs(sum(a * b for a, b in zip(left, up))) < 1e-6
        assert abs(sum(a * b for a, b in zip(up, forward))) < 1e-6
        cross = (left[1] * up[2] - left[2] * up[1], left[2] * up[0] - left[0] * up[2],
                 left[0] * up[1] - left[1] * up[0])
        assert [round(x, 6) for x in cross] == [round(x, 6) for x in forward], v["name"]


def test_axis_views_look_at_the_box_centre_with_z_up():
    views = {v["name"]: v for v in W.make_views(None, BBOX)}
    centre = (5.0, 2.0, -10.0)
    for name, v in views.items():
        assert [round(x, 6) for x in _orbit_centre(v)] == list(centre), name
        assert v["fov"] == W.AXIS_FOV_DEG
    def forward(name):
        return [round(x, 6) + 0.0 for x in _axes(views[name])[2]]
    assert forward("Top") == [0.0, 0.0, -1.0]
    assert forward("Front") == [0.0, 1.0, 0.0]
    assert forward("Back") == [0.0, -1.0, 0.0]
    assert forward("Right") == [-1.0, 0.0, 0.0]
    assert forward("Left") == [1.0, 0.0, 0.0]
    assert _axes(views["Top"])[1] == pytest.approx([0.0, 1.0, 0.0])       # north up
    for name in ("Iso", "Front", "Back", "Left", "Right"):
        assert _axes(views[name])[1][2] > 0.5, name                       # Z up on screen


def test_axis_views_fit_the_box():
    views = {v["name"]: v for v in W.make_views(None, BBOX)}
    extent = 20.0
    needed = extent / 2 / math.tan(math.radians(W.AXIS_FOV_DEG / 2))
    assert views["Front"]["co"] > needed
    assert views["Front"]["co"] < needed * 3


def test_camera_along_up_vector_still_works():
    cam = {"eye": (5.0, 2.0, 60.0), "target": (5.0, 2.0, -10.0), "up": (0.0, 0.0, 1.0),
           "fov": 45.0, "perspective": True}
    v = W.make_views(cam, BBOX)[0]
    left, up, forward, _pos = _axes(v)
    assert [round(x, 6) + 0.0 for x in forward] == [0.0, 0.0, -1.0]
    assert abs(sum(a * b for a, b in zip(left, up))) < 1e-6


def test_u3d_view_node_axes_are_the_pdf_axes_turned_about_up():
    """The U3D view node looks down its own -z: right and back are the PDF
    view's left and forward reversed."""
    cam = {"eye": (30.0, -30.0, 30.0), "target": (5.0, 2.0, -10.0), "up": (0.0, 0.0, 1.0)}
    right, up, back = W.camera_axes(cam["eye"], cam["target"], cam["up"])
    left, up2, forward, _pos = _axes(W._view("v", cam["eye"], cam["target"], cam["up"], 45.0))
    assert [round(a + b, 9) for a, b in zip(right, left)] == [0.0, 0.0, 0.0]
    assert [round(a + b, 9) for a, b in zip(back, forward)] == [0.0, 0.0, 0.0]
    assert [round(a - b, 9) for a, b in zip(up, up2)] == [0.0, 0.0, 0.0]


def test_degenerate_box_and_camera():
    views = W.make_views({"eye": (1, 1, 1), "target": (1, 1, 1), "up": (0, 0, 1), "fov": 45.0,
                          "perspective": False}, ((1, 1, 1), (1, 1, 1)))
    assert len(views) == 7
    for v in views:
        assert all(math.isfinite(x) for x in v["c2w"]) and v["co"] > 0
