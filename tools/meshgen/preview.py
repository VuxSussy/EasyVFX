"""The mesh set drawn the way evfx draws a MeshPart: each shell from three angles, with
the texture it is made for (the slash ribbon on crescents, an energy strip elsewhere)."""

import math

import numpy as np
from PIL import Image, ImageDraw

from evfx import core, render

TEXTURES = {"crescent": "pack://seq_slash_ribbon_00", "lotus": "pack://art_petal_single", "cylinder": "pack://strip_pillar_streaks"}
DEFAULT = "pack://strip_energy_streak"
ANGLES = ((0.0, 25.0), (60.0, 50.0), (150.0, 10.0))
CELL = (300, 220)


def draw(shell, kind, yaw, pitch, color=(1.0, 0.82, 0.35)):
    verts, uvs, tris = shell
    a, b = math.radians(yaw), math.radians(pitch)
    eye = (1.6 * math.cos(b) * math.sin(a), 1.6 * math.sin(b), 1.6 * math.cos(b) * math.cos(a))
    cam = core.Camera(eye, (0, 0, 0), size=CELL)
    canvas = render.Canvas(cam)
    tex = render.texture(TEXTURES.get(kind, DEFAULT))
    render.draw_mesh(canvas, verts, uvs, tris, tex, color, 1.0, 1.0)
    return render.to_image(canvas.finish())


def sheet(items):
    w, h = CELL
    out = Image.new("RGB", (w * len(ANGLES) + 8, (h + 24) * len(items) + 8), (18, 20, 25))
    d = ImageDraw.Draw(out)
    for row, (mesh_id, shell) in enumerate(items):
        y = 8 + row * (h + 24)
        kind = mesh_id.split("/")[1].split("_")[0]
        d.text((8, y), f"{mesh_id}  {len(shell[2])} tris", fill=(225, 228, 235))
        for col, (yaw, pitch) in enumerate(ANGLES):
            out.paste(draw(shell, kind, yaw, pitch), (4 + col * w, y + 18))
    return out
