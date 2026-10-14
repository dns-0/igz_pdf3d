# SPDX-License-Identifier: GPL-3.0-or-later
import math

import pytest

from igz_pdf3d import _views as W

BBOX = ((0.0, 0.0, -20.0), (10.0, 4.0, 0.0))


def _axes(view):
    c = view["c2w"]
    return c[0:3], c[3:6], c[6:9], c[9:12]


def test_names_and_order_with_camera():
    cam = {"eye": (30.0, 30.0, 30.0), "target": (5.0, 2.0, -10.0), "up": (0.0, 1.0, 0.0),
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
    right, up, back, pos = _axes(v)
    assert [round(x, 6) for x in right] == [1.0, 0.0, 0.0]
    assert [round(x, 6) for x in up] == [0.0, 1.0, 0.0]
    assert [round(x, 6) for x in back] == [0.0, 0.0, 1.0]
    assert pos == [0.0, 0.0, 50.0]
    assert v["co"] == 50.0 and v["fov"] == 40.0


def test_axes_are_orthonormal_for_every_view():
    cam = {"eye": (30.0, 30.0, 30.0), "target": (5.0, 2.0, -10.0), "up": (0.0, 1.0, 0.0),
           "fov": 45.0, "perspective": True}
    for v in W.make_views(cam, BBOX):
        right, up, back, _pos = _axes(v)
        for a in (right, up, back):
            assert abs(math.sqrt(sum(x * x for x in a)) - 1.0) < 1e-6, v["name"]
        assert abs(sum(a * b for a, b in zip(right, up))) < 1e-6
        assert abs(sum(a * b for a, b in zip(up, back))) < 1e-6
        cross = (right[1] * up[2] - right[2] * up[1], right[2] * up[0] - right[0] * up[2],
                 right[0] * up[1] - right[1] * up[0])
        assert [round(x, 6) for x in cross] == [round(x, 6) for x in back], v["name"]


def test_axis_views_look_at_the_box_centre():
    views = {v["name"]: v for v in W.make_views(None, BBOX)}
    centre = (5.0, 2.0, -10.0)
    for name, v in views.items():
        right, up, back, pos = _axes(v)
        target = [p - b * v["co"] for p, b in zip(pos, back)]
        assert [round(x, 6) for x in target] == list(centre), name
        assert v["fov"] == W.AXIS_FOV_DEG
    assert [round(x, 6) for x in _axes(views["Top"])[2]] == [0.0, 1.0, 0.0]
    assert [round(x, 6) for x in _axes(views["Front"])[2]] == [0.0, 0.0, 1.0]
    assert [round(x, 6) for x in _axes(views["Right"])[2]] == [1.0, 0.0, 0.0]
    assert [round(x, 6) for x in _axes(views["Left"])[2]] == [-1.0, 0.0, 0.0]
    assert [round(x, 6) for x in _axes(views["Back"])[2]] == [0.0, 0.0, -1.0]
    assert _axes(views["Top"])[1] == pytest.approx([0.0, 0.0, -1.0])


def test_axis_views_fit_the_box():
    views = {v["name"]: v for v in W.make_views(None, BBOX)}
    extent = 20.0
    needed = extent / 2 / math.tan(math.radians(W.AXIS_FOV_DEG / 2))
    assert views["Front"]["co"] > needed
    assert views["Front"]["co"] < needed * 3


def test_camera_along_up_vector_still_works():
    cam = {"eye": (5.0, 60.0, -10.0), "target": (5.0, 2.0, -10.0), "up": (0.0, 1.0, 0.0),
           "fov": 45.0, "perspective": True}
    v = W.make_views(cam, BBOX)[0]
    right, up, back, _pos = _axes(v)
    assert [round(x, 6) for x in back] == [0.0, 1.0, 0.0]
    assert abs(sum(a * b for a, b in zip(right, up))) < 1e-6


def test_degenerate_box_and_camera():
    views = W.make_views({"eye": (1, 1, 1), "target": (1, 1, 1), "up": (0, 1, 0), "fov": 45.0,
                          "perspective": False}, ((1, 1, 1), (1, 1, 1)))
    assert len(views) == 7
    for v in views:
        assert all(math.isfinite(x) for x in v["c2w"]) and v["co"] > 0
