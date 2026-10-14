# Catalog submission

1. Release: bump `__version__` in `igz_pdf3d/__init__.py` and `version` in
   `catalog/igz_pdf3d.toml`; `.venv/Scripts/python devtools/package.py`;
   `certutil -hashfile dist\igz_pdf3d.zip SHA256`; `gh release create vX.Y.Z
   dist/igz_pdf3d.zip --title "igz_pdf3d X.Y.Z" --notes "..."`.
2. Put the release asset URL and the SHA-256 in `catalog/igz_pdf3d.toml`.
3. In the fork `dns-0/ingetrazo-extensions`, branch `igz-pdf3d-X.Y.Z`, copy
   the TOML to `extensions/igz_pdf3d.toml` and the screenshot to
   `screenshots/igz_pdf3d.png`, open a PR against `ingelibre/ingetrazo-extensions`.
   The catalog's `check` workflow fails if any `summary.<lang>` is over 240
   characters. Merged entries auto-publish from dns-0.
