"""Draws the JSON written by tests/snapshot.luau into a contact sheet.

Beams are drawn as camera-facing ribbons along their cubic Bezier curves (the
same math Roblox uses), additively blended, with a blur pass standing in for
Bloom. Parts are drawn as glowing balls or plain rocks. It is an approximation
for sanity-checking shapes, not a renderer.

usage: python3 render_snapshot.py snapshot.json out.png
"""

import json
import math
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

W, H = 420, 300
FOV = 360.0

CAMERAS = {
    "energy_blast": ((26, 10, -6), (0, 2, -14)),
    "slash": ((0, 9, 14), (0, 2, -3)),
    "multi_slash": ((0, 9, 14), (0, 2, -2)),
    "lightning": ((26, 16, 34), (0, 10, 0)),
    "level_up": ((20, 12, 26), (0, 7, 0)),
}
DEFAULT_CAMERA = ((16, 12, 20), (0, 1.5, 0))


def sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def add(a, b):
    return [a[i] + b[i] for i in range(3)]


def mul(a, s):
    return [a[i] * s for i in range(3)]


def dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def norm(a):
    m = math.sqrt(dot(a, a)) or 1.0
    return [x / m for x in a]


class Camera:
    def __init__(self, eye, target):
        self.eye = list(eye)
        self.f = norm(sub(target, eye))
        self.r = norm(cross(self.f, [0, 1, 0]))
        self.u = cross(self.r, self.f)

    def project(self, p):
        d = sub(p, self.eye)
        z = dot(d, self.f)
        if z < 0.1:
            return None
        x, y = dot(d, self.r), dot(d, self.u)
        return (W / 2 + FOV * x / z, H / 2 - FOV * y / z, z)


def bezier(p0, p1, p2, p3, t):
    a = (1 - t) ** 3
    b = 3 * (1 - t) ** 2 * t
    c = 3 * (1 - t) * t * t
    d = t ** 3
    return [a * p0[i] + b * p1[i] + c * p2[i] + d * p3[i] for i in range(3)]


def lerp(a, b, t):
    return a + (b - a) * t


def draw_grid(draw, cam):
    for i in range(-30, 31, 4):
        for a, b in (([i, 0, -30], [i, 0, 30]), ([-30, 0, i], [30, 0, i])):
            pa, pb = cam.project(a), cam.project(b)
            if pa and pb:
                draw.line([pa[:2], pb[:2]], fill=(52, 56, 64), width=1)


def render_shot(shot):
    cam = Camera(*CAMERAS.get(shot["id"], DEFAULT_CAMERA))
    base = Image.new("RGB", (W, H), (30, 33, 40))
    bd = ImageDraw.Draw(base)
    draw_grid(bd, cam)
    glow = Image.new("RGB", (W, H), (0, 0, 0))

    # rocks first (normal blend), glowing parts additive
    for part in sorted(shot["parts"], key=lambda p: -dot(sub(p["pos"], cam.eye), cam.f)):
        pr = cam.project(part["pos"])
        if not pr:
            continue
        r = max(1.5, FOV * max(part["size"]) / 2 / pr[2])
        alpha = 1 - part["t"]
        col = tuple(int(255 * c) for c in part["color"])
        if "Neon" in part["material"] or "ForceField" in part["material"]:
            layer = Image.new("RGB", (W, H), (0, 0, 0))
            ld = ImageDraw.Draw(layer)
            if "Cylinder" in part["shape"]:
                half = mul(part["right"], part["size"][0] / 2)
                a, b = cam.project(add(part["pos"], half)), cam.project(sub(part["pos"], half))
                if a and b:
                    width = max(2, int(FOV * part["size"][1] / pr[2]))
                    ld.line([a[:2], b[:2]], fill=tuple(int(c * alpha) for c in col), width=width)
            else:
                ld.ellipse([pr[0] - r, pr[1] - r, pr[0] + r, pr[1] + r], fill=tuple(int(c * alpha) for c in col))
            glow = ImageChops.add(glow, layer)
        else:
            shade = tuple(int(c * 0.8) for c in col)
            bd.polygon([(pr[0] - r, pr[1]), (pr[0], pr[1] - r), (pr[0] + r, pr[1]), (pr[0], pr[1] + r)], fill=shade)

    for beam in shot["beams"]:
        p0, p3 = beam["p0"], beam["p3"]
        p1 = add(p0, mul(beam["a0"], beam["c0"]))
        p2 = sub(p3, mul(beam["a1"], beam["c1"]))
        n = 14
        pts = []
        for k in range(n + 1):
            t = k / n
            pr = cam.project(bezier(p0, p1, p2, p3, t))
            if pr is None:
                pts = []
                break
            w = lerp(beam["w0"], beam["w1"], t) * FOV / pr[2] / 2
            tr = lerp(beam["t0"], beam["t1"], t)
            col = [lerp(beam["color"][i], beam["color1"][i], t) for i in range(3)]
            pts.append((pr[0], pr[1], w, tr, col))
        if len(pts) < 2:
            continue
        layer = Image.new("RGB", (W, H), (0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for k in range(len(pts) - 1):
            x0, y0, w0, t0, c0 = pts[k]
            x1, y1, w1, t1, c1 = pts[k + 1]
            dx, dy = x1 - x0, y1 - y0
            m = math.hypot(dx, dy) or 1
            nx, ny = -dy / m, dx / m
            a = 1 - (t0 + t1) / 2
            col = tuple(int(255 * a * (c0[i] + c1[i]) / 2) for i in range(3))
            ld.polygon(
                [(x0 + nx * w0, y0 + ny * w0), (x1 + nx * w1, y1 + ny * w1), (x1 - nx * w1, y1 - ny * w1), (x0 - nx * w0, y0 - ny * w0)],
                fill=col,
            )
        glow = ImageChops.add(glow, layer)

    bloom = glow.filter(ImageFilter.GaussianBlur(6))
    out = ImageChops.add(base, glow)
    out = ImageChops.add(out, bloom)
    d = ImageDraw.Draw(out)
    d.text((8, 6), shot["id"], fill=(235, 235, 240))
    return out


def main():
    data = json.load(open(sys.argv[1]))
    cols = 3
    rows = math.ceil(len(data) / cols)
    sheet = Image.new("RGB", (W * cols, H * rows), (0, 0, 0))
    for i, shot in enumerate(data):
        sheet.paste(render_shot(shot), ((i % cols) * W, (i // cols) * H))
    sheet.save(sys.argv[2])
    print("saved", sys.argv[2])


if __name__ == "__main__":
    main()
