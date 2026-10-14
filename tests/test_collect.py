# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from PySide6.QtGui import QImage, QMatrix4x4, QVector3D

from igz_pdf3d import _collect as C
from core.group import Group
from core.layers import Layer
from core.scene import Scene
from core.camera import OrbitCamera


def V(x, y, z):
    return QVector3D(x, y, z)


def add_box(mesh, origin=(0, 0, 0), size=1.0, attrs=None):
    ox, oy, oz = origin
    s = size
    p = [V(ox, oy, oz), V(ox + s, oy, oz), V(ox + s, oy + s, oz), V(ox, oy + s, oz),
         V(ox, oy, oz + s), V(ox + s, oy, oz + s), V(ox + s, oy + s, oz + s), V(ox, oy + s, oz + s)]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return [mesh.add_face([p[i] for i in q], attrs=attrs) for q in quads]


def box_group(name, origin=(0, 0, 0), layer=None, attrs=None, ifc=None):
    g = Group(name=name)
    add_box(g.mesh, origin, attrs=attrs)
    g.layer = layer
    g.ifc = ifc
    return g


def translate(x, y, z):
    m = QMatrix4x4()
    m.translate(x, y, z)
    return m


class FakeViewport:
    def __init__(self, image=None):
        self.camera = OrbitCamera()
        self._image = image

    def render_image(self, w, h=None):
        return self._image


# ---- resolve --------------------------------------------------------------

def test_resolve_whole_model_skips_hidden():
    scene = Scene()
    scene.layers.append(Layer("Hidden", visible=False))
    a = box_group("A")
    b = box_group("B")
    b.hidden = True
    c = box_group("C", layer="Hidden")
    scene.groups += [a, b, c]
    face = add_box(scene.mesh, (5, 5, 5))[0]
    hidden_face = add_box(scene.mesh, (9, 9, 9), attrs={"layer": "Hidden"})[0]
    groups, faces, whole = C.resolve(scene)
    assert whole and groups == [a]
    assert face in faces and hidden_face not in faces


def test_resolve_selection_keeps_groups_and_faces_only():
    scene = Scene()
    a = box_group("A")
    scene.groups.append(a)
    faces = add_box(scene.mesh)
    edge = scene.mesh.add_edge(V(0, 0, 0), V(1, 1, 1))
    scene.selection.update([a, faces[0], edge])
    groups, sel_faces, whole = C.resolve(scene)
    assert not whole and groups == [a] and sel_faces == [faces[0]]


def test_collect_refuses_edges_only():
    scene = Scene()
    scene.selection.add(scene.mesh.add_edge(V(0, 0, 0), V(1, 0, 0)))
    with pytest.raises(C.NothingToExport):
        C.collect(scene, "in")
    assert "edges" in C.describe_selection(scene).lower()


def test_collect_refuses_all_hidden():
    scene = Scene()
    scene.layers[0].visible = False
    scene.groups.append(box_group("A"))
    with pytest.raises(C.NothingToExport):
        C.collect(scene, "in")


def test_describe_selection():
    scene = Scene()
    scene.groups.append(box_group("A"))
    add_box(scene.mesh)
    assert C.describe_selection(scene).startswith("Whole visible model")
    scene.selection.add(scene.groups[0])
    assert C.describe_selection(scene) == "Selection: 1 groups, 0 loose faces"


# ---- geometry -------------------------------------------------------------

def test_collect_layers_nodes_instances_and_loose(qapp):
    scene = Scene()
    scene.layers.append(Layer("Steel"))
    proto = box_group("Beam", layer="Steel", ifc={"class": "IfcBeam", "name": "B-1"})
    proto.xform = translate(0, 0, 0)
    twin = Group(mesh=proto.mesh, name="Beam")
    twin.layer = "Steel"
    twin.ifc = {"class": "IfcBeam", "name": "B-1"}
    twin.xform = translate(2.0, 0, 0)
    scene.groups += [proto, twin]
    add_box(scene.mesh, (10, 0, 0))
    out = C.collect(scene, "in")
    assert out["units"] == "in" and out["scale"] == pytest.approx(39.3700787)
    assert [ly["name"] for ly in out["layers"]] == ["Layer 0", "Steel"]
    steel = out["layers"][1]["nodes"]
    assert [n["name"] for n in steel] == ["IfcBeam Beam", "IfcBeam Beam"]
    assert steel[0]["mesh"] == steel[1]["mesh"]                 # instanced
    assert steel[0]["matrix"][12:15] == [0.0, 0.0, 0.0]
    assert [round(v, 3) for v in steel[1]["matrix"][12:15]] == [78.74, 0.0, 0.0]
    loose = out["layers"][0]["nodes"]
    assert loose[0]["name"] == C.LOOSE_NAME and loose[0]["matrix"] is None
    mesh = out["meshes"][steel[0]["mesh"]]
    assert len(mesh["positions"]) == 8 and len(mesh["faces"]) == 12
    assert out["counts"] == {"groups": 2, "faces": 18}            # 6 per box, plus the loose box
    lo, hi = out["bbox"]
    assert [round(v, 2) for v in lo] == [0.0, 0.0, -39.37]
    assert [round(v, 2) for v in hi] == [433.07, 39.37, 0.0]


def test_selected_group_exports_hidden_children(qapp):
    scene = Scene()
    parent = box_group("Parent")
    parent.xform = translate(0, 0, 0)
    child = box_group("Child", (3, 0, 0))
    child.hidden = True
    child.xform = translate(0, 0, 0)
    parent.children.append(child)
    scene.groups.append(parent)
    scene.selection.add(parent)
    out = C.collect(scene, "m")
    assert [n["name"] for n in out["layers"][0]["nodes"]] == ["Parent", "Child"]
    scene.selection.clear()
    out = C.collect(scene, "m")
    assert [n["name"] for n in out["layers"][0]["nodes"]] == ["Parent"]


def test_collect_materials_follow_host_rules(qapp):
    scene = Scene()
    g = Group(name="Mixed")
    add_box(g.mesh, (0, 0, 0), attrs={"color": (0.2, 0.3, 0.4), "mat": "Concrete smooth"})
    add_box(g.mesh, (2, 0, 0), attrs={"color": (0.2, 0.3, 0.4), "opacity": 0.5})
    add_box(g.mesh, (4, 0, 0))
    scene.groups.append(g)
    out = C.collect(scene, "in")
    mats = out["materials"]
    assert [m["name"] for m in mats] == ["Concrete_smooth", "mat1", "mat2"]
    assert mats[0]["color"] == (0.2, 0.3, 0.4) and mats[0]["opacity"] is None
    assert mats[1]["opacity"] == 0.5
    assert mats[2]["color"] == C.DEFAULT_COLOR
    mesh = out["meshes"][out["layers"][0]["nodes"][0]["mesh"]]
    assert sorted(set(f[0] for f in mesh["faces"])) == [0, 1, 2]


def _write_png(path, w=8, h=4, alpha=False):
    img = QImage(w, h, QImage.Format_RGBA8888 if alpha else QImage.Format_RGB888)
    img.fill(0xFF336699)
    assert img.save(str(path))
    return str(path)


def test_collect_textures_bake_per_placement(qapp, tmp_path):
    path = _write_png(tmp_path / "brick.png")
    scene = Scene()
    proto = box_group("Wall", attrs={"texture": {"path": path, "sw": 0.5, "sh": 0.25}, "mat": "Brick"})
    proto.xform = translate(0, 0, 0)
    twin = Group(mesh=proto.mesh, name="Wall")
    twin.xform = translate(5.0, 0, 0)
    scene.groups += [proto, twin]
    out = C.collect(scene, "m")
    nodes = out["layers"][0]["nodes"]
    assert nodes[0]["mesh"] != nodes[1]["mesh"]                  # baked, not instanced
    assert nodes[0]["matrix"] is None and nodes[1]["matrix"] is None
    m0, m1 = out["meshes"][nodes[0]["mesh"]], out["meshes"][nodes[1]["mesh"]]
    assert [round(v, 3) for v in m1["positions"][1]] == [round(v, 3) for v in (m0["positions"][1][0] + 5.0, m0["positions"][1][1], m0["positions"][1][2])]
    assert all(f[3] is not None for f in m0["faces"])
    assert len(m0["texcoords"]) > 0
    assert out["materials"] == [{"name": "Brick", "color": (1.0, 1.0, 1.0), "opacity": None,
                                 "texture": "brick.png", "cutout": False}]
    tex = out["textures"]["brick.png"]
    assert (tex["width"], tex["height"], tex["format"], tex["alpha"]) == (8, 4, "jpeg", False)
    assert tex["data"][:2] == b"\xff\xd8"
    assert out["fallbacks"] == []


def test_collect_cutout_texture_is_png(qapp, tmp_path):
    path = _write_png(tmp_path / "leaf_cutout.png", alpha=True)
    scene = Scene()
    g = Group(name="Leaf")
    g.mesh.add_face([V(0, 0, 0), V(1, 0, 0), V(1, 1, 0)], attrs={"texture": {"path": path, "sw": 1, "sh": 1}})
    scene.groups.append(g)
    out = C.collect(scene, "m")
    tex = out["textures"]["leaf_cutout.png"]
    assert tex["format"] == "png" and tex["alpha"] is True and tex["data"][:4] == b"\x89PNG"
    assert out["materials"][0]["cutout"] is True


def test_collect_missing_texture_falls_back(qapp, tmp_path):
    scene = Scene()
    g = Group(name="Wall")
    add_box(g.mesh, attrs={"texture": {"path": str(tmp_path / "gone.png"), "sw": 1, "sh": 1}})
    scene.groups.append(g)
    out = C.collect(scene, "m")
    assert out["materials"][0]["texture"] is None
    assert out["materials"][0]["color"] == C.FALLBACK_TEXTURE_COLOR
    assert out["textures"] == {}
    assert len(out["fallbacks"]) == 1 and "gone.png" in out["fallbacks"][0]
    mesh = out["meshes"][out["layers"][0]["nodes"][0]["mesh"]]
    assert all(f[3] is None for f in mesh["faces"])


def test_collect_camera_and_poster(qapp):
    scene = Scene()
    scene.groups.append(box_group("A"))
    img = QImage(64, 48, QImage.Format_RGB888)
    img.fill(0xFFFFFFFF)
    vp = FakeViewport(img)
    vp.camera.target = V(1.0, 2.0, 3.0)
    vp.camera.distance = 10.0
    vp.camera.yaw = 0.0
    vp.camera.pitch = 0.0
    out = C.collect(scene, "in", viewport=vp, poster_size=(64, 48))
    cam = out["camera"]
    assert [round(v, 2) for v in cam["target"]] == [39.37, 118.11, -78.74]
    assert [round(v, 2) for v in cam["eye"]] == [round(11.0 * 39.3700787, 2), 118.11, -78.74]
    assert cam["up"] == (0.0, 1.0, 0.0)
    assert cam["fov"] == 45.0 and cam["perspective"] is True
    assert out["poster"][:2] == b"\xff\xd8" and out["poster_size"] == (64, 48)


def test_collect_without_viewport(qapp):
    scene = Scene()
    scene.groups.append(box_group("A"))
    out = C.collect(scene, "in")
    assert out["camera"] is None and out["poster"] is None


def test_collect_group_without_faces_is_skipped(qapp):
    scene = Scene()
    empty = Group(name="Empty")
    scene.groups += [empty, box_group("A")]
    out = C.collect(scene, "in")
    assert [n["name"] for n in out["layers"][0]["nodes"]] == ["A"]


def test_collect_skips_nested_child_on_hidden_layer(qapp):
    scene = Scene()
    scene.layers.append(Layer("Scaffolding", visible=False))
    parent = box_group("Parent")
    parent.xform = translate(0, 0, 0)
    child = box_group("Scaffold", (3, 0, 0), layer="Scaffolding")
    child.xform = translate(0, 0, 0)
    parent.children.append(child)
    scene.groups.append(parent)
    out = C.collect(scene, "m")
    assert [ly["name"] for ly in out["layers"]] == ["Layer 0"]
    assert [n["name"] for n in out["layers"][0]["nodes"]] == ["Parent"]
