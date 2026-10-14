# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path


def test_package_key():
    import igz_pdf3d
    assert igz_pdf3d.KEY == "igz_pdf3d"
    assert igz_pdf3d.EXT_VERSION == 1
    assert igz_pdf3d.__version__ == "1.0.0"


def test_sample_files_present(data_dir):
    sizes = {"box.u3d": 1276, "box_2shaders.u3d": 1776, "box_group.u3d": 1640,
             "VertexColor.u3d": 25492, "TextureLayers.u3d": 96260}
    for name, size in sizes.items():
        assert (data_dir / name).stat().st_size == size, name


def test_every_py_has_spdx():
    root = Path(__file__).resolve().parent.parent
    for path in list(root.glob("igz_pdf3d/*.py")) + list(root.glob("tests/**/*.py")):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert first == "# SPDX-License-Identifier: GPL-3.0-or-later", path


def test_build_zip(tmp_path):
    import zipfile
    from devtools.package import build_zip
    out = build_zip(tmp_path / "igz_pdf3d.zip")
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "igz_pdf3d/__init__.py" in names
    assert "igz_pdf3d/_u3d_bits.py" in names and "igz_pdf3d/_dialog.py" in names
    assert "igz_pdf3d/icons/tb_pdf3d.svg" in names and "igz_pdf3d/icons/tb_pdf3d_light.svg" in names
    assert "igz_pdf3d/LICENSE" in names and "igz_pdf3d/THIRD-PARTY.md" in names
    assert not any(n.endswith(".pyc") or "__pycache__" in n for n in names)
    assert not any(n.startswith("tests/") for n in names)
