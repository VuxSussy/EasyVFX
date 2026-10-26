"""Draws one moment of a timeline with numpy and Pillow.

Two passes, like the engine: a normal-blend pass (smoke, rocks, the floor) and an
additive pass (LightEmission, Neon) that also feeds a bloom. Particles are textured
quads warped into place; beams are ribbons along their Bezier curves with the texture's
profile across their width. It is an approximation for judging shape, timing and
budget, not a copy of Roblox's renderer.
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import core

# a dim grey stage, so the effect's own light is what shows it (Phát, 2026-10-24): a grey wall,
# and a grey floor lit by a low ambient plus every PointLight the effect carries
BACK_TOP = np.array([0.105, 0.105, 0.11], np.float32)
BACK_BOTTOM = np.array([0.15, 0.15, 0.155], np.float32)
FLOOR_LINE = np.array([0.26, 0.26, 0.27], np.float32)
FLOOR_ALBEDO = np.array([0.5, 0.5, 0.5], np.float32)
AMBIENT = 0.3
LIGHT_GAIN = 0.55
BODY = np.array([0.36, 0.38, 0.42], np.float32)
BLOOM = 0.55
TEXTURE_SIZE = 128

_textures = {}
_colours = {}
# pack textures read from an image on disk (not stood in for by a procedural shape)
_images = set()


def _procedural(kind):
    n = TEXTURE_SIZE
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    u, v = (x + 0.5) / n * 2 - 1, (y + 0.5) / n * 2 - 1
    r = np.sqrt(u * u + v * v)
    if kind == "ring":
        a = np.clip(1 - np.abs(r - 0.78) / 0.12, 0, 1)
    elif kind == "star":
        a = np.clip(1 - (np.abs(u) * np.abs(v) * 30 + r * 0.6), 0, 1) + np.clip(1 - r / 0.25, 0, 1)
    elif kind == "square":
        a = ((np.abs(u) < 0.8) & (np.abs(v) < 0.8)).astype(np.float32)
    elif kind == "smoke":
        rng = np.random.default_rng(7)
        noise = rng.random((8, 8)).astype(np.float32)
        noise = np.array(Image.fromarray((noise * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC)) / 255.0
        a = np.clip(1 - r, 0, 1) ** 1.5 * (0.55 + 0.45 * noise)
    elif kind == "fire":
        a = np.clip(1 - np.sqrt(u * u * 2.2 + (v + 0.15) ** 2), 0, 1) ** 1.2
    else:
        a = np.clip(1 - r, 0, 1) ** 2
    return np.clip(a, 0, 1).astype(np.float32)


BUILT_IN = {
    "implosion": "glow",
    "shockwave": "ring",
    "smoke": "smoke",
    "sparkles": "star",
    "fire": "fire",
    "core": "glow",
    "forcefield": "ring",
    "square": "square",
}


def _texture_path(name):
    """Where a pack texture's PNG is, or None: uploaded ones in pack/textures, library v4 in
    pack/generated, CC0 packs in pack/cc0."""
    if not name.startswith("pack://"):
        return None
    for folder in (core.PACK, core.GENERATED, core.CC0):
        path = os.path.join(folder, name[7:] + ".png")
        if os.path.exists(path):
            return path
    return None


def texture(name):
    """The texture's mask (0..1 floats). Pack images are read from disk; Roblox's built-in ones are
    stood in for by simple shapes. A pack image is read again when its file changes, so a
    long-running studio never draws a texture texgen has since rebuilt."""
    path = _texture_path(name)
    stamp = (os.stat(path).st_mtime_ns, os.stat(path).st_size) if path else None
    if name in _textures and _textures[name][0] == stamp:
        return _textures[name][1]
    mask = None
    _colours.pop(name, None)
    if path:
        _images.add(name)
        img = Image.open(path).convert("RGBA")
        rgba = np.asarray(img, np.float32) / 255.0
        rgb = rgba[..., :3]
        if np.abs(rgb - rgb.mean(axis=2, keepdims=True)).max() > 2 / 255:
            # a baked palette (texgen "ramp", a coloured CC0 sheet): Roblox multiplies the
            # texture's colour by the particle's, so keep it and use alpha alone as the mask
            _colours[name] = rgb
            mask = rgba[..., 3]
        else:
            lum = rgb.max(axis=2)
            mask = lum * rgba[..., 3]
    if mask is None:
        low = name.lower()
        kind = next((v for k, v in BUILT_IN.items() if k in low), "glow" if name else "square")
        mask = _procedural(kind)
    _textures[name] = (stamp, mask)
    return mask


def texture_colour(name):
    """A coloured texture's RGB (0..1 floats), or None when it is white or grey."""
    texture(name)
    return _colours.get(name)


def _cell(mask, grid, cell):
    if grid <= 1:
        return mask
    h, w = mask.shape[:2]
    r, c = divmod(cell, grid)
    return mask[r * h // grid : (r + 1) * h // grid, c * w // grid : (c + 1) * w // grid]


def _coeffs(dest, src):
    """Perspective coefficients mapping output points `dest` back to input points `src`."""
    rows = []
    for (x, y), (u, v) in zip(dest, src):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(rows, np.float64)
    b = np.array([c for p in src for c in p], np.float64)
    try:
        return np.linalg.solve(a, b)
    except np.linalg.LinAlgError:
        return None


def _warp(mask, quad, w, h):
    """Draws `mask` (or an RGB image) into the screen quad `quad` (4 points). Returns (x0, y0, patch)."""
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    x0, y0 = max(0, int(math.floor(min(xs)))), max(0, int(math.floor(min(ys))))
    x1, y1 = min(w, int(math.ceil(max(xs))) + 1), min(h, int(math.ceil(max(ys))) + 1)
    if x1 - x0 < 1 or y1 - y0 < 1 or (x1 - x0) * (y1 - y0) > w * h:
        return None
    th, tw = mask.shape[:2]
    src = [(0, 0), (tw, 0), (tw, th), (0, th)]
    dest = [(p[0] - x0, p[1] - y0) for p in quad]
    k = _coeffs(dest, src)
    if k is None:
        return None
    img = Image.fromarray((mask * 255).astype(np.uint8), "L" if mask.ndim == 2 else "RGB")
    patch = img.transform((x1 - x0, y1 - y0), Image.PERSPECTIVE, tuple(k), Image.BILINEAR)
    return x0, y0, np.asarray(patch, np.float32) / 255.0


class Canvas:
    def __init__(self, cam):
        self.cam = cam
        self.w, self.h = cam.w, cam.h
        t = np.linspace(0, 1, self.h, dtype=np.float32)[:, None, None]
        self.base = np.broadcast_to(BACK_TOP * (1 - t) + BACK_BOTTOM * t, (self.h, self.w, 3)).copy()
        self.glow = np.zeros((self.h, self.w, 3), np.float32)

    def blend(self, x0, y0, patch, color, alpha, additive):
        h, w = patch.shape[:2]
        region = (slice(y0, y0 + h), slice(x0, x0 + w))
        col = np.asarray(color, np.float32)
        if additive > 0:
            self.glow[region] += patch[..., None] * col * alpha * additive
        if additive < 1:
            a = patch[..., None] * alpha * (1 - additive)
            self.base[region] = self.base[region] * (1 - a) + col * a

    def polygon(self, points, color, alpha=1.0, additive=0.0):
        mask = Image.new("L", (self.w, self.h), 0)
        ImageDraw.Draw(mask).polygon([(p[0], p[1]) for p in points], fill=255)
        patch = np.asarray(mask, np.float32) / 255.0
        self.blend(0, 0, patch, color, alpha, additive)

    def finish(self, screens=()):
        bloom_src = Image.fromarray((np.clip(self.glow, 0, 1) * 255).astype(np.uint8))
        bloom = np.asarray(bloom_src.filter(ImageFilter.GaussianBlur(7)), np.float32) / 255.0
        out = self.base + self.glow + bloom * BLOOM
        for s in screens:
            if s.get("className") != "ColorCorrectionEffect":
                continue
            out = out + s["brightness"]
            out = (out - 0.5) * (1 + s["contrast"]) + 0.5
            grey = out.mean(axis=2, keepdims=True)
            out = grey + (out - grey) * (1 + s["saturation"])
            out = out * np.asarray(s["tint"], np.float32)
        return np.clip(out, 0, 1)


def _lit_floor(canvas, lights):
    """Paints the floor plane (y = 0) grey, lit by a low ambient and the effect's PointLights,
    fading into the wall toward the horizon."""
    cam = canvas.cam
    ys, xs = np.mgrid[0:canvas.h, 0:canvas.w].astype(np.float32)
    f, r, u = (np.asarray(v, np.float32) for v in (cam.f, cam.r, cam.u))
    d = f[None, None] + r[None, None] * ((xs - cam.w / 2) / cam.scale)[..., None] - u[None, None] * ((ys - cam.h / 2) / cam.scale)[..., None]
    eye = np.asarray(cam.eye, np.float32)
    down = d[..., 1] < -1e-4
    t = np.where(down, -eye[1] / np.where(down, d[..., 1], -1.0), 0.0)
    world = eye[None, None] + d * t[..., None]
    light = np.full(world.shape, AMBIENT, np.float32)
    for lt in lights:
        lp = np.asarray(lt["pos"], np.float32)
        rng = float(lt["range"])
        if rng <= 0:
            continue
        to = lp[None, None] - world
        dist = np.maximum(np.linalg.norm(to, axis=-1), 1e-3)
        fall = np.clip(1 - dist / rng, 0, 1) ** 2
        facing = np.clip(to[..., 1] / dist, 0, 1)
        light += (np.asarray(lt["color"], np.float32)[None, None] * (float(lt["brightness"]) * LIGHT_GAIN) * (fall * facing)[..., None])
    floor = FLOOR_ALBEDO * light
    # far floor fades into the wall
    far = np.clip((t * np.linalg.norm(d, axis=-1) - 25) / 60, 0, 1)[..., None]
    floor = floor * (1 - far) + canvas.base * far
    canvas.base = np.where(down[..., None], floor, canvas.base).astype(np.float32)


def _floor(canvas, center, lights=()):
    cam = canvas.cam
    _lit_floor(canvas, lights)
    img = Image.fromarray((np.clip(canvas.base, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    cx, cz = round(center[0] / 4) * 4, round(center[2] / 4) * 4
    for i in range(-40, 41, 4):
        for a, b in (((cx + i, 0, cz - 40), (cx + i, 0, cz + 40)), ((cx - 40, 0, cz + i), (cx + 40, 0, cz + i))):
            pa, pb = cam.project(a), cam.project(b)
            if pa and pb:
                d.line([pa[:2], pb[:2]], fill=tuple(int(c * 255) for c in FLOOR_LINE), width=1)
    canvas.base = np.asarray(img, np.float32) / 255.0


def _body(canvas, holder):
    """A 5-stud mannequin pill at the effect, for scale and for the buries-the-body score."""
    cam = canvas.cam
    top, bottom = add_y(holder, 2.6), add_y(holder, -2.0)
    pt, pb = cam.project(top), cam.project(bottom)
    if not (pt and pb):
        return None
    radius = cam.pixels(1.0, (pt[2] + pb[2]) / 2)
    mask = Image.new("L", (canvas.w, canvas.h), 0)
    d = ImageDraw.Draw(mask)
    d.line([pt[:2], pb[:2]], fill=255, width=max(2, int(radius * 2)))
    for p in (pt, pb):
        d.ellipse([p[0] - radius, p[1] - radius, p[0] + radius, p[1] + radius], fill=255)
    patch = np.asarray(mask, np.float32) / 255.0
    canvas.blend(0, 0, patch, BODY, 1.0, 0.0)
    return patch > 0.5


def add_y(p, dy):
    return (p[0], p[1] + dy, p[2])


def _particle(canvas, p):
    cam = canvas.cam
    e = p["emitter"]
    alpha = 1 - p["transparency"]
    if p["size"] <= 0.001 or alpha <= 0.002:
        return
    pr = cam.project(p["pos"])
    if pr is None:
        return
    pos = p["pos"]
    to_cam = core.norm(core.sub(cam.eye, pos))
    mode = e["orientation"]
    rot = math.radians(p["rotation"])
    vel = p["vel"]
    moving = core.dot(vel, vel) > 1e-8
    if mode == "VelocityPerpendicular":
        n = core.norm(vel) if moving else p["dir"]
        hint = core.mul(p["up_hint"], -1)
        up = core.sub(hint, core.mul(n, core.dot(hint, n)))
        if core.dot(up, up) < 1e-6:
            up = core.sub(cam.r, core.mul(n, core.dot(cam.r, n)))
        up = core.norm(up)
        right = core.norm(core.cross(up, n))
        up, right = core.rotate_about(up, n, rot), core.rotate_about(right, n, rot)
    elif mode == "VelocityParallel":
        up = core.norm(vel) if moving else p["dir"]
        right = core.norm(core.cross(up, to_cam))
    else:
        right, up = cam.r, cam.u
        if mode == "FacingCameraWorldUp":
            # upright to the world, then turned by its Rotation in its own plane, as Roblox does
            up = (0, 1, 0)
            right = core.norm(core.cross(up, to_cam))
            axis = core.norm(core.cross(right, up))
            right, up = core.rotate_about(right, axis, -rot), core.rotate_about(up, axis, -rot)
        else:
            axis = core.norm(core.cross(right, up))
            right, up = core.rotate_about(right, axis, -rot), core.rotate_about(up, axis, -rot)
    size, squash = p["size"], p["squash"]
    if mode == "VelocityParallel":
        sx, sy = size / (1 + abs(squash) * 0.5), size * (1 + abs(squash))
    elif squash >= 0:
        sx, sy = size / (1 + squash), size * (1 + squash)
    else:
        sx, sy = size * (1 - squash), size / (1 - squash)
    hx, hy = core.mul(right, sx / 2), core.mul(up, sy / 2)
    corners = [
        core.add(core.sub(pos, hx), hy),
        core.add(core.add(pos, hx), hy),
        core.sub(core.add(pos, hx), hy),
        core.sub(core.sub(pos, hx), hy),
    ]
    mask = _cell(texture(e["texture"]), p["grid"], p["cell"])
    tint = texture_colour(e["texture"])
    tint = _cell(tint, p["grid"], p["cell"]) if tint is not None else None
    light = e.get("lightEmission", 0)
    brightness = e.get("brightness", 1) if light > 0 else 1
    base = np.asarray([c * brightness for c in p["color"]], np.float32)
    quad = [cam.project(c) for c in corners]
    if all(q is not None for q in quad):
        _draw_quad(canvas, mask, tint, [q[:2] for q in quad], base, alpha, light)
        return
    # a big quad (a wide floor decal) can reach behind the camera: draw it in tiles and skip
    # only the tiles that do, instead of dropping the whole sprite
    n = 8
    th, tw = mask.shape[:2]
    for j in range(n):
        for i in range(n):
            def at(a, b):
                top = core.add(core.mul(corners[0], 1 - a), core.mul(corners[1], a))
                bot = core.add(core.mul(corners[3], 1 - a), core.mul(corners[2], a))
                return core.add(core.mul(top, 1 - b), core.mul(bot, b))
            cs = [at(i / n, j / n), at((i + 1) / n, j / n), at((i + 1) / n, (j + 1) / n), at(i / n, (j + 1) / n)]
            q = [cam.project(c) for c in cs]
            if any(x is None for x in q):
                continue
            ys, xs = slice(j * th // n, (j + 1) * th // n), slice(i * tw // n, (i + 1) * tw // n)
            sub = mask[ys, xs]
            if not sub.size or not sub.any():
                continue
            _draw_quad(canvas, sub, tint[ys, xs] if tint is not None else None, [x[:2] for x in q], base, alpha, light)


def _draw_quad(canvas, mask, tint, quad, color, alpha, light):
    warped = _warp(mask, quad, canvas.w, canvas.h)
    if warped is None:
        return
    x0, y0, patch = warped
    if tint is not None:
        rgb = _warp(tint, quad, canvas.w, canvas.h)
        if rgb is not None and rgb[2].shape[:2] == patch.shape:
            color = rgb[2] * color
    canvas.blend(x0, y0, patch, color, alpha, min(1.0, light))


def _profile(name, steps):
    mask = texture(name) if name else None
    if mask is None or not name:
        return np.ones(steps, np.float32)
    column = mask.mean(axis=1)
    if column.max() <= 0:
        return np.ones(steps, np.float32)
    column = column / column.max()
    idx = np.linspace(0, len(column) - 1, steps).astype(int)
    return column[idx]


def _beam(canvas, beam, t=0.0):
    cam = canvas.cam
    p0, p3 = beam["p0"], beam["p3"]
    p1 = core.add(p0, core.mul(beam["a0"], beam["c0"]))
    p2 = core.sub(p3, core.mul(beam["a1"], beam["c1"]))
    # at least 32 steps along a beam, and one every 4 pixels on screen, so a transparency or colour
    # gradient along it reads smooth: each step has one alpha, and a long beam showed them as bands
    def sample(n):
        out = []
        for k in range(n + 1):
            f = k / n
            pr = cam.project(core.bezier(p0, p1, p2, p3, f))
            if pr is None:
                return None
            width = cam.pixels(beam["w0"] + (beam["w1"] - beam["w0"]) * f, pr[2]) / 2
            out.append((pr[0], pr[1], width, f))
        return out

    n = max(32, int(beam.get("segments", 10)))
    pts = sample(n)
    if pts is None:
        return
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    if length / n > 4:
        pts = sample(min(240, int(length / 4)))
    light = min(1.0, beam.get("lightEmission", 0))
    if beam.get("texture", "").startswith("pack://") and texture(beam["texture"]) is not None and beam["texture"] in _images:
        _beam_textured(canvas, beam, pts, light, t)
        return
    # a plain beam (or one whose texture isn't in the pack) is drawn the textured way too, with its
    # profile across the width as the mask: drawn as a grid of separate quads its overlapping edges
    # added up twice and showed as seams (Phát, 2026-10-26: the drop's pillar looked broken)
    column = _profile(beam.get("texture", ""), 32)
    _beam_textured(canvas, beam, pts, light, t, mask=np.repeat(column[:, None], 4, axis=1))


def _beam_textured(canvas, beam, pts, light, t=0.0, mask=None):
    """A beam with a pack texture, drawn as Roblox lays it: U along the beam (Stretch repeats it
    TextureLength times over the length; Wrap and Static every TextureLength studs), V across
    its width. Each segment gets its own slice of the texture. TextureSpeed scrolls it toward
    Attachment1, `t` seconds into the play."""
    name = beam.get("texture", "")
    tint = None
    if mask is None:
        mask, tint = texture(name), texture_colour(name)
    tw = mask.shape[1]
    reps = max(1e-3, beam.get("textureLength", 1) or 1)
    if beam.get("textureMode", "Stretch") != "Stretch":
        reps = math.dist(beam["p0"], beam["p3"]) / reps
    brightness = beam.get("brightness", 1) if light > 0 else 1
    for k in range(len(pts) - 1):
        x0, y0, w0, t0 = pts[k]
        x1, y1, w1, t1 = pts[k + 1]
        dx, dy = x1 - x0, y1 - y0
        m = math.hypot(dx, dy) or 1
        nx, ny = -dy / m, dx / m
        tm = (t0 + t1) / 2
        alpha = 1 - core.number_at(beam["transparency"], tm)
        if alpha <= 0.002:
            continue
        u0 = (t0 * reps - t * (beam.get("textureSpeed", 0) or 0)) % 1
        u1 = u0 + (t1 - t0) * reps
        c0, c1 = int(u0 * tw), min(tw, max(int(u0 * tw) + 1, int(math.ceil(min(1.0, u1) * tw))))
        quad = [(x0 - nx * w0, y0 - ny * w0), (x1 - nx * w1, y1 - ny * w1), (x1 + nx * w1, y1 + ny * w1), (x0 + nx * w0, y0 + ny * w0)]
        warped = _warp(mask[:, c0:c1], quad, canvas.w, canvas.h)
        if warped is None:
            continue
        px, py, patch = warped
        color = np.asarray([c * brightness for c in core.color_at(beam["color"], tm)], np.float32)
        if tint is not None:
            rgb = _warp(np.ascontiguousarray(tint[:, c0:c1]), quad, canvas.w, canvas.h)
            if rgb is not None and rgb[2].shape[:2] == patch.shape:
                color = rgb[2] * color
        canvas.blend(px, py, patch, color, alpha, light)


def _fill(canvas, quad, color, alpha, additive):
    xs, ys = [q[0] for q in quad], [q[1] for q in quad]
    x0, y0 = max(0, int(min(xs))), max(0, int(min(ys)))
    x1, y1 = min(canvas.w, int(max(xs)) + 2), min(canvas.h, int(max(ys)) + 2)
    if x1 <= x0 or y1 <= y0:
        return
    mask = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(mask).polygon([(q[0] - x0, q[1] - y0) for q in quad], fill=255)
    canvas.blend(x0, y0, np.asarray(mask, np.float32) / 255.0, color, alpha, additive)


GLOWING = ("Neon", "ForceField")


def glows(part):
    """A part that glows: a glowing material, or a mesh shell frame whose
    SurfaceAppearance has an emissive mask (recorded as `emissive`)."""
    return part["material"] in GLOWING or (part.get("emissive") or 0) > 0


_meshes = {}


def mesh(name):
    """A pack mesh (pack/meshes/<name>.obj, from tools/meshgen) as (verts, uvs, tris)."""
    if name not in _meshes:
        path = os.path.join(core.MESHES, name + ".obj")
        verts, uvs, tris = [], [], []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    q = line.split()
                    if not q:
                        continue
                    if q[0] == "v":
                        verts.append([float(x) for x in q[1:4]])
                    elif q[0] == "vt":
                        uvs.append([float(q[1]), 1 - float(q[2])])
                    elif q[0] == "f":
                        tris.append([int(x.split("/")[0]) - 1 for x in q[1:4]])
        _meshes[name] = (np.array(verts, np.float64), np.array(uvs, np.float64), np.array(tris, np.int64)) if tris else None
    return _meshes[name]


def draw_mesh(canvas, world, uvs, tris, tex, color, alpha, additive):
    """Rasterizes a textured mesh (world-space vertices) into the canvas. Coverage is
    combined with max before blending once, so a two-sided shell isn't drawn twice."""
    cam = canvas.cam
    proj = [cam.project(tuple(p)) for p in world]
    cover = np.zeros((canvas.h, canvas.w), np.float32)
    th, tw = tex.shape
    for a, b, c in tris:
        pa, pb, pc = proj[a], proj[b], proj[c]
        if pa is None or pb is None or pc is None:
            continue
        xs, ys = (pa[0], pb[0], pc[0]), (pa[1], pb[1], pc[1])
        x0, x1 = max(0, int(math.floor(min(xs)))), min(canvas.w, int(math.ceil(max(xs))) + 1)
        y0, y1 = max(0, int(math.floor(min(ys)))), min(canvas.h, int(math.ceil(max(ys))) + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        den = (pb[1] - pc[1]) * (pa[0] - pc[0]) + (pc[0] - pb[0]) * (pa[1] - pc[1])
        if abs(den) < 1e-9:
            continue
        py, px = np.mgrid[y0:y1, x0:x1].astype(np.float32) + 0.5
        w0 = ((pb[1] - pc[1]) * (px - pc[0]) + (pc[0] - pb[0]) * (py - pc[1])) / den
        w1 = ((pc[1] - pa[1]) * (px - pc[0]) + (pa[0] - pc[0]) * (py - pc[1])) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -0.01) & (w1 >= -0.01) & (w2 >= -0.01)
        if not inside.any():
            continue
        iz = np.array([1 / pa[2], 1 / pb[2], 1 / pc[2]], np.float32)
        q = w0 * iz[0] + w1 * iz[1] + w2 * iz[2]
        u = (w0 * uvs[a, 0] * iz[0] + w1 * uvs[b, 0] * iz[1] + w2 * uvs[c, 0] * iz[2]) / q
        v = (w0 * uvs[a, 1] * iz[0] + w1 * uvs[b, 1] * iz[1] + w2 * uvs[c, 1] * iz[2]) / q
        tx = np.clip((u * (tw - 1)).astype(int), 0, tw - 1)
        ty = np.clip((v * (th - 1)).astype(int), 0, th - 1)
        sample = np.where(inside, tex[ty, tx], 0)
        region = cover[y0:y1, x0:x1]
        np.maximum(region, sample, out=region)
    if cover.any():
        canvas.blend(0, 0, cover, color, alpha, additive)


def _mesh_part(canvas, part):
    found = mesh(part["meshId"][7:])
    if not found:
        return
    verts, uvs, tris = found
    extent = np.maximum(verts.max(0) - verts.min(0), 1e-6)
    local = verts / extent * np.asarray(part["size"], np.float64)
    cf = part["cframe"]
    rot = np.array(cf[3:12], np.float64).reshape(3, 3)
    world = local @ rot.T + np.asarray(cf[:3], np.float64)
    tex = texture(part.get("textureId") or "") if part.get("textureId") else np.ones((4, 4), np.float32)
    glowing = glows(part)
    draw_mesh(canvas, world, uvs, tris, tex, part["color"], 1 - part["t"], 1.0 if glowing else 0.0)


def _part(canvas, part):
    cam = canvas.cam
    cf = part["cframe"]
    center = tuple(cf[:3])
    alpha = 1 - part["t"]
    color = part["color"]
    glowing = part["material"] in GLOWING
    additive = 1.0 if glowing else 0.0
    if part.get("className") == "MeshPart" and str(part.get("meshId", "")).startswith("pack://"):
        _mesh_part(canvas, part)
        return
    if part["shape"] == "Ball":
        pr = cam.project(center)
        if not pr:
            return
        r = cam.pixels(max(part["size"]) / 2, pr[2])
        quad = [(pr[0] - r, pr[1] - r), (pr[0] + r, pr[1] - r), (pr[0] + r, pr[1] + r), (pr[0] - r, pr[1] + r)]
        disk = _procedural("disk_hard")
        disk = (disk > 0).astype(np.float32)
        warped = _warp(disk, quad, canvas.w, canvas.h)
        if warped:
            x0, y0, patch = warped
            canvas.blend(x0, y0, patch, color, alpha, additive)
        return
    sx, sy, sz = (s / 2 for s in part["size"])
    corners = []
    for cx in (-sx, sx):
        for cy in (-sy, sy):
            for cz in (-sz, sz):
                pr = cam.project(core.add(center, core.rot_apply(cf, (cx, cy, cz))))
                if pr is None:
                    return
                corners.append(pr[:2])
    hull = _hull(corners)
    shade = color if glowing else [c * 0.82 for c in color]
    canvas.polygon(hull, shade, alpha, additive)


def _hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def draw(timeline, t, cam, body=True):
    """The frame `t` seconds into the play, seen through `cam`. Returns (rgb, info)."""
    frame = core.frame_at(timeline, t)
    canvas = Canvas(cam)
    holder = tuple(timeline["holder"][:3])
    _floor(canvas, holder, frame["lights"] if frame else ())
    body_mask = _body(canvas, add_y(holder, 0.5)) if body else None
    if frame:
        # a PointLight shows only on what it lights (the floor, in _floor), not as a glow in the air
        parts = sorted(frame["parts"], key=lambda p: -core.dot(core.sub(p["cframe"][:3], cam.eye), cam.f))
        for part in parts:
            _part(canvas, part)
    particles = core.particles_at(timeline, t)
    particles.sort(key=lambda p: -core.dot(core.sub(p["pos"], cam.eye), cam.f))
    for p in particles:
        _particle(canvas, p)
    if frame:
        for beam in frame["beams"]:
            _beam(canvas, beam, t)
    rgb = canvas.finish(frame["screens"] if frame else ())
    return rgb, {"particles": len(particles), "glow": canvas.glow, "body": body_mask, "frame": frame}


def to_image(rgb):
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
