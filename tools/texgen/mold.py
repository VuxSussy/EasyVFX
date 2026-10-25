"""Molded textures: a shape pushed around by hand, then shaded in code.

A mold is a small JSON file in tools/texgen/molds/: a base shape (a bank texture, or a plain
blob), the warp painted over it in the mold page (`evfx serve`, /mold), and the shading
settings. Painting is the part a person does well (the silhouette); the shading stays code,
so it can be tuned and repeated. The `molded` recipe rebuilds a mold at any size, the same way
the page's preview does, so what the page shows is what the bank builds.

The warp is a grid of offsets in texture units (u and v run -1..1): the output at a point p is
the base read at p minus the offset there (a backward warp, so it never tears).

The tone is an optional grid of the same size, painted with the page's Dodge and Burn brushes:
the shaded brightness at each point is multiplied by 2 to the power of the tone there, so +1
doubles it and -1 halves it. It sits on the finished texture, not on the base, so warping the
shape after painting leaves the tone where it was painted.
"""

import json
import os
import re

import numpy as np
from PIL import Image, ImageFilter

import lib

MOLDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "molds")
NAME = re.compile(r"^[a-z0-9_]{1,40}$")

# shading defaults, also the page's slider starting points
SHADING = {
    "cut": 0.3,  # where the base's alpha becomes the shape
    "edge_soft": 0.1,  # how soft that cut is, in the base's alpha
    "reach": 0.08,  # how deep into the shape the brightness keeps rising
    "edge": 0.35,  # brightness at the shape's edge (1 at the core)
    "gamma": 0.8,  # how the brightness rises from edge to core
    "fold": 0.0,  # how dark the drawn fold line is
    "fold_width": 0.05,
    "soften": 0.01,  # a final blur, as a share of the texture
    "light": 0.0,  # how much darker the shape's far side is than its lit side
    "light_angle": 90.0,  # where the light comes from, degrees on screen (0 right, 90 top)
}


def path(name):
    if not NAME.match(name or ""):
        raise ValueError(f"a mold name is lowercase letters, digits and _, got {name!r}")
    return os.path.join(MOLDS, name + ".json")


def load(name):
    with open(path(name), encoding="utf-8") as f:
        return json.load(f)


def save(name, mold):
    os.makedirs(MOLDS, exist_ok=True)
    clean = {
        "base": str(mold.get("base", "blob")),
        "cell": int(mold.get("cell", 0)),
        "grid": int(mold["grid"]),
        "warp": [round(float(x), 5) for x in mold["warp"]],
        "fold": [[round(float(a), 4), round(float(b), 4)] for a, b in mold.get("fold", [])],
        "tone": [round(float(x), 3) for x in mold.get("tone") or []],
        "shading": {k: float(mold.get("shading", {}).get(k, v)) for k, v in SHADING.items()},
    }
    if len(clean["warp"]) != clean["grid"] * clean["grid"] * 2:
        raise ValueError("the warp needs grid x grid x 2 numbers")
    if not any(clean["tone"]):
        del clean["tone"]
    elif len(clean["tone"]) != clean["grid"] * clean["grid"]:
        raise ValueError("the tone needs grid x grid numbers")
    with open(path(name), "w", encoding="utf-8") as f:
        json.dump(clean, f, separators=(",", ":"))
        f.write("\n")
    return path(name)


def base_alpha(base, cell, size):
    """The shape to mold: "blob" (a soft round lump, a true circle), or a bank texture's alpha; for a sheet or
    flipbook, its `cell`-th frame."""
    u, v = lib.grid(size)
    if base == "blob":
        r = np.sqrt(u ** 2 + v ** 2) / 0.46
        return np.clip(1.2 - r, 0, 1).astype(np.float32)
    import bank

    e = bank.get(base)
    grid = int(e.get("grid", 1))
    rgba, _ = bank.render(base, size=size * grid)
    a = rgba[..., 3].astype(np.float32) / 255
    if grid > 1:
        r_, c_ = divmod(int(cell) % (grid * grid), grid)
        a = a[r_ * size : (r_ + 1) * size, c_ * size : (c_ + 1) * size]
    return a


def warp(alpha, grid, offsets):
    """Reads `alpha` back through the offset grid (grid x grid x 2, texture units)."""
    size = alpha.shape[0]
    d = np.asarray(offsets, np.float32).reshape(grid, grid, 2)
    u, v = lib.grid(size)
    # the grid's nodes span -1..1 corner to corner
    gx = (u + 1) / 2 * (grid - 1)
    gy = (v + 1) / 2 * (grid - 1)
    du = lib.sample(d[..., 0], gx, gy, wrap=False)
    dv = lib.sample(d[..., 1], gx, gy, wrap=False)
    sx = ((u - du) + 1) / 2 * size - 0.5
    sy = ((v - dv) + 1) / 2 * size - 0.5
    inside = (sx >= 0) & (sx <= size - 1) & (sy >= 0) & (sy <= size - 1)
    return lib.sample(alpha, sx, sy, wrap=False) * inside


def _blur(a, radius_px):
    if radius_px <= 0.05:
        return a
    top = max(1e-6, float(a.max()))
    img = Image.fromarray(np.clip(a / top * 255, 0, 255).astype(np.uint8))
    return np.asarray(img.filter(ImageFilter.GaussianBlur(radius_px)), np.float32) / 255 * top


def _fold_distance(u, v, pts):
    d = np.full(u.shape, 9.0, np.float32)
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        seg, _ = lib.sd_segment(u, v, ax, ay, bx, by)
        d = np.minimum(d, seg)
    return d


def tone_at(grid, tone, size):
    """The painted tone grid read at every pixel of a (size, size) texture."""
    t = np.asarray(tone, np.float32).reshape(grid, grid)
    u, v = lib.grid(size)
    return lib.sample(t, (u + 1) / 2 * (grid - 1), (v + 1) / 2 * (grid - 1), wrap=False)


def shade(shape, fold, s, size, tone=None, grid=None):
    """The molded shape as one white tone: cut, brightest deep inside, a drawn fold darkened,
    then the painted `tone` (a grid x grid list, see the module notes) applied."""
    s = {**SHADING, **(s or {})}
    px = 2.0 / size
    # a soft cut: the shape ramps in over `edge_soft` of the base's alpha around the cut level
    m = np.clip((shape - s["cut"]) / max(s["edge_soft"], 1e-3) + 0.5, 0, 1)
    depth = _blur(m, s["reach"] * size / 2)
    depth = np.clip((depth - 0.5) / 0.5, 0, 1)
    out = m * (s["edge"] + (1 - s["edge"]) * depth ** s["gamma"])
    if s["light"] > 0 and m.sum() > 0:
        # a ramp across the shape's own extent, 1 on the lit side, 1 - light on the far side
        u, v = lib.grid(size)
        a = np.radians(s["light_angle"])
        t = u * np.cos(a) - v * np.sin(a)
        inside = m > 0.5
        lo, hi = (float(t[inside].min()), float(t[inside].max())) if inside.any() else (-1.0, 1.0)
        out = out * (1 - s["light"] * np.clip((hi - t) / max(hi - lo, 1e-3), 0, 1))
    if s["fold"] > 0 and len(fold) >= 2:
        u, v = lib.grid(size)
        d = _fold_distance(u, v, fold)
        out = out * (1 - s["fold"] * np.exp(-((d / max(s["fold_width"], px)) ** 2)))
    if tone is not None and len(tone) and grid:
        out = out * np.exp2(tone_at(grid, tone, size))
    out = _blur(out, s["soften"] * size)
    u, v = lib.grid(size)
    return np.clip(out, 0, 1) * lib.vignette(u, v, 0.94, 0.995)


def render(mold, size):
    """A mold (a dict as saved) as a (size, size) alpha."""
    a = base_alpha(mold.get("base", "blob"), mold.get("cell", 0), size)
    a = warp(a, int(mold["grid"]), mold["warp"])
    return shade(a, mold.get("fold", []), mold.get("shading"), size, mold.get("tone"), int(mold["grid"]))


def to_png(alpha):
    import io

    buf = io.BytesIO()
    Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8)).save(buf, "PNG")
    return buf.getvalue()


def bank_id(name):
    return "shape/mold_" + name


def register(name):
    """Gives a saved mold a bank entry (`shape/mold_<name>`, recipe `molded`) if it has none, and
    builds its texture into the pack. Returns the bank id."""
    import bank

    tid = bank_id(name)
    with open(bank.BANK, encoding="utf-8") as f:
        text = f.read()
    if f'"{tid}"' not in text:
        line = json.dumps({"recipe": "molded", "kind": "shape", "size": 512, "seed": 1, "params": {"mold": name},
                           "role": "base", "use": f"molded by hand in the mold page (tools/texgen/molds/{name}.json), shaded in code"})
        # the entries close with the line "  }": add this one as the last entry before it
        head, tail = text.rsplit("\n  }\n", 1)
        text = head + ",\n" + f'    "{tid}": {line}' + "\n  }\n" + tail
        with open(bank.BANK, "w", encoding="utf-8") as f:
            f.write(text)
        bank._bank = None
    rgba, meta = bank.render(tid)
    bank.write([(rgba, meta)])
    return tid
