# igz_pdf3d — 3D PDF export for IngeTrazo

Date: 2026-10-14. Author: David Songer, with Claude. Status: approved design.

## Purpose

Let a stakeholder who does not have IngeTrazo open a project model in Adobe
Acrobat Reader or Bluebeam Revu, orbit it, hide parts of it from a model tree
and measure it. The user window-selects what to share (or nothing, for the
whole model), clicks the **3D PDF** toolbar button, fills a short dialog and
gets a one-page PDF with an interactive 3D view.

Success: the PDF opens in Acrobat DC and Revu with the model visible from the
same angle as the viewport, the layers and objects listed in the model tree,
materials and textures matching the viewport, and the measure tool reading
inches. Viewers without 3D support show the viewport snapshot.

## Constraints

- IngeTrazo 0.5.8 frozen build on Windows; extension API version 2; no pip.
  Only the host's bundled libraries (numpy, trimesh, mapbox_earcut, PySide6)
  and the standard library are available at run time.
- GPL-3.0-or-later, catalog-listed, same layout and release path as igz_steel.
- U3D only. Bluebeam Revu rejects PRC. Acrobat accepts U3D.
- Imperial first, with a Metric switch, as in igz_steel.
- An extension never breaks the app: every failure is caught, logged and shown.

## Workflow and selection rules

1. The user selects with the Select tool (window selection or clicks), or
   leaves nothing selected.
2. The user clicks the **3D PDF** toolbar button (also Extensions ▸ Export
   3D PDF…). The dialog opens with a scope line.
3. The user adjusts title, note, units, page size and output path, then
   clicks Export. A progress bar runs; the file is written; the status bar
   flashes the path; the dialog offers Open PDF and Show in folder.

Selection resolution (`scene.selection` is a set of faces, edges and groups):

- A selected group exports whole, with all its children, even hidden parts.
- Selected loose faces export as one node per layer.
- Selected edges alone are ignored (a 3D PDF has no lines).
- An empty selection exports every visible layer and group. Hidden layers and
  hidden groups are left out (`scene.entity_visible`).
- Only edges selected, or nothing visible, gives a refusal in the dialog and
  no file is written.

## Architecture

Package `igz_pdf3d/`, one job per module. Everything after `_collect` works on
plain Python data (dicts, lists, float tuples, bytes) and is testable without
the host.

| Module | Job | Depends on |
|---|---|---|
| `__init__.py` | `setup(app)`: toolbar button with icon, Extensions menu entry, `__version__`, `KEY` | host `ExtensionApp`, Qt |
| `_collect.py` | Resolve the selection into a scene description: layers → nodes (mesh key, 4×4 transform, display name, BIM class); meshes keyed by prototype; material table following the host's paint rules; texture image bytes | host scene, `core.group.iter_placements`, `core.layers.layer_of`, `core.texture`, `formats.meshexport.export_names` |
| `_tessellate.py` | Face loops → triangles with one flat normal per face, a material index per face, and per-corner UVs for textured faces | host `face.triangulate()` when present, else mapbox_earcut on the face plane |
| `_u3d_bits.py` | Bit writer and bit reader: U8/U16/U32/F32/string, compressed U32/U16/U8 with the dynamic-histogram arithmetic coder, data block framing with padding and metadata | stdlib |
| `_u3d.py` | U3D file assembly: file header, modifier chains, group and model nodes, CLOD mesh declaration and continuation, shader, material and texture resources. A decoder for tests | `_u3d_bits` |
| `_pdf.py` | PDF 1.7 writer: page, title strip, poster image XObject, 3D annotation, 3D stream, named views, xref table | stdlib `zlib` |
| `_dialog.py` | Qt dialog: scope line, inputs, progress, worker thread, result actions | Qt, all of the above |

Data flow:

1. `_dialog` calls `_collect.collect(scene, selection, units)` on the main
   thread. Result: a `SceneData` dict with `layers`, `nodes`, `meshes`,
   `materials`, `textures`, `bbox`, plus `camera` from the viewport and a
   `poster` JPEG from `viewport.render_image(w, h)`.
2. A `QThread` worker runs `_tessellate` then `_u3d.write(scene_data)` →
   U3D bytes, then `_pdf.write(options, u3d_bytes, poster, views)` → PDF
   bytes. Progress is reported per stage through a `Signal(object)` on a
   queued connection to a bound method of the dialog.
3. The dialog writes the file, or deletes the partial file on failure.

Coordinates: positions pass through the placement transform (world, metres),
then the unit scale (inches: ×39.3701; metres: ×1), then a fixed rotation
from Z-up to Y-up (x, y, z) → (x, z, −y). The camera is converted the same
way. All six named views are computed from the converted bounding box.

## Materials and textures

Follows `formats.meshexport._add_face` so the PDF matches the viewport, GLB
and DAE:

- Material key: `("color", rgb)` or `("color", rgb, opacity)` for solids;
  `("tex", basename)` or `("tex", basename, opacity)` for textures. Opacity
  below 0.999 is kept, rounded to 3 decimals.
- Faces with `attrs["mat"]` export under that registry name through
  `export_names`; anonymous paints get `matN`; unpainted faces get the host's
  default cream (0.96, 0.95, 0.925).
- Solid: one U3D Material Resource (diffuse = color, ambient = color × 0.2,
  specular = 0, opacity) and one Lit Texture Shader with no texture layers.
- Textured: a Texture Resource with the image bytes read from `tex["path"]`
  (the texture cache); JPEG-24 for opaque images, PNG for images where
  `core.texture.image_has_cutout` is true; a shader with one texture layer,
  repeat on both axes, blending Multiply on a white diffuse. UVs per corner
  from `affine_uv(uvw, points)` when the texture has `uvw`, else
  `planar_uv(normal, points, sw, sh, rot)`, on world positions.
- Front paint only; back-side paint and finish are not exported.
- Instancing: a prototype with no textured faces is written once and
  referenced by one Model Node per placement. A prototype with textured faces
  is baked once per placement in world coordinates.
- A texture file missing from the cache falls back to the material's color;
  the dialog lists the fallbacks after export.

## U3D file layout

ECMA-363, written the way the reference library's IDTFConverter writes files
(those are known to open in Acrobat and Revu). Block order:

1. File Header (version as the reference library writes, profile 0,
   declaration size, file size, character encoding UTF-8, units scaling 1).
2. For each layer: Group Node, with a Modifier Chain wrapper.
3. For each placement: Model Node with parent = its layer node, the 4×4
   matrix, and the mesh resource name; Modifier Chain wrapper. Names are the
   model tree labels, built as `<BIM class> <group name>` or the group name,
   deduplicated with ` (2)`, ` (3)` suffixes (U3D names must be unique).
4. For each mesh: CLOD Mesh Declaration with minimum resolution = maximum
   resolution = vertex count, attributes excluding texture coordinates unless
   the mesh has a textured face, one shading description per material used
   by the mesh; then one CLOD Base Mesh Continuation block with positions,
   flat normals (one per face), texture coordinates, and faces with
   per-face shading index and per-corner indices. No resolution updates.
5. Shader, Material and Texture Resources (texture image bytes in Texture
   Continuation blocks).
6. No lights, no views (the PDF supplies both).

Encoding: `_u3d_bits` ports the reference library's bit stream (Apache-2.0,
compatible with GPL-3.0-or-later; notice in THIRD-PARTY.md): 32-bit
arithmetic coder, dynamic histograms per context with escape symbols, the
spec's context constants for every mesh field, and uncompressed F32 for
positions, normals and UVs. Every data block is padded to 4 bytes.

## PDF layout

PDF 1.7, pure Python, classic xref table, objects: Catalog, Pages, Page,
content stream, Helvetica and Helvetica-Bold font dictionaries, poster image
XObject (DCTDecode JPEG), 3D annotation, 3D stream (U3D, FlateDecode), seven
3D view dictionaries.

- Page: Letter (11 × 8.5 in) or A4 landscape, 0.5 in margins.
- Title strip (top 1.0 in of the content area): title in Helvetica-Bold
  18 pt; second line in Helvetica 10 pt: note, date (ISO), "Model units:
  inches" or "Model units: metres"; third line in Helvetica 8 pt grey:
  "Interactive in Adobe Acrobat Reader and Bluebeam Revu. Click the view
  to activate 3D."
- 3D annotation: fills the content area below the strip. `/3DA` with
  activate on page open (`/A /PO`), deactivate on page close (`/D /PC`),
  instantiated and interactive (`/AIS /I`). `/AP /N` is a form XObject that
  draws the poster image. `/3DV` is the default view.
- 3D stream: `/Type /3D /Subtype /U3D`, `/VA` the seven views, `/DV` the
  first. Views: "Exported view" from the viewport camera; "Iso", "Top",
  "Front", "Back", "Left", "Right" from the bounding box, each with
  `/MS /M` and a camera-to-world matrix, `/CO` centre of orbit distance,
  orthographic for the six axis views and perspective for the exported
  view, `/LS` lighting `/Subtype /CAD`, `/RM` render mode `/Subtype
  /Solid`, `/BG` white background.
- Poster: `viewport.render_image(w, h)` at the annotation's aspect ratio,
  about 1600 px wide, JPEG quality 85.

## Dialog

Parented to `app.window`, non-modal, one instance reused.

- Scope line (read-only) with a Refresh button.
- Title: defaults to the document file stem, or "Untitled model".
- Note: one line, optional.
- Units: Imperial (inches) or Metric (metres); Imperial default.
- Page: Letter landscape or A4 landscape; Letter default.
- Output file: default `<igz folder>/<stem>.pdf`, Browse opens a save dialog.
- Export: disables inputs, shows a progress bar with stage names
  (Collecting, Tessellating, Encoding, Writing), Cancel stops between stages.
- Success: status bar flash with the path; buttons Open PDF
  (`QDesktopServices.openUrl`) and Show in folder.

## Error handling

- Nothing exportable → message in the dialog, no file.
- Missing texture file → color fallback, listed after export.
- Worker exception → caught, traceback to the `ingetrazo.plugins` logger,
  short message with the log folder path, partial file deleted.
- `setup(app)` wraps the toolbar and menu in try/except so a Qt difference
  degrades to the menu entry only.
- The scene is never touched off the main thread.

## Testing

pytest with host stubs in `tests/conftest.py`, as in igz_steel.

- `test_u3d_bits.py`: decoder reads the reference library's sample files
  (`box.u3d`, `box_2shaders.u3d`, `box_group.u3d`, `VertexColor.u3d`, under
  `tests/data` with the Apache notice) and recovers block types, node names,
  vertex counts and positions. Encoder round-trips random U32 sequences and
  random meshes bit-exactly through the decoder.
- `test_u3d.py`: a cube exports; the decoder yields the expected nodes, mesh
  and materials; name deduplication; instancing versus baking.
- `test_tessellate.py`: n-gons with holes, slivers dropped, normals outward.
- `test_collect.py`: stubbed scene with layers, hidden items, nested groups,
  component instances, each selection case, material keys and names.
- `test_pdf.py`: output parses with pypdf (dev venv only); one page, one 3D
  annotation, a U3D stream, seven views, poster present.
- `test_package.py`: zip layout.
- Manual: David opens the PDF in Acrobat DC and Bluebeam Revu and checks
  orientation, model tree, materials, textures, measurement in inches.

## Release

Repo `dns-0/igz_pdf3d`, GPL-3.0-or-later, `THIRD-PARTY.md` with the U3D
reference library notice, `devtools/package.py` → `dist/igz_pdf3d.zip`,
`catalog/igz_pdf3d.toml` with es/en/pt names and summaries under 240
characters, tags `export`, `collaboration`, `ingetrazo = "0.5.8"`, version
1.0.0, GitHub release with the zip and sha256, then a PR on
`ingelibre/ingetrazo-extensions` from the fork.

## Out of scope for 1.0

Lines and edges, back-side paint, finishes, lights, animations, multiple
pages, object tables, PRC output, progressive (CLOD) resolution updates.
