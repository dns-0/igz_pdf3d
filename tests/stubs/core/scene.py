# SPDX-License-Identifier: GPL-3.0-or-later
from core.layers import DEFAULT_LAYER, Layer, layer_of
from core.mesh import Mesh


class Scene:
    def __init__(self):
        self.mesh = Mesh()
        self.groups = []
        self.selection = set()
        self.layers = [Layer(DEFAULT_LAYER)]
        self.edit_group = None
        self.materials = {}

    @property
    def loose_mesh(self):
        return self.mesh

    def layer(self, name):
        for ly in self.layers:
            if ly.name == name:
                return ly
        return None

    def entity_visible(self, entity):
        if getattr(entity, "hidden", False):
            return False
        ly = self.layer(layer_of(entity))
        return ly is None or ly.visible
