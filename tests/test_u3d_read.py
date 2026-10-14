# SPDX-License-Identifier: GPL-3.0-or-later
import struct

import pytest

from igz_pdf3d import _u3d as U
from igz_pdf3d._u3d_bits import BitReader, BitWriter


def test_pack_block_pads_payload_to_four_bytes():
    out = U.pack_block(0xFFFFFF15, b"\x01\x00\x00\x00\x02")
    assert out == struct.pack("<III", 0xFFFFFF15, 5, 0) + b"\x01\x00\x00\x00\x02\x00\x00\x00"
    blocks = list(U.iter_blocks(out + U.pack_block(1, b"")))
    assert blocks == [(0xFFFFFF15, b"\x01\x00\x00\x00\x02"), (1, b"")]


@pytest.mark.parametrize("name", ["", "A", "AB", "ABC", "ABCD", "Box01", "DefaultView", "Lines Texture"])
def test_chain_block_inner_blocks_start_aligned(name):
    inner = U.pack_block(0xFFFFFF21, b"\x00\x00\x00\x00\x00\x00")
    chain = U.chain_block(name, U.CHAIN_NODE, [inner, inner])
    btype, payload = next(U.iter_blocks(chain))
    assert btype == U.BT_CHAIN
    r = BitReader(payload)
    assert r.string() == name
    assert r.u32() == U.CHAIN_NODE
    assert r.u32() == 0
    pad = (4 - ((2 + len(name.encode())) & 3)) & 3
    for _ in range(pad):
        assert r.u8() == 0
    assert r.u32() == 2
    start = r.bitcount() // 8
    assert start % 4 == 0
    assert payload[start:] == inner + inner


def test_header_and_priority_blocks():
    data = U.header_block() + U.priority_block(0) + U.priority_block(256)
    data = U.patch_file_size(data)
    blocks = list(U.iter_blocks(data))
    assert [b for b, _ in blocks] == [U.BT_HEADER, U.BT_PRIORITY, U.BT_PRIORITY]
    r = BitReader(blocks[0][1])
    assert (r.u32(), r.u32(), r.u32(), r.u64(), r.u32()) == (0, 0, 36, len(data), 106)
    assert BitReader(blocks[2][1]).u32() == 256


def _chains(doc):
    return [b for b in doc["blocks"] if b["type"] == "chain"]


def test_reads_box_sample(data_dir):
    doc = U.read_u3d((data_dir / "box.u3d").read_bytes())
    assert doc["header"] == {"version": 0, "profile": 0, "declaration_size": 36,
                             "file_size": 1276, "encoding": 106, "units": None}
    chains = _chains(doc)
    assert [(c["name"], c["chain_type"]) for c in chains] == [
        ("DefaultView", 0), ("Box01", 0), ("Omni01", 0), ("Box01", 1)]
    model = chains[1]["blocks"][0]
    assert model["type"] == "model" and model["resource"] == "Box01" and model["visibility"] == 1
    assert model["parents"][0]["name"] == ""
    assert [round(x, 6) for x in model["parents"][0]["matrix"][12:15]] == [-3.336568, -63.002571, 0.0]
    shading = chains[1]["blocks"][1]
    assert shading == {"type": "shading", "name": "Box01", "chain_index": 1,
                       "attributes": 15, "lists": [["Box010"]]}
    clod = chains[3]["blocks"][0]
    assert clod["type"] == "clod" and clod["faces"] == 12 and clod["positions"] == 8
    assert clod["normals"] == 36 and clod["texcoords"] == 0
    assert clod["shading"] == [{"attributes": 0, "layers": [], "original_id": 0}]
    assert (clod["min_resolution"], clod["max_resolution"]) == (0, 8)
    shader = next(b for b in doc["blocks"] if b["type"] == "shader")
    assert shader["name"] == "Box010" and shader["material"] == "Material"
    assert (shader["flags"], shader["alpha_test_func"], shader["blend_func"]) == (1, 0x617, 0x606)
    assert shader["layers"] == []
    material = next(b for b in doc["blocks"] if b["type"] == "material")
    assert material["name"] == "Material" and material["attributes"] == 63
    assert [round(c, 4) for c in material["diffuse"]] == [0.8784, 0.5608, 0.3412]
    assert material["opacity"] == 1.0
    priorities = [b["priority"] for b in doc["blocks"] if b["type"] == "priority"]
    assert priorities == [0, 256]
    assert doc["blocks"][-1]["type"] == "progressive"


def test_reads_group_sample(data_dir):
    doc = U.read_u3d((data_dir / "box_group.u3d").read_bytes())
    chains = _chains(doc)
    group = chains[1]["blocks"][0]
    assert group["type"] == "group" and group["name"] == "Box_Group"
    box02 = chains[3]["blocks"][0]
    assert box02["name"] == "Box02" and box02["parents"][0]["name"] == "Box_Group"
    assert [round(x, 3) for x in box02["parents"][0]["matrix"][12:15]] == [25.0, 25.0, 25.0]
    assert box02["resource"] == "LightBoxModel"


def test_reads_texture_sample(data_dir):
    doc = U.read_u3d((data_dir / "TextureLayers.u3d").read_bytes())
    chains = _chains(doc)
    tex_chains = [c for c in chains if c["chain_type"] == U.CHAIN_TEXTURE]
    assert [c["name"] for c in tex_chains] == ["Texture2", "Texture RGB", "Lines Texture"]
    decl = tex_chains[0]["blocks"][0]
    assert decl == {"type": "texture", "name": "Texture2", "height": 4, "width": 4,
                    "image_type": 14,
                    "continuations": [{"compression": 1, "channels": 14, "attributes": 0, "size": 741}]}
    clod = next(b for c in chains for b in c["blocks"] if b["type"] == "clod")
    assert clod["texcoords"] == 3
    assert [s["layers"] for s in clod["shading"]] == [[2, 2], [2]]
    shader = next(b for b in doc["blocks"] if b["type"] == "shader" and b["name"] == "ModelShader1")
    assert shader["channels"] == 5
    assert [layer["texture"] for layer in shader["layers"]] == ["Texture2", "Texture RGB"]
    assert shader["layers"][0]["blend"] == 2 and shader["layers"][0]["repeat"] == 3
    cont = next(b for b in doc["blocks"] if b["type"] == "texture_continuation")
    assert cont["name"] == "Texture2" and cont["index"] == 0
    assert len(cont["data"]) == 741 and cont["data"][:2] == b"\xff\xd8"
    priorities = [b["priority"] for b in doc["blocks"] if b["type"] == "priority"]
    assert priorities == [0, 1, 256]


def test_reads_vertex_color_sample(data_dir):
    doc = U.read_u3d((data_dir / "VertexColor.u3d").read_bytes())
    clods = [b for c in _chains(doc) for b in c["blocks"] if b["type"] == "clod"]
    teapot = next(c for c in clods if c["name"] == "teapot")
    assert (teapot["faces"], teapot["positions"], teapot["diffuse"]) == (2102, 1085, 1085)
    assert teapot["shading"][0]["attributes"] == 1
