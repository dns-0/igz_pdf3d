# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal stand-in for core.mesh: welded vertices, faces with attrs, fan
triangulation (the real host uses an ear clipper)."""
from PySide6.QtGui import QVector3D


def _key(p):
    return (round(p.x(), 6), round(p.y(), 6), round(p.z(), 6))


class Vertex:
    def __init__(self, position):
        self.position = position


class Edge:
    def __init__(self, v0, v1):
        self.v0, self.v1 = v0, v1


class Face:
    def __init__(self, loop, holes):
        self.loop = loop
        self.hole_loops = holes
        self.attrs = {}

    @property
    def vertices(self):
        return [v.position for v in self.loop]

    @property
    def holes(self):
        return [[v.position for v in h] for h in self.hole_loops]

    def normal(self):
        n = QVector3D(0, 0, 0)
        pts = self.vertices
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            n += QVector3D((a.y() - b.y()) * (a.z() + b.z()),
                           (a.z() - b.z()) * (a.x() + b.x()),
                           (a.x() - b.x()) * (a.y() + b.y()))
        return n.normalized()

    def area(self):
        return self.normal().length() if len(self.loop) >= 3 else 0.0

    def triangulate(self, normal=None):
        pts = self.vertices
        if len(pts) < 3:
            return []
        return [(pts[0], pts[i], pts[i + 1]) for i in range(1, len(pts) - 1)]


class Mesh:
    def __init__(self):
        self.faces = []
        self.edges = []
        self.vertices = []
        self._verts = {}

    def vertex(self, position):
        k = _key(position)
        v = self._verts.get(k)
        if v is None:
            v = Vertex(QVector3D(position))
            self._verts[k] = v
            self.vertices.append(v)
        return v

    def add_face(self, loop_positions, hole_loops=None, attrs=None):
        loop = [self.vertex(p) for p in loop_positions]
        holes = [[self.vertex(p) for p in h] for h in (hole_loops or [])]
        face = Face(loop, holes)
        if attrs:
            face.attrs.update(attrs)
        self.faces.append(face)
        return face

    def add_edge(self, a, b):
        e = Edge(self.vertex(a), self.vertex(b))
        self.edges.append(e)
        return e
