# SPDX-License-Identifier: GPL-3.0-or-later
"""Units and axes: IngeTrazo models in Z-up metres and the stakeholder wants
inches. One U3D unit is one inch (Imperial) or one metre (Metric).

The axes are kept as they are: Acrobat treats Z as up (its Spin tool turns
the model about Z, and its Walk tool keeps Z vertical), so a Z-up model
orbits the way it does in IngeTrazo. An earlier version turned the model
Y-up, which made those tools tumble it."""
from __future__ import annotations

INCHES_PER_METRE = 39.3700787
IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def scale_for(units: str) -> float:
    return INCHES_PER_METRE if units == "in" else 1.0


def point(p, scale: float) -> tuple:
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    return (x * scale, y * scale, z * scale)


def direction(v) -> tuple:
    return (float(v[0]), float(v[1]), float(v[2]))


def matrix(rows, scale: float) -> list:
    """``rows``: a 4×4 matrix as four rows (column-vector convention, the way
    ``QMatrix4x4.row(i)`` reads it). Returns the 16 floats U3D stores: the
    linear part column by column, then the scaled translation, then 1."""
    n = tuple(tuple(float(rows[r][c]) for c in range(3)) for r in range(3))
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
