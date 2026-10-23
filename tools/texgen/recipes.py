"""The recipes behind library v4. A recipe draws one texture from its knobs:

    fn(p, rng, size) -> alpha (h, w), or a list of frames, or {"alpha": ..., "rgb": ...}

`p` holds the recipe's knobs (its defaults, then the bank entry's params, then any
--set), `rng` is a numpy Generator seeded from the entry's seed, and `size` is the
output's width in pixels (a frame's width for flipbooks and sheets). Coordinates come
from lib.grid: u and v run -1..1 across a square texture, v pointing down.

Every texture is white with its shape in alpha (the pack convention); only a recipe
whose bank entry says `"rgb": "spectrum"` may return colour.
"""

import math

import numpy as np

import lib

RECIPES = {}
DEFAULTS = {}


def recipe(name, **defaults):
    def wrap(fn):
        RECIPES[name] = fn
        DEFAULTS[name] = defaults
        return fn

    return wrap


def _seed(rng):
    return int(rng.integers(0, 2**31 - 1))


def _frames(p):
    return int(p.get("frames", 16))


def _amount(t, p):
    """How far a dissolve has eroded at time t: nothing before `hold`, everything by the
    last frame, shaped by `ease` (the timing knobs)."""
    return lib.ease_in(lib.smooth(p["hold"], 1.0, t) if p["hold"] < 1 else np.float32(t >= 1), p["ease"])


# ================================================================== shapes


@recipe("core_flash", core=0.11, glow=0.42, rays=8, ray_gain=0.22)
def core_flash(p, rng, size):
    """The white-hot centre of a hit: a hard core, a short hot falloff and a faint
    ray crown, so it reads as a flash, not a ball."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    core = lib.aa(r - p["core"], size, 2.0)
    hot = np.exp(-((r / (p["core"] * 1.9)) ** 2))
    glow = 0.42 * np.exp(-((r / p["glow"]) ** 2))
    n = int(p["rays"])
    crown = np.cos(a * n) ** 40 * np.exp(-r / 0.22) * p["ray_gain"]
    alpha = np.maximum(core, np.maximum(hot, glow + crown))
    return alpha * lib.vignette(u, v, 0.7, 0.96)


def _ray(along, across, length, width, power=2.2):
    t = np.clip(np.abs(along) / length, 0, 1)
    w = width * (1 - t) ** 1.5 + 1e-4
    return np.exp(-((across / w) ** 2)) * (1 - t) ** power


@recipe("cross_flare", long=0.96, short=0.6, width=0.03, diagonal=0.32)
def cross_flare(p, rng, size):
    """A four-point lens flare: a long horizontal spike, a shorter vertical one,
    faint diagonals and a small hot core. Thin and anisotropic."""
    u, v = lib.grid(size)
    r = np.sqrt(u * u + v * v)
    h = _ray(u, v, p["long"], p["width"])
    vert = _ray(v, u, p["short"], p["width"] * 0.9)
    du, dv = (u + v) * 0.7071, (u - v) * 0.7071
    diag = 0.5 * np.maximum(_ray(du, dv, p["diagonal"], p["width"] * 0.5), _ray(dv, du, p["diagonal"], p["width"] * 0.5))
    core = np.exp(-((r / 0.05) ** 2)) + 0.3 * np.exp(-((r / 0.16) ** 2))
    alpha = np.clip(np.maximum.reduce([h, vert, diag]) + core, 0, 1)
    return alpha * lib.vignette(u, v, 0.86, 0.98)


@recipe("godray_fan", rays=30, min_len=0.4, max_len=0.94, width=0.05)
def godray_fan(p, rng, size):
    """Radial god-ray spikes of uneven length and width around a core: the frame-one
    burst of a heavy hit."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    n = int(p["rays"])
    angles, _ = lib.rng_angles(_seed(rng), n, 0.45)
    out = np.zeros_like(u)
    for k in range(n):
        length = rng.uniform(p["min_len"], p["max_len"]) * (1.0 if k % 3 else 0.7)
        width = rng.uniform(0.25, 1.0) * p["width"]
        gain = rng.uniform(0.45, 1.0)
        da = (a - angles[k] + np.pi) % (2 * np.pi) - np.pi
        across = da * r
        t = np.clip(r / length, 0, 1)
        w = width * (1 - t) ** 0.9 + 1e-4
        ray = np.exp(-((across / w) ** 2)) * (1 - t) ** 1.4 * gain * lib.smooth(0.02, 0.12, r)
        out = np.maximum(out, ray)
    core = np.exp(-((r / 0.07) ** 2)) + 0.25 * np.exp(-((r / 0.2) ** 2))
    return np.clip(out + core, 0, 1) * lib.vignette(u, v, 0.86, 0.98)


@recipe("aniso_shard", width=0.1, head=-0.55, facet=0.62)
def aniso_shard(p, rng, size):
    """A long faceted shard pointing up (the texture's top follows the velocity, like
    spark_streak): a hard kite with one darker facet and a white core line."""
    u, v = lib.grid(size)
    w = p["width"]
    head = p["head"]
    left = lib.polygon(u, v, [(0, -0.94), (-w, head), (0, 0.94)])
    right = lib.polygon(u, v, [(0, -0.94), (0, 0.94), (w * 0.8, head + 0.08)])
    body = np.maximum(lib.aa(left, size) * 1.0, lib.aa(right, size) * p["facet"])
    fade = 1 - lib.smooth(0.2, 0.94, v) * 0.55
    d, _ = lib.sd_segment(u, v, 0, -0.86, 0, 0.6)
    core = np.exp(-((d / 0.012) ** 2)) * (1 - lib.smooth(-0.2, 0.6, v))
    return np.clip(np.maximum(body * fade, core), 0, 1) * lib.vignette(u, v, 0.9, 0.99)


def _brush(u, v, size, pts, width, seed, attack=0.06, release=0.3, swell=0.25, dry=0.45, rough=0.025, density=0.45):
    """A calligraphic stroke: pressure along the path, a rough edge, bristle streaks that
    open into dry-brush gaps toward the tail, and ink density from the bristles."""
    d, s, across = lib.stroke(u, v, pts, lambda t: width * lib.taper(t, attack, release, swell, 1.4) * (1.15 - 0.3 * t) + 1e-3, caps=False)
    s = np.clip(s, 0, 1)
    edge = (lib.fbm(u.shape, 8, 4, seed=seed) - 0.5) * rough
    mask = lib.aa(d + edge, size)
    fib = lib.fibres(s * 1.5, across, seed=seed + 1, count=36, length=5)
    gap = 0.14 + lib.smooth(dry, 1.0, s) * 0.75 + lib.smooth(0.55, 1.0, np.abs(across)) * 0.3
    bristle = lib.smooth(gap - 0.04, gap + 0.04, fib)
    ink = 1 - density * (1 - fib)
    return mask * bristle * ink, s, across


@recipe("ink_stroke", width=0.085, dry=0.5)
def ink_stroke(p, rng, size):
    """One hard ink slash across the frame: a sharp entry, a heavy belly and a dry,
    split tail. Tinted black with normal blending, it is the ZZZ ink accent."""
    u, v = lib.grid(size)
    pts = lib.bezier([(-0.86, 0.5), (-0.3, -0.05), (0.3, -0.25), (0.88, -0.42)], 80)
    alpha, s, _ = _brush(u, v, size, pts, p["width"], _seed(rng), attack=0.08, release=0.3, swell=0.4, dry=p["dry"], density=0.3)
    flecks = np.zeros_like(u)
    for _ in range(7):
        cx, cy = rng.uniform(0.35, 0.8), rng.uniform(-0.55, -0.2)
        flecks = np.maximum(flecks, lib.aa(lib.sd_circle(u - cx, v - cy, rng.uniform(0.006, 0.016)), size))
    return np.maximum(alpha, flecks) * lib.vignette(u, v, 0.9, 0.99)


# ================================================================== erosion flipbooks


@recipe("burst_dissolve", frames=16, hold=0.18, ease=1.3, spikes=16, start=0.4, reach=0.52)
def burst_dissolve(p, rng, size):
    """A spiky burst that bursts out, hollows from its centre and breaks up by noise
    until nothing is left."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    n = int(p["spikes"])
    angles, _ = lib.rng_angles(_seed(rng), n, 0.5)
    lengths = rng.uniform(0.5, 1.0, n)
    noise = lib.fbm(u.shape, 4, 5, seed=_seed(rng))
    def frame(t):
        grow = lib.ease_out(t, 3)
        radius = p["start"] + p["reach"] * grow
        spike = np.zeros_like(u)
        for k in range(n):
            da = (a - angles[k] + np.pi) % (2 * np.pi) - np.pi
            reach = radius * lengths[k] * 1.25
            tt = np.clip(r / reach, 0, 1)
            w = 0.075 * (1 - tt) ** 1.4 + 1e-4
            spike = np.maximum(spike, lib.aa(np.abs(da * r) - w * reach, size) * (r < reach))
        disk = lib.aa(r - radius * 0.3, size)
        body = np.maximum(spike, disk)
        hot = np.exp(-((r / (radius * 0.35)) ** 2)) * (1 - lib.smooth(0.0, 0.3, t))
        hollow = 0.6 * noise + 0.4 * np.clip(r / max(radius, 1e-3), 0, 1)
        shade = 0.72 + 0.28 * noise
        alpha = np.maximum(lib.erode(body * shade, hollow, _amount(t, p), 0.05), hot)
        return alpha * lib.vignette(u, v, 0.86, 0.97)
    return lib.frames(_frames(p), frame)


@recipe("smoke_puff", frames=16, hold=0.3, ease=1.2, warp=0.35, start=0.4, reach=0.4, soft=0.07)
def smoke_puff(p, rng, size):
    """A domain-warped smoke puff with a defined, billowy edge and inner shading. It
    swells, curls and erodes away; a body layer, drawn with normal blending."""
    u, v = lib.grid(size)
    r, _ = lib.polar(u, v)
    seed = _seed(rng)
    base = lib.fbm(u.shape, 3, 5, seed=seed)
    du, dv = lib.fbm(u.shape, 2, 4, seed=seed + 1), lib.fbm(u.shape, 2, 4, seed=seed + 2)
    holes = lib.fbm(u.shape, 5, 4, seed=seed + 3)
    def frame(t):
        curl = p["warp"] * (0.35 + 0.65 * t)
        w = lib.warp(base, du, dv, curl * 0.5)
        radius = p["start"] + p["reach"] * lib.ease_out(t, 2.5)
        d = r / radius + (w - 0.5) * 0.9
        body = lib.smooth(1.0, 1.0 - p["soft"] * 2, d)
        shade = 0.55 + 0.45 * lib.smooth(0.25, 0.75, w)
        alpha = lib.erode(body * shade, 0.55 * holes + 0.45 * w, _amount(t, p), 0.08)
        return alpha * lib.vignette(u, v, 0.86, 0.97)
    return lib.frames(_frames(p), frame)


@recipe("flame_tongue", frames=16, sway=0.42, height=0.9)
def flame_tongue(p, rng, size):
    """A flame tongue that loops: the noise scrolls up exactly one period over the 16
    frames, so the last frame flows into the first. A hot inner tongue sits inside a
    lighter body."""
    u, v = lib.grid(size)
    seed = _seed(rng)
    field = lib.fbm((size, size), 3, 4, seed=seed)
    fine = lib.fbm((size, size), 6, 3, seed=seed + 1)
    n = _frames(p)
    h = np.clip((0.42 - v) / (0.42 + p["height"]), 0, 1)
    ys = (np.arange(size, dtype=np.float32)[:, None] + np.zeros((1, size), np.float32))
    xs = (np.arange(size, dtype=np.float32)[None, :] + np.zeros((size, 1), np.float32))
    cells = []
    for k in range(n):
        off = k / n * size
        wob = lib.sample(field, xs, (ys + off) % size)
        flick = lib.sample(fine, xs, (ys + off * 2) % size)
        uu = u + (wob - 0.5) * p["sway"] * h * 1.6
        def tongue(scale):
            width = 0.34 * scale * (1 - h) ** 1.35 * (v < 0.42)
            base = lib.sd_circle(uu, v - 0.42, 0.34 * scale)
            return np.minimum(np.abs(uu) - width, base)
        tip = lib.smooth(-0.12, 0.12, (flick - 0.5) * 0.9 + 0.75 - h ** 1.6)
        body = lib.aa(tongue(1.0), size, 2.0) * tip
        inner = lib.aa(tongue(0.5) + 0.02, size, 2.0) * lib.smooth(-0.1, 0.1, (flick - 0.5) * 0.6 + 0.5 - h)
        alpha = np.maximum(body * 0.6, inner)
        cells.append(alpha * lib.vignette(u, v, 0.86, 0.97))
    return cells


@recipe("shock_ring", frames=16, hold=0.25, ease=1.0, start=0.12, reach=0.78, thick=0.13)
def shock_ring(p, rng, size):
    """A shock ring with a hard leading edge and a soft trail. It races out, thins and
    breaks into arcs as angular noise erodes it."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    seed = _seed(rng)
    ang = lib.polar_sample(lib.fbm((256, 256), 4, 4, seed=seed), np.full_like(r, 0.5), a)
    grain = lib.fbm(u.shape, 8, 3, seed=seed + 1)
    def frame(t):
        radius = p["start"] + p["reach"] * lib.ease_out(t, 3)
        th = p["thick"] * (1 - t) ** 1.3 + 0.01
        lead = lib.aa(r - radius, size)
        trail = np.exp(-np.clip(radius - r, 0, None) / th) * lead
        edge = lib.aa(np.abs(r - radius + th * 0.18) - th * 0.12, size)
        ring = np.maximum(trail * 0.7, edge)
        alpha = lib.erode(ring, 0.7 * ang + 0.3 * grain, _amount(t, p), 0.05)
        return alpha * lib.vignette(u, v, 0.88, 0.98)
    return lib.frames(_frames(p), frame)


@recipe("slash_erode", frames=16, hold=0.12, ease=1.4, sweep=210, radius=0.74, width=0.2)
def slash_erode(p, rng, size):
    """A crescent slash that erodes from its tail to its tip: the tail goes first,
    broken by noise, the blade thins, and a bright edge runs along the outside."""
    u, v = lib.grid(size)
    sweep = math.radians(p["sweep"])
    start = -math.pi / 2 - sweep * 0.62
    pts = lib.arc(0.05, 0.12, p["radius"], start, start + sweep, 96)
    width = lambda s: p["width"] * np.clip(s / 0.72, 0, 1) ** 0.9 * (1 - lib.smooth(0.72, 1.0, s)) ** 0.6 + 1e-3
    d, s, across = lib.stroke(u, v, pts, width)
    s = np.clip(s, 0, 1)
    noise = lib.fbm(u.shape, 6, 4, seed=_seed(rng))
    body = lib.aa(d, size)
    edge = lib.smooth(0.35, 0.9, -across) * body
    def frame(t):
        cut = lib.ease_in(lib.smooth(p["hold"], 1.0, t), p["ease"]) * 1.25 - 0.08
        keep = lib.smooth(cut - 0.02, cut + 0.1, s + (noise - 0.5) * 0.25)
        thin = lib.aa(d + p["width"] * 0.55 * t * (1 - s), size)
        alpha = np.maximum(thin * 0.62, edge * thin) * keep
        return alpha * lib.vignette(u, v, 0.88, 0.98)
    return lib.frames(_frames(p), frame)


@recipe("dust_ring", frames=16, hold=0.2, ease=1.1, start=0.18, reach=0.66, thick=0.2)
def dust_ring(p, rng, size):
    """A ground dust ring seen from above: a lumpy band of warped smoke that rolls
    outward and thins out. A body layer, normal blending."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    seed = _seed(rng)
    lumps = lib.polar_sample(lib.fbm((256, 256), 6, 4, seed=seed), np.full_like(r, 0.5), a)
    puff = lib.fbm(u.shape, 5, 5, seed=seed + 1)
    du, dv = lib.fbm(u.shape, 3, 3, seed=seed + 2), lib.fbm(u.shape, 3, 3, seed=seed + 3)
    def frame(t):
        radius = p["start"] + p["reach"] * lib.ease_out(t, 2.6)
        th = p["thick"] * (0.6 + 0.6 * t)
        w = lib.warp(puff, du, dv, 0.12 + 0.2 * t)
        d = np.abs(r - radius - (lumps - 0.5) * th * 0.9) / th + (w - 0.5) * 0.8
        body = lib.smooth(1.0, 0.7, d)
        shade = 0.5 + 0.5 * lib.smooth(0.3, 0.7, w)
        alpha = lib.erode(body * shade, 0.6 * w + 0.4 * lumps, _amount(t, p), 0.08)
        return alpha * lib.vignette(u, v, 0.88, 0.98)
    return lib.frames(_frames(p), frame)


# ================================================================== spritesheets (variants, not a sequence)


@recipe("rock_chunks", count=16, light=-2.3)
def rock_chunks(p, rng, size):
    """Flat rock chunks to replace plain-block debris: jagged polygons split into
    facets of three alpha values (lit, mid, shade), with a crack cut through some."""
    u, v = lib.grid(size)
    cells = []
    for k in range(int(p["count"])):
        n = int(rng.integers(5, 9))
        base = np.sort(rng.uniform(0, 2 * np.pi, n))
        rad = rng.uniform(0.42, 0.78, n) * rng.uniform(0.85, 1.05)
        squash = rng.uniform(0.6, 1.0)
        pts = [(float(np.cos(t) * q), float(np.sin(t) * q * squash)) for t, q in zip(base, rad)]
        d = lib.polygon(u, v, pts)
        mask = lib.aa(d, size)
        cx, cy = rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15)
        ang = np.arctan2(v - cy, u - cx)
        vert = np.array([math.atan2(y - cy, x - cx) for x, y in pts])
        order = np.argsort(vert)
        sector = np.searchsorted(vert[order], ang) % n
        mid = (vert[order] + np.roll(vert[order], 1)) / 2
        mid[0] += np.pi
        facing = np.cos(mid[sector] - p["light"])
        shade = np.where(facing > 0.35, 1.0, np.where(facing > -0.35, 0.82, 0.64))
        alpha = mask * shade
        if k % 3 != 2:
            j = int(rng.integers(0, n))
            crack, _ = lib.sd_segment(u, v, cx, cy, pts[j][0] * 0.9, pts[j][1] * 0.9)
            alpha *= 1 - lib.aa(crack - 0.012, size)
        cells.append(alpha * lib.vignette(u, v, 0.86, 0.97))
    return cells


@recipe("embers", count=16)
def embers(p, rng, size):
    """Small hot fragments: jagged specks with a white core, some with a short tail or a
    split. Variants so a stream of them never repeats."""
    u, v = lib.grid(size)
    cells = []
    for k in range(int(p["count"])):
        ang = rng.uniform(0, np.pi)
        cu, cv = u * np.cos(ang) + v * np.sin(ang), -u * np.sin(ang) + v * np.cos(ang)
        n = int(rng.integers(4, 7))
        t = np.sort(rng.uniform(0, 2 * np.pi, n))
        rr = rng.uniform(0.12, 0.3, n)
        stretch = rng.uniform(1.0, 2.6)
        pts = [(float(np.cos(a) * q * stretch), float(np.sin(a) * q)) for a, q in zip(t, rr)]
        speck = lib.aa(lib.polygon(cu, cv, pts), size)
        r = np.sqrt(cu * cu / stretch**2 + cv * cv)
        core = np.exp(-((r / 0.09) ** 2))
        halo = 0.28 * np.exp(-((r / 0.38) ** 2))
        alpha = np.maximum(speck * 0.8, core) + halo
        if k % 4 == 1:
            tail = np.exp(-((cv / (0.05 * np.clip(1 + cu, 0.02, 2))) ** 2)) * lib.smooth(-0.85, 0, cu) * (cu < 0) * 0.6
            alpha = np.maximum(alpha, tail)
        if k % 5 == 3:
            off = lib.aa(lib.sd_circle(cu - 0.45, cv + 0.18, rng.uniform(0.04, 0.07)), size)
            alpha = np.maximum(alpha, off)
        cells.append(np.clip(alpha, 0, 1) * lib.vignette(u, v, 0.8, 0.96))
    return cells


def _bolt_points(rng, a, b, depth, rough):
    pts = [np.array(a, np.float32), np.array(b, np.float32)]
    disp = rough
    for _ in range(depth):
        out = [pts[0]]
        for i in range(len(pts) - 1):
            p0, p1 = pts[i], pts[i + 1]
            m = (p0 + p1) / 2
            dx, dy = p1 - p0
            nrm = np.array([-dy, dx]) / max(1e-6, math.hypot(dx, dy))
            out += [m + nrm * rng.uniform(-disp, disp) * math.hypot(dx, dy), p1]
        pts = out
        disp *= 0.62
    return np.array(pts, np.float32)


@recipe("bolt_variants", count=16, rough=0.55, width=0.03)
def bolt_variants(p, rng, size):
    """Lightning bolts from top to bottom, each with its own path and one or two forks;
    a white core that thins toward the end and a short glow."""
    u, v = lib.grid(size)
    cells = []
    for _ in range(int(p["count"])):
        main = _bolt_points(rng, (rng.uniform(-0.2, 0.2), -0.88), (rng.uniform(-0.35, 0.35), 0.88), 6, p["rough"])
        d, s, _ = lib.stroke(u, v, main, lambda t: p["width"] * (1 - 0.7 * t) + 0.004)
        dist = d + p["width"]
        alpha = np.maximum(lib.aa(d, size), 0.4 * np.exp(-np.clip(dist, 0, None) / 0.05))
        for _ in range(int(rng.integers(1, 3))):
            j = int(rng.integers(len(main) // 5, len(main) * 3 // 5))
            start = main[j]
            ang = rng.choice([-1, 1]) * rng.uniform(0.35, 0.9)
            end = start + np.array([math.sin(ang), math.cos(ang)]) * rng.uniform(0.3, 0.55)
            end = np.clip(end, -0.85, 0.85)
            fork = _bolt_points(rng, start, end, 4, p["rough"])
            fd, _, _ = lib.stroke(u, v, fork, lambda t: p["width"] * 0.55 * (1 - 0.8 * t) + 0.003)
            alpha = np.maximum(alpha, np.maximum(lib.aa(fd, size) * 0.85, 0.25 * np.exp(-np.clip(fd, 0, None) / 0.04)))
        cells.append(np.clip(alpha, 0, 1) * lib.vignette(u, v, 0.9, 0.99))
    return cells


# ================================================================== tiled strips (tile along u; width = 4 x height)


def _strip_grid(size):
    w, h = size, size // 4
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return (x + 0.5) / w, (y + 0.5) / h * 2 - 1, w, h


def _edges(y):
    return 1 - lib.smooth(0.8, 0.97, np.abs(y))


@recipe("energy_streak", core=0.1, body=0.42)
def energy_streak(p, rng, size):
    """A scrolling energy beam: a white core line inside long noisy streaks that pulse
    along the strip, with gaps. Tiles along its length."""
    x, y, w, h = _strip_grid(size)
    seed = _seed(rng)
    streaks = lib.normalize(lib.perlin((h, w), (6, 3), seed) * 0.6 + lib.perlin((h, w), (12, 6), seed + 1) * 0.4)
    pulse = lib.perlin((h, w), (1, 4), seed + 2)
    core = np.exp(-((y / p["core"]) ** 2)) * (0.75 + 0.25 * pulse)
    body = np.exp(-((y / p["body"]) ** 2)) * lib.smooth(0.42, 0.78, streaks * (0.6 + 0.7 * pulse))
    return np.clip(np.maximum(core, body * 0.8), 0, 1) * _edges(y)


@recipe("fire_band", height=1.0)
def fire_band(p, rng, size):
    """A band of flame tongues rising from a base line, for fire beams and trails that
    scroll. Tiles along its length."""
    x, y, w, h = _strip_grid(size)
    seed = _seed(rng)
    up = (0.75 - y) / 1.6
    tongues = lib.noise1(w, 6, seed, 3)[None, :]
    lick = lib.normalize(lib.perlin((h, w), (3, 10), seed + 1) * 0.6 + lib.perlin((h, w), (6, 20), seed + 2) * 0.4)
    top = p["height"] * (0.2 + 0.8 * tongues**1.6)
    level = top * (0.55 + 0.7 * lick) - up
    body = lib.smooth(0.0, 0.08, level) * (y < 0.92)
    core = lib.smooth(0.0, 0.06, level - top * 0.35) * 0.35
    base = 1 - lib.smooth(0.7, 0.95, y)
    return np.clip(body * 0.68 + core, 0, 1) * base * _edges(y)


@recipe("lightning_fringe", points=26, rough=0.55, width=0.035)
def lightning_fringe(p, rng, size):
    """A zig-zag electric line with small forks and a glow fringe, for beams. The path
    closes on itself, so the strip tiles along its length."""
    x, y, w, h = _strip_grid(size)
    n = int(p["points"])
    ys = rng.uniform(-p["rough"], p["rough"], n)
    ys[0] = 0.0
    span = 8.0
    xs = np.linspace(0, span, n, endpoint=False)
    pts = np.stack([np.concatenate([xs - span, xs, xs + span, [2 * span]]), np.concatenate([ys, ys, ys, [ys[0]]])], -1)
    X = x * span
    d, _, _ = lib.stroke(X, y, pts, p["width"])
    alpha = np.maximum(lib.aa(d, h * 1.0, 1.0), 0.45 * np.exp(-np.clip(d, 0, None) / 0.09))
    for k in range(5):
        j = int(rng.integers(1, n - 1))
        start = np.array([xs[j], ys[j]])
        end = start + np.array([rng.uniform(0.25, 0.6), rng.choice([-1, 1]) * rng.uniform(0.3, 0.5)])
        fork = np.stack([np.linspace(start[0], end[0], 4), np.linspace(start[1], end[1], 4) + rng.uniform(-0.08, 0.08, 4) * [0, 1, 1, 0]], -1)
        for shift in (-span, 0, span):
            fd, _, _ = lib.stroke(X, y, fork + [shift, 0], [p["width"] * 0.6, p["width"] * 0.15])
            alpha = np.maximum(alpha, lib.aa(fd, h * 1.0, 1.0) * 0.8)
    return np.clip(alpha, 0, 1) * _edges(y)


@recipe("wind_stroke", count=14)
def wind_stroke(p, rng, size):
    """Thin wind strokes of different lengths, pointed at both ends, for dashes and
    gusts. Each stroke wraps around the strip's ends, so it tiles."""
    x, y, w, h = _strip_grid(size)
    span = 4.0
    X = x * span
    alpha = np.zeros_like(x)
    for _ in range(int(p["count"])):
        cx = rng.uniform(0, span)
        cy = rng.uniform(-0.6, 0.6)
        length = rng.uniform(0.5, 2.2)
        width = rng.uniform(0.025, 0.07)
        gain = rng.uniform(0.45, 1.0)
        for shift in (-span, 0, span):
            nd = lib.needle(X, y, cx - length / 2 + shift, cy, cx + length / 2 + shift, cy - 0.04, width)
            alpha = np.maximum(alpha, lib.aa(nd, h * 1.0, 1.0) * gain)
    return alpha * _edges(y)


# ================================================================== art tier


@recipe("brush_sheet", width=0.1)
def brush_sheet(p, rng, size):
    """Four calligraphic brush strokes (a sweep, an S, a hook and a jab): tapered, with
    a swell, fibrous bristle marks and a dry-brush tail."""
    u, v = lib.grid(size)
    paths = [
        [(-0.84, 0.45), (-0.4, -0.55), (0.35, -0.6), (0.86, 0.1)],
        [(-0.8, -0.55), (0.4, -0.75), (-0.4, 0.7), (0.82, 0.5)],
        [(-0.7, -0.7), (0.3, -0.6), (0.6, 0.2), (0.05, 0.75)],
        [(-0.85, 0.3), (-0.2, 0.05), (0.4, -0.1), (0.88, -0.3)],
    ]
    cells = []
    for k, ctrl in enumerate(paths):
        pts = lib.bezier(ctrl, 90)
        alpha, _, _ = _brush(u, v, size, pts, p["width"] * (1.15 if k == 3 else 1.0), _seed(rng),
                                attack=0.1, release=0.3 if k != 3 else 0.2, swell=0.35, dry=0.4)
        cells.append(alpha * lib.vignette(u, v, 0.9, 0.99))
    return cells


def _line(d, size, w):
    return lib.aa(np.abs(d) - w, size)


def _glyphs(u, v, size, rng, count, r0, r1, w):
    """Rune-like marks around a band: each glyph is two or three strokes picked from a
    3 x 3 grid, placed in polar coordinates."""
    r, a = lib.polar(u, v)
    out = np.zeros_like(u)
    cell = 2 * np.pi / count
    for k in range(count):
        centre = k * cell
        da = (a - centre + np.pi) % (2 * np.pi) - np.pi
        gx = da / cell * 2.2
        gy = (r - (r0 + r1) / 2) / ((r1 - r0) / 2)
        for _ in range(int(rng.integers(2, 4))):
            p0 = rng.integers(0, 3, 2) - 1
            p1 = rng.integers(0, 3, 2) - 1
            if (p0 == p1).all():
                p1 = -p0 if p0.any() else np.array([1, 0])
            d, _ = lib.sd_segment(gx, gy, p0[0] * 0.6, p0[1] * 0.7, p1[0] * 0.6, p1[1] * 0.7)
            out = np.maximum(out, lib.aa(d * (r1 - r0) / 2 - w, size))
    return out


@recipe("sigil_ornate", folds=8, line=0.007)
def sigil_ornate(p, rng, size):
    """An ornate sigil coin: double rim with ticks, lens petals in polar repetition,
    dots, an inner star and a hard centre. Line art in code, the multibrush idea."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    n = int(p["folds"])
    w = p["line"]
    out = np.maximum(_line(r - 0.9, size, w * 1.6), _line(r - 0.84, size, w))
    ticks = np.cos(a * n * 6) > 0.93
    tick_len = np.where(np.cos(a * n * 3) > 0.5, 0.05, 0.028)
    out = np.maximum(out, ticks * (r > 0.84) * (r < 0.84 + tick_len) * 1.0)
    sector = 2 * np.pi / n
    fa = (a + np.pi) % sector - sector / 2
    fu, fv = r * np.cos(fa), r * np.sin(fa)
    c1 = lib.sd_circle(fu - 0.52, fv - 0.17, 0.27)
    c2 = lib.sd_circle(fu - 0.52, fv + 0.17, 0.27)
    lens = np.maximum(c1, c2)
    out = np.maximum(out, np.maximum(_line(lens, size, w), lib.aa(lens, size) * 0.22))
    vein = lib.sd_segment(fu, fv, 0.34, 0, 0.7, 0)[0]
    out = np.maximum(out, lib.aa(vein - w * 0.7, size))
    ga = (a + np.pi + sector / 2) % sector - sector / 2
    gu, gv = r * np.cos(ga), r * np.sin(ga)
    out = np.maximum(out, lib.aa(lib.sd_circle(gu - 0.76, gv, 0.022), size))
    star = lib.sd_star(u, v, n, 0.3, 0.13, phase=np.pi / n)
    out = np.maximum(out, np.maximum(_line(star, size, w), lib.aa(star, size) * 0.3))
    out = np.maximum(out, lib.aa(r - 0.07, size))
    out = np.maximum(out, _line(r - 0.11, size, w * 0.8))
    return out * lib.vignette(u, v, 0.94, 0.995)


@recipe("sigil_runes", glyphs=16, line=0.008)
def sigil_runes(p, rng, size):
    """A magic circle: three rings, a band of rune glyphs, a hexagram and a broken inner
    ring."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    w = p["line"]
    out = np.maximum.reduce([_line(r - 0.92, size, w * 1.5), _line(r - 0.86, size, w), _line(r - 0.62, size, w)])
    out = np.maximum(out, _glyphs(u, v, size, rng, int(p["glyphs"]), 0.66, 0.82, w * 0.9))
    tri = []
    for flip in (0, np.pi):
        pts = [(float(0.6 * np.cos(flip + np.pi / 2 + k * 2 * np.pi / 3)), float(-0.6 * np.sin(flip + np.pi / 2 + k * 2 * np.pi / 3))) for k in range(3)]
        tri.append(_line(lib.polygon(u, v, pts), size, w))
    out = np.maximum(out, np.maximum(*tri))
    dash = (np.cos(a * 12) > -0.3) * _line(r - 0.24, size, w * 1.2)
    out = np.maximum(out, dash)
    out = np.maximum(out, lib.aa(r - 0.05, size))
    return out * lib.vignette(u, v, 0.95, 0.995)


@recipe("petals_cel", outline=0.022)
def petals_cel(p, rng, size):
    """Cel-style petals and shards (2 x 2): a flat fill a step darker than a hard
    outline, with one inner line, the lotus look of reference G."""
    u, v = lib.grid(size)
    o = p["outline"]
    cells = []

    def cel(d, inner, fill=0.48, grad=None):
        fill_a = lib.aa(d, size) * (fill if grad is None else grad)
        edge = _line(d + o, size, o)
        return np.maximum.reduce([fill_a, edge, inner])

    lens = np.maximum(lib.sd_circle(u - 0.38, v + 0.05, 0.62), lib.sd_circle(u + 0.38, v + 0.05, 0.62))
    lens = np.maximum(lens, v - 0.78)
    vein = lib.aa(lib.sd_segment(u, v, 0, 0.55, 0, -0.4)[0] - o * 0.5, size) * 0.85
    cells.append(cel(lens, vein, grad=0.32 + 0.3 * lib.smooth(0.7, -0.6, v)))

    round_ = lib.sd_circle(u, v + 0.05, 0.62)
    notch = lib.sd_circle(u, v + 0.78, 0.18)
    round_ = np.maximum(round_, -notch)
    vein2 = lib.aa(lib.sd_segment(u, v, 0, 0.5, 0, -0.25)[0] - o * 0.5, size) * 0.85
    cells.append(cel(round_, vein2, grad=0.3 + 0.28 * lib.smooth(0.6, -0.5, v)))

    kite = lib.polygon(u, v, [(0, -0.86), (0.26, -0.15), (0, 0.86), (-0.22, -0.05)])
    facet = lib.aa(lib.sd_segment(u, v, 0, -0.8, 0.05, 0.8)[0] - o * 0.4, size)
    half = (u > 0) * lib.aa(kite, size) * 0.2
    cells.append(np.maximum(cel(kite, facet, fill=0.4), half + lib.aa(kite, size) * 0.4))

    cluster = np.zeros_like(u)
    for ang, length, wdt in ((0.0, 0.85, 0.2), (-0.55, 0.62, 0.15), (0.6, 0.55, 0.14)):
        cu, cv = u * np.cos(ang) - v * np.sin(ang), u * np.sin(ang) + v * np.cos(ang)
        sh = lib.polygon(cu, cv + 0.25, [(0, -length), (wdt, -length * 0.35), (0, 0.55), (-wdt, -length * 0.35)])
        line = lib.aa(lib.sd_segment(cu, cv + 0.25, 0, -length * 0.9, 0, 0.45)[0] - o * 0.4, size)
        cluster = np.maximum(cluster, cel(sh, line, fill=0.42))
    cells.append(cluster)
    return [c * lib.vignette(u, v, 0.9, 0.99) for c in cells]


@recipe("fringe_ring", radius=0.68, band=0.07, hue=0.0, span=1.0)
def fringe_ring(p, rng, size):
    """A thin ring with a rainbow fringe baked in: white at its crest, red outside,
    violet inside. The one coloured texture: a world-space chromatic fake (reference E)
    that needs no post effect. `hue` shifts where the spectrum starts."""
    u, v = lib.grid(size)
    r, _ = lib.polar(u, v)
    x = (r - p["radius"]) / p["band"]
    alpha = np.exp(-(x**2) * 1.6) + 0.35 * np.exp(-((x / 2.4) ** 2))
    crest = np.exp(-((x / 0.32) ** 2))
    t = ((0.5 - x * 0.28 * p["span"]) + p["hue"]) % 1.0
    rgb = lib.spectrum(t)
    rgb = rgb * (1 - crest[..., None]) + crest[..., None]
    alpha = np.clip(alpha, 0, 1) * lib.vignette(u, v, 0.9, 0.99)
    return {"alpha": alpha, "rgb": rgb}


@recipe("ground_frost", arms=6, line=0.016)
def ground_frost(p, rng, size):
    """A frost ground sigil, seen from above: a six-arm crystal with branching side
    spurs, a hexagon, a ring of small diamonds and a faint frost bloom."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    n = int(p["arms"])
    w = p["line"]
    sector = 2 * np.pi / n
    fa = (a + sector / 2) % sector - sector / 2
    fu, fv = r * np.cos(fa), np.abs(r * np.sin(fa))
    arm, s, _ = lib.stroke(fu, fv, [(0.08, 0), (0.86, 0)], [w * 1.4, w * 0.3])
    out = lib.aa(arm, size)
    for at, length in ((0.32, 0.2), (0.5, 0.16), (0.66, 0.11)):
        sd, _, _ = lib.stroke(fu, fv, [(at, 0), (at + length * 0.5, length * 0.866)], [w * 0.9, w * 0.2])
        out = np.maximum(out, lib.aa(sd, size))
    hexa = lib.polygon(u, v, [(float(0.28 * np.cos(k * sector)), float(0.28 * np.sin(k * sector))) for k in range(n)])
    out = np.maximum(out, _line(hexa, size, w * 0.6))
    ring = _line(r - 0.93, size, w * 0.5)
    da = (a + sector / 4) % (sector / 2) - sector / 4
    du, dv = r * np.cos(da) - 0.93, r * np.sin(da)
    diamond = lib.aa(np.abs(du) / 0.035 + np.abs(dv) / 0.018 - 1, size, 3.0)
    out = np.maximum.reduce([out, ring, diamond])
    return out * lib.vignette(u, v, 0.95, 0.995)


@recipe("ground_flame", tongues=10, line=0.014)
def ground_flame(p, rng, size):
    """A flame ground sigil: a ring of curved flame tongues licking outward, a rim, an
    inner rune band and a hot centre mark."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    n = int(p["tongues"])
    w = p["line"]
    sector = 2 * np.pi / n
    fa = (a + np.pi) % sector - sector / 2
    bend = (r - 0.55) * 0.9
    fa2 = fa - bend * 0.5
    fu, fv = r * np.cos(fa2), r * np.sin(fa2)
    h = np.clip((fu - 0.55) / 0.38, 0, 1)
    width = 0.11 * (1 - h) ** 0.9 * (fu > 0.5)
    tongue = np.abs(fv) - width
    noise = lib.fbm(u.shape, 6, 4, seed=_seed(rng))
    lick = lib.aa(tongue + (noise - 0.5) * 0.03, size) * (fu < 0.94)
    out = np.maximum(lick * 0.75, _line(tongue, size, w * 0.5) * (fu > 0.5) * (fu < 0.94))
    out = np.maximum(out, _line(r - 0.55, size, w * 1.2))
    out = np.maximum(out, _glyphs(u, v, size, rng, 12, 0.32, 0.48, w * 0.6))
    out = np.maximum(out, _line(r - 0.3, size, w * 0.6))
    star = lib.sd_star(u, v, 5, 0.18, 0.07, phase=-np.pi / 2)
    out = np.maximum(out, lib.aa(star, size))
    return out * lib.vignette(u, v, 0.95, 0.995)


@recipe("ground_storm", arms=3, bolts=6, line=0.013)
def ground_storm(p, rng, size):
    """A storm ground sigil: three tapering spiral arms, zig-zag bolt spokes, a dashed
    outer ring and a ringed eye."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    w = p["line"]
    out = np.zeros_like(u)
    for k in range(int(p["arms"])):
        t = np.linspace(0, 1, 70)
        ang = k * 2 * np.pi / p["arms"] + t * 3.3
        rad = 0.14 + 0.76 * t
        pts = np.stack([rad * np.cos(ang), rad * np.sin(ang)], -1)
        d, _, _ = lib.stroke(u, v, pts, lambda s: w * (2.6 * (1 - s) + 0.3))
        out = np.maximum(out, lib.aa(d, size))
    for k in range(int(p["bolts"])):
        ang = (k + 0.5) * 2 * np.pi / p["bolts"]
        dirv = np.array([math.cos(ang), math.sin(ang)])
        bolt = _bolt_points(rng, dirv * 0.2, dirv * 0.82, 4, 0.35)
        d, _, _ = lib.stroke(u, v, bolt, lambda s: w * (1.1 - 0.8 * s))
        out = np.maximum(out, lib.aa(d, size) * 0.9)
    dash = (np.cos(a * 18) > -0.2) * _line(r - 0.92, size, w * 0.9)
    out = np.maximum.reduce([out, dash, _line(r - 0.12, size, w * 0.7), lib.aa(r - 0.05, size)])
    return out * lib.vignette(u, v, 0.95, 0.995)


@recipe("floor_streaks", count=72, width=0.006)
def floor_streaks(p, rng, size):
    """Radial streaks scored into the floor around an impact: uneven, tapered lines
    starting a little away from the centre, so the crater reads."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    out = np.zeros_like(u)
    for _ in range(int(p["count"])):
        ang = rng.uniform(0, 2 * np.pi)
        r0 = rng.uniform(0.1, 0.32)
        r1 = r0 + rng.uniform(0.2, 0.62)
        r1 = min(r1, 0.95)
        width = p["width"] * rng.uniform(0.6, 2.2)
        gain = rng.uniform(0.4, 1.0)
        da = (a - ang + np.pi) % (2 * np.pi) - np.pi
        t = np.clip((r - r0) / (r1 - r0), 0, 1)
        w = width * (1 - t) ** 0.8 * lib.smooth(0, 0.08, t)
        line = lib.aa(np.abs(da * r) - w, size) * (r > r0) * (r < r1)
        out = np.maximum(out, line * gain * (1 - 0.5 * t))
    return out * lib.vignette(u, v, 0.94, 0.995)


@recipe("dark_halo", inner=0.2, peak=0.34, outer=0.92)
def dark_halo(p, rng, size):
    """A wide soft ring with a defined inner edge, to sit behind a flare as negative
    space. Tinted black, normal blending."""
    u, v = lib.grid(size)
    r, _ = lib.polar(u, v)
    rise = lib.smooth(p["inner"], p["peak"], r)
    fall = (1 - lib.smooth(p["peak"], p["outer"], r)) ** 1.6
    return rise * fall * 0.9 * lib.vignette(u, v, 0.9, 0.99)


# ================================================================== source maps (not uploaded)


@recipe("src_fbm", period=4, octaves=6)
def src_fbm(p, rng, size):
    return lib.fbm((size, size), int(p["period"]), int(p["octaves"]), seed=_seed(rng))


@recipe("src_ridged", period=4, octaves=5)
def src_ridged(p, rng, size):
    return lib.ridged((size, size), int(p["period"]), int(p["octaves"]), seed=_seed(rng))


@recipe("src_worley", cells=8)
def src_worley(p, rng, size):
    return lib.worley((size, size), int(p["cells"]), seed=_seed(rng), second=True)
