# SPDX-License-Identifier: GPL-3.0-or-later
import io
import zlib

import pytest
from pypdf import PdfReader
from pypdf.generic import IndirectObject

from igz_pdf3d import _pdf as P
from igz_pdf3d import _views as W

U3D = b"U3D\0" + bytes(range(256)) * 4
JPEG = b"\xff\xd8\xff\xe0" + bytes(range(100)) + b"\xff\xd9"
VIEWS = W.make_views({"eye": (10.0, 10.0, 10.0), "target": (0.0, 0.0, 0.0), "up": (0.0, 1.0, 0.0),
                      "fov": 45.0, "perspective": True}, ((-1, -1, -1), (1, 1, 1)))
OPTIONS = {"title": "Bonnie Compressor (Rev B)", "note": "Issued for review",
           "date": "2026-10-14", "units_label": "inches", "page": "letter"}


def _resolve(x):
    return x.get_object() if isinstance(x, IndirectObject) else x


def _read(data):
    return PdfReader(io.BytesIO(data))


def _annot(reader):
    page = reader.pages[0]
    annots = [_resolve(a) for a in page["/Annots"]]
    assert len(annots) == 1
    return annots[0]


def test_page_sizes():
    for page, (w, h) in (("letter", (792.0, 612.0)), ("a4", (841.89, 595.28))):
        data = P.write_pdf({**OPTIONS, "page": page}, U3D, VIEWS, JPEG, (64, 48))
        reader = _read(data)
        assert len(reader.pages) == 1
        box = reader.pages[0].mediabox
        assert (round(float(box.width), 2), round(float(box.height), 2)) == (w, h)


def test_annotation_rect_leaves_room_for_the_strip():
    x0, y0, x1, y1 = P.annotation_rect("letter")
    assert (x0, y0) == (36.0, 36.0) and x1 == 792.0 - 36.0
    assert y1 < 612.0 - 36.0 - 72.0 and y1 > 400


def test_3d_annotation_structure():
    data = P.write_pdf(OPTIONS, U3D, VIEWS, JPEG, (64, 48))
    reader = _read(data)
    a = _annot(reader)
    assert a["/Subtype"] == "/3D" and bool(a["/3DI"]) is True
    assert [float(v) for v in a["/Rect"]] == list(P.annotation_rect("letter"))
    act = _resolve(a["/3DA"])
    assert act["/A"] == "/PO" and act["/D"] == "/PC" and act["/AIS"] == "/I"
    stream = _resolve(a["/3DD"])
    assert stream["/Type"] == "/3D" and stream["/Subtype"] == "/U3D"
    assert stream.get_data() == U3D
    views = [_resolve(v) for v in stream["/VA"]]
    assert [str(v["/XN"]) for v in views] == ["Exported view", "Iso", "Top", "Front", "Back", "Left", "Right"]
    assert _resolve(stream["/DV"])["/XN"] == "Exported view"
    assert _resolve(a["/3DV"])["/XN"] == "Exported view"
    v = views[0]
    assert v["/Type"] == "/3DView" and v["/MS"] == "/M"
    assert len(v["/C2W"]) == 12 and float(v["/CO"]) == pytest.approx(VIEWS[0]["co"])
    assert [round(float(x), 6) for x in v["/C2W"]] == [round(x, 6) for x in VIEWS[0]["c2w"]]
    proj = _resolve(v["/P"])
    assert proj["/Subtype"] == "/P" and float(proj["/FOV"]) == 45.0
    assert _resolve(v["/LS"])["/Subtype"] == "/CAD"
    assert _resolve(v["/RM"])["/Subtype"] == "/Solid"
    bg = _resolve(v["/BG"])
    assert bg["/Subtype"] == "/SC" and [float(c) for c in bg["/C"]] == [1.0, 1.0, 1.0]


def test_poster_is_the_normal_appearance():
    data = P.write_pdf(OPTIONS, U3D, VIEWS, JPEG, (64, 48))
    a = _annot(_read(data))
    form = _resolve(_resolve(a["/AP"])["/N"])
    assert form["/Subtype"] == "/Form"
    x0, y0, x1, y1 = P.annotation_rect("letter")
    assert [round(float(v), 2) for v in form["/BBox"]] == [0, 0, round(x1 - x0, 2), round(y1 - y0, 2)]
    image = _resolve(_resolve(form["/Resources"])["/XObject"]["/Im1"])
    assert image["/Subtype"] == "/Image" and image["/Filter"] == "/DCTDecode"
    assert (int(image["/Width"]), int(image["/Height"])) == (64, 48)
    assert image.get_data() == JPEG
    assert b"/Im1 Do" in form.get_data()


def test_without_poster_still_valid():
    data = P.write_pdf(OPTIONS, U3D, VIEWS, None, None)
    a = _annot(_read(data))
    form = _resolve(_resolve(a["/AP"])["/N"])
    assert "/XObject" not in _resolve(form["/Resources"])
    assert b"re" in form.get_data()                 # a grey placeholder rectangle


def test_title_strip_text_and_info():
    data = P.write_pdf(OPTIONS, U3D, VIEWS, None, None)
    reader = _read(data)
    text = reader.pages[0].extract_text()
    assert "Bonnie Compressor (Rev B)" in text
    assert "Issued for review" in text and "2026-10-14" in text and "Model units: inches" in text
    assert "Acrobat" in text
    assert reader.metadata.title == "Bonnie Compressor (Rev B)"
    assert "igz_pdf3d" in reader.metadata.producer


def test_special_characters_are_escaped():
    opts = {**OPTIONS, "title": "Back\\slash (and) parens — café ☃", "note": ""}
    data = P.write_pdf(opts, U3D, VIEWS, None, None)
    reader = _read(data)
    text = reader.pages[0].extract_text()
    assert "Back\\slash (and) parens" in text and "café" in text
    assert reader.metadata.title == opts["title"]


def test_u3d_stream_is_flate_compressed():
    data = P.write_pdf(OPTIONS, U3D, VIEWS, None, None)
    stream = _resolve(_annot(_read(data))["/3DD"])
    assert stream["/Filter"] == "/FlateDecode"
    assert len(data) < len(U3D) + 6000


def test_xref_offsets_are_exact():
    data = P.write_pdf(OPTIONS, U3D, VIEWS, JPEG, (64, 48))
    start = int(data[data.rindex(b"startxref") + 9:].split()[0])
    assert data[start:start + 4] == b"xref"
    lines = data[start:].split(b"\n")
    count = int(lines[1].split()[1])
    for i in range(1, count):
        offset = int(lines[2 + i][:10])
        assert data[offset:].startswith(f"{i} 0 obj".encode())
