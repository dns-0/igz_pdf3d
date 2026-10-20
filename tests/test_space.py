# SPDX-License-Identifier: GPL-3.0-or-later
import math

import pytest

from igz_pdf3d import _space as S


def test_scale_for_units():
    assert S.scale_for("in") == pytest.approx(39.3700787)
    assert S.scale_for("m") == 1.0


def test_point_keeps_z_up_and_scales():
    """Acrobat treats Z as up (its Spin tool turns about Z), so the axes pass
    through unchanged."""
    assert S.point((1.0, 2.0, 3.0), 1.0) == (1.0, 2.0, 3.0)
    x, y, z = S.point((1.0, 2.0, 3.0), S.scale_for("in"))
    assert (round(x, 3), round(y, 3), round(z, 3)) == (39.37, 78.74, 118.11)


def test_direction_keeps_up_up():
    assert S.direction((0.0, 0.0, 1.0)) == (0.0, 0.0, 1.0)
    assert S.direction((0.0, 1.0, 0.0)) == (0.0, 1.0, 0.0)


_apply = S.apply


def test_apply_uses_row_vector_convention():
    m = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 5.0, 6.0, 7.0, 1]
    assert S.apply(m, (1.0, 2.0, 3.0)) == (6.0, 8.0, 10.0)
    assert S.apply(None, (1.0, 2.0, 3.0)) == (1.0, 2.0, 3.0)


def test_identity_matrix():
    rows = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    assert S.matrix(rows, 1.0) == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def test_translation_is_scaled():
    rows = [[1, 0, 0, 1.0], [0, 1, 0, 2.0], [0, 0, 1, 3.0], [0, 0, 0, 1]]
    out = S.matrix(rows, 2.0)
    assert out[12:15] == [2.0, 4.0, 6.0]
    assert out[:12] == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]


def test_rotation_about_z_stays_about_z():
    c, s = math.cos(math.radians(90)), math.sin(math.radians(90))
    rows = [[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    out = S.matrix(rows, 1.0)
    # A point on +X turned 90 degrees about Z lands on +Y.
    moved = _apply(out, S.point((1.0, 0.0, 0.0), 1.0))
    assert [round(v, 6) for v in moved] == [0.0, 1.0, 0.0]


def test_scaled_placement_matches_scaled_points():
    rows = [[2, 0, 0, 0.5], [0, 2, 0, 0], [0, 0, 2, -1], [0, 0, 0, 1]]
    scale = 39.3700787
    out = S.matrix(rows, scale)
    p = (0.25, -0.5, 1.0)
    world = (2 * 0.25 + 0.5, 2 * -0.5, 2 * 1.0 - 1)
    assert [round(v, 4) for v in _apply(out, S.point(p, scale))] == [round(v, 4) for v in S.point(world, scale)]
