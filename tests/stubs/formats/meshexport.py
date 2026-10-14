# SPDX-License-Identifier: GPL-3.0-or-later
def export_names(materials):
    names = {}
    used = set()
    for i, (key, info) in enumerate(materials.items()):
        raw = (info.get("mat") or "").strip()
        if raw:
            base = "".join(c if c.isalnum() or c in "._-" else "_"
                           for c in raw).strip("._-") or f"mat{i}"
            if base[0].isdigit():
                base = f"m_{base}"
        else:
            base = f"mat{i}"
        name, n = base, 2
        while name in used:
            name = f"{base}_{n}"
            n += 1
        used.add(name)
        names[key] = name
    return names
