# SPDX-License-Identifier: GPL-3.0-or-later
from PySide6.QtGui import QVector3D


def projection_axes(normal, rot=0.0):
    n = normal.normalized()
    z = QVector3D(0, 0, 1)
    if abs(QVector3D.dotProduct(n, z)) > 0.999:
        u = QVector3D(1, 0, 0)
    else:
        u = QVector3D.crossProduct(z, n).normalized()
    v = QVector3D.crossProduct(n, u).normalized()
    return u, v


def planar_uv(normal, positions, sw, sh, rot=0.0):
    u_axis, v_axis = projection_axes(normal, rot)
    sw = sw if abs(sw) > 1e-9 else 1.0
    sh = sh if abs(sh) > 1e-9 else 1.0
    return [(QVector3D.dotProduct(p, u_axis) / sw,
             QVector3D.dotProduct(p, v_axis) / sh) for p in positions]


def affine_uv(uvw, positions):
    ux, uy, uz, uc = uvw[0], uvw[1], uvw[2], uvw[3]
    vx, vy, vz, vc = uvw[4], uvw[5], uvw[6], uvw[7]
    return [(ux * p.x() + uy * p.y() + uz * p.z() + uc,
             vx * p.x() + vy * p.y() + vz * p.z() + vc) for p in positions]


def image_has_cutout(path):
    return str(path).endswith("_cutout.png")
