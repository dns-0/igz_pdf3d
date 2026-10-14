# igz_pdf3d — 3D PDF export for IngeTrazo

Select what you want to share (or nothing, for the whole visible model), click
the **3D PDF** toolbar button (or Extensions ▸ Export 3D PDF…), set a title
and a note, and save. The one-page PDF opens in Adobe Acrobat Reader and
Bluebeam Revu as an interactive 3D model with a model tree by layer and
object, the document's materials and textures, and named views (the exported
view plus Iso, Top, Front, Back, Left, Right). Other viewers show a snapshot
of the viewport.

## Selection rules

- A selected group exports whole, with all its children.
- Selected loose faces export as one "Loose geometry" node per layer.
- Nothing selected exports every visible layer and group.
- Edges are ignored; a 3D PDF has no lines.

## Units

Imperial (default): one U3D unit is one inch. Metric: metres. The PDF has no
unit field that viewers honour, so set the viewer's measure tool to the unit
printed in the title strip.

## Viewer notes

- Acrobat Reader asks to trust the document before it activates 3D content.
- Bluebeam Revu reads U3D; it does not read PRC, which is why this extension
  writes U3D.
- Browsers, Edge, macOS Preview and phones show the snapshot only.

## Development

`python -m venv .venv && .venv/Scripts/python -m pip install pytest pypdf PySide6`
then `.venv/Scripts/python -m pytest -q`. The U3D writer is validated by a
reader that parses the U3D reference library's sample files (`tests/data`).
`devtools/package.py` builds the catalog ZIP.

GPL-3.0-or-later. Requires IngeTrazo 0.5.8 or later. No dependencies.
Third-party notices in THIRD-PARTY.md.
