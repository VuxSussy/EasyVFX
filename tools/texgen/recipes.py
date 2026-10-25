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


@recipe("soft_glow", falloff=2.6)
def soft_glow(p, rng, size):
    """A plain soft disc of light, no core and no rim: a contact glow where a flame meets
    the floor, a halo behind a hot shape. Lying flat, it stays soft from any angle."""
    u, v = lib.grid(size)
    r = np.sqrt(u * u + v * v)
    # a round fade to nothing before the edge: a square border fade showed as a square pool
    return np.exp(-p["falloff"] * r * r * 2.2) * (1 - lib.smooth(0.55, 0.97, r))


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


@recipe("streak_ring", radius=0.6, band=0.05, glow=0.6, out=0.3, into=0.12, streaks=40, rag=0.5,
        sharp=2.0, fur=0.6, tail=1.2, rays=0, ray_from=0.0, ray_len=0.9, ray_width=0.05, ray_gain=1.0,
        ray_jitter=0.0, core=0.0, core_size=0.12, bend=0.0, kink=0.0, kink_at=0.6, taper=0.0, cut=0.0, gain=1.0, half=0,
        palette="", body=0.35, hot=0.7, ray_vary=0.0, ray_fade=0.0, smudge=0.0)
def streak_ring(p, rng, size):
    """A soft ring of radial streaks, the family of glow rings and starbursts in VFX texture packs:
    ragged fur rings, hollow halos with rays, starbursts and needle stars.

    The streaks are noise around the circle stretched along the radius: `streaks` of them around,
    `sharp` turns soft fur (1) into separate needles (4+), `fur` lets them wave along their length.
    Each reaches `out` past the ring and `into` inside it, `rag` of that length varying around the
    circle, and fades with power `tail`. `radius` 0 with no band makes a starburst from the middle.
    Fangs: `bend` curves each streak sideways more and more toward its tip, `kink` steps it
    sideways at radius `kink_at` (an inner spike and an outer one, offset: a zigzag), and `taper`
    thins it toward the tip; the side each streak goes is slow noise around the circle, so
    neighbours lean together. `cut` above 0 cuts the soft streaks into solid cel shards at that
    brightness, so the fang shapes read with hard edges. `band` and `glow` add a plain soft ring under the streaks. `rays` adds that many long tapered
    needles from `ray_from` to `ray_len` (a star or a needle ring); `ray_vary` gives each ray its
    own length and width (0 all alike, 1 from a third to full), `ray_fade` fades each toward its tip
    instead of ending it full, and `smudge` blurs the result (a share of the texture), so the rays
    read as soot streaks rather than petals. `core` a glow in the middle.
    `gain` scales the whole thing up before it is clipped, so soft rays read solid. `half` 1
    keeps only the top half, for a sprite whose middle sits on the floor. `palette` (with a
    bank entry's "rgb": "ramp") colours it in flat bands by brightness: the rim colour below
    `body`, the body colour up to `hot`, the core colour above."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    seed = _seed(rng)
    n = max(2, int(p["streaks"]))
    def around(period, k, ang):
        return np.clip((lib.polar_sample(lib.perlin((8, 2048), (1, period), seed + k), r * 0, ang) - 0.5) * 2.6 + 0.5, 0, 1)
    d = r - p["radius"]
    # the fang warp: turn the angle the streaks are read at, by radius, each side chosen slowly
    t_out = np.clip(d / max(p["out"], 1e-3), 0, 1)
    side = 2 * around(max(3, n // 4), 9, a) - 1
    aw = a + p["bend"] * side * t_out ** 2 + p["kink"] * side * lib.smooth(p["kink_at"] - 0.03, p["kink_at"] + 0.03, r)
    # three octaves around the circle, so broad streaks carry finer strands
    fine = sum(w * lib.perlin((64, 2048), (2, n * o), seed + o) for o, w in ((1, 0.55), (2, 0.3), (4, 0.15)))
    f = np.clip((lib.polar_sample(fine, r, aw, radial_scale=p["fur"]) - 0.5) * 2.6 + 0.5, 0, 1)
    f = f ** (p["sharp"] * (1 + p["taper"] * t_out))
    # each streak's own length, over a slower ragged swell around the circle: feathered tips
    reach = 1 - p["rag"] + p["rag"] * (0.5 * around(max(3, n // 5), 7, aw) + 0.5 * around(n, 8, aw))
    far = np.clip(1 - d / np.maximum(p["out"] * reach, 1e-3), 0, 1)
    near = np.clip(1 + d / np.maximum(p["into"] * reach, 1e-3), 0, 1)
    streak = f * np.where(d >= 0, far, near) ** p["tail"]
    ring = p["glow"] * np.exp(-((d / max(p["band"], 1e-3)) ** 2)) * (0.7 + 0.3 * f)
    out = 1 - (1 - streak) * (1 - ring)
    k = int(p["rays"])
    if k:
        angles, _ = lib.rng_angles(seed + 2, k, p["ray_jitter"])
        span = max(p["ray_len"] - p["ray_from"], 1e-3)
        t = (r - p["ray_from"]) / span
        inside = (t >= 0) & (t <= 1)
        w = p["ray_width"] * np.maximum(np.sin(np.pi * np.clip(t, 0, 1)), 0) ** 0.8 + 1e-4
        own = np.random.default_rng(seed + 3)
        for ang in angles:
            da = (a - ang + np.pi) % (2 * np.pi) - np.pi
            if p["ray_vary"] or p["ray_fade"]:
                reach = 1 - p["ray_vary"] * own.uniform(0, 0.67)
                ti = t / reach
                wi = p["ray_width"] * (1 + p["ray_vary"] * own.uniform(-0.4, 0.4))
                wi = wi * np.maximum(np.sin(np.pi * np.clip(ti, 0, 1)), 0) ** 0.8 + 1e-4
                ray = np.exp(-((da * r / wi) ** 2)) * ((ti >= 0) & (ti <= 1)) * p["ray_gain"]
                ray = ray * (1 - p["ray_fade"] * np.clip(ti, 0, 1))
            else:
                ray = np.exp(-((da * r / w) ** 2)) * inside * p["ray_gain"]
            out = np.maximum(out, ray)
    if p["core"]:
        out = 1 - (1 - out) * (1 - p["core"] * np.exp(-((r / p["core_size"]) ** 2)))
    if p["smudge"] > 0:
        out = _blur_f(out, p["smudge"] * size)
    out = np.clip(out * p["gain"], 0, 1) * lib.vignette(u, v, 0.88, 0.99)
    if p["cut"]:
        # solid inside, the brightness bands kept for the colours
        out = np.clip((out - p["cut"]) / (3 * 2.0 / size) + 0.5, 0, 1) * (0.55 + 0.45 * out)
    if p["half"]:
        out = out * (1 - lib.smooth(-0.01, 0.01, v))
    if not p["palette"]:
        return out
    pal = PALETTES[p["palette"]]
    px = 2.0 / size
    rgb = np.zeros(out.shape + (3,), np.float32) + np.array(pal[0], np.float32)
    for edge, c in ((p["body"], pal[1]), (p["hot"], pal[2])):
        m = np.clip((out - edge) / (4 * px) + 0.5, 0, 1)[..., None]
        rgb = rgb * (1 - m) + np.array(c, np.float32) * m
    return {"alpha": out, "rgb": rgb}


def _polar_voronoi(r, a, n, m, inner, span, rng, jitter=1.0, wobble=0.0, turn=0.0):
    """Voronoi cells laid around the circle: `n` around and `m` out from `inner` over `span`, so
    a cell stretches along the radius. Returns the distances to the nearest three points (cell
    units) and to the fourth, the nearest cell's random pick and gain, a pick shared by the
    three nearest cells (the same all around the corner where they meet), and the pick of the
    next corner along the border (the first two cells with the fourth)."""
    x = ((a / (2 * np.pi) + turn) % 1.0) * n
    y = (r - inner) / span * m
    if wobble:
        x = x + wobble * (lib.polar_sample(lib.perlin((64, 1024), (3, n), _seed(rng)), r, a) - 0.5)
    pts = 0.5 + (rng.random((m + 2, n, 2)) - 0.5) * jitter
    pick = rng.random((m + 2, n))
    gain = rng.uniform(0.75, 1.0, (m + 2, n))
    f1 = np.full(r.shape, 9.0, np.float32)
    f2 = np.full(r.shape, 9.0, np.float32)
    f3 = np.full(r.shape, 9.0, np.float32)
    f4 = np.full(r.shape, 9.0, np.float32)
    lit = np.zeros(r.shape, np.float32)
    k2 = np.zeros(r.shape, np.float32)
    k3 = np.zeros(r.shape, np.float32)
    k4 = np.zeros(r.shape, np.float32)
    g = np.zeros(r.shape, np.float32)
    cy, cx = np.floor(y).astype(int), np.floor(x).astype(int)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            gy, gx = cy + dy, cx + dx
            row, col = np.clip(gy + 1, 0, m + 1), gx % n
            q = pts[row, col]
            d = np.sqrt((gy + q[..., 0] - y) ** 2 + (gx + q[..., 1] - x) ** 2).astype(np.float32)
            c1, c2, c3 = d < f1, d < f2, d < f3
            f4 = np.where(c3, f3, np.minimum(f4, d))
            pk = pick[row, col]
            c4 = d < f4
            k4 = np.where(c3, k3, np.where(c4, pk, k4))
            k3 = np.where(c2, k2, np.where(c3, pk, k3))
            k2 = np.where(c1, lit, np.where(c2, pk, k2))
            f3 = np.where(c2, f2, np.minimum(f3, d))
            f2 = np.where(c1, f1, np.where(c2, d, f2))
            lit = np.where(c1, pk, lit)
            g = np.where(c1, gain[row, col], g)
            f1 = np.where(c1, d, f1)
    return f1, f2, f3, f4, lit, g, (lit + k2 + k3) % 1.0, (lit + k2 + k4) % 1.0


def _ramp(alpha, heat, pal, body, hot, px):
    """Flat fire bands by `heat` (0 at a shape's edge, 1 deep inside): rim, body, hot core."""
    rgb = np.zeros(alpha.shape + (3,), np.float32) + np.array(pal[0], np.float32)
    for e, c in ((body, pal[1]), (hot, pal[2])):
        mk = np.clip((heat - e) / (2 * px) + 0.5, 0, 1)[..., None]
        rgb = rgb * (1 - mk) + np.array(c, np.float32) * mk
    return rgb


@recipe("voronoi_shards", cells=16, rows=2, inner=0.3, outer=0.95, fill=0.6, edge=0.12, point=0.5,
        jitter=1.0, wobble=0.0, half=0, palette="", body=0.3, hot=0.65)
def voronoi_shards(p, rng, size):
    """A ring of flame shards cut from Voronoi cells laid out around the circle: `cells` around
    and `rows` out from `inner` to `outer`, so each cell is stretched along the radius. A cell's
    shard is the part farther than `edge` from its borders (the second-nearest point minus the
    nearest), which leaves faceted, pointed shapes; the cut rises by `point` toward the outer edge
    so the shards taper to tips. Neighbouring rows' cells sit offset, so an inner shard and the
    outer one past it are displaced like fangs. `fill` of the cells are lit; `jitter` scatters the
    points in their cells; `wobble` bends the borders with noise. `half` 1 keeps the top half;
    `palette` (with "rgb": "ramp") bands it by depth into the shard: rim, body, hot core."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    m = max(1, int(p["rows"]))
    span = max(p["outer"] - p["inner"], 1e-3)
    f1, f2, _, _, lit, g, _, _ = _polar_voronoi(r, a, max(3, int(p["cells"])), m, p["inner"], span, rng, p["jitter"], p["wobble"])
    depth = f2 - f1
    t = np.clip((r - p["inner"]) / span, 0, 1)
    cut = p["edge"] + p["point"] * t ** 1.5
    px = 2.0 / size * m / span
    inside = (r > p["inner"]) & (r < p["outer"]) & (lit < p["fill"])
    alpha = np.clip((depth - cut) / (2 * px) + 0.5, 0, 1) * inside * g
    alpha = alpha * lib.vignette(u, v, 0.9, 0.99)
    if p["half"]:
        alpha = alpha * (1 - lib.smooth(-0.01, 0.01, v))
    if not p["palette"]:
        return alpha
    heat = np.clip((depth - cut) / np.maximum(0.5 - cut, 1e-3), 0, 1)
    return {"alpha": alpha, "rgb": _ramp(alpha, heat, PALETTES[p["palette"]], p["body"], p["hot"], px)}


@recipe("voronoi_fangs", cells=24, rows=2, inner=0.3, outer=0.95, width=0.14, reach=0.35, curve=1.6,
        fill=0.7, layers=2, jitter=1.0, wobble=0.0, half=0, palette="", body=0.35, hot=0.7)
def voronoi_fangs(p, rng, size):
    """Fang shards from the negative of a Voronoi pattern laid around the circle (the borders,
    not the cells): near each corner where three cells meet, the borders are thickened into
    prongs that thin away from the corner, so each corner becomes a forked, concave-sided fang
    like the fire pit's shards. `width` is a prong's width at its corner, `reach` how far along
    the border it runs before closing to a point (in cell units), `curve` how fast it thins
    (above 1 hollows its sides). `fill` of the corners are lit, each whole (picked by the three
    cells that meet there). `layers` passes at offset scales and turns are laid over each other for an uneven ring.
    Cells are `cells` around and `rows` out from `inner` to `outer`, so the prongs run outward.
    `half` 1 keeps the top half; `palette` (with "rgb": "ramp") bands each prong from its rim in."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    span = max(p["outer"] - p["inner"], 1e-3)
    alpha = np.zeros(r.shape, np.float32)
    heat = np.zeros(r.shape, np.float32)
    m0 = max(1, int(p["rows"]))
    for k in range(max(1, int(p["layers"]))):
        scale = 1.0 + 0.35 * k
        n, m = max(3, int(round(p["cells"] * scale))), max(1, int(round(m0 * scale)))
        f1, f2, f3, f4, _, _, lit, nxt = _polar_voronoi(r, a, n, m, p["inner"], span, rng, p["jitter"], p["wobble"], turn=0.37 * k)
        border = f2 - f1
        # how close to a corner: the third point is as near as the first two there
        corner = np.clip((f3 - f1) / max(p["reach"], 1e-3), 0, 1)
        # and close to a point where the next corner takes over (the fourth point as near as the
        # third) when that corner is unlit, so a prong never ends cut off; when it is lit the two
        # prongs run on into each other
        close = np.where(nxt < p["fill"], 1.0, lib.smooth(0.0, 0.1, f4 - f3))
        # and thin to nothing toward the inner and outer edges, so no prong is cut off there
        edge = lib.smooth(p["inner"], p["inner"] + 0.1, r) * (1 - lib.smooth(p["outer"] - 0.15, p["outer"], r))
        w = p["width"] * (1 - corner) ** p["curve"] * close * edge
        px = 2.0 / size * m / span
        # anti-aliased inside the prong only, so a border where the width is zero leaves no hairline
        a_k = np.clip((w - border) / (2 * px), 0, 1) * (lit < p["fill"])
        h_k = np.clip(1 - border / np.maximum(w, 1e-4), 0, 1)
        heat = np.where(a_k > alpha, h_k, heat)
        alpha = np.maximum(alpha, a_k)
    alpha = alpha * lib.vignette(u, v, 0.9, 0.99)
    if p["half"]:
        alpha = alpha * (1 - lib.smooth(-0.01, 0.01, v))
    if not p["palette"]:
        return alpha
    return {"alpha": alpha, "rgb": _ramp(alpha, heat, PALETTES[p["palette"]], p["body"], p["hot"], 2.0 / size)}


@recipe("polar_shards", count=14, start=(0.28, 0.6), length=(0.3, 0.6), width=(0.02, 0.05),
        belly=0.3, sharp=1.8, bend=0.25, fork=0.45, fork_at=(0.3, 0.6), fork_len=(0.4, 0.7),
        fork_turn=(0.5, 1.0), skip=0.15, half=0)
def polar_shards(p, rng, size):
    """Flame shards flung out of a centre, built in polar coordinates: the circle is cut into
    `count` slots by angle (a jittered grid, so they spread evenly but not regularly), and each
    slot may hold one shard (`skip` of them stay empty). A shard is a lens along the radius: it
    starts at a radius in `start`, runs `length`, and is `width` wide at its belly, which sits
    `belly` of the way out, so it swells fast and tapers long to a sharp tip; both ends are
    points, and `sharp` above 1 hollows its sides so it reads as a needle, not a petal. Its spine curves sideways by up to `bend` of its length. With chance `fork`, a second,
    smaller lens branches off it at `fork_at` of its length, turned `fork_turn` radians to one
    side and `fork_len` as long: the Y-shaped shards. All ranges are (low, high), drawn per shard.
    `half` 1 keeps the top half, for a sprite whose middle sits on the floor."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    n = max(1, int(p["count"]))
    out = np.zeros(r.shape, np.float32)
    px = 2.0 / size

    def lens(t, w):
        # zero at both ends, widest at `belly`: the near side swells fast, the far side tapers long
        b = p["belly"]
        tt = np.where(t < b, t / b * 0.5, 0.5 + (t - b) / (1 - b) * 0.5)
        return w * np.maximum(np.sin(np.pi * np.clip(tt, 0, 1)), 0) ** p["sharp"]

    def draw(along, across, length, w):
        t = along / length
        inside = (t > 0) & (t < 1)
        half_w = lens(np.clip(t, 0, 1), w)
        return np.clip((half_w - np.abs(across)) / px + 0.5, 0, 1) * inside * (half_w > 0)

    for k in range(n):
        if rng.random() < p["skip"]:
            continue
        ang = (k + rng.uniform(0.15, 0.85)) / n * 2 * np.pi
        r0 = rng.uniform(*p["start"])
        length = rng.uniform(*p["length"])
        w = rng.uniform(*p["width"])
        bend = rng.uniform(-1, 1) * p["bend"]
        # the shard's own frame: along the ray from r0, across it as an arc length, its spine bent
        da = (a - ang + np.pi) % (2 * np.pi) - np.pi
        along = r - r0
        t = np.clip(along / length, 0, 1)
        across = da * r - bend * length * t ** 2
        out = np.maximum(out, draw(along, across, length, w))
        if rng.random() < p["fork"]:
            tf = rng.uniform(*p["fork_at"])
            side = rng.choice([-1.0, 1.0])
            turn = rng.uniform(*p["fork_turn"]) * side
            # the branch point, in the texture's own coordinates
            rb = r0 + tf * length
            ab = ang + (bend * length * tf ** 2) / max(rb, 1e-3)
            bx, by = rb * np.cos(ab), rb * np.sin(ab)
            dirx, diry = np.cos(ab + turn), np.sin(ab + turn)
            fl = length * rng.uniform(*p["fork_len"])
            fa = (u - bx) * dirx + (v - by) * diry
            fc = -(u - bx) * diry + (v - by) * dirx
            out = np.maximum(out, draw(fa + fl * 0.08, fc, fl, w * 0.8))
    out = out * lib.vignette(u, v, 0.92, 0.99)
    if p["half"]:
        out = out * (1 - lib.smooth(-0.01, 0.01, v))
    return out


@recipe("voronoi_web", cells=10, rows=2, inner=0.15, outer=0.98, width=0.22, taper=1.4, grow=0.08,
        radial=0.0, erode=0.45, erode_scale=3, jitter=1.0, half=0)
def voronoi_web(p, rng, size):
    """The whole border network of a Voronoi pattern laid out in polar coordinates: `cells`
    around and `rows` out from `inner` to `outer`, so every cell is a wedge and its borders run
    out from the centre and branch where three cells meet. A border is kept where it is nearer
    than the local width to both cells (the second-nearest point minus the nearest), which is
    widest at the branch points, so the network is connected, with concave forks. The width
    shrinks along the radius with power `taper`, to nothing at `outer`, so every strand ends in an
    outward tip; it swells in over `grow` past `inner`. `erode` cuts the network into connected
    clusters with low noise around the circle (`erode_scale` blobs around), thinning where the
    noise is low, so some strands break off into tips and others vanish. `radial` (0..1) thins
    the borders that run around the circle rather than out from it, so the strands read as
    flung outward. `half` 1 keeps the top half."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    m = max(1, int(p["rows"]))
    span = max(p["outer"] - p["inner"], 1e-3)
    f1, f2, _, _, _, _, _, _ = _polar_voronoi(r, a, max(3, int(p["cells"])), m, p["inner"], span, rng, p["jitter"])
    border = f2 - f1
    t = np.clip((r - p["inner"]) / span, 0, 1)
    w = p["width"] * (1 - t) ** p["taper"] * lib.smooth(p["inner"], p["inner"] + p["grow"], r)
    if p["radial"]:
        # across a border the distance changes fastest; if that is along the radius, the border
        # runs around the circle
        gy, gx = np.gradient(border)
        along = np.abs(gx * u + gy * v) / np.maximum(r, 1e-4) / np.maximum(np.hypot(gx, gy), 1e-6)
        w = w * (1 - p["radial"] * lib.smooth(0.4, 0.9, along))
    if p["erode"]:
        n = lib.polar_sample(lib.perlin((32, 512), (2, max(1, int(p["erode_scale"]))), _seed(rng)), r, a, radial_scale=0.8)
        keep = np.clip((n - p["erode"]) / max(1 - p["erode"], 1e-3) * 2.5, 0, 1)
        w = w * keep
    px = 2.0 / size * m / span
    out = np.clip((w - border) / (2 * px), 0, 1)
    out = out * lib.vignette(u, v, 0.92, 0.99)
    if p["half"]:
        out = out * (1 - lib.smooth(-0.01, 0.01, v))
    return out


def _thorn(out, u, v, ax, ay, bx, by, width, sharp, px, zoom=1.0):
    """Stamps one thorn into `out` (max): a needle from (ax, ay) to its tip (bx, by), widest a third
    of the way out, its sides hollowed by `sharp`. Only the thorn's own box is touched."""
    pad = width + 2 * px
    x0, x1 = min(ax, bx) - pad, max(ax, bx) + pad
    y0, y1 = min(ay, by) - pad, max(ay, by) + pad
    h, w = out.shape
    c0, c1 = max(0, int((x0 * zoom + 1) / 2 * w)), min(w, int((x1 * zoom + 1) / 2 * w) + 2)
    r0, r1 = max(0, int((y0 * zoom + 1) / 2 * h)), min(h, int((y1 * zoom + 1) / 2 * h) + 2)
    if c0 >= c1 or r0 >= r1:
        return
    uu, vv = u[r0:r1, c0:c1], v[r0:r1, c0:c1]
    d, t = lib.sd_segment(uu, vv, ax, ay, bx, by)
    prof = np.clip(np.where(t < 0.33, t / 0.33, (1 - t) / 0.67), 0, 1) ** sharp
    m = np.clip((width * prof - d) / px, 0, 1)
    out[r0:r1, c0:c1] = np.maximum(out[r0:r1, c0:c1], m)


def _thorn_sdf(field, u, v, ax, ay, bx, by, width, sharp, k, zoom=1.0):
    """Merges one thorn (as `_thorn` draws it) into the signed-distance `field` with a smooth
    minimum of reach `k`: where two thorns come within `k` they melt together with a concave web,
    and everywhere else, tips included, each keeps its own edge."""
    pad = width + k + 0.01
    x0, x1 = min(ax, bx) - pad, max(ax, bx) + pad
    y0, y1 = min(ay, by) - pad, max(ay, by) + pad
    h, w = field.shape
    c0, c1 = max(0, int((x0 * zoom + 1) / 2 * w)), min(w, int((x1 * zoom + 1) / 2 * w) + 2)
    r0, r1 = max(0, int((y0 * zoom + 1) / 2 * h)), min(h, int((y1 * zoom + 1) / 2 * h) + 2)
    if c0 >= c1 or r0 >= r1:
        return
    uu, vv = u[r0:r1, c0:c1], v[r0:r1, c0:c1]
    d, t = lib.sd_segment(uu, vv, ax, ay, bx, by)
    prof = np.clip(np.where(t < 0.33, t / 0.33, (1 - t) / 0.67), 0, 1) ** sharp
    b = d - width * prof
    a = field[r0:r1, c0:c1]
    hh = np.clip(k - np.abs(a - b), 0, None) / k
    field[r0:r1, c0:c1] = np.minimum(a, b) - hh * hh * k * 0.25


@recipe("thorn_burst", ring=0.32, band=0.1, count=36, length=(0.14, 0.32), width=0.03, sharp=1.6,
        turn=0.35, long=0.25, small=2.0, gaps=0.0, gap_scale=5, smear=0.22, steps=24, cut=0.32, core=0.0,
        spin=0.0, merge=0.0, point=0.0, fade=0.0, body=0.0, body_reach=2.5, zoom=1.0, half=0)
def thorn_burst(p, rng, size):
    """A burst of thorns flung out of a ring, built like a Substance Designer graph (VFX_Haku's
    flame shape): an outline (the ring, `band` thick around radius `ring`) where tile samplers
    scatter thorns, three passes at different sizes (`count` mid-size thorns, `long` times as many
    long ones and `small` times as many short ones), each pointing out along the radius give or
    take `turn` radians; `gaps` (0..1) leaves empty stretches around the circle where slow noise
    (`gap_scale` swells around) is low, so the thorns come in clusters; then a slope
    blur along a radial gradient smears them outward over `smear`, which joins neighbours at their
    roots and draws each one out to a tapered tip; then levels cut it to a hard shape at `cut`.
    `merge` is how close two thorns must come to melt into one shape (a smooth union, as a
    fraction of the texture): they join with a webbed, concave crotch and keep their own tapered
    ends, so neighbours fuse into forked spikes; 0 keeps them apart. `point` eats the shape away
    more and more toward the outside (by that much at the longest thorn's reach), so merged clumps
    narrow to points instead of ending round.

    Shading, so the texture is not one flat white: `fade` darkens it along the radius, toward the
    tips (a radial gradient multiplied over it); `body` darkens it toward its edges, so each piece
    is brightest in its middle and glows there; `body_reach` is how fast it gets there from the
    edge (low: only the very middle is bright; high: a thin dim rim and a bright inside). `core` fills the middle disc (the filled
    shape the graph blends in). `spin` turns the whole
    burst by that many degrees, the thorns unchanged, to choose which ones stand on top. `half` 1
    keeps the top half."""
    gu, gv = lib.grid(size)
    # the burst is drawn `zoom` times larger than its own units, so it fills the frame
    zoom = max(p["zoom"], 1e-3)
    u, v = gu / zoom, gv / zoom
    r, a = lib.polar(u, v)
    px = 2.0 / size / zoom
    img = np.zeros(u.shape, np.float32)
    sdf = np.full(u.shape, 9.0, np.float32) if (p["merge"] or p["point"]) else None
    lo, hi = p["length"]
    n = max(1, int(p["count"]))
    # drawn only with gaps on, so a burst without them keeps its own thorns
    gap = lib.perlin((1, 512), (1, max(1, int(p["gap_scale"]))), _seed(rng))[0] if p["gaps"] else None
    for count, scale in ((int(n * p["long"]), 1.6), (n, 1.0), (int(n * p["small"]), 0.5)):
        for _ in range(count):
            ang = rng.uniform(0, 2 * np.pi) + np.radians(p["spin"])
            if p["gaps"] and gap[int(ang / (2 * np.pi) * 512) % 512] < p["gaps"]:
                continue
            rr = p["ring"] + rng.uniform(-1, 1) * p["band"]
            ax, ay = rr * np.cos(ang), rr * np.sin(ang)
            d = ang + rng.uniform(-1, 1) * p["turn"]
            ln = rng.uniform(lo, hi) * scale
            wd = p["width"] * scale ** 0.5 * rng.uniform(0.7, 1.2)
            if sdf is None:
                _thorn(img, u, v, ax, ay, ax + ln * np.cos(d), ay + ln * np.sin(d), wd, p["sharp"], px, zoom)
            else:
                _thorn_sdf(sdf, u, v, ax, ay, ax + ln * np.cos(d), ay + ln * np.sin(d), wd, p["sharp"], max(p["merge"], 1e-4), zoom)
    reach = p["ring"] + p["band"] + hi * 1.6
    t_out = np.clip((r - (p["ring"] - p["band"])) / max(reach - (p["ring"] - p["band"]), 1e-3), 0, 1)
    if sdf is not None:
        sdf = sdf + p["point"] * t_out ** 1.5
        img = np.clip(0.5 - sdf / px, 0, 1)
    if p["core"]:
        img = np.maximum(img, p["core"] * lib.crisp(r - p["ring"], px))
    # the slope blur: average of the image looked up inward along the radius, so bright parts
    # streak outward and fade with distance
    k = max(1, int(p["steps"]))
    ux, uy = u / np.maximum(r, 1e-4), v / np.maximum(r, 1e-4)
    acc = np.zeros_like(img)
    wsum = 0.0
    for i in range(k + 1):
        s = p["smear"] * i / k
        wt = 1 - i / (k + 1)
        x = ((u - ux * s) * zoom + 1) / 2 * size - 0.5
        y = ((v - uy * s) * zoom + 1) / 2 * size - 0.5
        acc += wt * lib.sample(img, x, y, wrap=False)
        wsum += wt
    soft = acc / wsum
    out = np.clip((soft - p["cut"]) / (4 * px) + 0.5, 0, 1)
    if p["fade"]:
        out = out * (1 - p["fade"] * t_out)
    if p["body"]:
        inside = np.clip((soft - p["cut"]) / max(1 - p["cut"], 1e-3) * p["body_reach"], 0, 1)
        out = out * (1 - p["body"] + p["body"] * inside)
    out = out * lib.vignette(gu, gv, 0.92, 0.99)
    if p["half"]:
        out = out * (1 - lib.smooth(-0.01, 0.01, gv))
    return out


def _drop_spine(start, heading, length, curl, n, wobble, rng, hook=2.2):
    """A curling spine: from `start`, heading `heading` (radians, v down), turning by `curl` over
    its length, mostly near the end (more so the higher `hook`), so it ends in a hook. Returns
    (n, 2) points and each one's share of the way along."""
    t = np.linspace(0, 1, n)
    ang = heading + curl * t ** hook + wobble * np.sin(t * rng.uniform(4, 7) + rng.uniform(0, 6.3)) * 0.25
    step = length / (n - 1)
    pts = np.zeros((n, 2))
    pts[0] = start
    for i in range(1, n):
        pts[i] = pts[i - 1] + step * np.array([np.cos(ang[i - 1]), np.sin(ang[i - 1])])
    return pts, t


def _drop_width(t, w, plateau, taper):
    """A drop's half-width along its spine: full over the first `plateau` of it (a flat body, not
    a round head), then thinning to a sharp point with power `taper`."""
    return w * np.clip((1 - t) / max(1 - plateau, 1e-3), 0, 1) ** taper


@recipe("flame_drops", frames=16, mode="curl", width=0.26, plateau=0.35, taper=1.6, length=(1.3, 1.8),
        curl=(1.8, 2.8), hook=3.5, branches=(0, 2), wobble=0.12, lumps=0.22, lump_freq=(9, 14),
        edge=0.035, flat=0.0, bands=(0.35, 0.7), body=0.0, body_reach=1.0, root_fade=0.0, soften=0.0,
        peak=0.5, fill=1.7, streaks=0.0, bite=1.1, fold=0.6, rise=0)
def flame_drops(p, rng, size):
    """Splashed flame: 16 single drops, one per cell, for a burst of many particles that flies
    out in all directions and so reads as volume (the fire pit's splash at the jets' base).
    Each drop is a chain of discs along a curling spine: a flat body (full width over `plateau`
    of it), thinning to a pointed tail that hooks over at the end (`curl` radians in all, packed
    toward the end by `hook`), with `branches` smaller curls forking off it. `mode` "curl" puts the
    body at the top of the cell and the hooked tail trailing below, for VelocityParallel particles
    flung sideways; "lick" puts a wide base at the bottom and the hooked tip at the top, for
    upright tongues, its base cut flat by `flat`; "sweep" is a fiery splash: a thick root low in
    the cell sweeping out to one side and curling up into a thin whip, its branches curling up
    off it too; `root_fade` fades its root out over that many root widths, so it grows out of
    the burst instead of ending in a blunt cap; "crescent" is a soft fire splash: a thick arc
    bent through `curl` radians at an even rate, widest in its middle and tapering to a horn at
    each end (widest `peak` of the way along, so a low `peak` makes a fan that sweeps into a
    long blade), with branches hooking off it. `soften` blurs the finished drop by that share of
    the cell, for the soft, glowing splashes of a painted fire sheet; `streaks` lays brightness
    streaks along the drop's sweep, like brush strokes. `fill` is how much of the cell the drop
    spans (2 is edge to edge). "wedge" is a chunky folded splash: a fat, short arc with a round
    bite (`bite` of its width) taken out of its inner side, so the two corners where the bite
    meets the body stand out as short, thick horns; it is shaded like a twisted ribbon of flame,
    bright along its edges with a dark `fold` running down its middle. Lumpy, like cel fire: the width swells and
    pinches `lumps` of itself `lump_freq` times along the spine, and noise roughens the edge by
    `edge`; `wobble` bends the spine. Shading is crisp cel bands: the alpha steps up at each depth
    in `bands` (shares of the drop's width in from the edge), so the colour ramp reads as a rim, a
    body and a hot core; `body` above 0 adds the soft thorn_burst gradient instead."""
    u, v = lib.grid(size)
    px = 2.0 / size
    cells = []
    lick = p["mode"] == "lick"
    for k_cell in range(_frames(p)):
        side = rng.choice([-1.0, 1.0])
        length = rng.uniform(*p["length"])
        curl = rng.uniform(*p["curl"]) * side
        # a lick grows up from its base; a curl runs down from its head; a sweep goes out to one
        # side and curls up (v points down, so up is a negative turn going right)
        if p["mode"] in ("crescent", "wedge"):
            # `rise` 1 starts it pointing up, for a ribbon of flame peeling up off a fire
            heading = -np.pi / 2 + rng.uniform(-0.35, 0.35) if p["rise"] else rng.uniform(0, 2 * np.pi)
        elif p["mode"] == "sweep":
            heading = -rng.uniform(0.1, 0.45) if side > 0 else np.pi + rng.uniform(0.1, 0.45)
            curl = -abs(curl) * side
        elif lick:
            heading = -np.pi / 2 + rng.uniform(-0.25, 0.25)
        else:
            heading = np.pi / 2 + rng.uniform(-0.3, 0.3)
        spines = []
        pts, t = _drop_spine(np.zeros(2), heading, length, curl, 64, p["wobble"], rng, p["hook"])
        w = p["width"] * rng.uniform(0.85, 1.15)
        f = rng.uniform(*p["lump_freq"])
        lump = 1 + p["lumps"] * (np.sin(t * f + rng.uniform(0, 6.3)) + 0.5 * np.sin(t * f * 2.3 + rng.uniform(0, 6.3))) / 1.5
        if p["mode"] in ("crescent", "wedge"):
            # widest in the middle, a horn at each end
            pk = min(max(p["peak"], 0.05), 0.95)
            tt = np.where(t < pk, t / pk * 0.5, 0.5 + (t - pk) / (1 - pk) * 0.5)
            prof = np.clip(np.sin(np.pi * tt), 0, 1) ** p["taper"]
            spines.append((pts, w * prof * lump))
        else:
            spines.append((pts, _drop_width(t, w, p["plateau"], p["taper"]) * lump))
        for _ in range(int(rng.integers(p["branches"][0], p["branches"][1] + 1))):
            if p["mode"] == "crescent":
                # a horn near one end, turning back the other way: the S of a splash
                k = int((rng.uniform(0.08, 0.22) if rng.random() < 0.5 else rng.uniform(0.72, 0.9)) * 63)
                bt = t[k]
                # a fang: long, nearly straight, sharp, bending only a little back at its tip
                bpts, bt2 = _drop_spine(pts[k], heading + curl * bt + rng.uniform(0.6, 1.3) * -np.sign(curl),
                                        length * rng.uniform(0.5, 0.75), -curl * rng.uniform(0.15, 0.35), 32, p["wobble"] * 0.5, rng, 1.6)
                bw = w * float(np.sin(np.pi * bt)) ** p["taper"] * 0.9 + w * 0.3
                spines.append((bpts, bw * (1 - bt2) ** 1.6))
                continue
            k = int(rng.uniform(0.3, 0.65) * 63)
            bt = t[k]
            bpts, bt2 = _drop_spine(pts[k], heading + curl * bt ** p["hook"] + rng.uniform(0.5, 1.0) * rng.choice([-1, 1]),
                                    length * rng.uniform(0.3, 0.5), -curl * rng.uniform(0.6, 1.2), 32, p["wobble"], rng, p["hook"])
            bw = float(_drop_width(np.array([bt]), w, p["plateau"], p["taper"])[0]) * 0.9
            spines.append((bpts, _drop_width(bt2, bw, 0.0, p["taper"])))
        # fit the drop into the cell
        allp = np.vstack([q for q, _ in spines])
        allr = np.concatenate([r_ for _, r_ in spines])
        lo = (allp - allr[:, None]).min(0)
        hi = (allp + allr[:, None]).max(0)
        scale = p["fill"] / max(hi - lo)
        mid = (lo + hi) / 2
        sdf = np.full(u.shape, 9.0, np.float32)
        spine_d = np.full(u.shape, 9.0, np.float32)
        for si, (q, rr) in enumerate(spines):
            for (cx, cy), ri in zip((q - mid) * scale, rr * scale):
                dd = np.sqrt((u - cx) ** 2 + (v - cy) ** 2)
                sdf = np.minimum(sdf, dd - ri)
                if si == 0:
                    spine_d = np.minimum(spine_d, dd)
        if p["mode"] == "wedge":
            # bite a round notch out of the inner side of the arc; its rim and the body's edge
            # meet in two sharp corners, the horns
            q0 = (spines[0][0] - mid) * scale
            m_i = len(q0) // 2
            tx, ty = q0[m_i + 1] - q0[m_i - 1]
            tl = max(float(np.hypot(tx, ty)), 1e-6)
            sgn = float(np.sign(curl)) if curl else 1.0
            nx, ny = -ty / tl * sgn, tx / tl * sgn
            wb = w * scale
            br = p["bite"] * wb
            bx, by = q0[m_i][0] + nx * (wb * 0.55 + br), q0[m_i][1] + ny * (wb * 0.55 + br)
            sdf = np.maximum(sdf, br - np.sqrt((u - bx) ** 2 + (v - by) ** 2))
        if p["edge"]:
            sdf = sdf + (lib.fbm(u.shape, 6, 4, seed=_seed(rng)) - 0.5) * 2 * p["edge"]
        if lick and p["flat"]:
            # a flat base: cut the bottom off at `flat` of the way up from the lowest point
            base = ((hi[1] - mid[1]) * scale) - p["flat"] * (hi[1] - lo[1]) * scale
            sdf = np.maximum(sdf, v - base)
        alpha = np.clip(0.5 - sdf / px, 0, 1)
        wd = max(w * scale, 1e-3)
        if p["mode"] == "wedge":
            # a twisted ribbon: bright near its edges, a dark fold down its middle
            rim = 1 - np.clip(-sdf / (wd * 0.55), 0, 1)
            fold = np.exp(-((spine_d / (wd * 0.35)) ** 2))
            out = alpha * np.clip(0.35 + 0.65 * rim, 0, 1) * (1 - p["fold"] * fold)
        elif p["body"]:
            depth = np.clip(-sdf / wd * p["body_reach"], 0, 1)
            out = alpha * (1 - p["body"] + p["body"] * depth)
        else:
            # cel bands: a dim rim, a mid body and a bright core, stepped at depths in `bands`
            levels = [0.45, 0.75, 1.0]
            out = alpha * levels[0]
            for edge_at, lvl, prev in zip(p["bands"], levels[1:], levels[:-1]):
                step = np.clip((-sdf - edge_at * wd) / px + 0.5, 0, 1)
                out = out + alpha * step * (lvl - prev)
        if p["streaks"]:
            # brush streaks along the drop's sweep: noise stretched along its middle heading
            am = heading + curl * 0.5
            al, ac = u * np.cos(am) + v * np.sin(am), -u * np.sin(am) + v * np.cos(am)
            field = lib.fbm((256, 256), 4, 3, seed=_seed(rng))
            st = lib.sample(field, ((al * 0.35 + 1) * 128) % 256, ((ac * 3.0 + 1) * 128) % 256)
            out = out * (1 - p["streaks"] + p["streaks"] * np.clip((st - 0.25) * 2.0, 0, 1))
        if p["soften"]:
            out = _blur_f(out, p["soften"] * size)
        if p["root_fade"]:
            r0x, r0y = (spines[0][0][0] - mid) * scale
            reach = p["root_fade"] * spines[0][1][0] * scale
            out = out * lib.smooth(0.0, max(reach, px), np.sqrt((u - r0x) ** 2 + (v - r0y) ** 2))
        cells.append(out * lib.vignette(u, v, 0.92, 0.99))
    return cells


@recipe("molded", mold="")
def molded(p, rng, size):
    """A shape molded by hand in the mold page and shaded in code (tools/texgen/mold.py): `mold`
    names its file in tools/texgen/molds/."""
    import mold

    return mold.render(mold.load(p["mold"]), size)


@recipe("blob_carve", frames=4, blobs=(2, 4), stretch=(1.3, 2.6), blob_size=(0.22, 0.42), carve=(1, 3),
        carve_size=(0.2, 0.42), smooth=0.12, warp=0.12, soft=0.025, grain=0.25, fill=1.45, edge=0.47,
        reach=0.12, gamma=0.8, strokes=(0, 0), stroke_len=(0.6, 1.0), stroke_width=(0.1, 0.2),
        stroke_bend=(0.2, 0.6), tip=(0.3, 1.0), tail=(0.1, 0.5))
def blob_carve(p, rng, size):
    """Abstract splash shapes, one per cell: a few soft stretched blobs melted together
    (`blobs` of them, `blob_size` across, stretched `stretch` times along a random axis, joined
    with a smooth union of reach `smooth`), with `carve` discs bitten out of them (`carve_size`
    across), so the bites leave curved notches and the pieces between them stand out as horns.
    Then the whole shape is warped by low noise (`warp`), softened (`soft`, a share of the cell)
    and given a faint grain of brightness (`grain`). `fill` sets how much of the cell it spans.
    Only the biggest piece is kept. Brightness is `edge` at the rim and rises to 1 over `reach`
    (a share of the cell) into the body, bent by `gamma`. One white tone, for the particle to colour.
    `strokes` adds curved tongues melted in with the blobs: a bent curve (`stroke_len` long,
    bowed `stroke_bend` of its length) swept by a disc `stroke_width` across at its widest,
    narrowing to a point at its start by the power `tip` and at its end by `tail`, so a tongue
    has a thin tip and a thicker root. Made to be sampled many times and kept by measurement
    (texgen measure)."""
    u, v = lib.grid(size)
    cells = []
    for _ in range(_frames(p)):
        wu = u + (lib.fbm(u.shape, 2, 3, seed=_seed(rng)) - 0.5) * 2 * p["warp"]
        wv = v + (lib.fbm(u.shape, 2, 3, seed=_seed(rng)) - 0.5) * 2 * p["warp"]
        body = None
        n = int(rng.integers(p["blobs"][0], p["blobs"][1] + 1))
        centres = []
        for _ in range(n):
            cx, cy = rng.uniform(-0.35, 0.35, 2)
            a = rng.uniform(0, np.pi)
            rad = rng.uniform(*p["blob_size"])
            st = rng.uniform(*p["stretch"])
            du, dv = wu - cx, wv - cy
            along = du * np.cos(a) + dv * np.sin(a)
            across = -du * np.sin(a) + dv * np.cos(a)
            d = np.sqrt((along / st) ** 2 + across ** 2) - rad / st ** 0.5
            centres.append((cx, cy))
            if body is None:
                body = d
            else:
                k = p["smooth"]
                h = np.clip(0.5 + 0.5 * (d - body) / k, 0, 1)
                body = d * (1 - h) + body * h - k * h * (1 - h)
        for _ in range(int(rng.integers(p["strokes"][0], p["strokes"][1] + 1)) if p["strokes"][1] > 0 else 0):
            length = rng.uniform(*p["stroke_len"])
            ang = rng.uniform(0, 2 * np.pi)
            x0, y0 = rng.uniform(-0.3, 0.3, 2) - 0.5 * length * np.array([np.cos(ang), np.sin(ang)])
            x2, y2 = x0 + length * np.cos(ang), y0 + length * np.sin(ang)
            bend = rng.uniform(*p["stroke_bend"]) * length * rng.choice([-1, 1])
            x1, y1 = (x0 + x2) / 2 - np.sin(ang) * bend, (y0 + y2) / 2 + np.cos(ang) * bend
            width, tip, tail = rng.uniform(*p["stroke_width"]), rng.uniform(*p["tip"]), rng.uniform(*p["tail"])
            ts = np.linspace(0.02, 0.98, 32)
            prof = ts ** tip * (1 - ts) ** tail
            prof = prof / prof.max() * width / 2
            d = None
            for t, r in zip(ts, prof):
                qx = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * x1 + t * t * x2
                qy = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * y1 + t * t * y2
                dd = np.sqrt((wu - qx) ** 2 + (wv - qy) ** 2) - r
                d = dd if d is None else np.minimum(d, dd)
                centres.append((qx, qy)) if t in (ts[8], ts[24]) else None
            if body is None:
                body = d
            else:
                k = p["smooth"]
                h = np.clip(0.5 + 0.5 * (d - body) / k, 0, 1)
                body = d * (1 - h) + body * h - k * h * (1 - h)
        # bites: discs centred near the body's edge, so they cut notches, not holes
        for _ in range(int(rng.integers(p["carve"][0], p["carve"][1] + 1))):
            ang = rng.uniform(0, 2 * np.pi)
            cx, cy = centres[int(rng.integers(0, len(centres)))]
            r = rng.uniform(*p["carve_size"])
            bx, by = cx + np.cos(ang) * r * 1.1, cy + np.sin(ang) * r * 1.1
            body = np.maximum(body, r - np.sqrt((wu - bx) ** 2 + (wv - by) ** 2))
        mask = (body < 0).astype(np.float32)
        if not mask.any():
            cells.append(np.zeros_like(u)); continue
        # keep the piece holding the deepest point: flood it grey, drop the rest
        from PIL import Image, ImageDraw
        deep = _blur_f(mask, 0.04 * size) * mask + mask * 1e-3
        y0, x0 = np.unravel_index(int(np.argmax(deep)), deep.shape)
        flood = Image.fromarray((mask * 255).astype(np.uint8)).copy()
        ImageDraw.floodfill(flood, (int(x0), int(y0)), 128)
        mask = (np.array(flood) == 128).astype(np.float32)
        ys, xs = np.nonzero(mask)
        # fit the shape into the cell
        cx0, cy0 = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
        span = max(xs.max() - xs.min(), ys.max() - ys.min()) + 1
        scale = p["fill"] * size / 2 / span
        img = Image.fromarray((mask * 255).astype(np.uint8))
        img = img.transform((size, size), Image.AFFINE, (1 / scale, 0, cx0 - size / 2 / scale, 0, 1 / scale, cy0 - size / 2 / scale), Image.BILINEAR)
        m = np.asarray(img, np.float32) / 255
        depth = np.clip((_blur_f(m, p["reach"] * size / 2) - 0.5) / 0.5, 0, 1)
        a = m * (p["edge"] + (1 - p["edge"]) * depth ** p["gamma"])
        a = _blur_f(a, p["soft"] * size)
        a = a * (1 - p["grain"] + p["grain"] * lib.fbm(u.shape, 3, 4, seed=_seed(rng)))
        cells.append(np.clip(a, 0, 1) * lib.vignette(u, v, 0.92, 0.99))
    return cells


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
    # the fire pit's jets: a deeper red rim and a red-orange body (Phát: "more red than our orange")
    "fire_red": [(0.70, 0.05, 0.05), (0.96, 0.25, 0.08), (1.0, 0.88, 0.60)],
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
        wide=1.25, base=0.30, tips=0.16, kink=0.035, core_drop=0.06, ink=0.0, crown=1, round=1.0, seat=0.0, pivot="center",
        burnout=0, start=0, tone="bands", floor=0.0)
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
      round      rounds the bottom into a bowl (1, the default since Phát asked for a rounded
                 base, 2026-10-24; 0 keeps the sim's flat source line)
      seat       a clean base (ref 013, Phát: "so clean"): the core runs down to the bottom, so
                 no red rim lines the base, and the bottom fades softly into the floor, where a
                 contact glow hides the seam. Use it with round 0 so the base lies flat
      pivot      "base" draws the flame in each cell's top half with its base on the centre line:
                 a particle billboard turns and grows about its middle, so this puts the pivot
                 on the base, to sit exactly on the floor (Phát). It halves the flame's pixels
      burnout    1 makes a OneShot of the fire dying instead of a loop: the same frames, the heat
                 falling to nothing, so the cool tips go first and the hot base last, top down
                 (Phát: real fire burns steady and dies from the top, it doesn't shrink).
                 `start` is the loop frame it begins on, so it takes over from the loop
                 mid-motion without a jump
      crown      1 cools the heat toward the cell's top so tongues end before it; 0 for a
                 lick (sim `flame_lick`), which is meant to rise through the cell
      tone       "bands" (the default) bakes the three colour bands below; "single" draws one
                 white shape whose alpha follows the heat, dim at the edge and full in the hot
                 middle, for the engine to colour with its colour and transparency curves (the
                 fire pit's splash does it that way; Phát, 2026-10-24)
      floor      fades the bottom of the flame out over its lower part, so no flat base line shows
                 where a particle stands on or flies over the floor (0 is off, 1 fades it fully)
    then cut at three heights into a rim, a body and a core, each a flat colour with a 1 px
    edge. `frames` 16 steps the 64-frame sim on fours (12 a second gives a 1.3 s loop, the
    on-twos look); 64 keeps every frame."""
    heat = _sim_frames(p["sim"])
    step = max(1, heat.shape[0] // int(p["frames"]))
    heat = heat[::step][: int(p["frames"])]
    n = len(heat)
    first = int(p["start"]) % n if p["burnout"] else 0
    if first:
        heat = np.roll(heat, -first, axis=0)
    pal = PALETTES[p["palette"]]
    u, v = lib.grid(size)
    px = size / 256
    out = []
    for j, h in enumerate(_flame_fit(heat, size, p["wide"], p["margin"], p["edge"], 0.04)):
        h = _blur_f(h, p["blur"] * size / 192)
        phase = 2 * np.pi * ((j + first) % n) / n
        if p["base"] > 0:
            breathe = 1 + 0.05 * np.sin(phase)
            h = h + p["base"] * np.exp(-1.6 * ((u / (0.40 * breathe)) ** 2 + ((v - 0.74) / 0.20) ** 2))
        if p["round"] > 0:
            # a bowl under the flame: the heat fades out along an ellipse below the middle
            bowl = np.sqrt((u / 0.74) ** 2 + (np.clip(v - 0.38, 0, None) / 0.52) ** 2)
            h = h * (1 - p["round"] * lib.smooth(0.9, 1.0, bowl))
        # cool toward the top of the cell, so tongues end before the edge
        if p["crown"]:
            h = h * lib.smooth(-0.97, -0.45, v)
        h = _pull_tips(h, p["tips"])
        if p["kink"] > 0:
            h = _kink(h, u, v, phase, p["kink"])
        if p["burnout"]:
            # the fire dies: heat falls to nothing, so the cool tips go first, the base last. The
            # top cools faster, so the tongues get shorter, and the shape softens as it goes, so
            # it ends in a few short, smooth strands, like a candle's, not a fork (Phát)
            t = j / (n - 1)
            up = np.clip((0.6 - v) / 1.6, 0, 1)
            h = h * max(0.0, 1 - t ** 1.3) * (1 - 0.75 * t * up)
            h = _blur_f(h, (1 + 5 * t) * size / 256)
        if p["seat"] > 0:
            # inside the flame's lower part, heat up to the core: the base burns hottest
            inside = np.clip((h - p["edge"]) / 0.05, 0, 1)
            h = h + p["seat"] * lib.smooth(0.4, 0.82, v) * inside * p["core"] * 1.3
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
        if p["seat"] > 0:
            alpha = alpha * (1 - p["seat"] * lib.smooth(0.56, 0.92, v) ** 0.8)
        if p["tone"] == "single":
            # one shape; its alpha rises from the edge to the core with the heat
            heat_in = np.clip((h - p["edge"]) / max(p["core"] - p["edge"], 1e-3), 0, 1)
            alpha = rim * (0.3 + 0.7 * heat_in ** 0.8)
            rgb = np.ones((size, size, 3), np.float32)
        if p["floor"] > 0:
            alpha = alpha * (1 - p["floor"] * lib.smooth(0.35, 0.9, v))
        out.append({"alpha": alpha * lib.vignette(u, v, 0.94, 0.995), "rgb": rgb})
    if p["pivot"] == "base":
        # the base line comes from the fit, not from what a frame draws, so a burn-out (which
        # draws less as it dies) sits exactly where its loop does
        out = _pivot_base(out, size, int((1 - p["margin"]) * size))
    return out


def _pivot_base(frames, size, low):
    """Halves every frame and sets it in the cell's top half, the flame's base row `low` (the
    same for every frame) on the cell's centre line, so the billboard pivots on the base."""
    from PIL import Image

    half = size // 2
    top = half - (low + 1) // 2
    out = []
    for f in frames:
        a = np.zeros((size, size), np.float32)
        rgb = np.zeros((size, size, 3), np.float32)
        small_a = np.asarray(Image.fromarray((f["alpha"] * 255).astype(np.uint8)).resize((half, half), Image.LANCZOS), np.float32) / 255
        small_c = np.asarray(Image.fromarray((np.clip(f["rgb"], 0, 1) * 255).astype(np.uint8)).resize((half, half), Image.LANCZOS), np.float32) / 255
        x0 = size // 4
        y0, y1 = max(0, top), min(size, top + half)
        a[y0:y1, x0 : x0 + half] = small_a[y0 - top : y1 - top]
        rgb[y0:y1, x0 : x0 + half] = small_c[y0 - top : y1 - top]
        out.append({"alpha": a, "rgb": rgb})
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
        pool=0.0, reach=0.92, zoom=1.0, palette="fire", frames=0)
def ground_cracks(p, rng, size):
    """Glowing ground cracks seen from above, for a flat decal (additive):
      layout   `radial` cells that grow outward (the fire pit) or `hex` cells
      cells    how many cells across (more is finer)
      line     the line's half-width at the centre; `taper` thins it toward the rim
      drop     how many edges break off toward the rim (0 keeps every edge)
      warp     how much the lines wobble
      glow     a soft halo around the lines, for the light they cast
      pool     fills the centre cell with a hot glow (0 is off)
      reach    the cracks' radius (in the pattern's own units)
      zoom     draws `zoom` times more of the pattern into the texture, so a decal made `zoom`
               times bigger keeps its cells and lines the same size in the world (Phát: a wider
               patch at the same fine resolution)
      frames   0 is one still texture; 16 spreads the cracks out from the centre, hot at the
               leading edge, then settles
    Each line has two bands across its width, a hot middle and a red edge, and its heat falls
    from the palette's core at the centre to its rim colour at the edge."""
    gu, gv = lib.grid(size)
    z = max(float(p["zoom"]), 1e-3)
    u, v = gu * z, gv * z
    seed = _seed(rng)
    # noise periods scale with the zoom, so the wobble stays the same size against the cells
    du = (lib.fbm(u.shape, max(1, round(4 * z)), 4, seed=seed) - 0.5) * 2
    dv = (lib.fbm(u.shape, max(1, round(4 * z)), 4, seed=seed + 7) - 0.5) * 2
    wu, wv = u + du * p["warp"], v + dv * p["warp"]
    r = np.sqrt(u * u + v * v)
    pts = _crack_points(p["layout"], rng, int(p["cells"]))
    edge, key, cell = _voronoi_edges(wu, wv, pts)
    t = np.clip(r / p["reach"], 0, 1)
    vary = 0.5 + 1.0 * lib.fbm(u.shape, max(1, round(6 * z)), 3, seed=seed + 3)
    w = p["line"] * (1 - p["taper"] * t) * vary
    px = 2.0 / size * z
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
    halo = _blur_f(lit, 6 * size / 512 / z) * p["glow"] * 2
    rgb = red * 0.75 * np.ones(u.shape + (3,), np.float32)
    rgb = rgb * (1 - line[..., None]) + body * line[..., None]
    rgb = rgb * (1 - hot[..., None]) + core * hot[..., None]
    vig = lib.vignette(gu, gv, 0.94, 0.995)
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


def _crack_paths(p, rng):
    """The crack network as segments (ax, ay, bx, by, w0, w1, d0, d1): ends, widths at each end,
    and how far along the cracks from the impact each end lies (the reveal's clock)."""
    segs = []

    def walk(x, y, ang, dist, width, length, depth):
        step = p["step"]
        n = max(2, int(length / step))
        for k in range(n):
            ang += math.radians(rng.uniform(-p["wander"], p["wander"]))
            if rng.random() < p["kink"]:
                ang += math.radians(rng.choice([-1, 1]) * rng.uniform(20, 40))
            seg = step * rng.uniform(0.7, 1.3)
            nx, ny = x + math.cos(ang) * seg, y + math.sin(ang) * seg
            w1 = width * (1 - (k + 1) / n * p["taper"])
            w0 = width * (1 - k / n * p["taper"])
            segs.append((x, y, nx, ny, w0, w1, dist, dist + seg))
            if depth < p["depth"] and k < n - 1 and rng.random() < p["branch"]:
                side = rng.choice([-1, 1]) * math.radians(rng.uniform(25, 60))
                walk(nx, ny, ang + side, dist + seg, w1 * 0.6, length * rng.uniform(0.25, 0.5), depth + 1)
            x, y, dist = nx, ny, dist + seg
            if math.hypot(x, y) > 0.97:
                break
        return x, y

    mains = int(p["mains"])
    base = rng.uniform(0, 2 * math.pi)
    tips = []
    for i in range(mains):
        ang = base + i * 2 * math.pi / mains + math.radians(rng.uniform(-14, 14))
        r0 = p["hub"]
        length = p["reach"] * rng.uniform(0.7, 1.0)
        walk(math.cos(ang) * r0, math.sin(ang) * r0, ang, r0, p["width"], length, 0)
        tips.append(ang)
    # rings: broken arcs between neighbouring fissures, as the ground splits round the impact
    for r in p["rings"]:
        for i in range(mains):
            if rng.random() > p["ring_keep"]:
                continue
            a0 = tips[i]
            a1 = tips[(i + 1) % mains] + (2 * math.pi if i == mains - 1 else 0)
            pts = max(3, int((a1 - a0) * r / p["step"]))
            rr = r * rng.uniform(0.9, 1.1)
            last = None
            for k in range(pts + 1):
                a = a0 + (a1 - a0) * k / pts
                q = rr * rng.uniform(0.96, 1.04)
                cur = (math.cos(a) * q, math.sin(a) * q)
                if last:
                    d0 = r + (k - 1) * (a1 - a0) / pts * r
                    segs.append((last[0], last[1], cur[0], cur[1], p["ring_width"], p["ring_width"], d0, d0 + (a1 - a0) / pts * r))
                last = cur
    # the crushed hub: a small jagged ring at the impact
    if p["hub"] > 0:
        k = 7
        hub = [(math.cos(base + j * 2 * math.pi / k) * p["hub"] * rng.uniform(0.8, 1.2),
                math.sin(base + j * 2 * math.pi / k) * p["hub"] * rng.uniform(0.8, 1.2)) for j in range(k)]
        for j in range(k):
            a, b = hub[j], hub[(j + 1) % k]
            segs.append((a[0], a[1], b[0], b[1], p["width"] * 0.8, p["width"] * 0.8, 0.0, p["hub"]))
    return segs


@recipe("impact_cracks", mains=7, hub=0.07, reach=0.9, width=0.02, taper=0.8, step=0.06, wander=12, kink=0.15,
        branch=0.3, depth=2, rings=(0.38, 0.62), ring_keep=0.5, ring_width=0.006, warp=0.012, soft=1.0,
        glow=0.35, palette="fire", frames=0, lead=0.15)
def impact_cracks(p, rng, size):
    """Ground cracks drawn as paths, not cells: `mains` fissures run out from a crushed hub at
    the impact (`hub` across), wandering (`wander` degrees a step, a sharp `kink` now and then)
    and branching (`branch` chance a step, `depth` levels), `width` thick at the start and
    thinning by `taper` to their tips. `rings` are radii where the ground also splits round the
    impact: broken arcs joining neighbouring fissures (`ring_keep` of them, `ring_width` thick).
    Every point knows how far along the cracks it lies from the impact, so `frames` > 0 reveals
    them the way cracks run: each one races out along its own path, branches after the trunk
    they leave, the front hot (`lead`), then they hold. Coloured like ground_cracks: a hot
    middle band and a red edge, hottest near the impact."""
    u, v = lib.grid(size)
    du = (lib.fbm(u.shape, 6, 3, seed=_seed(rng)) - 0.5) * 2 * p["warp"]
    dv = (lib.fbm(u.shape, 6, 3, seed=_seed(rng)) - 0.5) * 2 * p["warp"]
    wu, wv = u + du, v + dv
    segs = _crack_paths(p, rng)
    best = np.full(u.shape, 9.0, np.float32)  # distance past the line's edge
    core = np.full(u.shape, 9.0, np.float32)
    clock = np.zeros(u.shape, np.float32)
    for ax, ay, bx, by, w0, w1, d0, d1 in segs:
        lo_x, hi_x = min(ax, bx) - 0.05, max(ax, bx) + 0.05
        lo_y, hi_y = min(ay, by) - 0.05, max(ay, by) + 0.05
        i0, i1 = max(0, int((lo_y + 1) / 2 * size)), min(size, int((hi_y + 1) / 2 * size) + 1)
        j0, j1 = max(0, int((lo_x + 1) / 2 * size)), min(size, int((hi_x + 1) / 2 * size) + 1)
        if i1 <= i0 or j1 <= j0:
            continue
        sl = (slice(i0, i1), slice(j0, j1))
        d, h = lib.sd_segment(wu[sl], wv[sl], ax, ay, bx, by)
        w = w0 + (w1 - w0) * h
        e = d - w
        better = e < best[sl]
        best[sl] = np.where(better, e, best[sl])
        core[sl] = np.minimum(core[sl], d - w * 0.35)
        clock[sl] = np.where(better, d0 + (d1 - d0) * h, clock[sl])
    px = 2.0 / size * p["soft"]
    line = np.clip(0.5 - best / px, 0, 1).astype(np.float32)
    hot = np.clip(0.5 - core / px, 0, 1).astype(np.float32)
    r = np.sqrt(u * u + v * v)
    t = np.clip(r / p["reach"], 0, 1)
    pal = PALETTES[p["palette"]]
    heat = ((1 - t) ** 1.5)[..., None]
    red, orange, cream = (np.array(c, np.float32) for c in pal)
    body = orange * 0.85 * heat + red * 0.8 * (1 - heat)
    hotc = cream * heat + orange * (1 - heat)
    lit = np.maximum(line, hot)
    halo = _blur_f(lit, 6 * size / 512) * p["glow"] * 2
    rgb = red * 0.75 * np.ones(u.shape + (3,), np.float32)
    rgb = rgb * (1 - line[..., None]) + body * line[..., None]
    rgb = rgb * (1 - hot[..., None]) + hotc * hot[..., None]
    vig = lib.vignette(u, v, 0.94, 0.995)
    if int(p["frames"]) <= 0:
        return {"alpha": np.clip(np.maximum(lit, halo), 0, 1) * vig, "rgb": rgb}
    out = []
    n = int(p["frames"])
    far = float(clock[line > 0.5].max()) if (line > 0.5).any() else 1.0
    # the halo spreads with the line it belongs to: blur the revealed line each frame
    for k in range(n):
        s = k / (n - 1)
        front = float(lib.ease_out(min(1.0, s / 0.6), 2.0)) * far * 1.02
        shown = np.clip((front - clock) / (0.02 * far) + 0.5, 0, 1) * (best < 0.05)
        a_line = lit * shown
        a = np.maximum(a_line, _blur_f(a_line, 6 * size / 512) * p["glow"] * 2)
        lead = np.exp(-(((clock - front) / (p["lead"] * far)) ** 2)) * shown * (s < 0.65)
        c = rgb + (np.array(pal[2], np.float32) - rgb) * (lead * lit)[..., None]
        out.append({"alpha": np.clip(a, 0, 1) * vig, "rgb": c})
    return out


def _network_clock(line, r, start=0.1, res=256):
    """How far each point of a crack network lies from the impact, travelling along the cracks:
    a breadth-first walk over the lit pixels (`line` > 0.3) out from the ones within `start` of
    the crack nearest the middle, done at `res` and scaled back, in units of the texture's half-width. Points the
    walk never reaches (cracks not joined to the rest) keep their straight-line distance."""
    from PIL import Image

    size = line.shape[0]
    small = np.asarray(Image.fromarray((np.clip(line, 0, 1) * 255).astype(np.uint8)).resize((res, res), Image.BILINEAR), np.float32) / 255
    rr = np.asarray(Image.fromarray(r.astype(np.float32)).resize((res, res), Image.BILINEAR), np.float32)
    walk = small > 0.3
    big = np.float32(1e9)
    # the walk starts on the cracks nearest the middle (the middle itself may be inside a plate)
    near = float(rr[walk].min()) if walk.any() else 0.0
    dist = np.where(walk & (rr < near + start), rr, big).astype(np.float32)
    step = 2.0 / res
    diag = step * 1.4142
    for _ in range(res * 3):
        pad = np.pad(dist, 1, constant_values=big)
        best = np.minimum.reduce([
            pad[1:-1, :-2] + step, pad[1:-1, 2:] + step, pad[:-2, 1:-1] + step, pad[2:, 1:-1] + step,
            pad[:-2, :-2] + diag, pad[:-2, 2:] + diag, pad[2:, :-2] + diag, pad[2:, 2:] + diag,
        ])
        nxt = np.where(walk, np.minimum(dist, best), big)
        if np.array_equal(nxt, dist):
            break
        dist = nxt
    dist = np.where(dist >= big, rr, dist)
    return np.asarray(Image.fromarray(dist).resize((size, size), Image.BILINEAR), np.float32)


@recipe("plate_cracks", cells=7, jitter=0.42, warp=0.025, width=0.0045, vary=1.0, thin=0.3, bulge=0.007,
        knot=0.03, hair=0.0, reach=0.95, fissures=0, glow=0.25, palette="fire", frames=0, lead=0.15,
        layout="grid", rings=5, spokes=9, inner=0.09, growth=1.5, core_width=0.0, across=1.0)
def plate_cracks(p, rng, size):
    """Lava-plate cracks seen from above: dark, uneven stone plates with glowing seams between
    them, not plain Voronoi. The plates are a jittered grid of `cells` across (`jitter` of a
    cell), the seams wobble (`warp`), every seam has its own width (`width`, varied by `vary`;
    a `thin` share of them are hairlines), and seams swell where plates meet (`bulge`, over
    `knot`), so the joins burn brightest. `layout` "radial" lays the plates out from the impact
    instead: a small plate in the middle, then `rings` rings of `spokes` plates, the first at
    `inner` and each `growth` times further out, so plates are small at the impact, large at the
    rim and stretched along the radius, as ground cracks run. `core_width` thickens the seams
    toward the middle (1 doubles them there), and `across` scales the seams that run round the
    impact (between rings) against those running out from it, so below 1 the radial cracks lead.
    `hair` adds fine cracks inside the plates; `fissures`
    lays that many fissures (impact_cracks) over them. The patch fades out past `reach`.
    `frames` > 0 reveals them the way cracks run: out from the impact along the seams
    themselves, so each seam lights from the join it starts at, the front hot (`lead`), then
    they hold."""
    u, v = lib.grid(size)
    du = (lib.fbm(u.shape, 5, 4, seed=_seed(rng)) - 0.5) * 2 * p["warp"]
    dv = (lib.fbm(u.shape, 5, 4, seed=_seed(rng)) - 0.5) * 2 * p["warp"]
    wu, wv = u + du, v + dv

    def seams(n, jit, width, vary, thin, bulge, knot, radial=False):
        step = 2.0 / n
        pts = []
        ring = []
        if radial:
            pts.append((rng.uniform(-0.01, 0.01), rng.uniform(-0.01, 0.01)))
            ring.append(-1)
            spin = rng.uniform(0, 2 * math.pi)
            for k in range(int(p["rings"]) + 2):
                r = p["inner"] * p["growth"] ** k
                m = int(p["spokes"])
                for i in range(m):
                    a = spin + (i + 0.5 * (k % 2) + rng.uniform(-jit, jit)) * 2 * math.pi / m
                    rr = r * (1 + rng.uniform(-jit, jit) * (p["growth"] - 1) * 0.6)
                    pts.append((math.cos(a) * rr, math.sin(a) * rr))
                    ring.append(k)
        else:
            for i in range(-1, n + 1):
                for j in range(-1, n + 1):
                    pts.append(((i + 0.5 + rng.uniform(-jit, jit)) * step - 1, (j + 0.5 + rng.uniform(-jit, jit)) * step - 1))
        pts = np.array(pts, np.float32)
        wid = {}
        # nearest plate centre
        f1 = np.full(u.shape, 9.0, np.float32)
        id1 = np.zeros(u.shape, np.int32)
        for k, (px_, py_) in enumerate(pts):
            d = (wu - px_) ** 2 + (wv - py_) ** 2
            m = d < f1
            f1 = np.where(m, d, f1)
            id1 = np.where(m, k, id1)
        # distance to the nearest and second-nearest seam (exact bisectors), and whose seam
        e1 = np.full(u.shape, 9.0, np.float32)
        e2 = np.full(u.shape, 9.0, np.float32)
        id2 = np.zeros(u.shape, np.int32)
        ax, ay = pts[id1, 0], pts[id1, 1]
        for k, (bx, by) in enumerate(pts):
            mx, my = (ax + bx) / 2, (ay + by) / 2
            nx, ny = bx - ax, by - ay
            ln = np.sqrt(nx * nx + ny * ny) + 1e-6
            e = ((wu - mx) * nx + (wv - my) * ny) / ln
            e = np.where(id1 == k, 9.0, np.abs(e))
            m = e < e1
            e2 = np.where(m, e1, np.minimum(e2, e))
            id2 = np.where(m, k, id2)
            e1 = np.where(m, e, e1)
        # each seam's own width, from its two plates
        a_, b_ = np.minimum(id1, id2), np.maximum(id1, id2)
        key = (a_ * 7919 + b_ * 104729) % 1000 / 1000.0
        w = width * (1 - vary / 2 + vary * key)
        w = np.where(key < thin, width * 0.3, w)
        if radial:
            rings_ = np.array(ring, np.int32)
            w = np.where(rings_[a_] != rings_[b_], w * p["across"], w)
        w = w + bulge * np.exp(-((e2 - e1) / knot) ** 2)
        return e1, w

    e1, w = seams(int(p["cells"]), p["jitter"], p["width"], p["vary"], p["thin"], p["bulge"], p["knot"], p["layout"] == "radial")
    if p["core_width"] > 0:
        w = w * (1 + p["core_width"] * (1 - np.clip(np.sqrt(u * u + v * v) / p["reach"], 0, 1)) ** 2)
    px = 2.0 / size
    line = np.clip((w - e1) / px + 0.5, 0, 1)
    hot = np.clip((w * 0.4 - e1) / px + 0.5, 0, 1)
    clock_src = np.sqrt(u * u + v * v)
    if p["hair"] > 0:
        h1, hw = seams(int(p["cells"]) * 3, 0.45, p["width"] * 0.25, 0.6, 0.5, 0.0, 0.05)
        hl = np.clip((hw - h1) / px + 0.5, 0, 1) * p["hair"]
        line = np.maximum(line, hl)
    if p["fissures"] > 0:
        f = RECIPES["impact_cracks"]({**DEFAULTS["impact_cracks"], "mains": int(p["fissures"]), "rings": (), "palette": "mono", "glow": 0}, rng, size)
        fl = f["alpha"]
        line = np.maximum(line, fl)
        hot = np.maximum(hot, fl * 0.6)
    r = clock_src
    t = np.clip(r / p["reach"], 0, 1)
    fade = 1 - lib.smooth(0.7, 1.0, t)
    line, hot = line * fade, hot * fade
    pal = PALETTES[p["palette"]]
    heat = ((1 - t) ** 1.2)[..., None]
    red, orange, cream = (np.array(c, np.float32) for c in pal)
    body = orange * 0.85 * heat + red * 0.8 * (1 - heat)
    hotc = cream * heat + orange * (1 - heat)
    lit = np.maximum(line, hot)
    halo = _blur_f(lit, 7 * size / 512) * p["glow"] * 2
    rgb = red * 0.75 * np.ones(u.shape + (3,), np.float32)
    rgb = rgb * (1 - line[..., None]) + body * line[..., None]
    rgb = rgb * (1 - hot[..., None]) + hotc * hot[..., None]
    vig = lib.vignette(u, v, 0.94, 0.995)
    if int(p["frames"]) <= 0:
        return {"alpha": np.clip(np.maximum(lit, halo), 0, 1) * vig, "rgb": rgb}
    out = []
    n = int(p["frames"])
    clock = _network_clock(lit, r)
    far = float(np.percentile(clock[lit > 0.5], 99)) if (lit > 0.5).any() else 1.0
    # every frame shows some crack (the first is the crack at the impact) and the last shows
    # them all, so a short flipbook (2x2) still reads as cracks running out
    for k in range(n):
        s = (k + 1) / n
        front = float(lib.ease_out(s, 1.4)) * far * 1.02
        shown = np.clip((front - clock) / (0.02 * far) + 0.5, 0, 1)
        a_line = lit * shown
        a = np.maximum(a_line, _blur_f(a_line, 7 * size / 512) * p["glow"] * 2)
        lead = np.exp(-(((clock - front) / (p["lead"] * far)) ** 2)) * shown * (k < n - 1)
        c = rgb + (cream - rgb) * (lead * lit)[..., None]
        out.append({"alpha": np.clip(a, 0, 1) * vig, "rgb": c})
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
        ease=1.4, ink=0.0, core=0.2, soft=0.0, wisp=0.0, terminator=0.03)
def smoke_cel(p, rng, size):
    """A cel-shaded smoke puff for a normal-blend layer, in greys to tint (a dark tint gives
    the fire pit's dark smoke, a pale one a dust puff).
      lobes    how many round lobes make the puff; `core` the middle lobe's radius. One big
               lobe (lobes 1, core 0.42) is a smoke ball: the part a smoke volume is built
               from, many overlapping, all upright so their light agrees
      grow     how much the lobes swell over the life; `drift` how far they spread apart
      light    where the light comes from, degrees (135 is top-left)
      shadow   the shadow tone (1 is the lit tone)
      split    where the lit tone gives way to shadow (0 is half lit; higher is more shadow)
      hold     the share of the life before the puff starts to break up; `ease` its pace
      ink      a dark outline this many pixels wide at 256 px a cell (0 is off)
      soft     how far in from the edge the puff takes to turn solid, as a share of its size
               (0 is a hard edge); `wisp` how much a fixed noise thins its body; `terminator`
               how wide the lit-to-shadow change is. Raised together they sit between cel and
               realistic smoke (Phát: "a baby with the realistic version")
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
    radii[0] = p["core"]
    wob_u = (lib.fbm(u.shape, 4, 3, seed=seed) - 0.5) * 0.05
    wob_v = (lib.fbm(u.shape, 4, 3, seed=seed + 1) - 0.5) * 0.05
    blobs = lib.fbm(u.shape, 3, 3, seed=seed + 2)
    thin = lib.fbm(u.shape, 6, 4, seed=seed + 3)
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
        if p["soft"] > 0:
            body = lib.smooth(0.0, p["soft"] * float(radii.max()) * scale, height)
        else:
            body = np.clip(height / px + 0.5, 0, 1)
        if p["wisp"] > 0:
            body = body * (1 - p["wisp"] * lib.smooth(0.35, 0.75, thin))
        gy, gx = np.gradient(np.maximum(height, 0), px)
        norm = np.sqrt(gx * gx + gy * gy + 1)
        lit = (-gx * lx - gy * ly + lz) / norm
        tone = np.clip((lit - 0.5 - p["split"]) / p["terminator"] + 0.5, 0, 1)
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


# ================================================================== the fire pit's entrance
# From the frame-by-frame dissection (docs/refs/dissection-fire-pit.md, corrected 2026-10-24): flame
# jets that shoot out of the spot, spiky flame shards fanned around them, the scorch left on the
# floor, and the hot spot under the fire.


def _fire_bands(d, w, px, pal):
    """Three flat bands inset along a shape's own outline: a red rim, an orange body and a
    cream core. `d` is the signed distance (negative inside), `w` the local half-width."""
    rim = np.clip(-d / px + 0.5, 0, 1)
    body = np.clip((-d - 0.28 * w) / px + 0.5, 0, 1)
    core = np.clip((-d - 0.55 * w) / px + 0.5, 0, 1)
    rgb = np.zeros(d.shape + (3,), np.float32)
    for m, c in ((rim, pal[0]), (body, pal[1]), (core, pal[2])):
        rgb = rgb * (1 - m[..., None]) + np.array(c, np.float32) * m[..., None]
    return rim, rgb


@recipe("flame_jet", count=4, width=0.24, teeth=3, bite=0.045, palette="fire")
def flame_jet(p, rng, size):
    """Flame jets for the ignition: long, tapered, a cream core inside orange and a red rim,
    their edges jagged with hook teeth swept back toward the base. Each jet is drawn in its
    cell's top half with its base on the centre line, so a particle placed on the spot pivots
    on the jet's base and the jet points along its velocity (VelocityParallel)."""
    u, v = lib.grid(size)
    pal = PALETTES[p["palette"]]
    px = 2.0 / size
    cells = []
    for _ in range(int(p["count"])):
        length = rng.uniform(0.85, 0.95)
        t = np.clip(-v / length, 0, 1)  # 0 at the base (centre line), 1 at the tip
        bend = rng.uniform(-0.08, 0.08) * t * t
        half = p["width"] * rng.uniform(0.8, 1.15) * (1 - t) ** 1.15 * (0.6 + 0.4 * lib.smooth(0.0, 0.08, t))
        # a few hooks in the lower half, swept back toward the base, each its own size and
        # place; the rest of the jet is a smooth taper (the fire pit's jets)
        off_l = np.zeros_like(u)
        off_r = np.zeros_like(u)
        for _ in range(int(p["teeth"])):
            at = rng.uniform(0.12, 0.55)
            span = rng.uniform(0.08, 0.14)
            f = np.clip((t - (at - span)) / span, 0, 1) * (t < at)
            hook = f ** 2.2 * p["bite"] * rng.uniform(0.6, 1.3) * (1 - at)
            if rng.uniform() < 0.5:
                off_l = np.maximum(off_l, hook)
            else:
                off_r = np.maximum(off_r, hook)
        off = np.where(u - bend > 0, off_r, off_l)
        d = np.abs(u - bend) - (half + off)
        d = np.where((v <= 0) & (t < 1), d, 1.0)
        a, rgb = _fire_bands(d, np.maximum(half, 1e-3), px, pal)
        a = a * (1 - lib.smooth(-0.02, 0.01, v))
        cells.append({"alpha": a * lib.vignette(u, v, 0.94, 0.99), "rgb": rgb})
    return cells


# The fire pit's left jet at f8, boxed tightly along its axis and unwarped into the square
# (Phát, 2026-10-24: "box their texture and then warp it ... so we can see this shape clearly"),
# then outlined by Phát by hand over that mask: the scattered bits and the spur around it belong
# to other layers. A thick body whose sides bulge out; only the dip between the two tips curves in.
# His line is hand-drawn and shaky, so each run of it became one cubic Bezier fitted to it, not a
# copy of it (Phát: "use a single function to describe each curve"). Then the jet was turned 20
# degrees clockwise to stand straight up, the left crease (the small tip to the tall one) became
# one smooth curve mirrored from the right crease, and both creases were deepened 1.8 times with
# the tips where they were (Phát picked from four depths). Four curves, each (start, control,
# control, end), each starting where the last ended, so the tips are corners: up the left side
# to the small tip, the left crease up to the tall tip, the right crease down to the right tip,
# and down the right side. (x, y) in 0..1, y down, the base at y = 1; the right side runs on
# past it.
SPIRE_CURVES = (
    ((0, 1), (0.002, 0.842), (0.024, 0.685), (0.056, 0.513)),
    ((0.056, 0.513), (0.288, 0.77), (0.35, 0.243), (0.447, 0)),
    ((0.447, 0), (0.556, 0.243), (0.626, 0.623), (0.888, 0.366)),
    ((0.888, 0.366), (0.969, 0.583), (0.974, 0.958), (1, 1.194)),
)


def _spire_outline(curves, turn=0.0, margin=0.03, n=120):
    """The jet's outline as a polygon: the curves end to end, turned `turn` degrees clockwise to
    stand it up, then fitted back into the box: the tip at y = 0 and the higher of the two ends at
    y = 1, so the base cuts straight across and runs on below it. `margin` keeps the sides off the
    texture's edges."""
    t = np.linspace(0, 1, n, endpoint=False)[:, None]
    line = []
    for c in curves:
        p0, p1, p2, p3 = (np.array(q, np.float64) for q in c)
        line.append((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)
    line = np.vstack(line + [np.array(curves[-1][-1:], np.float64)])
    a = math.radians(turn)
    x, y = line[:, 0] - 0.5, line[:, 1] - 1.0
    line = np.stack([x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)], 1)
    line[:, 0] = (line[:, 0] - line[:, 0].min()) / np.ptp(line[:, 0])
    top, base = line[:, 1].min(), min(line[0, 1], line[-1, 1])
    line[:, 1] = (line[:, 1] - top) / (base - top)
    line[:, 0] = margin + (1 - 2 * margin) * line[:, 0]
    return [(line[0, 0], 1.5)] + line.tolist() + [(line[-1, 0], 1.5)]


@recipe("flame_spire", rim=0.1, core=0.26, turn=0.0, palette="fire")
def flame_spire(p, rng, size):
    """One flame jet for a Beam (the fire pit's f8-9), traced from the reference's left jet: a thick body
    with a tall tip left of the middle, a dip, a lower tip on the right and a small step tip low on
    the left, in a red rim, an orange body and a cream core inset along its outline.
    Laid along U for a Beam, Attachment0 at the base: the base is the texture's left edge and the
    peaks point right, so TextureMode Stretch with TextureLength 1 fits the jet to the beam.
    `rim` and `core` set where the body and the core start, as shares of the shape's deepest
    inset; `rim` 0 leaves two tones, as the fire pit's jets have. `turn` leans the
    jet clockwise in degrees (0 stands it upright). Animate the Beam, not the texture: it flashes in, then narrows (Width0/Width1) as it
    stretches out (Attachment1)."""
    u, v = lib.grid(size)
    pal = PALETTES[p["palette"]]
    px = 2.0 / size
    # the sketch's y runs from the peak (0) to the base (1): along the beam, base at the left
    # the base runs on past the texture's edge, so the bands inset from the sides only and
    # the base stays solid where the jet leaves the spot
    pts = [(1 - 2 * y, 2 * x - 1) for x, y in _spire_outline(SPIRE_CURVES, p["turn"])]
    d = lib.polygon(u, v, pts)
    deep = float(-d.min())
    rim = np.clip(-d / px + 0.5, 0, 1)
    body = np.clip((-d - p["rim"] * deep) / px + 0.5, 0, 1)
    core = np.clip((-d - p["core"] * deep) / px + 0.5, 0, 1)
    rgb = np.zeros(d.shape + (3,), np.float32)
    for m, c in ((rim, pal[0]), (body, pal[1]), (core, pal[2])):
        rgb = rgb * (1 - m[..., None]) + np.array(c, np.float32) * m[..., None]
    # clear of the top and bottom edges; the base stays solid to the left edge
    return {"alpha": rim * (1 - lib.smooth(0.96, 0.995, np.abs(v))), "rgb": rgb}


@recipe("flame_shards", count=16, width=0.1, kinks=3, palette="fire")
def flame_shards(p, rng, size):
    """Spiky flame shards fanned around the jets: a jagged zigzag spike like a flame-coloured
    lightning bolt, wide at its base and a needle at its tip, sometimes with a barb, in the
    same three bands. They point up the cell (VelocityParallel)."""
    u, v = lib.grid(size)
    pal = PALETTES[p["palette"]]
    px = 2.0 / size
    cells = []
    for _ in range(int(p["count"])):
        n = int(p["kinks"]) + int(rng.integers(0, 2))
        ys = np.linspace(0.85, -0.88, n + 1)
        xs = np.cumsum(rng.uniform(-0.3, 0.3, n + 1)) * 0.7
        xs -= np.linspace(xs[0], xs[-1], n + 1) * 0.6
        pts = list(zip(xs.tolist(), ys.tolist()))
        w = p["width"] * rng.uniform(0.8, 1.4)
        d, s, across = lib.stroke(u, v, pts, lambda tt: w * (1 - tt) ** 1.1 + 1e-4)
        if rng.uniform() < 0.6:
            i = int(rng.integers(1, n))
            bx, by = pts[i]
            tip = (bx + rng.choice([-1, 1]) * rng.uniform(0.18, 0.3), by - rng.uniform(0.12, 0.25))
            bd, _, _ = lib.stroke(u, v, [(bx, by), tip], [w * 0.6, 1e-4])
            d = np.minimum(d, bd)
        a, rgb = _fire_bands(d, np.full(d.shape, w, np.float32), px, pal)
        cells.append({"alpha": a * lib.vignette(u, v, 0.92, 0.99), "rgb": rgb})
    return cells


@recipe("ground_scorch", spikes=13, disc=0.36, reach=0.95)
def ground_scorch(p, rng, size):
    """The scorch left on the floor (a decal, normal blend, tinted dark): a hard-edged dark disc
    with a ragged rim and dark spikes radiating out from it, as the fire pit's floor shows from
    the jets on."""
    u, v = lib.grid(size)
    r, a = lib.polar(u, v)
    seed = _seed(rng)
    rim = (lib.fbm(u.shape, 6, 4, seed=seed) - 0.5) * 0.09
    px = 2.0 / size
    disc = np.clip((p["disc"] + rim - r) / (px * 1.5) + 0.5, 0, 1) * 0.85
    spikes = np.zeros_like(u)
    n = int(p["spikes"])
    for k in range(n):
        ang = 2 * np.pi * (k + rng.uniform(-0.3, 0.3)) / n
        reach = p["reach"] * rng.uniform(0.55, 1.0)
        width = rng.uniform(0.05, 0.09)
        da = (a - ang + np.pi) % (2 * np.pi) - np.pi
        t = np.clip((r - p["disc"] * 0.8) / (reach - p["disc"] * 0.8), 0, 1)
        half = width * (1 - t) ** 1.3
        d = np.abs(da * r) - half
        spike = np.clip(-d / (px * 1.5) + 0.5, 0, 1) * (r > p["disc"] * 0.8) * (t < 1) * (0.75 - 0.35 * t)
        spikes = np.maximum(spikes, spike)
    return np.clip(np.maximum(disc, spikes), 0, 1) * lib.vignette(u, v, 0.94, 0.99)


@recipe("hot_spot", falloff=1.6, palette="fire")
def hot_spot(p, rng, size):
    """The hot spot on the ground under a fire: a soft disc of light, cream-yellow in the
    middle, orange, then red toward its round edge."""
    u, v = lib.grid(size)
    r = np.sqrt(u * u + v * v)
    pal = PALETTES[p["palette"]]
    alpha = np.exp(-p["falloff"] * r * r * 2.2) * (1 - lib.smooth(0.55, 0.97, r))
    heat = np.clip(1 - r / 0.75, 0, 1)
    red, orange, cream = (np.array(c, np.float32) for c in pal)
    mid = heat[..., None]
    rgb = np.where(mid > 0.5, orange + (cream - orange) * ((mid - 0.5) * 2), red + (orange - red) * (mid * 2))
    return {"alpha": alpha, "rgb": rgb.astype(np.float32)}


@recipe("shard_ring", frames=16, shards=12, inner=0.3, push=0.32, length=0.42, width=0.07, palette="fire")
def shard_ring(p, rng, size):
    """A full ring of spiky flame shards around a hollow middle (Phát, from the fire pit's f9: the
    shards around the core are one shape): jagged, curved spikes of uneven length pointing out,
    in the fire bands. As a OneShot flipbook the ring blasts outward and thins, so the motion the
    30 fps reference implies lives in the texture: out fast, slowing, then gone."""
    u, v = lib.grid(size)
    pal = PALETTES[p["palette"]]
    px = 2.0 / size
    n = int(p["shards"])
    shards = []
    for k in range(n):
        shards.append({
            "a": 2 * np.pi * (k + rng.uniform(-0.3, 0.3)) / n,
            "len": p["length"] * rng.uniform(0.45, 1.0),
            "w": p["width"] * rng.uniform(0.7, 1.3),
            "curve": rng.uniform(-0.5, 0.5),
            "zig": rng.uniform(0.04, 0.09) * rng.choice([-1, 1]),
            "barb": rng.uniform() < 0.45,
            "start": rng.uniform(-0.04, 0.06),
        })
    out = []
    count = _frames(p)
    for j in range(count):
        t = j / max(1, count - 1)
        go = float(lib.ease_out(t, 2.6))
        fade = 1 - float(lib.smooth(0.55, 1.0, t))
        d_all = np.full(u.shape, 9.0, np.float32)
        for sh in shards:
            r0 = p["inner"] + sh["start"] + p["push"] * go
            length = sh["len"] * (0.55 + 0.45 * float(lib.smooth(0.0, 0.25, t))) * (1 - 0.35 * t)
            pts = []
            for i in range(6):
                s = i / 5
                ang = sh["a"] + sh["curve"] * s * s * 0.6 + (sh["zig"] if i in (2, 4) else 0) / max(r0, 0.1)
                rr = r0 + length * s
                pts.append((rr * np.cos(ang), rr * np.sin(ang)))
            w = sh["w"] * (1 - 0.5 * t)
            d, _, _ = lib.stroke(u, v, pts, lambda tt: w * (1 - tt) ** 1.15 + 1e-4)
            if sh["barb"]:
                bx, by = pts[2]
                ang = sh["a"] + rng.uniform(0.5, 0.9) * rng.choice([-1, 1])
                tip = (bx + 0.6 * length * 0.5 * np.cos(ang), by + 0.6 * length * 0.5 * np.sin(ang))
                bd, _, _ = lib.stroke(u, v, [(bx, by), tip], [w * 0.6, 1e-4])
                d = np.minimum(d, bd)
            d_all = np.minimum(d_all, d)
        a, rgb = _fire_bands(d_all, np.full(u.shape, p["width"] * (1 - 0.5 * t), np.float32), px, pal)
        out.append({"alpha": a * fade * lib.vignette(u, v, 0.95, 0.995), "rgb": rgb})
    out[-1]["alpha"] = out[-1]["alpha"] * 0
    return out

