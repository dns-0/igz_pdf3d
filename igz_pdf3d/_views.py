# SPDX-License-Identifier: GPL-3.0-or-later
"""PDF 3D views: the camera the user exported from and six axis views framed
around the model. Everything is in U3D space (Y-up, scaled).

A view's C2W is the camera's right, up and back axes followed by its position
(PDF 32000-1, 3D view dictionary). The camera looks down its own -z, so the
back axis points from the target to the eye and ``co`` is their distance.
"""
from __future__ import annotations

import math

AXIS_FOV_DEG = 30.0         # narrow: axis views read as nearly parallel
_FIT_MARGIN = 1.25


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    length = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    if length < 1e-12:
        return None
    return (a[0] / length, a[1] / length, a[2] / length)


def _view(name: str, eye, target, up, fov: float) -> dict:
    back = _norm(_sub(eye, target))
    if back is None:
        back = (0.0, 0.0, 1.0)
    up = _norm(up) or (0.0, 1.0, 0.0)
    if abs(up[0] * back[0] + up[1] * back[1] + up[2] * back[2]) > 0.9999:
        up = (0.0, 0.0, -1.0) if back[1] > 0 else (0.0, 0.0, 1.0)
    right = _norm(_cross(up, back))
    up = _cross(back, right)
    distance = math.sqrt(sum(v * v for v in _sub(eye, target)))
    if distance < 1e-9:
        distance = 1.0
        eye = (target[0] + back[0], target[1] + back[1], target[2] + back[2])
    return {"name": name,
            "c2w": [float(v) for v in (*right, *up, *back, *eye)],
            "co": float(distance), "fov": float(fov)}


def make_views(camera, bbox) -> list:
    lo, hi = bbox
    centre = tuple((lo[i] + hi[i]) / 2.0 for i in range(3))
    extent = max(hi[i] - lo[i] for i in range(3))
    if not (extent > 0):
        extent = 1.0
    radius = extent * math.sqrt(3) / 2.0
    distance = radius / math.tan(math.radians(AXIS_FOV_DEG / 2.0)) * _FIT_MARGIN
    views = []
    if camera is not None:
        # Pivot on the model: the point of the sight line nearest the box
        # centre, so orbiting swings the model and not a spot in the air.
        eye, target = camera["eye"], camera["target"]
        forward = _norm(_sub(target, eye))
        if forward is not None:
            along = sum((centre[i] - eye[i]) * forward[i] for i in range(3))
            if along > 1e-6:
                target = tuple(eye[i] + forward[i] * along for i in range(3))
        views.append(_view("Exported view", eye, target, camera["up"], camera.get("fov") or 45.0))
    iso = _norm((1.0, 1.0, 1.0))
    axes = [("Iso", iso, (0.0, 1.0, 0.0)),
            ("Top", (0.0, 1.0, 0.0), (0.0, 0.0, -1.0)),
            ("Front", (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
            ("Back", (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
            ("Left", (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            ("Right", (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))]
    for name, direction, up in axes:
        eye = tuple(centre[i] + direction[i] * distance for i in range(3))
        views.append(_view(name, eye, centre, up, AXIS_FOV_DEG))
    return views
