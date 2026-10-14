# SPDX-License-Identifier: GPL-3.0-or-later
"""Units and axes: IngeTrazo models in Z-up metres; the PDF viewer expects
Y-up, and the stakeholder wants inches. One U3D unit is one inch (Imperial)
or one metre (Metric). Z-up to Y-up is ``(x, y, z) -> (x, z, -y)``."""
from __future__ import annotations

INCHES_PER_METRE = 39.3700787

# R maps Z-up to Y-up; RT is its inverse (transpose).
_R = ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0))
_RT = ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))


def scale_for(units: str) -> float:
    return INCHES_PER_METRE if units == "in" else 1.0


def point(p, scale: float) -> tuple:
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    return (x * scale, z * scale, -y * scale)


def direction(v) -> tuple:
    return (float(v[0]), float(v[2]), -float(v[1]))


def _mul3(a, b):
    return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)) for r in range(3))


def matrix(rows, scale: float) -> list:
    """``rows``: a 4×4 matrix as four rows (column-vector convention, the way
    ``QMatrix4x4.row(i)`` reads it). Returns the 16 floats U3D stores: the
    converted linear part ``R·A·Rᵀ`` column by column, then the converted,
    scaled translation, then 1."""
    a = tuple(tuple(float(rows[r][c]) for c in range(3)) for r in range(3))
    n = _mul3(_mul3(_R, a), _RT)
    t = point((rows[0][3], rows[1][3], rows[2][3]), scale)
    out = []
    for c in range(3):
        out.extend([n[0][c], n[1][c], n[2][c], 0.0])
    out.extend([t[0], t[1], t[2], 1.0])
    return [float(v) for v in out]


def apply(m, p) -> tuple:
    """Apply a U3D 16-float matrix (row-vector convention) to a point;
    ``None`` is the identity."""
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    if m is None:
        return (x, y, z)
    return (x * m[0] + y * m[4] + z * m[8] + m[12],
            x * m[1] + y * m[5] + z * m[9] + m[13],
            x * m[2] + y * m[6] + z * m[10] + m[14])
