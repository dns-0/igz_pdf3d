# SPDX-License-Identifier: GPL-3.0-or-later
"""U3D file assembly and, for the tests, a reader.

Block layouts follow the U3D Sample Software encoders (Apache-2.0, see
THIRD-PARTY.md) and were verified against its sample files. Every block is
``type U32, size U32, metadata size U32, payload padded to 4 bytes``; the
declarations of a node, a mesh or a texture sit inside a Modifier Chain block
of their own; shaders and materials are top-level blocks; continuation blocks
come after a Priority Update block.
"""
from __future__ import annotations

import struct

from ._u3d_bits import STATIC_FULL, BitReader, BitWriter

BT_HEADER = 0x00443355
BT_CHAIN = 0xFFFFFF14
BT_PRIORITY = 0xFFFFFF15
BT_GROUP = 0xFFFFFF21
BT_MODEL = 0xFFFFFF22
BT_LIGHT = 0xFFFFFF23
BT_VIEW = 0xFFFFFF24
BT_CLOD = 0xFFFFFF31
BT_BASEMESH = 0xFFFFFF3B
BT_PROGRESSIVE = 0xFFFFFF3C
BT_SHADING = 0xFFFFFF45
BT_LIGHT_RES = 0xFFFFFF51
BT_VIEW_RES = 0xFFFFFF52
BT_SHADER = 0xFFFFFF53
BT_MATERIAL = 0xFFFFFF54
BT_TEXTURE = 0xFFFFFF55
BT_TEXCONT = 0xFFFFFF5C

CHAIN_NODE, CHAIN_RESOURCE, CHAIN_TEXTURE = 0, 1, 2
CTX_SHADING_ID = 1                 # uACContextBaseShadingID
ENCODING_UTF8 = 106
DECLARATION_SIZE = 36              # what the reference writer leaves in the header
PRIORITY_TEXTURE = 1
PRIORITY_MESH = 256


# ---- framing ---------------------------------------------------------------

def _pad4(data: bytes) -> bytes:
    return data + b"\0" * ((-len(data)) % 4)


def pack_block(btype: int, payload: bytes) -> bytes:
    return struct.pack("<III", btype, len(payload), 0) + _pad4(payload)


def iter_blocks(data: bytes, start: int = 0):
    off = start
    end = len(data)
    while off + 12 <= end:
        btype, size, meta = struct.unpack_from("<III", data, off)
        yield btype, data[off + 12: off + 12 + size]
        off += 12 + ((size + 3) & ~3) + ((meta + 3) & ~3)


def chain_block(name: str, chain_type: int, inner_blocks) -> bytes:
    """A Modifier Chain block whose data holds ``inner_blocks`` (already
    packed with their headers) after a 4-byte aligned count."""
    w = BitWriter()
    w.write_string(name)
    w.write_u32(chain_type)
    w.write_u32(0)                                   # attributes: no bounds
    for _ in range((4 - ((2 + len(name.encode("utf-8"))) & 3)) & 3):
        w.write_u8(0)
    w.write_u32(len(inner_blocks))
    return pack_block(BT_CHAIN, w.get_bytes() + b"".join(inner_blocks))


def header_block() -> bytes:
    w = BitWriter()
    w.write_u32(0)                                   # version, first edition
    w.write_u32(0)                                   # profile
    w.write_u32(DECLARATION_SIZE)
    w.write_u64(0)                                   # file size, patched later
    w.write_u32(ENCODING_UTF8)
    return pack_block(BT_HEADER, w.get_bytes())


def priority_block(priority: int) -> bytes:
    w = BitWriter()
    w.write_u32(priority)
    return pack_block(BT_PRIORITY, w.get_bytes())


def patch_file_size(data: bytes) -> bytes:
    """The header's file size field sits at byte 24 (12 header + 12 payload)."""
    return data[:24] + struct.pack("<Q", len(data)) + data[32:]


# ---- reader (tests only) ---------------------------------------------------

def _read_node_common(r: BitReader) -> tuple:
    name = r.string()
    parents = []
    for _ in range(r.u32()):
        parents.append({"name": r.string(), "matrix": [r.f32() for _ in range(16)]})
    return name, parents


def _parse_block(btype: int, payload: bytes, decls: dict) -> dict:
    r = BitReader(payload)
    if btype == BT_HEADER:
        out = {"version": r.u32(), "profile": r.u32(), "declaration_size": r.u32(),
               "file_size": r.u64(), "encoding": r.u32()}
        out["units"] = r.f64() if out["profile"] & 8 else None
        return {"type": "header", **out}
    if btype == BT_PRIORITY:
        return {"type": "priority", "priority": r.u32()}
    if btype == BT_CHAIN:
        name = r.string()
        chain_type = r.u32()
        attrs = r.u32()
        if attrs & 1:
            [r.f32() for _ in range(4)]
        if attrs & 2:
            [r.f32() for _ in range(6)]
        for _ in range((4 - ((2 + len(name.encode("utf-8"))) & 3)) & 3):
            r.u8()
        count = r.u32()
        start = r.bitcount() // 8
        inner = [_parse_block(b, p, decls) for b, p in iter_blocks(payload, start)]
        return {"type": "chain", "name": name, "chain_type": chain_type,
                "count": count, "blocks": inner}
    if btype == BT_GROUP:
        name, parents = _read_node_common(r)
        return {"type": "group", "name": name, "parents": parents}
    if btype == BT_MODEL:
        name, parents = _read_node_common(r)
        return {"type": "model", "name": name, "parents": parents,
                "resource": r.string(), "visibility": r.u32()}
    if btype in (BT_LIGHT, BT_VIEW):
        name, parents = _read_node_common(r)
        return {"type": "light" if btype == BT_LIGHT else "view", "name": name,
                "parents": parents, "resource": r.string()}
    if btype == BT_CLOD:
        out = {"type": "clod", "name": r.string(), "chain_index": r.u32(),
               "attributes": r.u32(), "faces": r.u32(), "positions": r.u32(),
               "normals": r.u32(), "diffuse": r.u32(), "specular": r.u32(),
               "texcoords": r.u32()}
        shading = []
        for _ in range(r.u32()):
            sa = r.u32()
            layers = [r.u32() for _ in range(r.u32())]
            shading.append({"attributes": sa, "layers": layers, "original_id": r.u32()})
        out["shading"] = shading
        out["min_resolution"] = r.u32()
        out["max_resolution"] = r.u32()
        out["quality"] = [r.u32() for _ in range(3)]
        out["inverse_quant"] = [r.f32() for _ in range(5)]
        out["normal_params"] = [r.f32() for _ in range(3)]
        out["bones"] = r.u32()
        decls[out["name"]] = out
        return out
    if btype == BT_SHADING:
        out = {"type": "shading", "name": r.string(), "chain_index": r.u32(),
               "attributes": r.u32()}
        out["lists"] = [[r.string() for _ in range(r.u32())] for _ in range(r.u32())]
        return out
    if btype == BT_SHADER:
        out = {"type": "shader", "name": r.string(), "flags": r.u32(),
               "alpha_ref": r.f32(), "alpha_test_func": r.u32(), "blend_func": r.u32(),
               "render_passes": r.u32(), "channels": r.u32(), "alpha_channels": r.u32(),
               "material": r.string()}
        layers = []
        for i in range(8):
            if out["channels"] & (1 << i):
                layers.append({"texture": r.string(), "intensity": r.f32(),
                               "blend": r.u8(), "source": r.u8(), "constant": r.f32(),
                               "mode": r.u8(),
                               "transform": [r.f32() for _ in range(16)],
                               "wrap": [r.f32() for _ in range(16)],
                               "repeat": r.u8()})
        out["layers"] = layers
        return out
    if btype == BT_MATERIAL:
        return {"type": "material", "name": r.string(), "attributes": r.u32(),
                "ambient": [r.f32() for _ in range(3)], "diffuse": [r.f32() for _ in range(3)],
                "specular": [r.f32() for _ in range(3)], "emissive": [r.f32() for _ in range(3)],
                "reflectivity": r.f32(), "opacity": r.f32()}
    if btype == BT_TEXTURE:
        out = {"type": "texture", "name": r.string(), "height": r.u32(), "width": r.u32(),
               "image_type": r.u8()}
        conts = []
        for _ in range(r.u32()):
            c = {"compression": r.u8(), "channels": r.u8(), "attributes": r.u16()}
            if c["attributes"] == 0:
                c["size"] = r.u32()
            else:
                c["urls"] = [r.string() for _ in range(r.u32())]
            conts.append(c)
        out["continuations"] = conts
        return out
    if btype == BT_TEXCONT:
        name = r.string()
        index = r.u32()
        return {"type": "texture_continuation", "name": name, "index": index, "data": r.rest()}
    if btype == BT_BASEMESH:
        return _parse_basemesh(r, decls)
    if btype == BT_PROGRESSIVE:
        return {"type": "progressive", "name": r.string(), "chain_index": r.u32(),
                "start": r.u32(), "end": r.u32()}
    return {"type": "unknown", "block_type": btype, "size": len(payload)}


def _parse_basemesh(r: BitReader, decls: dict) -> dict:
    name = r.string()
    r.u32()                                          # chain index
    nfaces, npos, nnorm, ndiff, nspec, ntex = (r.u32() for _ in range(6))
    positions = [(r.f32(), r.f32(), r.f32()) for _ in range(npos)]
    normals = [(r.f32(), r.f32(), r.f32()) for _ in range(nnorm)]
    for _ in range(ndiff + nspec):
        [r.f32() for _ in range(4)]
    texcoords = []
    for _ in range(ntex):
        u, v = r.f32(), r.f32()
        r.f32()
        r.f32()
        texcoords.append((u, v))
    decl = decls[name]
    exclude_normals = bool(decl["attributes"] & 1)
    faces = []
    for _ in range(nfaces):
        shading = r.cu32(CTX_SHADING_ID)
        desc = decl["shading"][shading]
        layers = len(desc["layers"])
        pos, nor, tex = [], [], [[] for _ in range(layers)]
        for _corner in range(3):
            pos.append(r.cu32(STATIC_FULL + npos))
            if not exclude_normals:
                nor.append(r.cu32(STATIC_FULL + nnorm))
            if desc["attributes"] & 1:
                r.cu32(STATIC_FULL + ndiff)
            if desc["attributes"] & 2:
                r.cu32(STATIC_FULL + nspec)
            for layer in range(layers):
                tex[layer].append(r.cu32(STATIC_FULL + ntex))
        faces.append((shading, tuple(pos), tuple(nor), [tuple(t) for t in tex]))
    return {"type": "basemesh", "name": name, "positions": positions, "normals": normals,
            "texcoords": texcoords, "faces": faces}


def read_u3d(data: bytes) -> dict:
    decls: dict = {}
    blocks = [_parse_block(b, p, decls) for b, p in iter_blocks(data)]
    header = blocks[0] if blocks and blocks[0]["type"] == "header" else None
    if header is not None:
        header = {k: v for k, v in header.items() if k != "type"}
    return {"header": header, "blocks": blocks}


# ---- writer ----------------------------------------------------------------

IDENTITY = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
_ALPHA_ALWAYS = 0x0617
_ALPHA_GREATER = 0x0612
_BLEND_ALPHA = 0x0606
_TEX_MULTIPLY = 2                  # IFX_MODULATE
_TEX_SOURCE_CONSTANT = 1
_TEX_REPEAT_UV = 3
_IMAGE_RGB, _IMAGE_RGBA = 14, 15
_COMPRESSION_JPEG, _COMPRESSION_PNG = 1, 2


class _Namer:
    """Unique names within one U3D palette: ``name``, ``name (2)``, ``name (3)``."""

    def __init__(self) -> None:
        self.used: set = set()

    def unique(self, name: str) -> str:
        base = (name or "Unnamed").strip() or "Unnamed"
        candidate, n = base, 2
        while candidate in self.used:
            candidate = f"{base} ({n})"
            n += 1
        self.used.add(candidate)
        return candidate


def _node_block(btype: int, name: str, parent: str, matrix, resource: str | None) -> bytes:
    w = BitWriter()
    w.write_string(name)
    w.write_u32(1)
    w.write_string(parent)
    for v in (matrix or IDENTITY):
        w.write_f32(float(v))
    if btype == BT_MODEL:
        w.write_string(resource or "")
        w.write_u32(3)                               # front and back faces visible
    return pack_block(btype, w.get_bytes())


def _shading_block(node_name: str, shader_names) -> bytes:
    w = BitWriter()
    w.write_string(node_name)
    w.write_u32(1)                                   # chain index: after the node
    w.write_u32(15)                                  # attributes as the reference writes
    w.write_u32(len(shader_names))
    for shader in shader_names:
        w.write_u32(1)
        w.write_string(shader)
    return pack_block(BT_SHADING, w.get_bytes())


def _inverse_quant_position(positions) -> float:
    """The reference encoder's position quantizer for quality 1000, only so
    the declaration carries plausible values (unused without resolution
    updates)."""
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    zs = [p[2] for p in positions]
    cx, cy, cz = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2
    radius = max(((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) ** 0.5 for x, y, z in positions)
    quant = 2.0 ** 18
    if radius > 0:
        quant /= radius
    biggest = max(abs(v) for v in xs + ys + zs)
    if biggest > 0:
        quant = min(quant, 4294966784.0 / biggest)
    return 1.0 / quant


def _clod_declaration(name: str, mesh: dict, shading) -> bytes:
    w = BitWriter()
    w.write_string(name)
    w.write_u32(0)                                   # chain index
    w.write_u32(0)                                   # attributes: normals included
    w.write_u32(len(mesh["faces"]))
    w.write_u32(len(mesh["positions"]))
    w.write_u32(len(mesh["normals"]))
    w.write_u32(0)                                   # diffuse colours
    w.write_u32(0)                                   # specular colours
    w.write_u32(len(mesh["texcoords"]))
    w.write_u32(len(shading))
    for index, (_material_index, textured) in enumerate(shading):
        w.write_u32(0)                               # no vertex colours
        w.write_u32(1 if textured else 0)
        if textured:
            w.write_u32(2)                           # texture coordinate dimensions
        w.write_u32(index)
    npos = len(mesh["positions"])
    w.write_u32(npos)                                # minimum resolution
    w.write_u32(npos)                                # final maximum resolution
    for _ in range(3):
        w.write_u32(1000)                            # position, normal, texcoord quality
    w.write_f32(_inverse_quant_position(mesh["positions"]))
    for _ in range(4):
        w.write_f32(1.0 / 2.0 ** 14)
    w.write_f32(0.9)                                 # normal crease parameter
    w.write_f32(0.5)                                 # normal update parameter
    w.write_f32(0.985)                               # normal tolerance
    w.write_u32(0)                                   # bones
    return pack_block(BT_CLOD, w.get_bytes())


def _basemesh_block(name: str, mesh: dict, shading_index: dict, shading) -> bytes:
    w = BitWriter()
    w.write_string(name)
    w.write_u32(0)                                   # chain index
    npos, nnorm, ntex = len(mesh["positions"]), len(mesh["normals"]), len(mesh["texcoords"])
    w.write_u32(len(mesh["faces"]))
    w.write_u32(npos)
    w.write_u32(nnorm)
    w.write_u32(0)
    w.write_u32(0)
    w.write_u32(ntex)
    for x, y, z in mesh["positions"]:
        w.write_f32(float(x))
        w.write_f32(float(y))
        w.write_f32(float(z))
    for x, y, z in mesh["normals"]:
        w.write_f32(float(x))
        w.write_f32(float(y))
        w.write_f32(float(z))
    for u, v in mesh["texcoords"]:
        w.write_f32(float(u))
        w.write_f32(float(v))
        w.write_f32(0.0)
        w.write_f32(0.0)
    for material_index, corners, normal_index, tex in mesh["faces"]:
        sid = shading_index[material_index]
        textured = shading[sid][1]
        w.write_cu32(CTX_SHADING_ID, sid)
        for k in range(3):
            w.write_cu32(STATIC_FULL + npos, corners[k])
            w.write_cu32(STATIC_FULL + nnorm, normal_index)
            if textured:
                w.write_cu32(STATIC_FULL + ntex, tex[k])
    return pack_block(BT_BASEMESH, w.get_bytes())


def _shader_block(name: str, material_name: str, texture_name, cutout: bool, alpha: bool) -> bytes:
    w = BitWriter()
    w.write_string(name)
    w.write_u32(3 if cutout else 1)                  # lighting (+ alpha test)
    w.write_f32(0.5 if cutout else 0.0)              # alpha test reference
    w.write_u32(_ALPHA_GREATER if cutout else _ALPHA_ALWAYS)
    w.write_u32(_BLEND_ALPHA)
    w.write_u32(1)                                   # render pass 1 enabled
    w.write_u32(1 if texture_name else 0)            # texture channels
    w.write_u32(1 if (texture_name and alpha) else 0)
    w.write_string(material_name)
    if texture_name:
        w.write_string(texture_name)
        w.write_f32(1.0)                             # intensity
        w.write_u8(_TEX_MULTIPLY)
        w.write_u8(_TEX_SOURCE_CONSTANT)
        w.write_f32(0.5)                             # blend constant (unused)
        w.write_u8(0)                                # TM_NONE: use the mesh UVs
        for v in IDENTITY:
            w.write_f32(v)
        for v in IDENTITY:
            w.write_f32(v)
        w.write_u8(_TEX_REPEAT_UV)
    return pack_block(BT_SHADER, w.get_bytes())


def _material_block(name: str, material: dict) -> bytes:
    r, g, b = (float(c) for c in material["color"][:3])
    w = BitWriter()
    w.write_string(name)
    w.write_u32(63)
    for v in (r * 0.35, g * 0.35, b * 0.35):          # ambient
        w.write_f32(v)
    for v in (r, g, b):                              # diffuse
        w.write_f32(v)
    for v in (0.1, 0.1, 0.1):                        # specular
        w.write_f32(v)
    for v in (0.0, 0.0, 0.0):                        # emissive
        w.write_f32(v)
    w.write_f32(0.1)                                 # reflectivity
    opacity = material.get("opacity")
    w.write_f32(1.0 if opacity is None else float(opacity))
    return pack_block(BT_MATERIAL, w.get_bytes())


def _texture_declaration(name: str, tex: dict) -> bytes:
    image_type = _IMAGE_RGBA if tex.get("alpha") else _IMAGE_RGB
    w = BitWriter()
    w.write_string(name)
    w.write_u32(int(tex["height"]))
    w.write_u32(int(tex["width"]))
    w.write_u8(image_type)
    w.write_u32(1)                                   # one continuation image
    w.write_u8(_COMPRESSION_PNG if tex.get("format") == "png" else _COMPRESSION_JPEG)
    w.write_u8(image_type)
    w.write_u16(0)                                   # inline image data
    w.write_u32(len(tex["data"]))
    return pack_block(BT_TEXTURE, w.get_bytes())


def _texture_continuation(name: str, tex: dict) -> bytes:
    w = BitWriter()
    w.write_string(name)
    w.write_u32(0)                                   # continuation image index
    return pack_block(BT_TEXCONT, w.get_bytes() + bytes(tex["data"]))


def write_u3d(scene: dict) -> bytes:
    materials = scene["materials"]
    textures = scene.get("textures") or {}
    mat_namer, tex_namer = _Namer(), _Namer()
    material_names = [mat_namer.unique(m["name"]) for m in materials]
    texture_names = {key: tex_namer.unique(key) for key in textures}

    # Per mesh: the shading description list (material index, textured) in
    # order of first use, and the material -> shading index map.
    mesh_namer = _Namer()
    mesh_info: dict = {}
    for key, mesh in scene["meshes"].items():
        if not mesh["faces"]:
            raise ValueError(f"mesh {mesh.get('name', key)!r} has no faces")
        order: list = []
        index: dict = {}
        for material_index, _corners, _n, tex in mesh["faces"]:
            if material_index not in index:
                index[material_index] = len(order)
                textured = materials[material_index].get("texture") is not None
                order.append((material_index, textured))
            if order[index[material_index]][1] and tex is None:
                raise ValueError(f"mesh {mesh.get('name', key)!r}: textured material "
                                 f"{materials[material_index]['name']!r} on a face without UVs")
        mesh_info[key] = {"name": mesh_namer.unique(mesh["name"]), "shading": order,
                          "index": index}

    node_namer = _Namer()
    out = [header_block(), priority_block(0)]
    for layer in scene["layers"]:
        layer_name = node_namer.unique(layer["name"])
        out.append(chain_block(layer_name, CHAIN_NODE,
                               [_node_block(BT_GROUP, layer_name, "", None, None)]))
        for node in layer["nodes"]:
            info = mesh_info[node["mesh"]]
            node_name = node_namer.unique(node["name"])
            shaders = [material_names[m] for m, _t in info["shading"]]
            out.append(chain_block(node_name, CHAIN_NODE, [
                _node_block(BT_MODEL, node_name, layer_name, node.get("matrix"), info["name"]),
                _shading_block(node_name, shaders)]))
    for key, mesh in scene["meshes"].items():
        info = mesh_info[key]
        out.append(chain_block(info["name"], CHAIN_RESOURCE,
                               [_clod_declaration(info["name"], mesh, info["shading"])]))
    for key, tex in textures.items():
        out.append(chain_block(texture_names[key], CHAIN_TEXTURE,
                               [_texture_declaration(texture_names[key], tex)]))
    for material, name in zip(materials, material_names):
        tex_key = material.get("texture")
        tex = textures.get(tex_key) if tex_key is not None else None
        out.append(_shader_block(name, name, texture_names.get(tex_key) if tex else None,
                                 bool(material.get("cutout")) and tex is not None,
                                 bool(tex and tex.get("alpha"))))
    for material, name in zip(materials, material_names):
        out.append(_material_block(name, material))
    if textures:
        out.append(priority_block(PRIORITY_TEXTURE))
        for key, tex in textures.items():
            out.append(_texture_continuation(texture_names[key], tex))
    out.append(priority_block(PRIORITY_MESH))
    for key, mesh in scene["meshes"].items():
        info = mesh_info[key]
        out.append(_basemesh_block(info["name"], mesh, info["index"], info["shading"]))
    return patch_file_size(b"".join(out))
