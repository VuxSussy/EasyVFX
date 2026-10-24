"""The recipes behind library v4. A recipe draws one texture from its knobs:

    fn(p, rng, size) -> alpha (h, w), or a list of frames, or {"alpha": ..., "rgb": ...}

`p` holds the recipe's knobs (its defaults, then the bank entry's params, then any
--set), `rng` is a numpy Generator seeded from the entry's seed, and `size` is the
output's width in pixels (a frame's width for flipbooks and sheets). Coordinates come
from lib.grid: u and v run -1..1 across a square texture, v pointing down.

Every texture is white with its shape in alpha (the pack convention); only a recipe
whose bank entry says `"rgb": "spectrum"`, `"luma"` or `"ramp"` may return colour. `ramp` bakes
a palette in (stylized fire: a cream core, an orange body, a red rim), tinted white in Roblox.
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


def _brush(u, v, size, pts, width, seed, attack=0.06, release=0.3, swell=0.25, dry=0.45, rough=0.025, density=0.45, caps=False):
    """A calligraphic stroke: pressure along the path, a rough edge, bristle streaks that
    open into dry-brush gaps toward the tail, and ink density from the bristles."""
    d, s, across = lib.stroke(u, v, pts, lambda t: width * lib.taper(t, attack, release, swell, 1.4) * (1.15 - 0.3 * t) + 1e-3, caps=caps)
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
        trail = np.exp(-np.clip(radius - r, 0, None) / (th * 0.6)) * lead
        edge = lib.aa(np.abs(r - radius + th * 0.18) - th * 0.12, size)
        ring = np.maximum(trail * 0.45, edge)
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


# ================================================================== sequences (frames as separate images, for meshes)


@recipe("slash_ribbon", frames=16, hold=0.1, ease=1.4, edge=0.16, alpha="soft", fibres=10)
def slash_ribbon(p, rng, size):
    """A slash laid along a crescent shell: u runs from the tail (left) to the tip, v from
    the inner edge (top) to the outer one (bottom). A white-hot outer edge over a fibrous
    body; it erodes from the tail toward the tip and thins from the inside. Frames are
    separate images because a mesh can't play an atlas (reference H).

    alpha="soft" (the default) keeps the detail in alpha. alpha="solid" keeps alpha a
    crisp silhouette and puts the fibres in the RGB as grey (bank entry "rgb": "luma").
    In Studio both read the same; the halftone seen there was aliasing from an
    EditableImage without mipmaps, not the alpha (docs/meshgen.md). fibres sets how many
    fibres run across the ribbon; fewer alias less on a far shell."""
    w, h = size, size // 4
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    x, y = (xx + 0.5) / w, (yy + 0.5) / h
    seed = _seed(rng)
    n = int(p["fibres"])  # fibres across the ribbon; fewer alias less when the shell is far away
    streaks = lib.normalize(lib.perlin((h, w), (n, 3), seed) * 0.6 + lib.perlin((h, w), (n * 2, 6), seed + 1) * 0.4)
    noise = lib.fbm((h, w), 4, 4, seed=seed + 2)
    edge = lib.smooth(1 - p["edge"], 1 - p["edge"] * 0.3, y)
    body = 0.45 + 0.4 * lib.smooth(0.35, 0.75, streaks) * lib.smooth(0.0, 0.5, y)
    base = np.maximum(edge, body * lib.smooth(0.0, 0.25, y))

    solid = p["alpha"] == "solid"
    aa = 1.5 / h  # about a pixel and a half across the ribbon

    def frame(t):
        cut = lib.ease_in(lib.smooth(p["hold"], 1.0, t), p["ease"]) * 1.25 - 0.1
        along = x + (noise - 0.5) * 0.25
        across = y + (streaks - 0.5) * 0.2
        if not solid:
            keep = lib.smooth(cut - 0.02, cut + 0.1, along)
            thin = lib.smooth(t * 0.9 - 0.05, t * 0.9 + 0.1, across)
            return base * keep * np.maximum(thin, edge * (t < 0.85))
        keep = lib.smooth(cut, cut + aa * 2, along)
        thin = lib.smooth(t * 0.9, t * 0.9 + aa * 2, across)
        inner = lib.smooth(0.06, 0.06 + aa * 2, y)
        alpha = inner * keep * np.maximum(thin, edge * (t < 0.85))
        grey = np.clip(np.maximum(edge, 0.5 + 0.5 * (body - 0.45) / 0.4), 0, 1)
        return {"alpha": alpha, "rgb": np.repeat(grey[..., None], 3, axis=2)}
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


# ================================================================== Bloom Strike set (docs/refs/lotus-layers.md)


@recipe("star8", long=0.95, short=0.55, width=0.05, core=0.06)
def star8(p, rng, size):
    """An 8-point star: four long spikes, four shorter diagonals, a hot core. The flare
    of a heavy hit (Lotus beat E)."""
    u, v = lib.grid(size)
    r = np.sqrt(u * u + v * v)

    def spike(ang, length, width):
        along = u * math.cos(ang) + v * math.sin(ang)
        across = -u * math.sin(ang) + v * math.cos(ang)
        t = np.clip(np.abs(along) / length, 0, 1)
        w = width * (1 - t) ** 1.25 + 1e-4
        return np.exp(-((across / w) ** 2)) * (1 - t) ** 1.6

    out = np.zeros_like(u)
    for k in range(2):
        out = np.maximum(out, spike(k * math.pi / 2, p["long"], p["width"]))
        out = np.maximum(out, spike(math.pi / 4 + k * math.pi / 2, p["short"], p["width"] * 0.75) * 0.85)
    core = np.exp(-((r / p["core"]) ** 2)) + 0.35 * np.exp(-((r / (p["core"] * 3)) ** 2))
    return np.clip(out + core, 0, 1) * lib.vignette(u, v, 0.9, 0.99)


@recipe("hollow_ring", radius=0.6, line=0.07, glow=0.25)
def hollow_ring(p, rng, size):
    """A small hollow ring with a soft glow: orbit rings that scatter around a sigil."""
    u, v = lib.grid(size)
    r = np.sqrt(u * u + v * v)
    d = np.abs(r - p["radius"])
    ring = lib.aa(d - p["line"] * 0.5, size, 1.5)
    glow = p["glow"] * np.exp(-((d / (p["line"] * 2.5)) ** 2))
    return np.clip(ring + glow, 0, 1) * lib.vignette(u, v, 0.85, 0.97)


@recipe("bokeh", rim=0.15)
def bokeh(p, rng, size):
    """A soft out-of-focus disc with a faint brighter rim: depth haze behind a sigil."""
    u, v = lib.grid(size)
    r = np.sqrt(u * u + v * v)
    disc = 1 - lib.smooth(0.55, 0.8, r)
    rim = p["rim"] * np.exp(-(((r - 0.65) / 0.08) ** 2))
    return np.clip(disc * 0.55 + rim, 0, 1) * lib.vignette(u, v, 0.85, 0.97)


@recipe("flower_sigil", petals=8, length=0.88, width=0.13, line=0.012)
def flower_sigil(p, rng, size):
    """A flower sigil of thin petal strokes: each petal a pointed lens drawn as a bright
    outline over a faint fill, radiating from a small core (Lotus beat G)."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    n = int(p["petals"])
    out = np.zeros_like(u)
    for k in range(n):
        ang = k * 2 * math.pi / n + rng.uniform(-0.06, 0.06)
        length = p["length"] * rng.uniform(0.85, 1.0)
        along = u * math.cos(ang) + v * math.sin(ang)
        across = -u * math.sin(ang) + v * math.cos(ang)
        t = np.clip(along / length, 0, 1)
        half = p["width"] * np.clip(np.sin(np.pi * t), 0, 1) ** 0.8 * (along > 0)
        d = np.abs(across) - half
        edge = lib.aa(np.abs(d) - p["line"], size) * (along > 0) * (along < length)
        fill = lib.aa(d, size) * 0.18
        spine = lib.aa(np.abs(across) - p["line"] * 0.5, size) * (along > 0) * (1 - t) * 0.7
        out = np.maximum.reduce([out, edge, fill, spine])
    core = np.exp(-((r / 0.06) ** 2))
    return np.clip(np.maximum(out, core), 0, 1) * lib.vignette(u, v, 0.92, 0.99)


@recipe("brush_ring", radius=0.7, width=0.07, gap=0.7)
def brush_ring(p, rng, size):
    """A calligraphic ring: one brush stroke drawn around a circle, thick in the middle,
    tapering at both ends with a dry, fibrous tail. Gold rings and ground swirls (beats
    H and J)."""
    u, v = lib.grid(size)
    start = rng.uniform(0, 2 * math.pi)
    sweep = 2 * math.pi * (1 - (1 - p["gap"]) * 0.25)
    pts = lib.arc(0, 0, p["radius"], start, start + sweep, 160)
    # round caps: a near-closed ring has no free ends for the square cut to work on
    alpha, _, _ = _brush(u, v, size, pts, p["width"], _seed(rng), attack=0.08, release=0.55, swell=0.3, dry=0.6, density=0.3, caps=True)
    return alpha * lib.vignette(u, v, 0.9, 0.99)


@recipe("petal_single", outline=0.03)
def petal_single(p, rng, size):
    """One cel petal for the lotus mesh: a flat fill a step darker than a hard outline,
    with a centre vein. The tip is at the top of the image, the base at the bottom."""
    u, v = lib.grid(size)
    o = p["outline"]
    lens = np.maximum(lib.sd_circle(u - 0.55, v + 0.0, 0.78), lib.sd_circle(u + 0.55, v + 0.0, 0.78))
    lens = np.maximum(lens, np.abs(v) - 0.93)
    fill = lib.aa(lens, size) * (0.45 + 0.25 * lib.smooth(0.9, -0.6, v))
    edge = lib.aa(np.abs(lens + o) - o, size)
    vein = lib.aa(lib.sd_segment(u, v, 0, 0.85, 0, -0.55)[0] - o * 0.4, size) * 0.7
    return np.clip(np.maximum.reduce([fill, edge, vein]), 0, 1) * lib.vignette(u, v, 0.94, 0.995)


@recipe("pillar_streaks", streaks=26)
def pillar_streaks(p, rng, size):
    """Vertical light streaks for a pillar shell: u runs around the cylinder (so it tiles),
    v up its height; streaks of uneven brightness, bright at the base, fading to the top."""
    x, y, w, h = _strip_grid(size)
    seed = _seed(rng)
    cols = lib.noise1(w, int(p["streaks"]), seed, 2)[None, :]
    fine = lib.noise1(w, int(p["streaks"]) * 3, seed + 1, 1)[None, :]
    streak = lib.smooth(0.35, 0.75, cols * 0.7 + fine * 0.3)
    # bright on the top row, which a cylinder shell maps to its base (its v starts at the
    # bottom and the image's top row is v = 0), fading toward the pillar's top
    fade = lib.smooth(0.0, 0.9, 1 - (y + 1) / 2) ** 1.3
    return np.clip(streak * fade * 0.9 + 0.12 * fade, 0, 1) * (1 - lib.smooth(1 - 10.0 / h, 1 - 4.5 / h, np.abs(y)))


@recipe("grass", count=16)
def grass(p, rng, size):
    """Grass blade clumps, one variant per frame: thin curved tapering blades from a
    common base. Tinted dark green with normal blending, they are the dark accent near the
    ground (Lotus beat I)."""
    u, v = lib.grid(size)
    cells = []
    for _ in range(int(p["count"])):
        alpha = np.zeros_like(u)
        for _ in range(int(rng.integers(3, 7))):
            base = np.array([rng.uniform(-0.25, 0.25), 0.9])
            lean = rng.uniform(-0.55, 0.55)
            height = rng.uniform(0.9, 1.65)
            tip = base + np.array([lean, -height])
            mid = (base + tip) / 2 + np.array([lean * 0.4, 0.0])
            pts = lib.bezier([base, mid, tip], 24)
            d, _, _ = lib.stroke(u, v, pts, lambda s: 0.045 * (1 - s) ** 0.8 + 0.004, caps=False)
            alpha = np.maximum(alpha, lib.aa(d, size))
        cells.append(alpha * lib.vignette(u, v, 0.9, 0.99))
    return cells


@recipe("dome_glow", grain=0.15)
def dome_glow(p, rng, size):
    """A glow for a dome shell: u runs around the dome (so it tiles), v from its top (top
    row) to its rim; nearly solid at the top, fading toward the rim, with a faint grain."""
    x, y, w, h = _strip_grid(size)
    seed = _seed(rng)
    down = (y + 1) / 2
    grain = lib.normalize(lib.perlin((h, w), (4, 8), seed))
    body = (1 - lib.smooth(0.55, 1.0, down)) * (1 - p["grain"] + p["grain"] * grain)
    return np.clip(body, 0, 1) * (1 - lib.smooth(1 - 10.0 / h, 1 - 4.5 / h, np.abs(y)))


# ================================================================== the beam showcase set
# Shapes read off a paid plugin's palette in Twist VFX's beam tutorial (docs/refs/
# twist-beam.md); drawn from scratch here, nothing of theirs is used.


@recipe("impact_spikes", spikes=30, inner=0.3, reach=0.96, width=0.09)
def impact_spikes(p, rng, size):
    """A radial spike burst around a hollow centre: tapered spikes of uneven length and
    width, a thin inner ring. The frame-one shape of a hard impact."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    n = int(p["spikes"])
    angles, _ = lib.rng_angles(_seed(rng), n, 0.45)
    lengths = rng.uniform(0.45, 1.0, n) * (p["reach"] - p["inner"])
    widths = rng.uniform(0.5, 1.2, n) * p["width"]
    alpha = np.zeros_like(u)
    for ang, ln, wd in zip(angles, lengths, widths):
        da = np.angle(np.exp(1j * (a - ang)))
        t = np.clip((r - p["inner"]) / max(ln, 1e-3), 0, 1)
        half = wd * (1 - t) ** 1.4 / np.maximum(r, 0.05)
        spike = (np.abs(da) < half) * (r > p["inner"]) * (t < 1)
        alpha = np.maximum(alpha, spike * (1 - 0.35 * t))
    ring = np.exp(-((r - p["inner"]) / 0.012) ** 2) * 0.8
    return np.clip(np.maximum(alpha, ring), 0, 1) * lib.vignette(u, v, 0.92, 0.99)


@recipe("vortex_ring", arms=6, radius=0.6, width=0.2, twist=2.4)
def vortex_ring(p, rng, size):
    """A swirling vortex ring: arms that spiral in toward the centre, brightest on the
    ring and streaky along the swirl. Spun with RotSpeed, it reads as a suction or charge."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    phase = a * p["arms"] + p["twist"] * np.log(np.maximum(r, 1e-3)) * p["arms"]
    arms = (0.5 + 0.5 * np.cos(phase)) ** 3
    band = np.exp(-(((r - p["radius"]) / p["width"]) ** 2))
    grain = lib.normalize(lib.perlin(u.shape, (24, 3), _seed(rng)))
    return np.clip(arms * band * (0.6 + 0.4 * grain) * 1.3, 0, 1) * lib.vignette(u, v, 0.9, 0.99)


@recipe("saw_ring", teeth=18, radius=0.62, depth=0.22, line=0.03)
def saw_ring(p, rng, size):
    """A ring of shards pointing outward (a sharp circle impact): a thin band whose outer
    edge is saw-toothed, teeth of uneven height, with a soft glow inside."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    n = int(p["teeth"])
    k = (a / (2 * np.pi) * n) % 1.0
    idx = np.floor((a % (2 * np.pi)) / (2 * np.pi) * n).astype(int) % n
    heights = rng.uniform(0.45, 1.0, n)[idx]
    outer = p["radius"] + p["depth"] * heights * (1 - np.abs(k * 2 - 1)) ** 1.6
    inner = p["radius"] - p["line"]
    band = lib.aa(np.maximum(inner - r, r - outer), size)
    glow = 0.35 * np.exp(-(((r - p["radius"] + 0.08) / 0.12) ** 2))
    return np.clip(np.maximum(band, glow), 0, 1) * lib.vignette(u, v, 0.92, 0.99)


@recipe("comic_burst", points=13, outer=0.92, inner=0.55, outline=0.035)
def comic_burst(p, rng, size):
    """A comic-book starburst splat: jagged points of uneven reach, solid inside, with a
    separate outline just outside it. The cel 'POW' of a cartoon hit."""
    u, v = lib.grid(size)
    n = int(p["points"]) * 2
    angles, _ = lib.rng_angles(_seed(rng), n, 0.25)
    radii = [rng.uniform(0.82, 1.0) * p["outer"] if i % 2 == 0 else rng.uniform(0.85, 1.1) * p["inner"] for i in range(n)]
    pts = [(float(np.cos(t) * q), float(np.sin(t) * q)) for t, q in zip(np.sort(angles), radii)]
    d = lib.polygon(u, v, pts)
    fill = lib.aa(d + p["outline"] * 1.6, size)
    line = lib.aa(np.abs(d) - p["outline"] * 0.5, size)
    return np.clip(np.maximum(fill * 0.9, line), 0, 1) * lib.vignette(u, v, 0.94, 0.995)


@recipe("halftone_disc", cells=24, radius=0.92, power=1.3)
def halftone_disc(p, rng, size):
    """A halftone glow: a grid of dots whose size follows a radial falloff, the printed
    anime look of a soft glow without a gradient."""
    u, v = lib.grid(size)
    n = int(p["cells"])
    gu, gv = (u + 1) / 2 * n, (v + 1) / 2 * n
    cu, cv = (np.floor(gu) + 0.5) / n * 2 - 1, (np.floor(gv) + 0.5) / n * 2 - 1
    level = np.clip(1 - np.sqrt(cu * cu + cv * cv) / p["radius"], 0, 1) ** p["power"]
    du, dv = (gu % 1) - 0.5, (gv % 1) - 0.5
    d = np.sqrt(du * du + dv * dv) - 0.52 * np.sqrt(level)
    return np.clip(0.5 - d * n / 1.2, 0, 1) * (level > 0.02)


@recipe("star_set", count=16)
def star_set(p, rng, size):
    """Star and sparkle variants, one per frame: long thin 4-points, fat 4-points, 6- and
    8-points, an outlined 5-point, tiny twinkles with a halo."""
    u, v = lib.grid(size)
    r, _ = lib.polar(u, v)
    cells = []
    for k in range(int(p["count"])):
        kind = k % 6
        phase = rng.uniform(0, np.pi / 4) if kind in (2, 3) else 0.0
        if kind == 0:
            d = lib.sd_star(u, v, 4, 0.95, 0.035, phase)
        elif kind == 1:
            d = lib.sd_star(u, v, 4, 0.8, 0.16, phase)
        elif kind == 2:
            d = lib.sd_star(u, v, 6, 0.85, 0.12, phase)
        elif kind == 3:
            d = np.minimum(lib.sd_star(u, v, 4, 0.92, 0.05), lib.sd_star(u, v, 4, 0.55, 0.05, np.pi / 4))
        elif kind == 4:
            d = np.abs(lib.sd_star(u, v, 5, 0.8, 0.36, -np.pi / 2)) - 0.03
        else:
            d = lib.sd_star(u, v, 4, 0.5, 0.025, phase)
        shape = lib.aa(d, size)
        halo = np.exp(-((r / (0.18 if kind == 5 else 0.28)) ** 2)) * (0.7 if kind == 5 else 0.45)
        cells.append(np.clip(np.maximum(shape, halo), 0, 1) * lib.vignette(u, v, 0.9, 0.99))
    return cells


@recipe("comb_fringe", teeth=46, reach=0.85)
def comb_fringe(p, rng, size):
    """A hanging comb of streaks from the top edge, of uneven length with soft tips (an
    icicle or energy drip). Tiles along its length; as a beam's edge it frays the beam."""
    x, y, w, h = _strip_grid(size)
    down = (y + 1) / 2
    n = int(p["teeth"])
    lengths = lib.noise1(w, n // 4, _seed(rng)) * 0.6 + 0.25
    cols = lib.normalize(lib.perlin((h, w), (1, n), _seed(rng))) ** 1.6
    reach = np.clip(lengths[None, :] * p["reach"] + 0.15 * cols, 0.05, 1)
    body = (1 - lib.smooth(reach * 0.55, reach, down)) * (0.35 + 0.65 * cols)
    root = np.exp(-(((down - 0.09) / 0.05) ** 2))
    body = body * lib.smooth(0.04, 0.09, down)
    return np.clip(np.maximum(body, root), 0, 1) * (1 - lib.smooth(1 - 10.0 / h, 1 - 4.5 / h, np.abs(y)))


@recipe("helix_strands", strands=3, turns=3, amp=0.55, width=0.07)
def helix_strands(p, rng, size):
    """Strands that twist around a beam: sine strands out of phase, thicker and brighter
    where they swing toward the camera. Tiles along its length; scroll it for a spiral."""
    x, y, w, h = _strip_grid(size)
    alpha = np.zeros_like(x)
    n = int(p["strands"])
    for k in range(n):
        ph = 2 * np.pi * (x * p["turns"] + k / n)
        centre = p["amp"] * np.sin(ph)
        near = 0.5 + 0.5 * np.cos(ph)
        wd = p["width"] * (0.55 + 0.75 * near)
        alpha = np.maximum(alpha, np.exp(-(((y - centre) / wd) ** 2)) * (0.45 + 0.55 * near))
    return np.clip(alpha, 0, 1) * _edges(y)


@recipe("pulse_bars", bars=10, width=0.18, core=0.08)
def pulse_bars(p, rng, size):
    """Bright bars across a beam at a steady beat, with a thin core line through them.
    Scrolled fast along a beam it reads as energy pulsing down it. Tiles along its length."""
    x, y, w, h = _strip_grid(size)
    beat = (x * p["bars"]) % 1.0
    bar = np.exp(-(((beat - 0.5) / (p["width"] / 2)) ** 2))
    across = np.exp(-((y / 0.55) ** 2))
    core = np.exp(-((y / p["core"]) ** 2)) * 0.7
    return np.clip(np.maximum(bar * across, core), 0, 1) * _edges(y)


# ================================================================== stylized fire
# The target mix (docs/refs/dissection-fire-pit.md): chunky flame tongues in a few hard value
# bands, from a fluid sim so they move like fire (tools/texgen/sim.py `flame_loop`, baked into
# pack/sim). The sim gives the motion; the bands give the painted look.

import os as _os

_SIM = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "pack", "sim")
PALETTES = {
    "fire": [(0.80, 0.16, 0.07), (1.0, 0.52, 0.10), (1.0, 0.93, 0.66)],
    "magic": [(0.42, 0.10, 0.80), (0.75, 0.35, 1.0), (0.97, 0.88, 1.0)],
    "frost": [(0.10, 0.35, 0.85), (0.40, 0.75, 1.0), (0.92, 0.98, 1.0)],
    "poison": [(0.20, 0.45, 0.08), (0.50, 0.85, 0.15), (0.92, 1.0, 0.72)],
}


def _sim_frames(name):
    path = _os.path.join(_SIM, name + ".npz")
    if not _os.path.exists(path):
        raise SystemExit(f"texgen: {path} is missing; bake it: .venv-sim/bin/python tools/texgen/sim.py {name} -o {path}")
    z = np.load(path)
    return z["heat"].astype(np.float32) / 255 * float(z["scale"])


def _blur_f(a, r):
    from PIL import Image, ImageFilter

    top = max(1e-6, float(a.max()))
    img = Image.fromarray(np.clip(a / top * 255, 0, 255).astype(np.uint8))
    return np.asarray(img.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255 * top


def _bilinear(a, x, y):
    H, W = a.shape
    x = np.clip(x, 0, W - 1.001)
    y = np.clip(y, 0, H - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (a[y0, x0] * (1 - fx) * (1 - fy) + a[y0, x0 + 1] * fx * (1 - fy)
            + a[y0 + 1, x0] * (1 - fx) * fy + a[y0 + 1, x0 + 1] * fx * fy)


def _flame_fit(heat, size, wide, margin, edge, room):
    """One crop for every frame (so the flame doesn't jump), sat on the cell's bottom margin
    and centred; `wide` > 1 stretches it sideways, `room` leaves space above."""
    lit = heat > edge * 0.8
    rows = np.nonzero(lit.any(axis=(0, 2)))[0]
    cols = np.nonzero(lit.any(axis=(0, 1)))[0]
    hgt = (rows.max() - rows.min()) * (1 + 2 * margin)
    wid = (cols.max() - cols.min()) * (1 + 2 * margin)
    side = max(hgt, wid * wide) * (1 + room)
    cx = (cols.min() + cols.max()) / 2
    y0 = rows.max() + side * margin - side
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    sy = y0 + (yy + 0.5) / size * side
    sx = cx + ((xx + 0.5) / size - 0.5) * side / wide
    return [_bilinear(h, sx, sy) for h in heat]


def _pull_tips(h, length, keep=0.55, every=3):
    """Drags each tongue upward while it narrows a pixel a side every `every` rows, so the
    sim's rounded tops become tapered points."""
    k = int(length * h.shape[0])
    if k < 1:
        return h
    d = keep ** (1 / k)
    out, cur = h.copy(), h
    for i in range(k):
        cur = np.roll(cur, -1, axis=0) * d
        cur[-1] = 0
        if i % every == 0:
            cur = np.minimum(cur, np.minimum(np.roll(cur, 1, axis=1), np.roll(cur, -1, axis=1)))
        out = np.maximum(out, cur)
    return _blur_f(out, 0.8 * h.shape[0] / 256)


def _kink(h, u, v, phase, amp, freq=2.2):
    """Bends the field sideways, more toward the top, with a wave that travels up as the
    loop plays: brush-flick curls in the tongues."""
    up = np.clip((0.85 - v) / 1.7, 0, 1) ** 1.5
    dx = amp * up * (np.sin(2 * np.pi * freq * v + phase * 2) + 0.5 * np.sin(2 * np.pi * freq * 2.3 * v - phase * 3 + 1.3))
    n = h.shape[0]
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    return _bilinear(h, xx + dx * n / 2, yy)


def _band(h, t, px):
    """A hard band edge, anti-aliased over `px` pixels of the field's own slope."""
    gy, gx = np.gradient(h)
    g = np.sqrt(gx * gx + gy * gy) + 1e-5
    return np.clip((h - t) / (g * px) + 0.5, 0, 1)


@recipe("flame_stylized", frames=16, edge=0.12, body=0.24, core=0.42, blur=2.4, palette="fire", margin=0.06, sim="flame_loop",
        wide=1.25, base=0.30, tips=0.16, kink=0.035, core_drop=0.06, ink=0.0)
def flame_stylized(p, rng, size):
    """A looping flame in hard value bands (Phát's picks, 2026-10-24, from the Valorant muzzle
    flashes and the fire pit). A sim's heat (tongues that lick, merge and split) is fit once
    for every frame, softened, then shaped:
      base       a soft mound of heat added at the bottom, so the tongues grow out of a knot
      wide       stretches the flame sideways (it read thin at 1)
      tips       how far each tongue is pulled into a tapered point (cell heights; 0 is off).
                 Per element: fire 0.16; sharper for lightning, softer for water
      kink       a travelling sideways bend, more toward the top: brush-flick curls
      core_drop  sinks the cream core toward the base (cell heights)
      ink        a dark outline this many pixels wide at 256 px a cell (0 is off; 2 is F)
    then cut at three heights into a rim, a body and a core, each a flat colour with a 1 px
    edge. `frames` 16 steps the 64-frame sim on fours (12 a second gives a 1.3 s loop, the
    on-twos look); 64 keeps every frame."""
    heat = _sim_frames(p["sim"])
    step = max(1, heat.shape[0] // int(p["frames"]))
    heat = heat[::step][: int(p["frames"])]
    n = len(heat)
    pal = PALETTES[p["palette"]]
    u, v = lib.grid(size)
    px = size / 256
    out = []
    for j, h in enumerate(_flame_fit(heat, size, p["wide"], p["margin"], p["edge"], 0.04)):
        h = _blur_f(h, p["blur"] * size / 192)
        phase = 2 * np.pi * j / n
        if p["base"] > 0:
            breathe = 1 + 0.05 * np.sin(phase)
            h = h + p["base"] * np.exp(-1.6 * ((u / (0.40 * breathe)) ** 2 + ((v - 0.74) / 0.20) ** 2))
        # cool toward the top of the cell, so tongues end before the edge
        h = h * lib.smooth(-0.97, -0.45, v)
        h = _pull_tips(h, p["tips"])
        if p["kink"] > 0:
            h = _kink(h, u, v, phase, p["kink"])
        rim, body = _band(h, p["edge"], 1.0), _band(h, p["body"], 1.0)
        s = int(p["core_drop"] * size)
        hc = np.roll(h, s, axis=0)
        hc[:s] = 0
        layers = [(rim, pal[0]), (body, pal[1]), (_band(hc, p["core"], 1.0) * body, pal[2])]
        alpha = rim
        if p["ink"] > 0:
            from PIL import Image, ImageFilter

            r = max(1, int(round(p["ink"] * px))) * 2 + 1
            grown = Image.fromarray((rim * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(r)).filter(ImageFilter.GaussianBlur(0.6 * px))
            alpha = np.maximum(np.asarray(grown, np.float32) / 255, rim)
            ink = tuple(c * 0.28 for c in pal[0])
            layers.insert(0, (alpha, ink))
        rgb = np.zeros((size, size, 3), np.float32)
        for m, c in layers:
            rgb = rgb * (1 - m[..., None]) + np.array(c, np.float32) * m[..., None]
        out.append({"alpha": alpha * lib.vignette(u, v, 0.94, 0.995), "rgb": rgb})
    return out


# ================================================================== ground cracks
# The fire pit's glowing cracks (docs/refs/dissection-fire-pit.md, f12 on): Voronoi cells seen
# from above, small at the centre and growing outward, hot thick lines in the middle thinning
# to red at the rim, some segments broken off, a soft glow around the lines.


def _crack_points(layout, rng, cells):
    """Feature points in -1..1: `radial` rings that grow outward (the fire pit's cells), or a
    jittered `hex` lattice (hexagonal cells)."""
    if layout == "hex":
        step = 2.0 / cells
        pts = []
        for row in range(-cells - 1, cells + 2):
            for col in range(-cells - 1, cells + 2):
                x = (col + 0.5 * (row % 2)) * step
                y = row * step * 0.866
                pts.append((x + rng.normal(0, step * 0.08), y + rng.normal(0, step * 0.08)))
        return np.array(pts, np.float32)
    pts = [(rng.normal(0, 0.02), rng.normal(0, 0.02))]
    radius, count = 0.17, 5
    while radius < 1.35:
        phase = rng.uniform(0, 2 * np.pi)
        for k in range(count):
            a = phase + 2 * np.pi * (k + rng.uniform(-0.3, 0.3)) / count
            r = radius * rng.uniform(0.88, 1.12)
            pts.append((r * np.cos(a), r * np.sin(a)))
        radius *= 1.0 + 3.0 / cells
        count = int(count * 1.25) + 1
    return np.array(pts, np.float32)


def _voronoi_edges(u, v, pts):
    """True distance to the nearest cell edge, and a hash per edge (so whole segments can drop
    out): for the nearest point p1, the closest bisector with any other point."""
    d2 = np.stack([(u - x) ** 2 + (v - y) ** 2 for x, y in pts])
    i1 = np.argmin(d2, axis=0)
    p1 = pts[i1]
    edge = np.full(u.shape, 9.0, np.float32)
    other = np.zeros(u.shape, np.int64)
    for j, (x, y) in enumerate(pts):
        dx, dy = x - p1[..., 0], y - p1[..., 1]
        ln = np.sqrt(dx * dx + dy * dy) + 1e-6
        mx, my = (x + p1[..., 0]) / 2, (y + p1[..., 1]) / 2
        d = ((mx - u) * dx + (my - v) * dy) / ln
        d = np.where(i1 == j, 9.0, d)
        closer = d < edge
        edge = np.where(closer, d, edge)
        other = np.where(closer, j, other)
    lo, hi = np.minimum(i1, other), np.maximum(i1, other)
    key = (lo * 7919 + hi * 104729) % 1000 / 1000.0
    return edge, key.astype(np.float32), i1


@recipe("ground_cracks", layout="radial", cells=5, line=0.024, taper=0.75, drop=0.55, warp=0.035, glow=0.4,
        pool=0.0, reach=0.92, palette="fire", frames=0)
def ground_cracks(p, rng, size):
    """Glowing ground cracks seen from above, for a flat decal (additive):
      layout   `radial` cells that grow outward (the fire pit) or `hex` cells
      cells    how many cells across (more is finer)
      line     the line's half-width at the centre; `taper` thins it toward the rim
      drop     how many edges break off toward the rim (0 keeps every edge)
      warp     how much the lines wobble
      glow     a soft halo around the lines, for the light they cast
      pool     fills the centre cell with a hot glow (0 is off)
      reach    the cracks' radius
      frames   0 is one still texture; 16 spreads the cracks out from the centre, hot at the
               leading edge, then settles
    Each line has two bands across its width, a hot middle and a red edge, and its heat falls
    from the palette's core at the centre to its rim colour at the edge."""
    u, v = lib.grid(size)
    seed = _seed(rng)
    du = (lib.fbm(u.shape, 4, 4, seed=seed) - 0.5) * 2
    dv = (lib.fbm(u.shape, 4, 4, seed=seed + 7) - 0.5) * 2
    wu, wv = u + du * p["warp"], v + dv * p["warp"]
    r = np.sqrt(u * u + v * v)
    pts = _crack_points(p["layout"], rng, int(p["cells"]))
    edge, key, cell = _voronoi_edges(wu, wv, pts)
    t = np.clip(r / p["reach"], 0, 1)
    vary = 0.5 + 1.0 * lib.fbm(u.shape, 6, 3, seed=seed + 3)
    w = p["line"] * (1 - p["taper"] * t) * vary
    px = 2.0 / size
    keep = lib.smooth(-0.08, 0.08, key - p["drop"] * lib.smooth(0.25, 1.0, t))
    # the outer ends thin to points rather than fade
    w = w * (1 - lib.smooth(0.6, 1.0, t))
    fade = 1 - lib.smooth(0.85, 1.0, t)
    line = np.clip((w - edge) / px + 0.5, 0, 1) * keep * fade
    hot = np.clip((w * 0.35 - edge) / px + 0.5, 0, 1) * keep * fade * lib.smooth(0.75, 0.2, t)
    if p["pool"] > 0:
        pool = (cell == 0) * lib.smooth(0.0, 0.05, edge) * p["pool"]
        line, hot = np.maximum(line, pool), np.maximum(hot, pool)
    pal = PALETTES[p["palette"]]
    # additive in game, so the colours sit darker and more saturated than they read
    heat = ((1 - t) ** 1.5)[..., None]
    red, orange, cream = (np.array(c, np.float32) for c in pal)
    body = orange * 0.85 * heat + red * 0.8 * (1 - heat)
    core = cream * heat + orange * (1 - heat)
    lit = np.maximum(line, hot)
    halo = _blur_f(lit, 6 * size / 512) * p["glow"] * 2
    rgb = red * 0.75 * np.ones(u.shape + (3,), np.float32)
    rgb = rgb * (1 - line[..., None]) + body * line[..., None]
    rgb = rgb * (1 - hot[..., None]) + core * hot[..., None]
    vig = lib.vignette(u, v, 0.94, 0.995)
    if int(p["frames"]) <= 0:
        return {"alpha": np.clip(np.maximum(lit, halo), 0, 1) * vig, "rgb": rgb}
    out = []
    n = int(p["frames"])
    for k in range(n):
        s = k / (n - 1)
        front = float(lib.ease_out(min(1.0, s / 0.55), 2.2)) * 1.08
        shown = 1 - lib.smooth(front - 0.06, front, t)
        lead = np.exp(-(((t - front) / 0.08) ** 2)) * (s < 0.6)
        a = np.clip(np.maximum(lit, halo) * shown, 0, 1)
        c = rgb + (np.array(pal[2], np.float32) - rgb) * (lead * lit)[..., None]
        out.append({"alpha": a * vig, "rgb": c})
    return out


# ================================================================== stylized brush flicks
# The Valorant muzzle-flash language (inbox 012): hard-edged painted strokes that taper to
# needle points, bend once like a brush flick, in flat value bands, sometimes with an ink line.
# Not the dry ZZZ brush above: these are clean, for shards, licks, peels and slash accents.

PALETTES["mono"] = [(0.55, 0.55, 0.55), (0.8, 0.8, 0.8), (1.0, 1.0, 1.0)]

_FLICKS = ("flick", "thorn", "comma", "crescent", "lick")


def _flick_path(kind, rng):
    """A stroke's control points in -1..1 (it runs bottom-left to top-right) and its pressure:
    (attack, release, swell, power)."""
    j = lambda s=0.08: rng.uniform(-s, s)
    if kind == "flick":  # a C-curve that whips into a needle
        return [(-0.8 + j(), 0.6 + j()), (-0.2 + j(), 0.5 + j()), (0.35 + j(), 0.05 + j()), (0.75 + j(), -0.8 + j())], (0.12, 0.35, 0.3, 1.6)
    if kind == "thorn":  # almost straight, one kink, needle at both ends
        k = rng.uniform(0.35, 0.6)
        return [(-0.85, 0.75), (-0.85 + 1.7 * k + j(0.15), 0.75 - 1.5 * k + j(0.15)), (0.85, -0.8)], (0.3, 0.55, 0.2, 1.2)
    if kind == "comma":  # a fat head that curls into a thin tail: a peeling flame ribbon
        return [(-0.35 + j(), 0.75 + j()), (0.75 + j(), 0.45 + j()), (0.8 + j(), -0.75 + j()), (-0.4 + j(), -0.8 + j()), (-0.6 + j(), -0.15 + j())], (0.04, 0.2, 0.5, 1.3)
    if kind == "crescent":  # a swoosh, needle at both ends, widest in the middle
        return [(-0.85, 0.35 + j()), (-0.3 + j(), -0.55 + j()), (0.45 + j(), -0.45 + j()), (0.85, 0.3 + j())], (0.45, 0.55, 0.0, 1.4)
    # lick: an S-shaped flame tongue rising to a point
    return [(-0.05 + j(), 0.85), (-0.55 + j(), 0.25 + j()), (0.45 + j(), -0.2 + j()), (0.1 + j(), -0.88)], (0.05, 0.3, 0.45, 1.5)


@recipe("brush_flicks", count=16, width=0.16, core=0.38, offset=0.3, hot=0.7, ink=0.0, palette="mono")
def brush_flicks(p, rng, size):
    """A sheet of hard-edged painted strokes, cycling through five shapes: `flick`, `thorn`,
    `comma`, `crescent` and `lick`. Each tapers to needle points, has a 1 px edge and two
    flat bands: a core band along the spine, shifted `offset` toward the inside of the curve
    (the painted look) and gone by `hot` along the stroke (the head is hot, the tail cools),
    in a body colour.
      width    the widest half-width
      core     the core band's share of the width
      ink      a dark outline this many pixels wide at 256 px a cell (0 is off)
      palette  `mono` (greys, to tint in Roblox) or a fire/magic/frost/poison ramp"""
    u, v = lib.grid(size)
    pal = PALETTES[p["palette"]]
    px = 2.0 / size
    cells = []
    for k in range(int(p["count"])):
        kind = _FLICKS[k % len(_FLICKS)]
        ctrl, (attack, release, swell, power) = _flick_path(kind, rng)
        pts = lib.bezier(ctrl, 120)
        w = p["width"] * rng.uniform(0.7, 1.15) * (0.6 if kind == "thorn" else 1.0)
        # round caps: the fat end is rounded, the tapered end still comes to a point
        d, s, across = lib.stroke(u, v, pts, lambda t: w * lib.taper(t, attack, release, swell, power) + 1e-4)
        body = np.clip(-d / px + 0.5, 0, 1)
        if kind == "thorn":
            # two short barbs off the spine, swept toward the tip, like the thorn vines
            for at in rng.choice(np.arange(0.25, 0.75, 0.05), 2, replace=False):
                i = int(at * (len(pts) - 1))
                tx, ty = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
                tl = math.hypot(tx, ty) + 1e-6
                nx, ny = -ty / tl * rng.choice([-1, 1]), tx / tl
                length = rng.uniform(0.18, 0.3)
                tip = (pts[i][0] + (nx * 0.8 + tx / tl * 0.6) * length, pts[i][1] + (ny * 0.8 + ty / tl * 0.6) * length)
                bd, _, _ = lib.stroke(u, v, [tuple(pts[i]), tip], [w * 0.55, 1e-4])
                body = np.maximum(body, np.clip(-bd / px + 0.5, 0, 1))
        # which side is the inside of the curve: the side the control polygon bends toward
        mid = np.mean(np.asarray(ctrl, np.float32), axis=0)
        a, b = np.asarray(ctrl[0], np.float32), np.asarray(ctrl[-1], np.float32)
        side = 1.0 if (b[0] - a[0]) * (mid[1] - a[1]) - (b[1] - a[1]) * (mid[0] - a[0]) > 0 else -1.0
        band = np.abs(across - side * p["offset"]) - p["core"]
        width_px = np.maximum(-d, 0) / np.maximum(1 - np.abs(across), 1e-3)
        core = np.clip(-band * width_px / px + 0.5, 0, 1) * body * (1 - lib.smooth(p["hot"] - 0.15, p["hot"], s))
        layers = [(body, pal[1]), (core, pal[2])]
        alpha = body
        if p["ink"] > 0:
            from PIL import Image, ImageFilter

            r = max(1, int(round(p["ink"] * size / 256))) * 2 + 1
            grown = Image.fromarray((body * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(r)).filter(ImageFilter.GaussianBlur(0.6 * size / 256))
            alpha = np.maximum(np.asarray(grown, np.float32) / 255, body)
            layers.insert(0, (alpha, tuple(c * 0.28 for c in pal[0])))
        rgb = np.zeros((size, size, 3), np.float32)
        for m, c in layers:
            rgb = rgb * (1 - m[..., None]) + np.array(c, np.float32) * m[..., None]
        cells.append({"alpha": alpha * lib.vignette(u, v, 0.92, 0.99), "rgb": rgb})
    return cells


# ================================================================== stylized smoke
# The fire pit's smoke, painted: a cartoon puff of round lobes, cel-shaded in two hard tones,
# that swells, drifts and then breaks up through large holes. Every noise field is fixed for the
# whole flipbook and only thresholds move, so frames never jump (the flickering CC0 smoke).


@recipe("smoke_cel", frames=16, lobes=8, grow=0.45, drift=0.2, light=135, shadow=0.68, split=0.04, hold=0.35,
        ease=1.4, ink=0.0)
def smoke_cel(p, rng, size):
    """A cel-shaded smoke puff for a normal-blend layer, in greys to tint (a dark tint gives
    the fire pit's dark smoke, a pale one a dust puff).
      lobes    how many round lobes make the puff
      grow     how much the lobes swell over the life; `drift` how far they spread apart
      light    where the light comes from, degrees (135 is top-left)
      shadow   the shadow tone (1 is the lit tone)
      split    where the lit tone gives way to shadow (0 is half lit; higher is more shadow)
      hold     the share of the life before the puff starts to break up; `ease` its pace
      ink      a dark outline this many pixels wide at 256 px a cell (0 is off)
    Each lobe is a dome; the puff's height is the highest dome, its normal lights it, and the
    light is cut into two flat tones with a 1 px edge. The break-up erodes through a fixed
    field of big blobs from the outside in, so it opens holes and thins rather than flickers."""
    u, v = lib.grid(size)
    seed = _seed(rng)
    n = int(p["lobes"])
    # a small middle lobe and a ring of lobes around it, so the outline stays bumpy
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False) + rng.uniform(-0.3, 0.3, n) + rng.uniform(0, 2 * np.pi)
    rad = rng.uniform(0.14, 0.26, n)
    rad[0] = 0.0
    base = np.stack([rad * np.cos(ang), rad * np.sin(ang) * 0.8 - 0.04], -1)
    radii = rng.uniform(0.12, 0.19, n)
    radii[0] = 0.2
    wob_u = (lib.fbm(u.shape, 4, 3, seed=seed) - 0.5) * 0.05
    wob_v = (lib.fbm(u.shape, 4, 3, seed=seed + 1) - 0.5) * 0.05
    blobs = lib.fbm(u.shape, 3, 3, seed=seed + 2)
    la = np.radians(p["light"])
    lx, ly, lz = np.cos(la) * 0.7, -np.sin(la) * 0.7, 0.71
    px = 2.0 / size
    frames = []
    count = _frames(p)
    for k in range(count):
        t = k / max(1, count - 1)
        g = float(lib.ease_out(t, 2.5))
        scale = 0.62 + p["grow"] * g
        centres = base * (1 + p["drift"] / 0.28 * g) + np.array([0, -0.08 * g])
        height = np.full(u.shape, -1.0, np.float32)
        for (cx, cy), r0 in zip(centres, radii):
            r = r0 * scale
            q = ((u + wob_u - cx) ** 2 + (v + wob_v - cy) ** 2) / (r * r)
            height = np.maximum(height, np.sqrt(np.clip(1 - q, 0, 1)) * r - np.clip(q - 1, 0, None) * r)
        body = np.clip(height / px + 0.5, 0, 1)
        gy, gx = np.gradient(np.maximum(height, 0), px)
        norm = np.sqrt(gx * gx + gy * gy + 1)
        lit = (-gx * lx - gy * ly + lz) / norm
        tone = np.clip((lit - 0.5 - p["split"]) / 0.03 + 0.5, 0, 1)
        shade = p["shadow"] + (1 - p["shadow"]) * tone
        # break up: from `hold`, big holes open from the outside in
        amount = float(lib.ease_in(max(0.0, (t - p["hold"]) / (1 - p["hold"])), p["ease"]))
        r_all = np.sqrt(u * u + (v + 0.05) ** 2) / (0.75 * scale + 1e-3)
        field = 0.6 * blobs + 0.4 * (1 - np.clip(r_all, 0, 1))
        # the field runs about 0.3 at the rim to 1 in the middle: start biting at the rim
        keep = np.clip((field - (0.3 + 0.72 * amount)) / 0.02 + 0.5, 0, 1) if amount > 0 else 1.0
        alpha = body * keep
        rgb = np.repeat(shade[..., None], 3, -1).astype(np.float32)
        if p["ink"] > 0:
            from PIL import Image, ImageFilter

            rr = max(1, int(round(p["ink"] * size / 256))) * 2 + 1
            grown = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(rr)), np.float32) / 255
            rgb = rgb * alpha[..., None] + 0.12 * (1 - alpha[..., None])
            alpha = np.maximum(grown, alpha)
        if k == count - 1:
            alpha = alpha * 0
        frames.append({"alpha": alpha * lib.vignette(u, v, 0.9, 0.98), "rgb": rgb})
    return frames


# ================================================================== stylized smoke
# The fire pit's smoke, painted: a cartoon puff of round lobes, cel-shaded in two hard tones,
# that swells, drifts and then breaks up through large holes. Every noise field is fixed for the
# whole flipbook and only thresholds move, so frames never jump (the flickering CC0 smoke).


@recipe("smoke_cel", frames=16, lobes=8, grow=0.45, drift=0.2, light=135, shadow=0.68, split=0.04, hold=0.35,
        ease=1.4, ink=0.0)
def smoke_cel(p, rng, size):
    """A cel-shaded smoke puff for a normal-blend layer, in greys to tint (a dark tint gives
    the fire pit's dark smoke, a pale one a dust puff).
      lobes    how many round lobes make the puff
      grow     how much the lobes swell over the life; `drift` how far they spread apart
      light    where the light comes from, degrees (135 is top-left)
      shadow   the shadow tone (1 is the lit tone)
      split    where the lit tone gives way to shadow (0 is half lit; higher is more shadow)
      hold     the share of the life before the puff starts to break up; `ease` its pace
      ink      a dark outline this many pixels wide at 256 px a cell (0 is off)
    Each lobe is a dome; the puff's height is the highest dome, its normal lights it, and the
    light is cut into two flat tones with a 1 px edge. The break-up erodes through a fixed
    field of big blobs from the outside in, so it opens holes and thins rather than flickers."""
    u, v = lib.grid(size)
    seed = _seed(rng)
    n = int(p["lobes"])
    # a small middle lobe and a ring of lobes around it, so the outline stays bumpy
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False) + rng.uniform(-0.3, 0.3, n) + rng.uniform(0, 2 * np.pi)
    rad = rng.uniform(0.14, 0.26, n)
    rad[0] = 0.0
    base = np.stack([rad * np.cos(ang), rad * np.sin(ang) * 0.8 - 0.04], -1)
    radii = rng.uniform(0.12, 0.19, n)
    radii[0] = 0.2
    wob_u = (lib.fbm(u.shape, 4, 3, seed=seed) - 0.5) * 0.05
    wob_v = (lib.fbm(u.shape, 4, 3, seed=seed + 1) - 0.5) * 0.05
    blobs = lib.fbm(u.shape, 3, 3, seed=seed + 2)
    la = np.radians(p["light"])
    lx, ly, lz = np.cos(la) * 0.7, -np.sin(la) * 0.7, 0.71
    px = 2.0 / size
    frames = []
    count = _frames(p)
    for k in range(count):
        t = k / max(1, count - 1)
        g = float(lib.ease_out(t, 2.5))
        scale = 0.62 + p["grow"] * g
        centres = base * (1 + p["drift"] / 0.28 * g) + np.array([0, -0.08 * g])
        height = np.full(u.shape, -1.0, np.float32)
        for (cx, cy), r0 in zip(centres, radii):
            r = r0 * scale
            q = ((u + wob_u - cx) ** 2 + (v + wob_v - cy) ** 2) / (r * r)
            height = np.maximum(height, np.sqrt(np.clip(1 - q, 0, 1)) * r - np.clip(q - 1, 0, None) * r)
        body = np.clip(height / px + 0.5, 0, 1)
        gy, gx = np.gradient(np.maximum(height, 0), px)
        norm = np.sqrt(gx * gx + gy * gy + 1)
        lit = (-gx * lx - gy * ly + lz) / norm
        tone = np.clip((lit - 0.5 - p["split"]) / 0.03 + 0.5, 0, 1)
        shade = p["shadow"] + (1 - p["shadow"]) * tone
        # break up: from `hold`, big holes open from the outside in
        amount = float(lib.ease_in(max(0.0, (t - p["hold"]) / (1 - p["hold"])), p["ease"]))
        r_all = np.sqrt(u * u + (v + 0.05) ** 2) / (0.75 * scale + 1e-3)
        field = 0.6 * blobs + 0.4 * (1 - np.clip(r_all, 0, 1))
        # the field runs about 0.3 at the rim to 1 in the middle: start biting at the rim
        keep = np.clip((field - (0.3 + 0.72 * amount)) / 0.02 + 0.5, 0, 1) if amount > 0 else 1.0
        alpha = body * keep
        rgb = np.repeat(shade[..., None], 3, -1).astype(np.float32)
        if p["ink"] > 0:
            from PIL import Image, ImageFilter

            rr = max(1, int(round(p["ink"] * size / 256))) * 2 + 1
            grown = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(rr)), np.float32) / 255
            rgb = rgb * alpha[..., None] + 0.12 * (1 - alpha[..., None])
            alpha = np.maximum(grown, alpha)
        if k == count - 1:
            alpha = alpha * 0
        frames.append({"alpha": alpha * lib.vignette(u, v, 0.9, 0.98), "rgb": rgb})
    return frames


# ================================================================== jagged beam heads
# Phát, 2026-10-24: a beam's taper and its slowing belong to the Beam's properties (Width0,
# Width1, Transparency, the curve), not the texture. So this is a band of even width, and only
# its head is shaped: a jagged blade like a chainsaw's, as in the Valorant muzzle streaks.


def _saw_profile(at, period, depth, rng, slant):
    """Teeth along `at` (pixels): each tooth ramps up over its period and drops sharply
    (`slant` 1 points them one way, -1 the other, 0 makes them even triangles); every tooth
    has its own depth."""
    k = np.floor(at / period).astype(int)
    f = at / period - k
    if slant > 0:
        tooth = f
    elif slant < 0:
        tooth = 1 - f
    else:
        tooth = 1 - np.abs(2 * f - 1)
    sizes = rng.uniform(0.45, 1.0, 512)
    return tooth * depth * sizes[k % 512]


@recipe("beam_saw", tip_teeth=5, tip_depth=0.5, side_teeth=0, side_depth=0.13, head=0.35, slant=1, width=0.72,
        core=0.45, ink=0.0, palette="mono")
def beam_saw(p, rng, size):
    """A beam texture of even width whose head (the strip's right end, U = 1) is a jagged blade:
      tip_teeth   pointed teeth across the end (0 cuts it straight); `tip_depth` how deep they
                  bite, as a share of the strip's height
      side_teeth  sawteeth along both edges over the head, like a chainsaw (0 is off);
                  `side_depth` their bite, `head` the share of the length they cover, `slant`
                  which way they lean (1, -1, or 0 for even triangles)
      width       the band's half-height; `core` the core band's share, inset along the same
                  outline so it follows the teeth
      ink         a dark outline this many pixels wide (0 is off)
    The tail (U = 0) is cut straight: fade it with the Beam's Transparency."""
    x, y, w, h = _strip_grid(size)
    X, Y = x * w, y * h / 2
    H0 = p["width"] * h / 2
    end = w - 6.0
    dist = []
    # the tip: a jagged end, teeth of uneven length
    if int(p["tip_teeth"]) > 0:
        n = int(p["tip_teeth"])
        ys = np.linspace(-H0, H0, 2 * n + 1)
        ys[1:-1] += rng.uniform(-0.25, 0.25, 2 * n - 1) * (2 * H0 / (2 * n))
        bite = p["tip_depth"] * h
        xs = np.where(np.arange(2 * n + 1) % 2 == 1, end - rng.uniform(0.0, 0.35, 2 * n + 1) * bite, end - bite)
        tip_x = np.interp(Y, ys, xs)
    else:
        tip_x = np.full_like(Y, end)
    # the edges: sawteeth over the head
    half = np.full_like(X, H0)
    if int(p["side_teeth"]) > 0:
        span = p["head"] * w
        period = span / int(p["side_teeth"])
        # the teeth grow from nothing where the head starts to full bite at the tip
        inhead = np.clip((X - (end - span)) / span, 0, 1) ** 0.8
        top = _saw_profile(end - X, period, p["side_depth"] * h, rng, p["slant"])
        bottom = _saw_profile(end - X + period * 0.5, period, p["side_depth"] * h, rng, p["slant"])
        half = np.where(Y < 0, H0 - top * inhead, H0 - bottom * inhead)
    d = np.maximum(np.abs(Y) - half, X - tip_x)
    d = np.maximum(d, 2.0 - X)
    body = np.clip(-d + 0.5, 0, 1)
    core = np.clip(-(d + (1 - p["core"]) * H0) + 0.5, 0, 1)
    pal = PALETTES[p["palette"]]
    layers = [(body, pal[1]), (core, pal[2])]
    alpha = body
    if p["ink"] > 0:
        from PIL import Image, ImageFilter

        r = max(1, int(round(p["ink"]))) * 2 + 1
        grown = np.asarray(Image.fromarray((body * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(r)).filter(ImageFilter.GaussianBlur(0.6)), np.float32) / 255
        alpha = np.maximum(grown * (X > 1.0), body)
        layers.insert(0, (alpha, tuple(c * 0.28 for c in pal[0])))
    rgb = np.zeros((h, w, 3), np.float32)
    for m, c in layers:
        rgb = rgb * (1 - m[..., None]) + np.array(c, np.float32) * m[..., None]
    return {"alpha": alpha, "rgb": rgb}


# ================================================================== hooked beam streaks
# Phát's beam reference, 2026-10-24 (a hand-painted streak texture, reference only): bands of
# uneven width that run along the beam with wavy edges, and curled hook teeth along the edges
# like a chainsaw's, each a rounded lobe on a narrow neck that curls back, with a soft halo.
# The beam's taper and slowing belong to its properties (Width0, Width1, Transparency,
# TextureSpeed), not the texture, so the bands keep their width and the strip tiles.


def _wave(x, w, rng, amp, terms=3):
    """A smooth wobble that tiles over w pixels."""
    out = np.zeros_like(x)
    for m in range(1, terms + 1):
        out += rng.uniform(0.4, 1.0) / m * np.sin(2 * np.pi * m * x / w + rng.uniform(0, 2 * np.pi))
    return out * amp


@recipe("beam_hooks", bands=1, width=0.27, wobble=0.035, hooks=2, hook=0.17, long=2.2, halo=12)
def beam_hooks(p, rng, size):
    """One streak along a beam (Phát: one per texture, not three in one), tiling along its
    length (U), for TextureSpeed to scroll. The streak is the clear gap between dark bands
    (the white of the reference), centred, and the bands' hooks bite into its edges:
      bands   dark bands (1, wrapping across the top and bottom); `width` its half-height (share of the
              strip's height), `wobble` how far its centre and edges wander
      hooks   hook teeth per edge along the strip; `hook` how far they reach in (share of the
              height), `long` how much longer than that they run along the edge
      halo    a soft falloff into the streak around each hook, pixels
    Each hook is a lobe pushed out from the edge on a narrow neck, with a bite taken out of
    one side so it curls back toward its band, as a brush flick would leave it."""
    W, H = size, size // 4
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    shape = np.zeros((H, W), np.float32)
    hooks_only = np.zeros((H, W), np.float32)
    n = int(p["bands"])
    span = H
    for b in range(n):
        # the band sits on the strip's top and bottom edge, wrapping, so the clear streak
        # between bands (the beam) is centred and nothing is cut where it crosses the edge
        centre = span * b / n + _wave(x, W, rng, p["wobble"] * H)
        half = p["width"] * H * rng.uniform(0.9, 1.1) * (1 + _wave(x, W, rng, 0.12))
        dy = ((y - centre + H / 2) % H) - H / 2
        d = np.abs(dy) - half  # signed distance to the band, pixels
        teeth = np.full((H, W), 1e6, np.float32)
        r = p["hook"] * H
        count = int(p["hooks"])
        start = rng.uniform(0, W)
        # a hook reaches about its own size out: keep the streak open between the two edges
        clear = H - 2 * p["width"] * H * 1.1
        for side in (-1.0, 1.0):
            # the bottom edge's hooks sit halfway between the top edge's, as in the reference
            offset = 0.0 if side < 0 else 0.5
            xs = (np.arange(count) + offset + rng.uniform(-0.15, 0.15, count)) * W / count + start
            for x0 in xs:
                rr = min(r * rng.uniform(0.8, 1.2), clear * 0.62)
                curl = rng.choice([-1.0, 1.0])
                a = ((x - x0 + W / 2) % W) - W / 2  # along the edge, wrapped so it tiles
                o = (dy - side * half) * side  # outward from the edge
                # a lobe long along the edge, sunk into it, joined with a fillet
                ln = rr * p["long"]
                lobe = ((a / ln) ** 2 + ((o - rr * 0.42) / (rr * 0.58)) ** 2 - 1) * rr * 0.55
                k = rr * 0.35
                h = np.clip(0.5 + 0.5 * (d - lobe) / k, 0, 1)
                d = d * (1 - h) + lobe * h - k * h * (1 - h)
                # a thin slit under one end frees it from the band, so that end curls back
                slit = (1 - ((a - curl * ln * 0.75) / (ln * 0.4)) ** 2 - ((o - rr * 0.02) / (rr * 0.09)) ** 2) * rr * 0.09
                d = np.maximum(d, slit)
                teeth = np.minimum(teeth, lobe)
        shape = np.maximum(shape, np.clip(-d + 0.5, 0, 1))
        hooks_only = np.maximum(hooks_only, np.clip(-teeth + 0.5, 0, 1) * np.clip(-d + 0.5, 0, 1))
    shape = np.maximum(shape, hooks_only)
    def blur_wrap(a, r):
        # blurs across the strip's left and right ends too, so it still tiles
        pad = int(r * 4) + 2
        return _blur_f(np.pad(a, ((0, 0), (pad, pad)), mode="wrap"), r)[:, pad:-pad]

    halo = blur_wrap(hooks_only, p["halo"] * size / 1024) * 0.9
    edge = blur_wrap(shape, 1.5 * size / 1024)
    solid = np.maximum(np.maximum(shape, edge), halo)
    # the beam is the gap, not the band (Phát): the clear streak, bitten by the hooks
    alpha = 1 - solid
    fade = 1 - lib.smooth(0.9, 0.99, np.abs(y / H * 2 - 1))
    return alpha * fade
