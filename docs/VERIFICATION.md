# In-app verification record (igz_pdf3d 1.0.0)

Installed copy: %APPDATA%\ingetrazo\plugins\igz_pdf3d (built 2026-10-14 from commit on branch igz-pdf3d-1.0).
Automated suite: 97 tests pass (.venv/Scripts/python -m pytest -q).
Tick each line with the date when checked in IngeTrazo 0.5.8, Acrobat DC and Bluebeam Revu.

- [x] 1. (2026-10-14, David) The 3D PDF toolbar button and Extensions > Export 3D PDF... open the dialog; the scope line reads "Whole visible model: ...".
- [ ] 2. Window-select part of the model, click Refresh: "Selection: N groups, M loose faces".
- [x] 3. (2026-10-14, David: exports of two real models open in Acrobat DC and Revu with geometry, materials and opacity; Revu's own orbit remains clunky; Acrobat's 3D toolbar visibility depends on its UI mode) Export with the defaults. Acrobat DC: click to activate; the model appears from the viewport's angle; the model tree lists layers then objects with IFC classes; named views switch; the measure tool set to inches reads a known dimension.
- [ ] 4. Textures tile like the viewport. If upside down, set FLIP_V = True in _tessellate.py and re-test.
- [x] 5. (2026-10-14, David) Bluebeam Revu opens the same file and shows the model and the model tree.
- [ ] 6. Edge (browser) shows the snapshot and the title strip.
- [ ] 7. Export with Metric and A4 (Tabloid and Arch D added 2026-10-14): the strip says metres, the page is A4.
- [ ] 8. Select only edges and export: the dialog refuses, no file is written.
- [ ] 9. Hide a layer, export the whole model: the hidden layer is absent.
- [ ] 10. IngeTrazo's log folder shows no igz_pdf3d tracebacks.

Early check available before step 3: trial/trial_cube.pdf (two cubes and a textured panel, generated during planning).
