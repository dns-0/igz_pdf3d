# SPDX-License-Identifier: GPL-3.0-or-later
_UID = [0]


def new_uid():
    _UID[0] += 1
    return _UID[0]


class Group:
    def __init__(self, mesh=None, name=None):
        from core.mesh import Mesh
        self.mesh = mesh if mesh is not None else Mesh()
        self.name = name or f"Group {new_uid()}"
        self.xform = None
        self.children = []
        self.layer = None
        self.ifc = None
        self.ext = None
        self.component = True
        self.hidden = False
        self.billboard = False
        self.uid = new_uid()

    def is_component(self):
        return self.xform is not None and bool(self.component)


def iter_placements(group, base=None):
    m = getattr(group, "xform", None)
    if base is not None:
        m = base if m is None else base * m
    yield group, m
    for child in getattr(group, "children", None) or ():
        yield from iter_placements(child, m)
