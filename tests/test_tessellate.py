# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from igz_pdf3d import _tessellate as T


def test_fan_triangles():
    loop = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    assert T.fan_triangles(loop) == [((0, 0, 0), (1, 0, 0), (1, 1, 0)), ((0, 0, 0), (1, 1, 0), (0, 1, 0))]
    assert T.fan_triangles(loop[:2]) == []


def _cube_triangles(material=0):
    s = 1.0
    p = [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0), (0, 0, s), (s, 0, s), (s, s, s), (0, s, s)]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    tris = []
    for q in quads:
        for a, b, c in T.fan_triangles([p[i] for i in q]):
            tris.append((a, b, c, material, None))
    return tris


def test_build_mesh_welds_positions_and_makes_flat_normals():
    mesh = T.build_mesh("Cube", _cube_triangles())
    assert mesh["name"] == "Cube"
    assert len(mesh["positions"]) == 8
    assert len(mesh["faces"]) == 12
    assert len(mesh["normals"]) == 12
    assert mesh["texcoords"] == []
    bottom = mesh["normals"][0]
    assert [round(v, 6) for v in bottom] == [0.0, 0.0, -1.0]
    top = mesh["normals"][2]
    assert [round(v, 6) for v in top] == [0.0, 0.0, 1.0]
    for material, corners, n, tex in mesh["faces"]:
        assert material == 0 and tex is None and len(set(corners)) == 3
        assert 0 <= n < 12


def test_build_mesh_drops_slivers():
    tris = _cube_triangles() + [((0, 0, 0), (1, 0, 0), (2, 0, 0), 0, None),      # collinear
                                ((5, 5, 5), (5, 5, 5), (6, 6, 6), 0, None)]      # repeated corner
    mesh = T.build_mesh("Cube", tris)
    assert len(mesh["faces"]) == 12
    assert len(mesh["positions"]) == 8
    for n in mesh["normals"]:
        assert abs(sum(v * v for v in n) - 1.0) < 1e-6


def test_build_mesh_keeps_uvs_per_corner_and_dedupes():
    uv = ((0.0, 0.0), (2.0, 0.0), (2.0, 1.0))
    uv2 = ((0.0, 0.0), (2.0, 1.0), (0.0, 1.0))
    tris = [((0, 0, 0), (2, 0, 0), (2, 1, 0), 1, uv), ((0, 0, 0), (2, 1, 0), (0, 1, 0), 1, uv2)]
    mesh = T.build_mesh("Panel", tris)
    assert len(mesh["texcoords"]) == 4
    assert mesh["faces"][0][0] == 1
    assert mesh["faces"][0][3] == (0, 1, 2)
    assert mesh["faces"][1][3] == (0, 2, 3)
    assert mesh["texcoords"][3] == (0.0, 1.0)


def test_flip_v_constant(monkeypatch):
    monkeypatch.setattr(T, "FLIP_V", True)
    uv = ((0.0, 0.0), (1.0, 0.0), (1.0, 0.5))
    mesh = T.build_mesh("P", [((0, 0, 0), (1, 0, 0), (1, 1, 0), 0, uv)])
    assert mesh["texcoords"] == [(0.0, 0.0), (1.0, 0.0), (1.0, -0.5)]


def test_empty_input_gives_empty_mesh():
    mesh = T.build_mesh("Nothing", [])
    assert mesh["faces"] == [] and mesh["positions"] == []
