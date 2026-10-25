"""Numbers for a texture, so a look is matched by measurement instead of by description.

    texgen measure <png|id> [--grid N] [--json]             a cell-by-cell table
    texgen compare <a> <b> [--grid N] [--out overlay.png]   the gap, scored, with an overlay
    texgen fit <id|recipe:name> <reference.png> --space space.json [--grid N] [--iters K]

A cell is read as one grayscale image (brightness times alpha). Its silhouette is where it is
brighter than SIL. Every number is a share of the cell or a ratio, so cells of different sizes
compare. The prototype that proved the approach: matching a downloaded fire splash sheet
(2026-10-24), where measuring showed the reference is dim at its edges and bright inside, the
opposite of the description written from looking at it.
"""

import json
import os
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import bank

SIL = 0.25

# how far apart two values may sit before they count as one unit of difference
TOL = {
    "fill": 0.04, "margin": 0.03, "solidity": 0.04, "elong": 0.25, "roundness": 0.15, "thick": 0.025,
    "edge_b": 0.05, "mid_b": 0.05, "core_b": 0.05, "soft": 0.015, "peak": 0.05,
    "horns": 0.75, "horn_len": 0.04, "horn_thick": 0.02,
    "streak": 0.15, "fft_low": 0.08, "fft_mid": 0.06, "fft_high": 0.03,
    "radial_0": 0.08, "radial_1": 0.08, "radial_2": 0.08, "radial_3": 0.08, "radial_4": 0.08,
}
SCALARS = list(TOL)


# ------------------------------------------------------------------ loading


def load(src):
    """A png path or a bank id: (brightness 0..1 as (h, w), rgb 0..1 as (h, w, 3) or None if it
    is grey). Brightness is the colour's luma times alpha, so white-with-alpha textures and
    plain grey images read the same."""
    if os.path.exists(os.path.expanduser(src)):
        img = Image.open(os.path.expanduser(src))
        rgba = np.asarray(img.convert("RGBA"), np.float32) / 255
    else:
        i = bank.resolve([src])[0]
        raw = bank.read(i)
        if raw is None:
            raw, _ = bank.render(i)
        rgba = raw.astype(np.float32) / 255
    h, w = rgba.shape[:2]
    if h != w:
        # cells are square: centre a non-square image on a clear square
        n = max(h, w)
        sq = np.zeros((n, n, 4), np.float32)
        sq[(n - h) // 2:(n - h) // 2 + h, (n - w) // 2:(n - w) // 2 + w] = rgba
        rgba = sq
    return _split(rgba)


def _split(rgba):
    rgb, a = rgba[..., :3], rgba[..., 3]
    luma = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    bright = luma * a
    colour = rgb if float(np.abs(rgb - luma[..., None]).max()) > 0.04 else None
    return bright, colour


def cells(img, grid):
    n = img.shape[0] // grid
    return [img[r * n:(r + 1) * n, c * n:(c + 1) * n] for r in range(grid) for c in range(grid)]


# ------------------------------------------------------------------ shape helpers


def depth(mask):
    """Pixel distance into the mask (chessboard), by repeated 3x3 erosion."""
    img = Image.fromarray((mask * 255).astype(np.uint8))
    d = np.zeros(mask.shape, np.float32)
    cur = mask.copy()
    while cur.any():
        d += cur
        img = img.filter(ImageFilter.MinFilter(3))
        cur = np.asarray(img) > 127
    return d


def hull_area(ys, xs):
    pts = sorted(set(zip(xs.tolist(), ys.tolist())))
    if len(pts) < 3:
        return float(len(pts))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    h = lo[:-1] + hi[:-1]
    x = np.array([q[0] for q in h], float)
    y = np.array([q[1] for q in h], float)
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def outline(mask):
    pad = np.pad(mask, 1)
    return mask & ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])


def skeleton(mask):
    """Zhang-Suen thinning: the mask worn down to one-pixel lines through its middle."""
    s = np.pad(mask.astype(np.uint8), 1)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p2, p3, p4, p5 = s[:-2, 1:-1], s[:-2, 2:], s[1:-1, 2:], s[2:, 2:]
            p6, p7, p8, p9 = s[2:, 1:-1], s[2:, :-2], s[1:-1, :-2], s[:-2, :-2]
            ring = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            nb = sum(x.astype(int) for x in ring[:8])
            flips = sum(((ring[i] == 0) & (ring[i + 1] == 1)).astype(int) for i in range(8))
            if step == 0:
                side = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                side = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            gone = (s[1:-1, 1:-1] == 1) & (nb >= 2) & (nb <= 6) & (flips == 1) & side
            if gone.any():
                s[1:-1, 1:-1][gone] = 0
                changed = True
    return s[1:-1, 1:-1].astype(bool)


_NB8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def horns(mask, d):
    """The shape's horns: thin parts that stick out of the body. Each skeleton tip's branch is
    walked inward to the first junction (or, on a lone line, to its deepest point); the stretch
    from the tip until the shape is half as thick as its thickest part is the horn, and it
    counts when it is longer than a quarter of that thickness. Returns a list of (length,
    thickness) in pixels: how far it sticks out, and its mean width."""
    sk = skeleton(mask)
    pts = set(zip(*np.nonzero(sk)))

    def nbs(p):
        return [(p[0] + dy, p[1] + dx) for dy, dx in _NB8 if (p[0] + dy, p[1] + dx) in pts]

    tips = [p for p in pts if len(nbs(p)) == 1]
    dmax = float(d.max())
    out = []
    for tip in tips:
        path, prev, cur = [tip], None, tip
        while True:
            nxt = [q for q in nbs(cur) if q != prev and q not in path[-3:]]
            if len(nxt) == 2 and max(abs(nxt[0][0] - nxt[1][0]), abs(nxt[0][1] - nxt[1][1])) == 1:
                # a staircase step on the thinned line, not a fork: take the straight neighbour
                nxt = [q for q in nxt if q[0] == cur[0] or q[1] == cur[1]][:1] or nxt[:1]
            if len(nxt) != 1 or len(path) > 4 * mask.shape[0]:
                break
            prev, cur = cur, nxt[0]
            path.append(cur)
        deep = np.array([d[p] for p in path])
        if len(nbs(path[-1])) <= 1:
            # a lone line, no junction: cut it at its deepest point
            k = int(np.argmax(deep))
            path, deep = path[: k + 1], deep[: k + 1]
        # the horn is the stretch from the tip until the shape is half as thick as its thickest
        # part; its length is measured along the line (diagonal steps count root 2)
        body = 0.5 * dmax
        k = int(np.argmax(deep >= body)) if (deep >= body).any() else len(path) - 1
        steps = np.diff(np.array(path[: k + 1], float), axis=0)
        stick = float(np.hypot(steps[:, 0], steps[:, 1]).sum()) if len(steps) else 0.0
        if stick > max(3.0, 0.5 * body):
            out.append((stick, float(2 * deep[: k + 1].mean())))
    return out


# ------------------------------------------------------------------ one cell


def measure_cell(a, rgb=None):
    """The numbers for one cell (brightness 0..1, square). None when it is empty."""
    n = a.shape[0]
    m = a > SIL
    area = int(m.sum())
    if area < 10:
        return None
    ys, xs = np.nonzero(m)
    out = {}
    out["fill"] = area / (n * n)
    out["margin"] = min(xs.min(), ys.min(), n - 1 - xs.max(), n - 1 - ys.max()) / n
    out["solidity"] = area / max(hull_area(ys, xs), 1)
    cov = np.cov(np.stack([xs, ys]).astype(float))
    ev, evec = np.linalg.eigh(cov)
    out["elong"] = float(np.sqrt(ev[1] / max(ev[0], 1e-6)))
    edge = outline(m)
    out["roundness"] = edge.sum() ** 2 / (4 * np.pi * area)
    d = depth(m)
    dmax = float(d.max())
    out["thick"] = dmax / n
    rel = d / max(dmax, 1)
    for key, (lo, hi) in zip(("edge_b", "mid_b", "core_b"), ((0, 0.33), (0.33, 0.66), (0.66, 1.01))):
        sel = (rel > lo) & (rel <= hi)
        out[key] = float(a[sel].mean()) if sel.any() else 0.0
    out["soft"] = ((a > 0.1) & (a < 0.6)).sum() / max(edge.sum(), 1) / n
    out["peak"] = float(a.max())

    smooth = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(1, n / 128))), np.float32) / 255
    hs = horns(smooth > SIL, depth(smooth > SIL))
    out["horns"] = float(len(hs))
    out["horn_len"] = float(np.mean([h[0] for h in hs]) / n) if hs else 0.0
    out["horn_thick"] = float(np.mean([h[1] for h in hs]) / n) if hs else 0.0
    out["horn_list"] = [[round(h[0] / n, 4), round(h[1] / n, 4)] for h in hs]

    # brightness from the silhouette's centre outward, in five rings out to its farthest pixel
    cy, cx = ys.mean(), xs.mean()
    yy, xx = np.mgrid[0:n, 0:n]
    rr = np.hypot(yy - cy, xx - cx)
    rmax = float(rr[m].max()) or 1.0
    for k in range(5):
        sel = (rr >= rmax * k / 5) & (rr < rmax * (k + 1) / 5)
        out[f"radial_{k}"] = float(a[sel].mean()) if sel.any() else 0.0

    # streaks: how strongly the brightness changes along one direction inside the shape
    # (structure tensor coherence, 0 none to 1 all lined up), and that direction against the
    # shape's main axis
    gy, gx = np.gradient(smooth)
    jxx, jyy, jxy = (gx * gx)[m].sum(), (gy * gy)[m].sum(), (gx * gy)[m].sum()
    tr = jxx + jyy
    out["streak"] = float(np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / tr) if tr > 1e-9 else 0.0
    grad_ang = 0.5 * np.arctan2(2 * jxy, jxx - jyy)
    axis_ang = np.arctan2(evec[1, 1], evec[0, 1])
    rel_ang = abs(((grad_ang + np.pi / 2) - axis_ang + np.pi / 2) % np.pi - np.pi / 2)
    out["streak_dir"] = float(np.degrees(rel_ang))

    # detail: the spectrum's energy (without its mean) in broad, middle and fine bands, in
    # cycles per cell: broad is the shape itself (under 4), middle its lumps (4 to 12), fine its
    # texture and hard edges (12 and up)
    f = np.abs(np.fft.fftshift(np.fft.fft2(a - a.mean()))) ** 2
    fy, fx = np.mgrid[-n // 2:n - n // 2, -n // 2:n - n // 2]
    fr = np.hypot(fy, fx)
    tot = float(f.sum()) or 1.0
    out["fft_low"] = float(f[fr < 4].sum() / tot)
    out["fft_mid"] = float(f[(fr >= 4) & (fr < 12)].sum() / tot)
    out["fft_high"] = float(f[fr >= 12].sum() / tot)

    if rgb is not None:
        out["colours"] = colours(rgb[m], 4)
    return {k: (float(v) if isinstance(v, (np.floating, float, int, np.integer)) else v) for k, v in out.items()}


def colours(px, k=4, iters=12):
    """A few dominant colours of the given pixels (k-means): [[hex, share], ...], biggest first."""
    px = px.reshape(-1, 3)
    if len(px) > 4000:
        px = px[np.random.default_rng(0).choice(len(px), 4000, replace=False)]
    k = min(k, len(px))
    c = px[np.linspace(0, len(px) - 1, k).astype(int)].copy()
    for _ in range(iters):
        lab = np.argmin(((px[:, None] - c[None]) ** 2).sum(-1), 1)
        for j in range(k):
            if (lab == j).any():
                c[j] = px[lab == j].mean(0)
    share = np.bincount(lab, minlength=k) / len(px)
    order = np.argsort(-share)
    return [["#%02x%02x%02x" % tuple(int(v * 255) for v in c[j]), round(float(share[j]), 3)] for j in order]


# ------------------------------------------------------------------ images


def measure(src, grid=1):
    """Every cell's numbers and their means, for a png or a bank id."""
    bright, rgb = load(src) if isinstance(src, str) else src
    cs = cells(bright, grid)
    rs = cells(rgb, grid) if rgb is not None else [None] * len(cs)
    per = [measure_cell(np.clip(c, 0, 1), r) for c, r in zip(cs, rs)]
    return {"cells": per, "mean": means(per)}


def means(per):
    ok = [p for p in per if p]
    return {k: float(np.mean([p[k] for p in ok])) for k in SCALARS} if ok else {}


def table(result, label=""):
    per, mean = result["cells"], result["mean"]
    lines = [f"{label}{'':14s}" + "".join(f"  cell {i:<4d}" for i in range(len(per))) + "      mean"]
    for k in SCALARS:
        vals = "".join(f"  {p[k]:9.3f}" if p else "      empty" for p in per)
        lines.append(f"  {k:12s}{vals}  {mean.get(k, 0):9.3f}")
    for i, p in enumerate(per):
        if p and p.get("horn_list"):
            lines.append(f"  cell {i} horns (length, thickness): " + ", ".join(f"({a:.3f}, {b:.3f})" for a, b in p["horn_list"]))
        if p and p.get("colours"):
            lines.append(f"  cell {i} colours: " + ", ".join(f"{h} {s:.0%}" for h, s in p["colours"]))
    return "\n".join(lines)


def gap(ma, mb, skip=()):
    """Per-metric difference (b minus a) in tolerance units, and the total score (sum of squares).
    `skip` leaves metrics out, e.g. fill and margin when the reference is a tight crop."""
    diff = {k: (mb[k] - ma[k]) / TOL[k] for k in SCALARS if k in ma and k in mb and k not in skip}
    return diff, float(sum(v * v for v in diff.values()))


# ------------------------------------------------------------------ overlay


def _frame(m):
    ys, xs = np.nonzero(m)
    cov = np.cov(np.stack([xs, ys]).astype(float))
    _, v = np.linalg.eigh(cov)
    return xs.mean(), ys.mean(), np.arctan2(v[1, 1], v[0, 1]), m.sum()


def _place(src_pts, fa, fb, flip, extra):
    """Moves points from shape a's frame onto shape b's: centroid, main axis (turned `extra`,
    0 or pi) and area; `flip` mirrors across a's main axis first."""
    ax_, ay_, aa, aarea = fa
    bx, by, ba, barea = fb
    s = np.sqrt(barea / max(aarea, 1))
    dx, dy = src_pts[0] - ax_, src_pts[1] - ay_
    # into a's axis frame, maybe mirrored, then out along b's
    u = dx * np.cos(-aa) - dy * np.sin(-aa)
    w = dx * np.sin(-aa) + dy * np.cos(-aa)
    if flip:
        w = -w
    rot = ba + extra
    return bx + s * (u * np.cos(rot) - w * np.sin(rot)), by + s * (u * np.sin(rot) + w * np.cos(rot))


def aligned_iou(ca, cb):
    """Shape overlap (intersection over union) after laying a's silhouette onto b's by centroid,
    main axis and area, the best of the four ways the axis can match (turned, mirrored).
    Returns (iou, a's outline points placed on b) for the best fit."""
    ma, mb = ca > SIL, cb > SIL
    if ma.sum() < 10 or mb.sum() < 10:
        return 0.0, (np.array([]), np.array([]))
    fa, fb = _frame(ma), _frame(mb)
    n = cb.shape[0]
    ys, xs = np.nonzero(ma)
    eys, exs = np.nonzero(outline(ma))
    best = (-1.0, None)
    for flip in (False, True):
        for extra in (0.0, np.pi):
            px, py = _place((xs, ys), fa, fb, flip, extra)
            ok = (px >= 0) & (px < n) & (py >= 0) & (py < n)
            placed = np.zeros_like(mb)
            placed[py[ok].astype(int), px[ok].astype(int)] = True
            placed = np.asarray(Image.fromarray(placed.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(3)), np.uint8) > 127
            iou = float((placed & mb).sum() / max((placed | mb).sum(), 1))
            if iou > best[0]:
                best = (iou, _place((exs, eys), fa, fb, flip, extra))
    return best


def overlay(ca_list, cb_list, ma, mb, path, names=("a", "b")):
    """A sheet like the fit prototype's: a's cells, b's cells, b with a's outline laid over in
    cyan, and the numbers side by side. Cells are shown at 256 px."""
    C = 256
    g = int(np.ceil(np.sqrt(max(len(ca_list), len(cb_list)))))
    block = g * (C + 8)
    o = Image.new("RGB", (3 * (block + 16) + 16, block + 60 + 22 * (len(SCALARS) // 2 + 3)), (20, 20, 26))
    d = ImageDraw.Draw(o)
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:
        font = ImageFont.load_default()
    titles = (names[0], names[1], f"{names[1]} + {names[0]}'s outline (cyan)")
    for col, t in enumerate(titles):
        d.text((16 + col * (block + 16), 10), t, fill=(255, 230, 120), font=font)

    def cell_img(c):
        return Image.fromarray((np.clip(c, 0, 1) * 255).astype(np.uint8)).resize((C, C)).convert("RGB")

    ious = []
    for i in range(max(len(ca_list), len(cb_list))):
        r, k = divmod(i, g)
        y = 36 + r * (C + 8)
        if i < len(ca_list):
            o.paste(cell_img(ca_list[i]), (16 + k * (C + 8), y))
        if i < len(cb_list):
            o.paste(cell_img(cb_list[i]), (16 + block + 16 + k * (C + 8), y))
        if i < len(ca_list) and i < len(cb_list):
            ca, cb = ca_list[i], cb_list[i]
            iou, (px, py) = aligned_iou(ca, cb)
            ious.append(iou)
            img = np.stack([np.clip(cb, 0, 1) * 255] * 3, -1).astype(np.uint8)
            n = cb.shape[0]
            ok = (px >= 0) & (px < n) & (py >= 0) & (py < n)
            img[py[ok].astype(int), px[ok].astype(int)] = (60, 220, 255)
            o.paste(Image.fromarray(img).resize((C, C)), (16 + 2 * (block + 16) + k * (C + 8), y))
            d.text((16 + 2 * (block + 16) + k * (C + 8) + 4, y + 4), f"IoU {iou:.2f}", fill=(60, 220, 255), font=font)
    y = 50 + block
    diff, score = gap(ma, mb)
    short = [nm if len(nm) <= 12 else nm[:11] + "…" for nm in names]
    d.text((16, y), f"metric        {short[0]:>10s} {short[1]:>10s}   gap (tolerances)        score {score:.1f}", fill=(200, 200, 200), font=font)
    half = (len(SCALARS) + 1) // 2
    for j, k in enumerate(SCALARS):
        x0 = 16 + (j // half) * 760
        d.text((x0, y + 24 + (j % half) * 22), f"{k:12s} {ma.get(k, 0):10.3f} {mb.get(k, 0):10.3f}   {diff.get(k, 0):+7.2f}",
               fill=(255, 140, 120) if abs(diff.get(k, 0)) > 2 else (200, 200, 200), font=font)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    o.save(path)
    return ious


def compare(a, b, grid_a=1, grid_b=None, out=None):
    """The gap from a to b: both measured, the per-metric gap and score, IoU after alignment,
    and (with `out`) the overlay sheet."""
    grid_b = grid_b or grid_a
    la = load(a) if isinstance(a, str) else a
    lb = load(b) if isinstance(b, str) else b
    ra, rb = measure(la, grid_a), measure(lb, grid_b)
    diff, score = gap(ra["mean"], rb["mean"])
    ca, cb = cells(la[0], grid_a), cells(lb[0], grid_b)
    if out:
        ious = overlay(ca, cb, ra["mean"], rb["mean"], out,
                       names=(os.path.basename(a) if isinstance(a, str) else "a", os.path.basename(b) if isinstance(b, str) else "b"))
    else:
        ious = [aligned_iou(x, y)[0] for x, y in zip(ca, cb)]
    return {"a": ra, "b": rb, "diff": diff, "score": score, "iou": ious}


# ------------------------------------------------------------------ fitting


def _draw(space, rng):
    """One random setting from a search space. Values: [lo, hi] a float; {"int": [lo, hi]} an
    integer; {"pair": [[lo, hi], [span_lo, span_hi]]} a (low, low + span) range knob;
    {"choice": [...]} one of; anything else is fixed."""
    out = {}
    for k, s in space.items():
        if isinstance(s, list) and len(s) == 2 and all(isinstance(v, (int, float)) for v in s):
            out[k] = float(rng.uniform(*s))
        elif isinstance(s, dict) and "int" in s:
            out[k] = int(rng.integers(s["int"][0], s["int"][1] + 1))
        elif isinstance(s, dict) and "pair" in s:
            lo = float(rng.uniform(*s["pair"][0]))
            out[k] = (lo, lo + float(rng.uniform(*s["pair"][1])))
        elif isinstance(s, dict) and "choice" in s:
            out[k] = s["choice"][int(rng.integers(len(s["choice"])))]
        else:
            out[k] = s
    return out


def _nudge(x, space, rng, step):
    out = dict(x)
    for k, s in space.items():
        if isinstance(s, list) and len(s) == 2 and all(isinstance(v, (int, float)) for v in s):
            out[k] = float(np.clip(x[k] + rng.normal(0, step) * (s[1] - s[0]), *s))
        elif isinstance(s, dict) and "int" in s and rng.random() < step:
            out[k] = int(np.clip(x[k] + rng.choice([-1, 1]), *s["int"]))
        elif isinstance(s, dict) and "pair" in s:
            lo0, hi0 = x[k]
            lo = float(np.clip(lo0 + rng.normal(0, step) * np.ptp(s["pair"][0]), *s["pair"][0]))
            span = float(np.clip((hi0 - lo0) + rng.normal(0, step) * np.ptp(s["pair"][1]), *s["pair"][1]))
            out[k] = (lo, lo + span)
        elif isinstance(s, dict) and "choice" in s and rng.random() < step:
            out[k] = s["choice"][int(rng.integers(len(s["choice"])))]
    return out


def render_cells(target, params, seed, cell=128, frames=8):
    """A target's cells as brightness: a bank id (split by its own grid) or `recipe:<name>`,
    drawn straight from the recipe with `frames` cells of `cell` px."""
    import recipes

    if target.startswith("recipe:"):
        name = target.split(":", 1)[1]
        p = dict(recipes.DEFAULTS[name], **params)
        if "frames" in recipes.DEFAULTS[name]:
            p["frames"] = frames
        out = recipes.RECIPES[name](p, np.random.default_rng(seed), cell)
        out = out if isinstance(out, list) else [out]
        res = []
        for o in out:
            if isinstance(o, dict):
                rgb = o.get("rgb")
                a = o["alpha"] * (rgb @ np.array([0.299, 0.587, 0.114], np.float32) if rgb is not None else 1)
            else:
                a = o
            res.append(np.clip(np.asarray(a, np.float32), 0, 1))
        return res
    e = bank.get(target)
    rgba, _ = bank.render(target, seed=seed, **params)
    bright, _ = _split(rgba.astype(np.float32) / 255)
    return cells(bright, int(e.get("grid", 1)))


def fit(target, reference, space, grid=1, iters=300, refine=160, cell=128, log=print, skip=()):
    """Searches `space` for the target's settings whose measured means come closest to the
    reference's: random draws, then a local refine around the best few, each scored on two
    seeds so one lucky layout doesn't win."""
    ref = measure(reference, grid)["mean"]
    rng = np.random.default_rng(0)

    def score(x):
        total, mean = 0.0, None
        for seed in (1, 2):
            per = [measure_cell(c) for c in render_cells(target, x, seed, cell)]
            if sum(p is not None for p in per) < max(1, len(per) // 2):
                return 1e9, None
            mean = means(per)
            total += gap(ref, mean, skip)[1]
        return total / 2, mean

    tried = []
    for _ in range(iters):
        x = _draw(space, rng)
        s, m = score(x)
        tried.append((s, x, m))
    tried.sort(key=lambda t: t[0])
    log(f"random search: {iters} tried, best score {tried[0][0]:.1f}")
    best = tried[0]
    for start in tried[:4]:
        cur = start
        for j in range(refine // 4):
            x = _nudge(cur[1], space, rng, 0.12 if j < refine // 8 else 0.05)
            s, m = score(x)
            if s < cur[0]:
                cur = (s, x, m)
        if cur[0] < best[0]:
            best = cur
    log(f"refined: best score {best[0]:.1f}")
    return {"score": best[0], "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in best[1].items()},
            "means": best[2], "target": ref}
