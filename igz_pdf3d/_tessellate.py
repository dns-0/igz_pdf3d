# SPDX-License-Identifier: GPL-3.0-or-later
"""Triangle soup (already in U3D space) to the indexed mesh the U3D writer
takes: welded positions, one flat normal per triangle, per-corner texture
coordinates, degenerate triangles dropped."""
from __future__ import annotations

import math

#: Flip texture V. IngeTrazo's planar UVs put v=0 at the bottom of the image
#: (OpenGL style); if Acrobat shows textures upside down, set this to True.
FLIP_V = False

#: Triangles with twice-the-area below this (U3D units squared) are slivers.
MIN_CROSS = 1e-10
_WELD = 6                                            # decimals for welding


def fan_triangles(loop):
    pts = list(loop)
    if len(pts) < 3:
        return []
    return [(pts[0], pts[i], pts[i + 1]) for i in range(1, len(pts) - 1)]


def _normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length < MIN_CROSS:
        return None
    return (nx / length, ny / length, nz / length)


def build_mesh(name: str, triangles) -> dict:
    positions: list = []
    pos_index: dict = {}
    texcoords: list = []
    tex_index: dict = {}
    normals: list = []
    faces: list = []

    def vertex(p):
        key = (round(float(p[0]), _WELD), round(float(p[1]), _WELD), round(float(p[2]), _WELD))
        i = pos_index.get(key)
        if i is None:
            i = pos_index[key] = len(positions)
            positions.append((float(p[0]), float(p[1]), float(p[2])))
        return i

    def texcoord(uv):
        u, v = float(uv[0]), float(uv[1])
        if FLIP_V:
            v = -v
        key = (round(u, _WELD), round(v, _WELD))
        i = tex_index.get(key)
        if i is None:
            i = tex_index[key] = len(texcoords)
            texcoords.append((u, v))
        return i

    for a, b, c, material, uvs in triangles:
        n = _normal(a, b, c)
        if n is None:
            continue
        corners = (vertex(a), vertex(b), vertex(c))
        if len(set(corners)) < 3:
            continue
        tex = None
        if uvs is not None:
            tex = (texcoord(uvs[0]), texcoord(uvs[1]), texcoord(uvs[2]))
        normals.append(n)
        faces.append((int(material), corners, len(normals) - 1, tex))
    return {"name": name, "positions": positions, "normals": normals,
            "texcoords": texcoords, "faces": faces}
