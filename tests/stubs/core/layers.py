# SPDX-License-Identifier: GPL-3.0-or-later
DEFAULT_LAYER = "Layer 0"


class Layer:
    def __init__(self, name, visible=True, locked=False):
        self.name, self.visible, self.locked = name, visible, locked


def layer_of(entity):
    attrs = getattr(entity, "attrs", None)
    if attrs is not None:
        return attrs.get("layer") or DEFAULT_LAYER
    return getattr(entity, "layer", None) or DEFAULT_LAYER
