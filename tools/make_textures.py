"""Generates the optional EasyVFX sharp texture pack (white on transparent).

White textures take any color from the effect and glow with LightEmission = 1.
Upload them in Studio (Asset Manager > Bulk Import), then paste an image ID into
"Custom texture" in the plugin's Advanced section.

usage: python3 make_textures.py <out_dir>
"""

import math
import os
import random
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SIZE = 512
SS = 2  # supersampling for clean edges


def canvas():
    return Image.new("L", (SIZE * SS, SIZE * SS), 0)


def finish(alpha: Image.Image, blur: float = 0.0) -> Image.Image:
    if blur:
        alpha = alpha.filter(ImageFilter.GaussianBlur(blur * SS))
    alpha = alpha.resize((SIZE, SIZE), Image.LANCZOS)
    out = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    out.putalpha(alpha)
    return out


def slash():
    """Crescent blade: sharp outer edge, thick head, long fading tail."""
    a = canvas()
    px = a.load()
    n = SIZE * SS
    cx, cy = n / 2, n * 0.62
    r_out = n * 0.42
    for y in range(n):
        for x in range(n):
            dx, dy = x - cx, y - cy
            ang = math.atan2(-dy, dx)  # 0 = right, pi/2 = up
            if not (0.15 < ang < math.pi - 0.15):
                continue
            t = (ang - 0.15) / (math.pi - 0.3)  # 0 tail (right) .. 1 head (left)
            thickness = n * 0.17 * math.sin(math.pi * t ** 0.7)
            d = math.hypot(dx, dy)
            inner = r_out - thickness
            if inner <= d <= r_out:
                edge = (d - inner) / max(1.0, thickness)  # 0 inner .. 1 outer edge
                value = (0.6 + 0.4 * edge ** 1.5) * (0.3 + 0.7 * t)
                px[x, y] = int(255 * min(1.0, value))
    return finish(a, 0.6)


def star4():
    a = canvas()
    d = ImageDraw.Draw(a)
    n = SIZE * SS
    c = n / 2
    for angle, length, width in ((0, 0.48, 0.05), (90, 0.48, 0.05), (45, 0.22, 0.03), (135, 0.22, 0.03)):
        th = math.radians(angle)
        ux, uy = math.cos(th), math.sin(th)
        vx, vy = -uy, ux
        L, w = n * length, n * width
        d.polygon([(c + ux * L, c + uy * L), (c + vx * w, c + vy * w), (c - ux * L, c - uy * L), (c - vx * w, c - vy * w)], fill=255)
    glow = a.filter(ImageFilter.GaussianBlur(n * 0.02))
    core = Image.new("L", a.size, 0)
    ImageDraw.Draw(core).ellipse([c - n * 0.06, c - n * 0.06, c + n * 0.06, c + n * 0.06], fill=255)
    core = core.filter(ImageFilter.GaussianBlur(n * 0.03))
    return finish(_max(a, _max(glow, core)), 0.4)


def _max(a, b):
    return ImageChops.lighter(a, b)


def streak():
    a = canvas()
    d = ImageDraw.Draw(a)
    n = SIZE * SS
    c = n / 2
    d.polygon([(c, n * 0.02), (c + n * 0.035, c), (c, n * 0.98), (c - n * 0.035, c)], fill=255)
    return finish(a, 0.5)


def ring():
    a = canvas()
    d = ImageDraw.Draw(a)
    n = SIZE * SS
    m = n * 0.04
    d.ellipse([m, m, n - m, n - m], fill=255)
    w = n * 0.05
    d.ellipse([m + w, m + w, n - m - w, n - m - w], fill=0)
    return finish(a, 0.5)


def burst():
    """Anime impact: many sharp spikes from the center."""
    a = canvas()
    d = ImageDraw.Draw(a)
    n = SIZE * SS
    c = n / 2
    rng = random.Random(7)
    for i in range(22):
        th = i / 22 * math.tau + rng.uniform(-0.08, 0.08)
        L = n * rng.uniform(0.3, 0.49)
        w = n * rng.uniform(0.012, 0.03)
        ux, uy = math.cos(th), math.sin(th)
        vx, vy = -uy, ux
        start = n * 0.06
        d.polygon(
            [(c + ux * start + vx * w, c + uy * start + vy * w), (c + ux * L, c + uy * L), (c + ux * start - vx * w, c + uy * start - vy * w)],
            fill=255,
        )
    core = Image.new("L", a.size, 0)
    ImageDraw.Draw(core).ellipse([c - n * 0.1, c - n * 0.1, c + n * 0.1, c + n * 0.1], fill=255)
    return finish(_max(a, core.filter(ImageFilter.GaussianBlur(n * 0.04))), 0.4)


def flare():
    a = canvas()
    n = SIZE * SS
    c = n / 2
    px = a.load()
    for y in range(0, n):
        for x in range(0, n):
            r = math.hypot(x - c, y - c) / (n / 2)
            v = max(0.0, 1 - r) ** 3
            cross = max(0.0, 1 - abs(x - c) / (n * 0.012)) * max(0.0, 1 - r) + max(0.0, 1 - abs(y - c) / (n * 0.012)) * max(0.0, 1 - r)
            px[x, y] = int(255 * min(1.0, v + cross))
    return finish(a, 0.3)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "textures"
    os.makedirs(out, exist_ok=True)
    for name, fn in (("slash", slash), ("star4", star4), ("streak", streak), ("ring", ring), ("impact_burst", burst), ("flare", flare)):
        path = os.path.join(out, f"easyvfx_{name}.png")
        fn().save(path)
        print("wrote", path)


if __name__ == "__main__":
    main()
