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
    """Task 4 fills this in; until then the block is reported as opaque."""
    return {"type": "basemesh", "name": r.string()}


def read_u3d(data: bytes) -> dict:
    decls: dict = {}
    blocks = [_parse_block(b, p, decls) for b, p in iter_blocks(data)]
    header = blocks[0] if blocks and blocks[0]["type"] == "header" else None
    if header is not None:
        header = {k: v for k, v in header.items() if k != "type"}
    return {"header": header, "blocks": blocks}
