"""Building blocks for VFX textures: tileable noise, signed-distance shapes, polar
warps and erosion. Everything works on float32 arrays in 0..1.

The techniques follow the references in docs/texture-generator.md: an effect texture is
grayscale and tinted by the engine; noise and erosion maps drive how a shape breaks
up; a dissolve erodes a shape by a noise threshold instead of fading it evenly; tiled
textures repeat seamlessly so beams and trails can scroll them.
"""

import math

import numpy as np

# ------------------------------------------------------------------ grids


def grid(size, aspect=1.0):
    """Pixel-centred coordinates: u in -aspect..aspect, v in -1..1 (y down)."""
    h = size
    w = int(round(size * aspect))
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u = ((x + 0.5) / w * 2 - 1) * aspect
    v = (y + 0.5) / h * 2 - 1
    return u, v


def polar(u, v):
    return np.sqrt(u * u + v * v), np.arctan2(v, u)


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def crisp(d, edge=0.012):
    """Turns a signed distance (negative inside) into a hard, anti-aliased mask."""
    return np.clip(0.5 - d / edge, 0, 1)


# ------------------------------------------------------------------ noise


def _fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def perlin(shape, period, seed=0):
    """Gradient noise that tiles exactly: `period` lattice cells across each axis."""
    h, w = shape
    py, px = (period, period) if np.isscalar(period) else period
    rng = np.random.default_rng(seed)
    angles = rng.random((py + 1, px + 1)) * 2 * np.pi
    grads = np.stack([np.cos(angles), np.sin(angles)], -1)
    grads[-1, :] = grads[0, :]
    grads[:, -1] = grads[:, 0]
    y = np.linspace(0, py, h, endpoint=False)[:, None] + 0.5 * py / h
    x = np.linspace(0, px, w, endpoint=False)[None, :] + 0.5 * px / w
    y = np.broadcast_to(y, (h, w))
    x = np.broadcast_to(x, (h, w))
    y0, x0 = np.floor(y).astype(int), np.floor(x).astype(int)
    fy, fx = y - y0, x - x0

    def dot(gy, gx, dy, dx):
        g = grads[gy, gx]
        return g[..., 0] * dx + g[..., 1] * dy

    n00 = dot(y0, x0, fy, fx)
    n10 = dot(y0, x0 + 1, fy, fx - 1)
    n01 = dot(y0 + 1, x0, fy - 1, fx)
    n11 = dot(y0 + 1, x0 + 1, fy - 1, fx - 1)
    sx, sy = _fade(fx), _fade(fy)
    nx0 = n00 + sx * (n10 - n00)
    nx1 = n01 + sx * (n11 - n01)
    return (nx0 + sy * (nx1 - nx0)).astype(np.float32) * 0.7 + 0.5


def fbm(shape, period=4, octaves=5, gain=0.5, seed=0):
    """Fractal noise from tileable octaves, normalized to 0..1."""
    total = np.zeros(shape, np.float32)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        total += amp * perlin(shape, period * 2 ** o, seed + o * 101)
        norm += amp
        amp *= gain
    total /= norm
    return normalize(total)


def ridged(shape, period=4, octaves=5, seed=0):
    """Sharp crests (lightning, cracks, energy veins)."""
    total = np.zeros(shape, np.float32)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        n = perlin(shape, period * 2 ** o, seed + o * 131)
        total += amp * (1 - np.abs(n * 2 - 1)) ** 2
        norm += amp
        amp *= 0.5
    return normalize(total / norm)


def worley(shape, cells=8, seed=0, second=False):
    """Cellular noise that tiles: distance to the nearest feature point (or the
    second nearest minus the nearest, for cracked-ground edges)."""
    h, w = shape
    rng = np.random.default_rng(seed)
    pts = rng.random((cells, cells, 2))
    y = (np.arange(h) + 0.5) / h * cells
    x = (np.arange(w) + 0.5) / w * cells
    yy, xx = np.meshgrid(y, x, indexing="ij")
    best = np.full((h, w), 9.0, np.float32)
    best2 = np.full((h, w), 9.0, np.float32)
    cy, cx = np.floor(yy).astype(int), np.floor(xx).astype(int)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            gy, gx = cy + dy, cx + dx
            p = pts[gy % cells, gx % cells]
            d = np.sqrt((gy + p[..., 0] - yy) ** 2 + (gx + p[..., 1] - xx) ** 2).astype(np.float32)
            closer = d < best
            best2 = np.where(closer, best, np.minimum(best2, d))
            best = np.minimum(best, d)
    out = (best2 - best) if second else best
    return normalize(out)


def warp(field, du, dv, strength):
    """Samples `field` at coordinates pushed by two offset maps (domain warp), wrapping."""
    h, w = field.shape
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    sy = (y + (dv - 0.5) * strength * h) % h
    sx = (x + (du - 0.5) * strength * w) % w
    return sample(field, sx, sy)


def sample(field, x, y, wrap=True):
    """Bilinear lookup of `field` at float pixel coordinates."""
    h, w = field.shape
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    if wrap:
        x0, y0 = x0 % w, y0 % h
        x1, y1 = (x0 + 1) % w, (y0 + 1) % h
    else:
        x0, y0 = np.clip(x0, 0, w - 1), np.clip(y0, 0, h - 1)
        x1, y1 = np.clip(x0 + 1, 0, w - 1), np.clip(y0 + 1, 0, h - 1)
    a = field[y0, x0] * (1 - fx) + field[y0, x1] * fx
    b = field[y1, x0] * (1 - fx) + field[y1, x1] * fx
    return (a * (1 - fy) + b * fy).astype(np.float32)


def polar_sample(field, r, theta, radial_scale=1.0, turns=1):
    """Wraps a tileable field around a centre: angle across, radius down. Seamless,
    since the field tiles horizontally."""
    h, w = field.shape
    x = ((theta / (2 * np.pi)) % 1.0) * w * turns
    y = np.clip(r * radial_scale, 0, 0.999) * h
    return sample(field, x % w, y, wrap=True)


def normalize(a):
    lo, hi = float(a.min()), float(a.max())
    return ((a - lo) / max(1e-6, hi - lo)).astype(np.float32)


# ------------------------------------------------------------------ shapes (signed distance, negative inside)


def sd_circle(u, v, r):
    return np.sqrt(u * u + v * v) - r


def sd_ring(u, v, r, thick):
    return np.abs(np.sqrt(u * u + v * v) - r) - thick


def sd_star(u, v, points, outer, inner, phase=0.0):
    """A star with `points` sharp tips."""
    r, a = polar(u, v)
    sector = 2 * np.pi / points
    t = np.abs(((a - phase) % sector) / sector * 2 - 1)
    edge = inner + (outer - inner) * (1 - t) ** 2.2
    return r - edge


def sd_segment(u, v, ax, ay, bx, by):
    pax, pay = u - ax, v - ay
    bax, bay = bx - ax, by - ay
    h = np.clip((pax * bax + pay * bay) / (bax * bax + bay * bay), 0, 1)
    return np.sqrt((pax - bax * h) ** 2 + (pay - bay * h) ** 2), h


def needle(u, v, ax, ay, bx, by, width):
    """A streak pointed at both ends, widest a third of the way from the start."""
    d, h = sd_segment(u, v, ax, ay, bx, by)
    profile = np.where(h < 0.33, h / 0.33, (1 - h) / 0.67) ** 0.8
    return d - width * profile


def crescent(u, v, r, thick, sweep, offset=0.18):
    """A slash blade: the gap between two offset circles, cut to `sweep` radians."""
    outer = np.sqrt(u * u + v * v) - r
    inner = np.sqrt((u + offset * r) ** 2 + (v - offset * 0.35 * r) ** 2) - (r - thick)
    d = np.maximum(outer, -inner)
    a = np.arctan2(v, u)
    cut = np.abs(a + np.pi / 2) - sweep / 2
    return np.maximum(d, cut * r * 0.5)


def polygon(u, v, pts):
    """Signed distance to a convex or concave polygon given as (x, y) points."""
    d = np.full(u.shape, 1e9, np.float32)
    s = np.ones(u.shape, np.float32)
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[i - 1]
        ex, ey = bx - ax, by - ay
        wx, wy = u - ax, v - ay
        h = np.clip((wx * ex + wy * ey) / (ex * ex + ey * ey), 0, 1)
        d = np.minimum(d, (wx - ex * h) ** 2 + (wy - ey * h) ** 2)
        c1 = v >= ay
        c2 = v < by
        c3 = ex * wy > ey * wx
        flip = (c1 & c2 & c3) | (~c1 & ~c2 & ~c3)
        s = np.where(flip, -s, s)
    return s * np.sqrt(d)


# ------------------------------------------------------------------ erosion and layout


def erode(mask, noise, amount, soft=0.06):
    """Dissolves `mask` by `noise`: amount 0 keeps it, 1 removes it. The noise decides
    which parts go first, so the shape breaks up instead of fading evenly."""
    threshold = amount * (1 + soft) - soft
    return mask * smooth(threshold, threshold + soft, noise)


def frames(n, fn):
    """Calls fn(t) for t in 0..1 over n frames."""
    return [fn(k / max(1, n - 1)) for k in range(n)]


def atlas(cells, grid_n):
    """Packs grid_n * grid_n equally sized frames, left to right, top to bottom."""
    h, w = cells[0].shape
    out = np.zeros((h * grid_n, w * grid_n), np.float32)
    for i, c in enumerate(cells[: grid_n * grid_n]):
        r, k = divmod(i, grid_n)
        out[r * h : (r + 1) * h, k * w : (k + 1) * w] = c
    return out


def vignette(u, v, start=0.82, end=0.98):
    """Fades to zero before the texture's border, so a single sprite never clips."""
    r = np.maximum(np.abs(u), np.abs(v))
    return 1 - smooth(start, end, r)


def rng_angles(seed, n, jitter=0.35):
    rng = np.random.default_rng(seed)
    base = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return base + rng.uniform(-jitter, jitter, n) * (2 * math.pi / n), rng
