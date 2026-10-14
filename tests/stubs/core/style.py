# SPDX-License-Identifier: GPL-3.0-or-later
class Style:
    def __init__(self, name="default", face_mode="shaded", sky=True, background=(1.0, 1.0, 1.0)):
        self.name, self.face_mode, self.sky, self.background = name, face_mode, sky, background
