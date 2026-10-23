"""The mesh set (plan §3, step 2): shells that carry a texture, generated in code.

A shell is (vertices (n, 3), uvs (n, 2), triangles (m, 3)). Every shell fits the box
-0.5..0.5 on the axes it spans, since Roblox scales a mesh's bounds to its MeshPart's
Size. u runs along the shell (a slash's tail to its tip, or around a ring) and v across
it, so the strip and sequence textures of tools/texgen map straight on. Shells are drawn
from both sides: every triangle has a reversed twin, because MeshPart.DoubleSided can't
be set from a script.
"""

import math

import numpy as np

RECIPES = {}
DEFAULTS = {}


def recipe(name, **defaults):
    def wrap(fn):
        RECIPES[name] = fn
        DEFAULTS[name] = defaults
        return fn

    return wrap


def grid(nu, nv, fn):
    """A (nu + 1) x (nv + 1) vertex grid from fn(u, v) -> (x, y, z), u and v in 0..1."""
    us = np.linspace(0, 1, nu + 1)
    vs = np.linspace(0, 1, nv + 1)
    verts, uvs = [], []
    for v in vs:
        for u in us:
            verts.append(fn(u, v))
            uvs.append((u, v))
    tris = []
    row = nu + 1
    for j in range(nv):
        for i in range(nu):
            a, b = j * row + i, j * row + i + 1
            c, d = a + row, b + row
            tris += [(a, c, b), (b, c, d)]
    verts, tris = np.array(verts, np.float64), np.array(tris, np.int64)
    # pointed ends and poles collapse some quads; drop the zero-area triangles
    e1, e2 = verts[tris[:, 1]] - verts[tris[:, 0]], verts[tris[:, 2]] - verts[tris[:, 0]]
    keep = np.linalg.norm(np.cross(e1, e2), axis=1) > 1e-8
    return verts, np.array(uvs, np.float64), tris[keep]


def two_sided(verts, uvs, tris):
    return verts, uvs, np.concatenate([tris, tris[:, ::-1]])


def fit(verts, flat_axes=()):
    """Centres the shell and scales it so its largest side is 1 and every side it spans
    sits inside -0.5..0.5."""
    lo, hi = verts.min(0), verts.max(0)
    centre = (lo + hi) / 2
    span = (hi - lo).max()
    return (verts - centre) / max(span, 1e-9)


@recipe("crescent", sweep=200, inner=0.62, width=0.38, cone=0.18, taper=0.65, segments=64)
def crescent(p):
    """A slash shell: a band swept around an arc, widest two thirds of the way along and
    pointed at both ends, tilted into a shallow cone so it has depth."""
    sweep = math.radians(p["sweep"])
    start = -math.pi / 2 - sweep * 0.62

    def at(u, v):
        a = start + sweep * u
        swell = math.sin(math.pi * min(1.0, u / 0.68) * 0.5) if u < 0.68 else math.cos(math.pi * (u - 0.68) / 0.32 * 0.5)
        w = p["width"] * max(swell, 0.0) ** p["taper"]
        r = p["inner"] + w * v + (p["width"] - w) * 0.5
        return (r * math.cos(a), p["cone"] * v * w / p["width"], r * math.sin(a))

    verts, uvs, tris = grid(int(p["segments"]), 4, at)
    return two_sided(fit(verts), uvs, tris)


@recipe("cone", top=0.5, bottom=0.12, height=0.6, segments=48)
def cone(p):
    """An open truncated cone: a burst or shockwave thrown up from the ground. u goes
    around, v from the narrow bottom to the wide top."""

    def at(u, v):
        a = 2 * math.pi * u
        r = p["bottom"] + (p["top"] - p["bottom"]) * v
        return (r * math.cos(a), p["height"] * v, r * math.sin(a))

    verts, uvs, tris = grid(int(p["segments"]), 3, at)
    return two_sided(fit(verts), uvs, tris)


@recipe("sphere", segments=32, rings=16)
def sphere(p):
    """A sphere shell: a dome flash or a shield. u goes around, v from pole to pole."""

    def at(u, v):
        a, b = 2 * math.pi * u, math.pi * v
        return (math.sin(b) * math.cos(a), math.cos(b), math.sin(b) * math.sin(a))

    verts, uvs, tris = grid(int(p["segments"]), int(p["rings"]), at)
    return two_sided(fit(verts), uvs, tris)


@recipe("torus", major=0.4, minor=0.08, segments=48, sides=12)
def torus(p):
    """A torus: a hard ring that keeps its thickness at any angle. u goes around the ring,
    v around the tube."""

    def at(u, v):
        a, b = 2 * math.pi * u, 2 * math.pi * v
        r = p["major"] + p["minor"] * math.cos(b)
        return (r * math.cos(a), p["minor"] * math.sin(b), r * math.sin(a))

    verts, uvs, tris = grid(int(p["segments"]), int(p["sides"]), at)
    return two_sided(fit(verts), uvs, tris)


@recipe("cylinder", radius=0.5, height=1.0, segments=40)
def cylinder(p):
    """An open tube: a light pillar or a beam's body. u goes around, v along it."""

    def at(u, v):
        a = 2 * math.pi * u
        return (p["radius"] * math.cos(a), p["height"] * (v - 0.5), p["radius"] * math.sin(a))

    verts, uvs, tris = grid(int(p["segments"]), 2, at)
    return two_sided(fit(verts), uvs, tris)


def to_obj(verts, uvs, tris, name):
    """Wavefront OBJ, one-based indices. OBJ's v points up, so v is flipped to keep the
    texture's top row at v = 0, the way Roblox reads it."""
    lines = [f"# EasyVFX mesh set: {name} (tools/meshgen)", f"o {name}"]
    lines += [f"v {x:.5f} {y:.5f} {z:.5f}" for x, y, z in verts]
    lines += [f"vt {u:.5f} {1 - v:.5f}" for u, v in uvs]
    lines += [f"f {a + 1}/{a + 1} {b + 1}/{b + 1} {c + 1}/{c + 1}" for a, b, c in tris]
    return "\n".join(lines) + "\n"


def from_obj(text):
    verts, uvs, tris = [], [], []
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v":
            verts.append([float(x) for x in parts[1:4]])
        elif parts[0] == "vt":
            uvs.append([float(parts[1]), 1 - float(parts[2])])
        elif parts[0] == "f":
            tris.append([int(q.split("/")[0]) - 1 for q in parts[1:4]])
    return np.array(verts, np.float64), np.array(uvs, np.float64), np.array(tris, np.int64)
