# SPDX-License-Identifier: GPL-3.0-or-later
"""A one-page PDF 1.7 with a title strip and a 3D annotation (U3D).

Written by hand: a classic cross-reference table, standard Helvetica fonts
(no embedding), the U3D stream Flate-compressed, the viewport snapshot as a
DCTDecode image in the annotation's normal appearance so viewers without 3D
show it. Keys follow ISO 32000-1 section 13.6 (3D artwork).
"""
from __future__ import annotations

import zlib

PAGE_SIZES = {"letter": (792.0, 612.0), "a4": (841.89, 595.28)}
MARGIN = 36.0
STRIP = 72.0
GAP = 6.0
POSTER_GREY = 0.93
PRODUCER = "igz_pdf3d for IngeTrazo"


def annotation_rect(page: str) -> tuple:
    w, h = PAGE_SIZES.get(page, PAGE_SIZES["letter"])
    return (MARGIN, MARGIN, w - MARGIN, h - MARGIN - STRIP - GAP)


def _num(v: float) -> str:
    s = f"{float(v):.6f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _text(s: str) -> bytes:
    """A literal string in WinAnsi for page content and names."""
    raw = str(s).encode("cp1252", "replace")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _utext(s: str) -> bytes:
    """A UTF-16BE text string (document information, view names)."""
    raw = b"\xfe\xff" + str(s).encode("utf-16-be")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


class _Doc:
    def __init__(self) -> None:
        self.objects: list = []

    def reserve(self) -> int:
        self.objects.append(None)
        return len(self.objects)

    def set(self, num: int, body: bytes) -> int:
        self.objects[num - 1] = body
        return num

    def add(self, body: bytes) -> int:
        return self.set(self.reserve(), body)

    def stream(self, entries: bytes, data: bytes, flate: bool = False) -> int:
        if flate:
            data = zlib.compress(data, 9)
            entries = entries + b" /Filter /FlateDecode"
        body = b"<< " + entries + b" /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream"
        return self.add(body)

    def build(self, root: int, info: int) -> bytes:
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(self.objects, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(self.objects) + 1}\n".encode()
        out += b"0000000000 65535 f \n"
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += (f"trailer\n<< /Size {len(self.objects) + 1} /Root {root} 0 R /Info {info} 0 R >>\n"
                f"startxref\n{xref}\n%%EOF\n").encode()
        return bytes(out)


def _view_dict(view: dict) -> bytes:
    c2w = b" ".join(_num(v).encode() for v in view["c2w"])
    return (b"<< /Type /3DView /XN " + _utext(view["name"]) + b" /IN " + _text(view["name"])
            + b" /MS /M /C2W [" + c2w + b"] /CO " + _num(view["co"]).encode()
            + b" /P << /Subtype /P /FOV " + _num(view["fov"]).encode() + b" >>"
            + b" /LS << /Type /3DLightingScheme /Subtype /CAD >>"
            + b" /RM << /Type /3DRenderMode /Subtype /Solid >>"
            + b" /BG << /Type /3DBG /Subtype /SC /CS /DeviceRGB /C [1 1 1] >> >>")


def _strip_content(options: dict, page_w: float, page_h: float) -> bytes:
    top = page_h - MARGIN
    second = " · ".join(part for part in (
        options.get("note") or "", options.get("date") or "",
        f"Model units: {options.get('units_label') or 'inches'}") if part)
    hint = "Interactive in Adobe Acrobat Reader and Bluebeam Revu. Click the view to activate 3D."
    x0, y0, x1, y1 = annotation_rect(options.get("page") or "letter")
    lines = [
        b"q",
        b"BT /F1 18 Tf " + _num(MARGIN).encode() + b" " + _num(top - 20).encode() + b" Td "
        + _text(options.get("title") or "Untitled model") + b" Tj ET",
        b"BT /F2 10 Tf " + _num(MARGIN).encode() + b" " + _num(top - 38).encode() + b" Td "
        + _text(second) + b" Tj ET",
        b"0.45 g BT /F2 8 Tf " + _num(MARGIN).encode() + b" " + _num(top - 54).encode() + b" Td "
        + _text(hint) + b" Tj ET 0 g",
        b"0.75 G 0.5 w " + _num(MARGIN).encode() + b" " + _num(y1 + GAP / 2).encode() + b" m "
        + _num(page_w - MARGIN).encode() + b" " + _num(y1 + GAP / 2).encode() + b" l S",
        b"0.75 G 0.5 w " + _num(x0).encode() + b" " + _num(y0).encode() + b" "
        + _num(x1 - x0).encode() + b" " + _num(y1 - y0).encode() + b" re S",
        b"Q",
    ]
    return b"\n".join(lines)


def write_pdf(options: dict, u3d_bytes: bytes, views, poster=None, poster_size=None) -> bytes:
    page = options.get("page") or "letter"
    page_w, page_h = PAGE_SIZES.get(page, PAGE_SIZES["letter"])
    x0, y0, x1, y1 = annotation_rect(page)
    aw, ah = x1 - x0, y1 - y0
    doc = _Doc()
    catalog = doc.reserve()
    pages = doc.reserve()
    page_obj = doc.reserve()
    content = doc.stream(b"", _strip_content(options, page_w, page_h), flate=True)
    f1 = doc.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    f2 = doc.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")

    view_refs = [doc.add(_view_dict(v)) for v in views]
    va = b" ".join(f"{n} 0 R".encode() for n in view_refs)
    stream3d = doc.stream(b"/Type /3D /Subtype /U3D /VA [" + va + b"] /DV " + f"{view_refs[0]} 0 R".encode(),
                          u3d_bytes, flate=True)

    resources = b"<< >>"
    if poster and poster_size:
        pw, ph = int(poster_size[0]), int(poster_size[1])
        image = doc.stream(b"/Type /XObject /Subtype /Image /Width " + str(pw).encode() + b" /Height "
                           + str(ph).encode() + b" /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode",
                           bytes(poster))
        resources = f"<< /XObject << /Im1 {image} 0 R >> >>".encode()
        # Letterbox: keep the snapshot's aspect, centre it on a white field.
        scale = min(aw / pw, ah / ph)
        dw, dh = pw * scale, ph * scale
        ox, oy = (aw - dw) / 2.0, (ah - dh) / 2.0
        draw = (b"1 g 0 0 " + _num(aw).encode() + b" " + _num(ah).encode() + b" re f q "
                + _num(dw).encode() + b" 0 0 " + _num(dh).encode() + b" "
                + _num(ox).encode() + b" " + _num(oy).encode() + b" cm /Im1 Do Q")
    else:
        draw = (_num(POSTER_GREY).encode() + b" g 0 0 " + _num(aw).encode() + b" " + _num(ah).encode()
                + b" re f")
    appearance = doc.stream(b"/Type /XObject /Subtype /Form /BBox [0 0 " + _num(aw).encode() + b" "
                            + _num(ah).encode() + b"] /Resources " + resources, draw)

    annot = doc.add(
        b"<< /Type /Annot /Subtype /3D /F 4 /P " + f"{page_obj} 0 R".encode()
        + b" /Rect [" + b" ".join(_num(v).encode() for v in (x0, y0, x1, y1)) + b"]"
        + b" /Contents " + _utext(options.get("title") or "3D model") + b" /NM (igz_pdf3d)"
        + b" /3DD " + f"{stream3d} 0 R".encode() + b" /3DV " + f"{view_refs[0]} 0 R".encode()
        + b" /3DA << /A /PO /AIS /I /D /PC /DIS /U /TB true /NP true >> /3DI true"
        + b" /AP << /N " + f"{appearance} 0 R".encode() + b" >> >>")

    doc.set(page_obj, b"<< /Type /Page /Parent " + f"{pages} 0 R".encode()
            + b" /MediaBox [0 0 " + _num(page_w).encode() + b" " + _num(page_h).encode() + b"]"
            + b" /Contents " + f"{content} 0 R".encode()
            + b" /Resources << /Font << /F1 " + f"{f1} 0 R /F2 {f2} 0 R".encode() + b" >> >>"
            + b" /Annots [" + f"{annot} 0 R".encode() + b"] >>")
    doc.set(pages, b"<< /Type /Pages /Kids [" + f"{page_obj} 0 R".encode() + b"] /Count 1 >>")
    doc.set(catalog, b"<< /Type /Catalog /Pages " + f"{pages} 0 R".encode() + b" >>")
    date = (options.get("date") or "").replace("-", "")
    info = doc.add(b"<< /Title " + _utext(options.get("title") or "")
                   + b" /Producer " + _utext(PRODUCER)
                   + (b" /CreationDate (D:" + date.encode() + b")" if len(date) == 8 else b"") + b" >>")
    return doc.build(catalog, info)
