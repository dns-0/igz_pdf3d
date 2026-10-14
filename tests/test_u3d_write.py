# SPDX-License-Identifier: GPL-3.0-or-later
import copy

import pytest

from igz_pdf3d import _u3d as U

JPEG = b"\xff\xd8\xff\xe0" + bytes(range(60)) + b"\xff\xd9"


def cube_mesh(name="Cube", material=0, size=1.0):
    s = size
    p = [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0), (0, 0, s), (s, 0, s), (s, s, s), (0, s, s)]
    quads = [((0, 3, 2, 1), (0, 0, -1)), ((4, 5, 6, 7), (0, 0, 1)), ((0, 1, 5, 4), (0, -1, 0)),
             ((1, 2, 6, 5), (1, 0, 0)), ((2, 3, 7, 6), (0, 1, 0)), ((3, 0, 4, 7), (-1, 0, 0))]
    normals, faces = [], []
    for i, (q, n) in enumerate(quads):
        normals.append(n)
        faces.append((material, (q[0], q[1], q[2]), i, None))
        faces.append((material, (q[0], q[2], q[3]), i, None))
    return {"name": name, "positions": p, "normals": normals, "texcoords": [], "faces": faces}


def textured_quad(name="Panel", material=1):
    return {"name": name, "positions": [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)],
            "normals": [(0, 0, 1)], "texcoords": [(0, 0), (2, 0), (2, 1), (0, 1)],
            "faces": [(material, (0, 1, 2), 0, (0, 1, 2)), (material, (0, 2, 3), 0, (0, 2, 3))]}


def sample_scene():
    return {
        "layers": [
            {"name": "Steel", "nodes": [
                {"name": "IfcBeam B-1", "mesh": "m1", "matrix": None},
                {"name": "IfcBeam B-1", "mesh": "m1",
                 "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10.0, 0.0, 0.0, 1]}]},
            {"name": "Walls", "nodes": [{"name": "Panel", "mesh": "m2", "matrix": None}]},
        ],
        "meshes": {"m1": cube_mesh(), "m2": textured_quad()},
        "materials": [
            {"name": "Steel_grey", "color": (0.5, 0.5, 0.55), "opacity": 1.0, "texture": None, "cutout": False},
            {"name": "Brick", "color": (1.0, 1.0, 1.0), "opacity": 1.0, "texture": "brick.jpg", "cutout": False},
        ],
        "textures": {"brick.jpg": {"width": 8, "height": 4, "format": "jpeg", "alpha": False, "data": JPEG}},
    }


def _types(doc):
    return [b["type"] for b in doc["blocks"]]


def test_block_order_and_priorities():
    doc = U.read_u3d(U.write_u3d(sample_scene()))
    assert doc["header"]["file_size"] == doc["header"]["file_size"]  # parsed
    types = _types(doc)
    assert types[:2] == ["header", "priority"]
    chains = [b for b in doc["blocks"] if b["type"] == "chain"]
    assert [(c["name"], c["chain_type"]) for c in chains] == [
        ("Steel", 0), ("IfcBeam B-1", 0), ("IfcBeam B-1 (2)", 0), ("Walls", 0), ("Panel", 0),
        ("Cube", 1), ("Panel", 1), ("brick.jpg", 2)]   # meshes are their own palette
    assert [b["priority"] for b in doc["blocks"] if b["type"] == "priority"] == [0, 1, 256]
    assert types.index("shader") < types.index("texture_continuation") < types.index("basemesh")
    assert types.count("basemesh") == 2 and types.count("texture_continuation") == 1


def test_file_size_is_patched():
    data = U.write_u3d(sample_scene())
    assert U.read_u3d(data)["header"]["file_size"] == len(data)
    assert U.read_u3d(data)["header"]["declaration_size"] == 36


def test_nodes_reference_layers_and_meshes():
    doc = U.read_u3d(U.write_u3d(sample_scene()))
    chains = [b for b in doc["blocks"] if b["type"] == "chain"]
    group = chains[0]["blocks"][0]
    assert group["type"] == "group" and group["parents"][0]["name"] == ""
    assert group["parents"][0]["matrix"] == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    model, shading = chains[2]["blocks"]
    assert model["type"] == "model" and model["name"] == "IfcBeam B-1 (2)"
    assert model["parents"][0]["name"] == "Steel"
    assert model["parents"][0]["matrix"][12:15] == [10.0, 0.0, 0.0]
    assert model["resource"] == "Cube" and model["visibility"] == 3
    assert shading == {"type": "shading", "name": "IfcBeam B-1 (2)", "chain_index": 1,
                       "attributes": 15, "lists": [["Steel_grey"]]}
    panel = chains[4]["blocks"][0]
    assert panel["resource"] == "Panel"


def test_mesh_declaration_and_basemesh_round_trip():
    scene = sample_scene()
    doc = U.read_u3d(U.write_u3d(scene))
    clods = {b["name"]: b for c in doc["blocks"] if c["type"] == "chain" for b in c["blocks"] if b["type"] == "clod"}
    cube = clods["Cube"]
    assert (cube["faces"], cube["positions"], cube["normals"], cube["texcoords"]) == (12, 8, 6, 0)
    assert cube["shading"] == [{"attributes": 0, "layers": [], "original_id": 0}]
    assert (cube["min_resolution"], cube["max_resolution"]) == (8, 8)
    assert cube["quality"] == [1000, 1000, 1000] and cube["bones"] == 0
    panel = clods["Panel"]
    assert panel["shading"] == [{"attributes": 0, "layers": [2], "original_id": 0}]
    meshes = {b["name"]: b for b in doc["blocks"] if b["type"] == "basemesh"}
    bm = meshes["Cube"]
    assert bm["positions"] == [tuple(float(v) for v in p) for p in scene["meshes"]["m1"]["positions"]]
    assert bm["normals"] == [tuple(float(v) for v in n) for n in scene["meshes"]["m1"]["normals"]]
    assert [(f[0], f[1], f[2]) for f in bm["faces"]] == [
        (0, tri, (n, n, n)) for (_m, tri, n, _t) in scene["meshes"]["m1"]["faces"]]
    pm = meshes["Panel"]
    assert pm["texcoords"] == [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0)]
    assert pm["faces"][0] == (0, (0, 1, 2), (0, 0, 0), [(0, 1, 2)])


def test_shading_indices_are_per_mesh():
    scene = sample_scene()
    scene["materials"].append({"name": "Paint", "color": (1.0, 0.2, 0.2), "opacity": 1.0,
                               "texture": None, "cutout": False})
    mesh = scene["meshes"]["m1"]
    mesh["faces"] = [(2 if i % 2 else 0, tri, n, t) for i, (_m, tri, n, t) in enumerate(mesh["faces"])]
    doc = U.read_u3d(U.write_u3d(scene))
    clod = next(b for c in doc["blocks"] if c["type"] == "chain" for b in c["blocks"] if b["type"] == "clod" and b["name"] == "Cube")
    assert [s["layers"] for s in clod["shading"]] == [[], []]
    assert [s["original_id"] for s in clod["shading"]] == [0, 1]
    shading = next(b for c in doc["blocks"] if c["type"] == "chain" for b in c["blocks"] if b["type"] == "shading" and b["name"] == "IfcBeam B-1")
    assert shading["lists"] == [["Steel_grey"], ["Paint"]]
    bm = next(b for b in doc["blocks"] if b["type"] == "basemesh" and b["name"] == "Cube")
    assert [f[0] for f in bm["faces"]] == [i % 2 for i in range(12)]


def test_textured_material_on_face_without_uvs_is_refused():
    scene = sample_scene()
    mesh = scene["meshes"]["m1"]
    mesh["faces"] = [(1, tri, n, None) for (_m, tri, n, _t) in mesh["faces"]]
    with pytest.raises(ValueError):
        U.write_u3d(scene)


def test_shader_material_and_texture_blocks():
    doc = U.read_u3d(U.write_u3d(sample_scene()))
    shaders = {b["name"]: b for b in doc["blocks"] if b["type"] == "shader"}
    materials = {b["name"]: b for b in doc["blocks"] if b["type"] == "material"}
    assert shaders["Steel_grey"]["channels"] == 0 and shaders["Steel_grey"]["material"] == "Steel_grey"
    assert (shaders["Steel_grey"]["flags"], shaders["Steel_grey"]["alpha_test_func"],
            shaders["Steel_grey"]["blend_func"], shaders["Steel_grey"]["render_passes"]) == (1, 0x617, 0x606, 1)
    brick = shaders["Brick"]
    assert brick["channels"] == 1 and brick["layers"][0]["texture"] == "brick.jpg"
    assert (brick["layers"][0]["blend"], brick["layers"][0]["source"], brick["layers"][0]["mode"],
            brick["layers"][0]["repeat"]) == (2, 1, 0, 3)
    assert brick["layers"][0]["transform"] == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    assert materials["Steel_grey"]["attributes"] == 63
    assert [round(c, 3) for c in materials["Steel_grey"]["diffuse"]] == [0.5, 0.5, 0.55]
    assert materials["Steel_grey"]["opacity"] == 1.0
    tex = next(b for c in doc["blocks"] if c["type"] == "chain" for b in c["blocks"] if b["type"] == "texture")
    assert tex == {"type": "texture", "name": "brick.jpg", "height": 4, "width": 8, "image_type": 14,
                   "continuations": [{"compression": 1, "channels": 14, "attributes": 0, "size": len(JPEG)}]}
    cont = next(b for b in doc["blocks"] if b["type"] == "texture_continuation")
    assert cont["name"] == "brick.jpg" and cont["index"] == 0 and cont["data"] == JPEG


def test_cutout_png_texture_enables_alpha_test():
    scene = sample_scene()
    scene["materials"][1]["cutout"] = True
    scene["textures"]["brick.jpg"].update({"format": "png", "alpha": True})
    doc = U.read_u3d(U.write_u3d(scene))
    brick = next(b for b in doc["blocks"] if b["type"] == "shader" and b["name"] == "Brick")
    assert brick["flags"] == 3 and brick["alpha_ref"] == 0.5 and brick["alpha_test_func"] == 0x612
    assert brick["alpha_channels"] == 1
    tex = next(b for c in doc["blocks"] if c["type"] == "chain" for b in c["blocks"] if b["type"] == "texture")
    assert tex["image_type"] == 15 and tex["continuations"][0]["compression"] == 2


def test_opacity_is_written():
    scene = sample_scene()
    scene["materials"][0]["opacity"] = 0.4
    doc = U.read_u3d(U.write_u3d(scene))
    mat = next(b for b in doc["blocks"] if b["type"] == "material" and b["name"] == "Steel_grey")
    assert round(mat["opacity"], 3) == 0.4


def test_write_u3d_dedupes_node_names():
    scene = sample_scene()
    scene["layers"][1]["nodes"][0]["name"] = "Steel"          # a node named like a layer
    scene["layers"].append({"name": "Steel", "nodes": []})     # a second layer named Steel
    doc = U.read_u3d(U.write_u3d(scene))
    names = [c["name"] for c in doc["blocks"] if c["type"] == "chain" and c["chain_type"] == 0]
    assert names == ["Steel", "IfcBeam B-1", "IfcBeam B-1 (2)", "Walls", "Steel (2)", "Steel (3)"]
    assert len(set(names)) == len(names)


def test_large_mesh_round_trips_beyond_static_context_range():
    n = 17000
    positions = [(float(i), float(i % 7), 0.0) for i in range(n)]
    faces = [(0, (i, i + 1, i + 2), 0, None) for i in range(0, n - 2, 3)]
    scene = {"layers": [{"name": "L", "nodes": [{"name": "Big", "mesh": "m", "matrix": None}]}],
             "meshes": {"m": {"name": "Big", "positions": positions, "normals": [(0, 0, 1)],
                              "texcoords": [], "faces": faces}},
             "materials": [{"name": "m", "color": (1, 0, 0), "opacity": 1.0, "texture": None, "cutout": False}],
             "textures": {}}
    doc = U.read_u3d(U.write_u3d(scene))
    bm = next(b for b in doc["blocks"] if b["type"] == "basemesh")
    assert len(bm["positions"]) == n
    assert [f[1] for f in bm["faces"]] == [f[1] for f in faces]


def test_empty_mesh_is_refused():
    scene = sample_scene()
    scene["meshes"]["m1"]["faces"] = []
    with pytest.raises(ValueError):
        U.write_u3d(scene)


def test_view_and_light_are_written_from_the_camera():
    scene = sample_scene()
    scene["camera"] = {"eye": (0.0, 0.0, 50.0), "target": (0.0, 0.0, 0.0), "up": (0.0, 1.0, 0.0),
                       "fov": 40.0, "perspective": True}
    doc = U.read_u3d(U.write_u3d(scene))
    chains = [b for b in doc["blocks"] if b["type"] == "chain"]
    assert (chains[0]["name"], chains[0]["chain_type"]) == ("DefaultView", 0)
    view = chains[0]["blocks"][0]
    assert view["type"] == "view" and view["resource"] == "SceneViewResource"
    m = view["parents"][0]["matrix"]
    assert [round(v, 6) for v in m[0:3]] == [1.0, 0.0, 0.0]        # right
    assert [round(v, 6) for v in m[4:7]] == [0.0, 1.0, 0.0]        # up
    assert [round(v, 6) for v in m[8:11]] == [0.0, 0.0, 1.0]       # back (camera looks down -z)
    assert m[12:15] == [0.0, 0.0, 50.0]
    assert view["attributes"] == 0 and view["near"] == 1.0 and view["projection"] == 40.0
    assert view["viewport"] == [800.0, 600.0, 0.0, 0.0] and view["backdrops"] == 0 and view["overlays"] == 0
    light_chain = next(c for c in chains if c["name"] == "DefaultLight")
    light = light_chain["blocks"][0]
    assert light["type"] == "light" and light["resource"] == "DefaultPointLight"
    assert light["parents"][0]["matrix"][12:15] == [0.0, 0.0, 50.0]
    vres = next(b for b in doc["blocks"] if b["type"] == "view_resource")
    assert vres == {"type": "view_resource", "name": "SceneViewResource", "passes": [
        {"root": "", "attributes": 0, "fog_mode": 0, "fog_color": [0.0, 0.0, 0.0, 0.0],
         "fog_near": 0.0, "fog_far": 1000.0}]}
    lres = next(b for b in doc["blocks"] if b["type"] == "light_resource")
    assert lres == {"type": "light_resource", "name": "DefaultPointLight", "attributes": 1,
                    "light_type": 2, "color": [1.0, 1.0, 1.0, 1.0], "attenuation": [1.0, 0.0, 0.0],
                    "spot_angle": 180.0, "intensity": 1.0}
    # The model nodes still follow the view, and no view is written without a camera.
    assert [c["name"] for c in chains][1:3] == ["Steel", "IfcBeam B-1"]
    plain = U.read_u3d(U.write_u3d(sample_scene()))
    assert not any(b["type"] in ("view_resource", "light_resource") for b in plain["blocks"])


def test_reads_sample_view_and_light_resources(data_dir):
    doc = U.read_u3d((data_dir / "box.u3d").read_bytes())
    view = doc["blocks"][2]["blocks"][0]
    assert view["type"] == "view" and view["near"] == 1.0 and round(view["projection"], 3) == 34.516
    assert view["viewport"] == [800.0, 600.0, 0.0, 0.0]
    vres = next(b for b in doc["blocks"] if b["type"] == "view_resource")
    assert vres["passes"][0]["fog_far"] == 1000.0
    lres = next(b for b in doc["blocks"] if b["type"] == "light_resource")
    assert lres["light_type"] == 2 and lres["spot_angle"] == 180.0
