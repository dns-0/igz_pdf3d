# SPDX-License-Identifier: GPL-3.0-or-later
"""Zip igz_pdf3d/ into dist/igz_pdf3d.zip (the catalog's ZIP-package layout)."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "igz_pdf3d"
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc"}


def build_zip(out=ROOT / "dist" / "igz_pdf3d.zip") -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PKG.rglob("*")):
            if path.is_dir() or any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            zf.write(path, "igz_pdf3d/" + path.relative_to(PKG).as_posix())
    return out


if __name__ == "__main__":
    target = build_zip(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "igz_pdf3d.zip")
    print(f"wrote {target} ({target.stat().st_size // 1024} KB)")
