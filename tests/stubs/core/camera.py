# SPDX-License-Identifier: GPL-3.0-or-later
import math

from PySide6.QtGui import QVector3D


class OrbitCamera:
    def __init__(self):
        self.target = QVector3D(0.0, 0.0, 0.0)
        self.distance = 20.0
        self.yaw = math.radians(-45.0)
        self.pitch = math.radians(30.0)
        self.up = QVector3D(0.0, 0.0, 1.0)
        self.fov_deg = 45.0
        self.perspective = True

    def eye(self):
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        return self.target + QVector3D(self.distance * cp * cy,
                                       self.distance * cp * sy,
                                       self.distance * sp)

    def up_vector(self):
        return self.up
