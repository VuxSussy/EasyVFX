"""texgen selftest: the primitives' maths, one planted bad case per check (each must fail
with its reason), and every bank recipe rendered small and passing the checks."""

import os

import numpy as np

import bank
import checks
import lib

_fails = []


def ok(cond, what):
    if not cond:
        _fails.append(what)


def _seam(a):
    return checks.seam(a, 1)[0], checks.seam(a, 0)[0]


def primitives():
    s = (96, 96)
    for name, f in [("perlin", lib.perlin(s, 4, 1)), ("fbm", lib.fbm(s, 4, 4, seed=2)), ("ridged", lib.ridged(s, 4, 4, seed=3)),
                    ("worley", lib.worley(s, 6, 4)), ("worley edges", lib.worley(s, 6, 4, second=True))]:
        su, sv = _seam(f)
        ok(su < 2 and sv < 2, f"{name} tiles (seams {su:.2f}, {sv:.2f})")
        ok(f.min() >= 0 and f.max() <= 1, f"{name} stays in 0..1")
    n = lib.fbm(s, 3, 3, seed=5)
    w = lib.warp(n, lib.fbm(s, seed=6), lib.fbm(s, seed=7), 0.2)
    ok(max(_seam(w)) < 2, "a domain warp of a tiling field still tiles")
    line = lib.noise1(96, 4, 1)
    ok(abs(line[0] - line[-1]) < 3 * np.abs(np.diff(line)).mean() + 1e-3, "noise1 tiles")

    u, v = lib.grid(64)
    ok(lib.sd_circle(u, v, 0.5)[32, 32] < 0 < lib.sd_circle(u, v, 0.5)[0, 0], "circle: negative inside")
    ell = [(-0.6, -0.6), (0.6, -0.6), (0.6, -0.2), (-0.2, -0.2), (-0.2, 0.6), (-0.6, 0.6)]
    d = lib.polygon(u, v, ell)
    ok(d[50, 14] < 0 and d[50, 50] > 0 and d[14, 50] < 0, "concave polygon: inside the arms, outside the notch")
    ok(lib.sd_star(u, v, 5, 0.9, 0.3)[32, 32] < 0, "star: centre inside")
    m = np.ones(s, np.float32)
    ok(lib.erode(m, n, 0).min() == 1 and lib.erode(m, n, 1).max() == 0, "erosion keeps all at 0 and removes all at 1")
    half = lib.erode(m, n, 0.5)
    ok(0.2 < half.mean() < 0.8, "erosion at 0.5 removes part")
    at = lib.atlas([np.full((2, 2), i, np.float32) for i in range(16)], 4)
    ok(at[0, 2] == 1 and at[2, 0] == 4 and at[7, 7] == 15, "atlas: left to right, top to bottom")

    pts = [(-0.6, 0.0), (0.6, 0.0)]
    dr, s_, across = lib.stroke(u, v, pts, 0.1)
    dc, _, _ = lib.stroke(u, v, pts, 0.1, caps=False)
    col = int((-0.65 + 1) / 2 * 64)
    ok(dr[32, col] < 0 < dc[32, col], "stroke: round caps by default, square with caps=False")
    ok(s_[32, 8] < 0.1 and s_[32, 56] > 0.9, "stroke: s runs from the first point to the last")
    ok(across[28, 32] * across[36, 32] < 0, "stroke: across changes sign from one edge to the other")
    sp = lib.spectrum(np.array([0.0, 1.0]))
    ok(sp[0, 0] > 0.9 and sp[0, 2] < 0.1 and sp[1, 2] > 0.9, "spectrum: red to violet")


def planted():
    good = np.zeros((64, 64, 4), np.uint8)
    good[..., :3] = 255
    yy, xx = np.mgrid[0:64, 0:64]
    good[..., 3] = (np.clip(1 - np.hypot(xx - 31.5, yy - 31.5) / 20, 0, 1) * 255).astype(np.uint8)
    shape = {"kind": "shape"}
    ok(checks.check(shape, good) == [], "a clean sprite passes")

    def fails(entry, rgba, word, what):
        got = checks.check(entry, rgba)
        ok(any(word in f for f in got), f"planted {what} fails ({got or 'passed'})")

    fails(shape, good[:, :48], "powers of two", "non power-of-two size")
    big = np.zeros((2048, 2048, 4), np.uint8)
    big[..., :3] = 255
    big[1000:1050, 1000:1050, 3] = 255
    fails(shape, big, "at most 1024", "size over 1024")
    col = good.copy()
    col[..., 0] = 200
    fails(shape, col, "not white", "coloured RGB")
    ok(checks.check({"kind": "shape", "rgb": "spectrum"}, col) == [], "coloured RGB allowed with rgb: spectrum")
    grey = good.copy()
    grey[..., :3] = 180
    ok(checks.check({"kind": "shape", "rgb": "luma"}, grey) == [], "grey RGB allowed with rgb: luma")
    fails({"kind": "shape", "rgb": "luma"}, col, "isn't grey", "rgb: luma with coloured RGB")
    edge = good.copy()
    edge[:, 0, 3] = 120
    fails(shape, edge, "border", "sprite touching its border")
    fails({"kind": "sheet", "grid": 3}, good, "divide", "grid that does not divide the size")
    book = np.concatenate([np.concatenate([good] * 4, 1)] * 4, 0)
    flip = {"kind": "flipbook", "grid": 4, "dissolve": True}
    fails(flip, book, "last frame", "dissolve whose last frame is not empty")
    fails({"kind": "flipbook", "grid": 4, "frames": 12}, book, "frames", "flipbook short of frames")
    strip = np.zeros((32, 128, 4), np.uint8)
    strip[..., :3] = 255
    x = np.arange(128)
    strip[8:24, :, 3] = (127 + 120 * np.sin(x / 128 * 2 * np.pi * 3))[None, :].astype(np.uint8)
    ok(checks.check({"kind": "strip"}, strip) == [], "a strip that tiles passes")
    bad = strip.copy()
    bad[8:24, :, 3] = (x * 2)[None, :].astype(np.uint8)
    fails({"kind": "strip"}, bad, "edges don't match", "strip with a seam")
    tall = strip.copy()
    tall[0:2, :, 3] = 200
    fails({"kind": "strip"}, tall, "top or bottom", "strip reaching its top edge")
    src = np.zeros((64, 64, 4), np.uint8)
    src[..., :3] = 255
    src[..., 3] = (np.arange(64) * 4)[:, None].astype(np.uint8)
    fails({"kind": "source"}, src, "top and bottom", "source that doesn't tile vertically")


def recipes_small():
    for i in bank.ids():
        e = bank.get(i)
        size = 512 if e.get("grid", 1) > 1 else 256 if e["kind"] == "strip" else 128
        rgba, meta = bank.render(i, size=size)
        got = checks.check(dict(e, frames=meta["frames"]), rgba)
        ok(got == [], f"{i} at {size}px passes its checks ({'; '.join(got)})")
        ok(not os.path.exists(os.path.join(bank.UPLOADED, bank.filename(i))), f"{i}: its file name is free in pack/textures")
    a, _ = bank.render("shape/cross_flare", size=128)
    b, _ = bank.render("shape/cross_flare", size=128)
    ok((a == b).all(), "the same id and seed draw the same texture")
    c, _ = bank.render("shape/godray_fan", size=128, seed=99)
    d, _ = bank.render("shape/godray_fan", size=128)
    ok((c != d).any(), "another seed draws another take")
    rgba, _ = bank.render("flip/flame_tongue", size=256)
    cells = checks.cells(rgba[..., 3].astype(np.float32) / 255, 4)
    steps = [np.abs(cells[k + 1] - cells[k]).mean() for k in range(15)]
    wrap = np.abs(cells[0] - cells[-1]).mean()
    ok(wrap < 2.5 * np.mean(steps), f"flame loop: the last frame flows into the first ({wrap:.4f} vs {np.mean(steps):.4f})")
    try:
        bank.get("shape/core_flsh")
        ok(False, "an unknown id is refused")
    except bank.BankError as ex:
        ok("core_flash" in str(ex), "an unknown id names the closest ones")


def run():
    primitives()
    planted()
    recipes_small()
    for f in _fails:
        print("FAIL", f)
    print(f"texgen selftest: {'ok' if not _fails else str(len(_fails)) + ' failed'}")
    return 1 if _fails else 0
