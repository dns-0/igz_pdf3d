# SPDX-License-Identifier: GPL-3.0-or-later
"""Read the host scene into plain data for the U3D and PDF writers.

Main thread only: this is the one module that touches host objects (groups,
faces, textures, the viewport). Everything it returns is tuples, lists,
dicts, strings and bytes.
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import _space
from ._tessellate import build_mesh, fan_triangles

log = logging.getLogger("ingetrazo.plugins.igz_pdf3d")

DEFAULT_COLOR = (0.96, 0.95, 0.925)          # the host's unpainted cream
FALLBACK_TEXTURE_COLOR = (0.7, 0.7, 0.7)
MAX_TEXTURE_PX = 2048
LOOSE_NAME = "Loose geometry"
DEFAULT_LAYER = "Layer 0"


class NothingToExport(ValueError):
    """A user-facing refusal: nothing selected or visible that has faces."""


# ---- host helpers with fallbacks -------------------------------------------

def _layer_of(entity) -> str:
    try:
        from core.layers import layer_of
        return layer_of(entity)
    except Exception:  # noqa: BLE001 — stub-less environment
        attrs = getattr(entity, "attrs", None)
        if attrs is not None:
            return attrs.get("layer") or DEFAULT_LAYER
        return getattr(entity, "layer", None) or DEFAULT_LAYER


def _iter_placements(group):
    try:
        from core.group import iter_placements
        return iter_placements(group)
    except Exception:  # noqa: BLE001
        def walk(g, base=None):
            m = getattr(g, "xform", None)
            if base is not None:
                m = base if m is None else base * m
            yield g, m
            for child in getattr(g, "children", None) or ():
                yield from walk(child, m)
        return walk(group)


def _export_names(materials: dict) -> dict:
    try:
        from formats.meshexport import export_names
        return export_names(materials)
    except Exception:  # noqa: BLE001
        names, used = {}, set()
        for i, (key, info) in enumerate(materials.items()):
            raw = (info.get("mat") or "").strip()
            if raw:
                base = "".join(c if c.isalnum() or c in "._-" else "_" for c in raw).strip("._-") or f"mat{i}"
                if base[0].isdigit():
                    base = f"m_{base}"
            else:
                base = f"mat{i}"
            name, n = base, 2
            while name in used:
                name = f"{base}_{n}"
                n += 1
            used.add(name)
            names[key] = name
        return names


def _face_uvs(normal, points, tex: dict):
    from core.texture import affine_uv, planar_uv
    uvw = tex.get("uvw")
    if uvw:
        return affine_uv(uvw, points)
    return planar_uv(normal, points, float(tex.get("sw", 1.0) or 1.0),
                     float(tex.get("sh", 1.0) or 1.0), float(tex.get("rot", 0.0)))


def _has_cutout(path: str) -> bool:
    from core.texture import image_has_cutout
    return bool(image_has_cutout(path))


def _is_group(e) -> bool:
    return hasattr(e, "mesh") and hasattr(e, "name")


def _is_face(e) -> bool:
    return hasattr(e, "loop") and hasattr(e, "attrs")


def _xyz(v) -> tuple:
    return (v.x(), v.y(), v.z())


def _rows(m) -> list:
    return [[m.row(r).x(), m.row(r).y(), m.row(r).z(), m.row(r).w()] for r in range(4)]


# ---- selection ---------------------------------------------------------------

def resolve(scene):
    """``(groups, faces, whole)`` per the spec's selection rules."""
    selected = list(getattr(scene, "selection", None) or [])
    if selected:
        groups = [e for e in selected if _is_group(e)]
        faces = [e for e in selected if _is_face(e)]
        if not groups and not faces:
            raise NothingToExport("Only edges are selected. Select faces or groups, or clear "
                                  "the selection to export the whole visible model.")
        return groups, faces, False
    groups = [g for g in (getattr(scene, "groups", None) or []) if scene.entity_visible(g)]
    faces = [f for f in scene.loose_mesh.faces if scene.entity_visible(f)]
    if not groups and not faces:
        raise NothingToExport("Nothing is visible to export.")
    return groups, faces, True


def describe_selection(scene) -> str:
    try:
        groups, faces, whole = resolve(scene)
    except NothingToExport as ex:
        return str(ex)
    label = "Whole visible model" if whole else "Selection"
    return f"{label}: {len(groups)} groups, {len(faces)} loose faces"


# ---- materials and textures --------------------------------------------------

class _Materials:
    def __init__(self) -> None:
        self.keys: dict = {}
        self.items: list = []
        self.textures: dict = {}
        self.fallbacks: list = []

    def index_for(self, attrs) -> int:
        attrs = attrs or {}
        op = attrs.get("opacity")
        op = None if op is None or float(op) >= 0.999 else round(float(op), 3)
        tex = attrs.get("texture")
        if tex and tex.get("path"):
            base = Path(str(tex["path"])).name
            key = ("tex", base) if op is None else ("tex", base, op)
            if key not in self.keys:
                loaded = self._load_texture(str(tex["path"]), base)
                item = {"color": (1.0, 1.0, 1.0) if loaded else FALLBACK_TEXTURE_COLOR,
                        "opacity": op, "texture": base if loaded else None,
                        "cutout": bool(loaded and self.textures[base]["alpha"]),
                        "mat": attrs.get("mat")}
                self.keys[key] = len(self.items)
                self.items.append(item)
        else:
            col = tuple(float(c) for c in (attrs.get("color") or DEFAULT_COLOR))[:3]
            key = ("color", col) if op is None else ("color", col, op)
            if key not in self.keys:
                self.keys[key] = len(self.items)
                self.items.append({"color": col, "opacity": op, "texture": None,
                                   "cutout": False, "mat": attrs.get("mat")})
        index = self.keys[key]
        if attrs.get("mat") and not self.items[index].get("mat"):
            self.items[index]["mat"] = attrs["mat"]
        return index

    def textured(self, index: int) -> bool:
        return self.items[index]["texture"] is not None

    def _load_texture(self, path: str, base: str) -> bool:
        if base in self.textures:
            return True
        try:
            from PySide6.QtCore import QBuffer, QIODevice, Qt
            from PySide6.QtGui import QImage
            img = QImage(path)
            if img.isNull():
                raise ValueError("unreadable image")
            if max(img.width(), img.height()) > MAX_TEXTURE_PX:
                img = img.scaled(MAX_TEXTURE_PX, MAX_TEXTURE_PX, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)
            try:
                cutout = _has_cutout(path)
            except Exception:  # noqa: BLE001
                cutout = img.hasAlphaChannel()
            img = img.convertToFormat(QImage.Format_RGBA8888 if cutout else QImage.Format_RGB888)
            buf = QBuffer()
            buf.open(QIODevice.WriteOnly)
            if not img.save(buf, "PNG" if cutout else "JPEG", 90):
                raise ValueError("could not encode image")
            self.textures[base] = {"width": img.width(), "height": img.height(),
                                   "format": "png" if cutout else "jpeg", "alpha": cutout,
                                   "data": bytes(buf.data())}
            return True
        except Exception as ex:  # noqa: BLE001 — one bad texture never stops the export
            log.warning("igz_pdf3d: texture %s not exported (%s)", path, ex)
            self.fallbacks.append(f"{base}: {ex}")
            return False

    def finish(self) -> list:
        names = _export_names({key: {"mat": self.items[i].get("mat")} for key, i in self.keys.items()})
        out = []
        for key, i in self.keys.items():
            item = dict(self.items[i])
            item.pop("mat", None)
            item["name"] = names[key]
            out.append(item)
        return out


# ---- geometry ----------------------------------------------------------------

def _face_triangles(face):
    tri = getattr(face, "triangulate", None)
    if callable(tri):
        try:
            return list(tri())
        except Exception:  # noqa: BLE001 — fall back to a fan on a bad face
            log.exception("igz_pdf3d: triangulate failed; using a fan")
    return fan_triangles(list(face.vertices))


def _mesh_from_faces(name: str, faces, scale: float, m, materials: _Materials, baked: bool) -> dict:
    """``baked``: positions are taken to world space through ``m`` (textured
    groups and loose faces); otherwise they stay local (instanced prototypes)."""
    triangles = []
    for face in faces:
        if len(getattr(face, "loop", ())) < 3:
            continue
        material = materials.index_for(face.attrs)
        tex = face.attrs.get("texture") if materials.textured(material) else None
        normal = None
        if tex is not None:
            normal = face.normal()
            if baked and m is not None:
                normal = m.mapVector(normal)
        for a, b, c in _face_triangles(face):
            pts = [a, b, c]
            if baked and m is not None:
                pts = [m.map(p) for p in pts]
            uvs = None
            if tex is not None:
                uv = _face_uvs(normal, pts, tex)
                uvs = ((uv[0][0], uv[0][1]), (uv[1][0], uv[1][1]), (uv[2][0], uv[2][1]))
            triangles.append((_space.point(_xyz(pts[0]), scale), _space.point(_xyz(pts[1]), scale),
                              _space.point(_xyz(pts[2]), scale), material, uvs))
    return build_mesh(name, triangles)


def _node_name(group) -> str:
    ifc = getattr(group, "ifc", None)
    cls = ifc.get("class") if isinstance(ifc, dict) else None
    name = getattr(group, "name", None) or "Group"
    return f"{cls} {name}" if cls else name


def _is_textured(faces) -> bool:
    for f in faces:
        tex = (f.attrs or {}).get("texture")
        if tex and tex.get("path"):
            return True
    return False


# ---- camera and poster -------------------------------------------------------

def _camera(viewport, scale: float):
    cam = getattr(viewport, "camera", None)
    if cam is None:
        return None
    try:
        eye = cam.eye()
        up_fn = getattr(cam, "up_vector", None)
        up = up_fn() if callable(up_fn) else cam.up
        return {"eye": _space.point(_xyz(eye), scale),
                "target": _space.point(_xyz(cam.target), scale),
                "up": _space.direction(_xyz(up)),
                "fov": float(getattr(cam, "fov_deg", 45.0)),
                "perspective": bool(getattr(cam, "perspective", True))}
    except Exception:  # noqa: BLE001 — a camera problem costs only the default view
        log.exception("igz_pdf3d: camera not exported")
        return None


def _poster(viewport, size):
    if viewport is None or size is None:
        return None, None
    try:
        from PySide6.QtCore import QBuffer, QIODevice
        if size[1] is None:                          # height follows the viewport's aspect
            img = viewport.render_image(int(size[0]))
        else:
            img = viewport.render_image(int(size[0]), int(size[1]))
        if img is None or img.isNull():
            return None, None
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "JPEG", 85)
        return bytes(buf.data()), (img.width(), img.height())
    except Exception:  # noqa: BLE001 — the poster is best-effort
        log.exception("igz_pdf3d: poster not rendered")
        return None, None


# ---- entry point -------------------------------------------------------------

def collect(scene, units: str, viewport=None, poster_size=None) -> dict:
    scale = _space.scale_for(units)
    groups, faces, whole = resolve(scene)
    materials = _Materials()
    layers: dict = {}
    for ly in getattr(scene, "layers", None) or []:
        layers[ly.name] = {"name": ly.name, "nodes": []}

    def layer_nodes(name: str) -> list:
        return layers.setdefault(name, {"name": name, "nodes": []})["nodes"]

    meshes: dict = {}
    counts = {"groups": 0, "faces": 0}
    baked_count = 0
    for top in groups:
        for g, m in _iter_placements(top):
            if g is not top and whole and not scene.entity_visible(g):
                continue
            if getattr(g, "billboard", False):
                continue
            gfaces = [f for f in g.mesh.faces if len(f.loop) >= 3]
            if not gfaces:
                continue
            if _is_textured(gfaces):
                key = f"baked:{baked_count}"
                baked_count += 1
                meshes[key] = _mesh_from_faces(g.name, gfaces, scale, m, materials, baked=True)
                matrix = None
            else:
                key = f"proto:{id(g.mesh)}"
                if key not in meshes:
                    meshes[key] = _mesh_from_faces(g.name, gfaces, scale, None, materials, baked=False)
                matrix = _space.matrix(_rows(m), scale) if m is not None else None
            if not meshes[key]["faces"]:
                continue
            layer_nodes(_layer_of(g)).append({"name": _node_name(g), "mesh": key, "matrix": matrix})
            counts["groups"] += 1
            counts["faces"] += len(gfaces)
    by_layer: dict = {}
    for f in faces:
        if len(getattr(f, "loop", ())) >= 3:
            by_layer.setdefault(_layer_of(f), []).append(f)
    for layer_name, lfaces in by_layer.items():
        key = f"loose:{layer_name}"
        meshes[key] = _mesh_from_faces(LOOSE_NAME, lfaces, scale, None, materials, baked=True)
        if meshes[key]["faces"]:
            layer_nodes(layer_name).append({"name": LOOSE_NAME, "mesh": key, "matrix": None})
            counts["faces"] += len(lfaces)
    used_keys = {n["mesh"] for ly in layers.values() for n in ly["nodes"]}
    meshes = {k: v for k, v in meshes.items() if k in used_keys}
    if not used_keys:
        raise NothingToExport("The selection has no faces to export.")

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for ly in layers.values():
        for node in ly["nodes"]:
            for p in meshes[node["mesh"]]["positions"]:
                x, y, z = _space.apply(node["matrix"], p)
                lo[0], lo[1], lo[2] = min(lo[0], x), min(lo[1], y), min(lo[2], z)
                hi[0], hi[1], hi[2] = max(hi[0], x), max(hi[1], y), max(hi[2], z)
    poster, poster_size_out = _poster(viewport, poster_size)
    return {"units": units, "scale": scale,
            "layers": [ly for ly in layers.values() if ly["nodes"]],
            "meshes": meshes, "materials": materials.finish(), "textures": materials.textures,
            "camera": _camera(viewport, scale), "bbox": (tuple(lo), tuple(hi)),
            "poster": poster, "poster_size": poster_size_out,
            "fallbacks": list(materials.fallbacks), "counts": counts}
