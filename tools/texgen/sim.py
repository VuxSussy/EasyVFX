"""Fluid-simulated flipbooks for library v4: smoke and explosions that billow because they
are simulated, not drawn. A 2D stable-fluids solver (semi-Lagrangian advection, Jacobi
pressure projection, vorticity confinement, buoyancy) in Taichi.

Taichi has no wheel for the project's Python, so the sims run in their own environment
and their results are baked into pack/ like any texture; nothing else needs Taichi:

    uv venv -p 3.12 .venv-sim && uv pip install -p .venv-sim/bin/python taichi numpy Pillow
    .venv-sim/bin/python tools/texgen/sim.py smoke_puff -o out.npz   # texgen's `bake` does this

Each sim returns 16 frames of density (alpha) and light (a grey RGB: self-shadowing from a
light at the top left, or heat for explosions), as float arrays in 0..1. `flame_loop` instead
returns a looping sequence of the raw heat field, which texgen's stylized flame recipes cut
into hard colour bands (tools/texgen/recipes.py, "stylized fire").
"""

import argparse
import math
import sys

import numpy as np

import taichi as ti

N = 256


def _init(arch):
    ti.init(arch=arch, random_seed=0, default_fp=ti.f32, offline_cache=True, log_level=ti.WARN)


@ti.data_oriented
class Fluid:
    def __init__(self, n=N):
        self.n = n
        self.vel = ti.Vector.field(2, ti.f32, (n, n))
        self.vel2 = ti.Vector.field(2, ti.f32, (n, n))
        self.dens = ti.field(ti.f32, (n, n))
        self.dens2 = ti.field(ti.f32, (n, n))
        self.heat = ti.field(ti.f32, (n, n))
        self.heat2 = ti.field(ti.f32, (n, n))
        self.p = ti.field(ti.f32, (n, n))
        self.p2 = ti.field(ti.f32, (n, n))
        self.div = ti.field(ti.f32, (n, n))
        self.curl = ti.field(ti.f32, (n, n))
        self.turb = ti.Vector.field(2, ti.f32, (n, n))

    @ti.func
    def sample(self, f: ti.template(), x: ti.f32, y: ti.f32):
        n = self.n
        x = ti.math.clamp(x, 0.0, n - 1.001)
        y = ti.math.clamp(y, 0.0, n - 1.001)
        i, j = int(x), int(y)
        fx, fy = x - i, y - j
        a = f[i, j] * (1 - fx) + f[i + 1, j] * fx
        b = f[i, j + 1] * (1 - fx) + f[i + 1, j + 1] * fx
        return a * (1 - fy) + b * fy

    @ti.kernel
    def advect(self, dt: ti.f32, keep_d: ti.f32, keep_h: ti.f32):
        for i, j in self.vel:
            v = self.vel[i, j]
            mid = ti.Vector([i - 0.5 * dt * v.x, j - 0.5 * dt * v.y])
            vm = self.sample(self.vel, mid.x, mid.y)
            x, y = i - dt * vm.x, j - dt * vm.y
            self.vel2[i, j] = self.sample(self.vel, x, y) * 0.999
            self.dens2[i, j] = self.sample(self.dens, x, y) * keep_d
            self.heat2[i, j] = self.sample(self.heat, x, y) * keep_h
        for i, j in self.vel:
            self.vel[i, j] = self.vel2[i, j]
            self.dens[i, j] = self.dens2[i, j]
            self.heat[i, j] = self.heat2[i, j]

    @ti.kernel
    def stir(self, dt: ti.f32, amount: ti.f32):
        """Curl noise where there is smoke, so it breaks into billows instead of sliding."""
        for i, j in self.vel:
            self.vel[i, j] += dt * amount * self.turb[i, j] * ti.min(self.dens[i, j] * 3.0, 1.0)

    @ti.kernel
    def forces(self, dt: ti.f32, buoyancy: ti.f32, swirl: ti.f32):
        n = self.n
        for i, j in self.curl:
            if 0 < i < n - 1 and 0 < j < n - 1:
                self.curl[i, j] = 0.5 * ((self.vel[i + 1, j].y - self.vel[i - 1, j].y) - (self.vel[i, j + 1].x - self.vel[i, j - 1].x))
        for i, j in self.vel:
            if 1 < i < n - 2 and 1 < j < n - 2:
                gx = 0.5 * (abs(self.curl[i + 1, j]) - abs(self.curl[i - 1, j]))
                gy = 0.5 * (abs(self.curl[i, j + 1]) - abs(self.curl[i, j - 1]))
                g = ti.Vector([gx, gy])
                g = g / (g.norm() + 1e-5)
                self.vel[i, j] += dt * swirl * ti.Vector([g.y, -g.x]) * self.curl[i, j]
            self.vel[i, j].y += dt * buoyancy * (self.heat[i, j] - 0.2 * self.dens[i, j])

    @ti.kernel
    def divergence(self):
        n = self.n
        for i, j in self.div:
            l = self.vel[max(i - 1, 0), j].x
            r = self.vel[min(i + 1, n - 1), j].x
            b = self.vel[i, max(j - 1, 0)].y
            t = self.vel[i, min(j + 1, n - 1)].y
            self.div[i, j] = 0.5 * (r - l + t - b)
            self.p[i, j] = 0.0

    @ti.kernel
    def jacobi(self):
        n = self.n
        for i, j in self.p:
            s = self.p[max(i - 1, 0), j] + self.p[min(i + 1, n - 1), j] + self.p[i, max(j - 1, 0)] + self.p[i, min(j + 1, n - 1)]
            self.p2[i, j] = (s - self.div[i, j]) * 0.25
        for i, j in self.p:
            self.p[i, j] = self.p2[i, j]

    @ti.kernel
    def project(self):
        n = self.n
        for i, j in self.vel:
            gx = 0.5 * (self.p[min(i + 1, n - 1), j] - self.p[max(i - 1, 0), j])
            gy = 0.5 * (self.p[i, min(j + 1, n - 1)] - self.p[i, max(j - 1, 0)])
            self.vel[i, j] -= ti.Vector([gx, gy])

    @ti.kernel
    def emit(self, cx: ti.f32, half: ti.f32, y0: ti.f32, y1: ti.f32, strength: ti.f32, sway: ti.f32, kick: ti.f32):
        """A flickering heat source at the bottom: heat and a little smoke in a short wide
        patch, with strength and sideways sway driven from outside by slow noise, so the
        flame above licks instead of rising as one column."""
        for i, j in self.heat:
            dx = (i - cx) / half
            if ti.abs(dx) < 1.0 and y0 <= j <= y1:
                w = (1.0 - dx * dx) ** 2
                self.heat[i, j] = ti.max(self.heat[i, j], strength * w)
                self.dens[i, j] = ti.max(self.dens[i, j], 0.6 * strength * w)
                self.vel[i, j].y += kick * w
                self.vel[i, j].x += sway * w

    def step(self, dt, keep_d=0.995, keep_h=0.97, buoyancy=0.0, swirl=0.0, iters=40, stir=0.0):
        if stir:
            self.stir(dt, stir)
        self.forces(dt, buoyancy, swirl)
        self.divergence()
        for _ in range(iters):
            self.jacobi()
        self.project()
        self.advect(dt, keep_d, keep_h)


def _noise(n, seed, cells=8):
    """Smooth random field (bicubic-upsampled lattice), -1..1."""
    from PIL import Image

    rng = np.random.default_rng(seed)
    small = rng.random((cells, cells)).astype(np.float32)
    big = np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC), np.float32) / 255
    return big * 2 - 1


def _blur(a, r):
    from PIL import Image, ImageFilter

    img = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8))
    return np.asarray(img.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255


def _edge_fade(n):
    """Fades to zero before the cell border, so a frame never clips (texgen's rule)."""
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    r = np.maximum(np.abs(x + 0.5 - n / 2), np.abs(y + 0.5 - n / 2)) / (n / 2)
    t = np.clip((r - 0.78) / 0.18, 0, 1)
    return 1 - t * t * (3 - 2 * t)


def _light(dens, k=2.2, shift=(10, 10), soft=6):
    """Self-shadowing from a light at the top left: density blurred and moved toward the
    light, so the lit side is bright and the far side falls into shade."""
    occ = _blur(np.clip(dens, 0, 1), soft)
    occ = np.roll(occ, shift, axis=(0, 1))
    return np.clip(np.exp(-k * occ) * 0.75 + 0.35 * np.clip(dens, 0, 1) ** 0.5, 0, 1)


def _curl_noise(n, seed, cells=24):
    """A divergence-free swirl field: the curl of a smooth random potential."""
    psi = _noise(n, seed, cells) + 0.5 * _noise(n, seed + 7, cells * 2)
    gy, gx = np.gradient(psi)
    v = np.stack([gy, -gx], -1)
    return v / (np.abs(v).max() + 1e-6)


def _setup_burst(f, seed, radius, impulse, swirl_noise, heat, puffs=12):
    """A cluster of small puffs, each pushed out from the centre with its own spin, so the
    cloud breaks into billows. Taichi fields index [x, y]; numpy arrays are [row, col]."""
    n = f.n
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    cx = cy = n / 2
    dens = np.zeros((n, n), np.float32)
    hot = np.zeros((n, n), np.float32)
    vel = np.zeros((n, n, 2), np.float32)
    for k in range(puffs):
        ang = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(0.0, radius) * n * (0.3 if k == 0 else 1.0)
        px, py = cx + math.cos(ang) * dist, cy + math.sin(ang) * dist
        pr = rng.uniform(0.35, 0.75) * radius * n
        dx, dy = xx - px, yy - py
        r2 = (dx * dx + dy * dy) / (pr * pr)
        blob = np.exp(-r2 * 2.5)
        dens = np.maximum(dens, blob * rng.uniform(0.7, 1.0))
        hot = np.maximum(hot, blob * heat * (1.0 if k < 3 else rng.uniform(0.3, 0.8)))
        out = np.array([math.cos(ang), math.sin(ang)]) * impulse * rng.uniform(0.6, 1.2)
        spin = rng.uniform(-1, 1) * impulse * 0.8
        tang = np.stack([-dy, dx], -1) / pr
        vel += blob[..., None] * (out + spin * tang * np.exp(-r2)[..., None])
    turb = _curl_noise(n, seed + 3)
    vel += turb * swirl_noise * np.clip(dens, 0, 1)[..., None]
    f.dens.from_numpy(np.ascontiguousarray(dens.T))
    f.heat.from_numpy(np.ascontiguousarray(hot.T))
    f.vel.from_numpy(np.ascontiguousarray(np.transpose(vel, (1, 0, 2))))
    f.turb.from_numpy(np.ascontiguousarray(np.transpose(_curl_noise(n, seed + 5, 32), (1, 0, 2))))


def _capture(f):
    # back to image orientation: rows top to bottom, with Taichi's +y pointing up
    d = f.dens.to_numpy().T[::-1]
    h = f.heat.to_numpy().T[::-1]
    return d, h


def smoke_puff(seed=12, steps=120, frames=16):
    """A burst of smoke that swells, curls and thins out (flip_smoke)."""
    f = Fluid()
    _setup_burst(f, seed, radius=0.11, impulse=2.1, swirl_noise=2.5, heat=0.25, puffs=14)
    every = steps // frames
    dens, light = [], []
    for k in range(steps):
        f.step(0.6, keep_d=0.993, keep_h=0.96, buoyancy=0.6, swirl=2.5, stir=6.0 if k < 70 else 2.0)
        if k % every == every - 1:
            d, _ = _capture(f)
            dens.append(d)
    out_a, out_l = [], []
    edge = _edge_fade(f.n)
    for i, d in enumerate(dens[:frames]):
        t = i / (frames - 1)
        a = np.clip((d - 0.04) / 0.35, 0, 1) ** 0.8
        fade = 1 - np.clip((t - 0.55) / 0.45, 0, 1) ** 1.5
        thresh = np.clip((t - 0.5) / 0.5, 0, 1) * 0.6
        a = np.clip((a - thresh) / max(1e-3, 1 - thresh), 0, 1) * fade * edge
        out_a.append(a)
        out_l.append(_light(d, k=4.5, shift=(7, 7), soft=3))
    out_a[-1][:] = 0
    return np.stack(out_a), np.stack(out_l)


def explosion(seed=11, steps=90, frames=16):
    """A hot burst: a fast radial blast whose heat lights the core white and cools to grey
    smoke at the edges (flip_impact)."""
    f = Fluid()
    _setup_burst(f, seed, radius=0.09, impulse=5.0, swirl_noise=3.0, heat=1.0, puffs=18)
    every = steps // frames
    caps = []
    for k in range(steps):
        f.step(0.5, keep_d=0.988, keep_h=0.94, buoyancy=0.4, swirl=3.0, stir=8.0 if k < 50 else 2.0)
        if k % every == every - 1:
            caps.append(_capture(f))
    out_a, out_l = [], []
    edge = _edge_fade(f.n)
    for i, (d, h) in enumerate(caps[:frames]):
        t = i / (frames - 1)
        a = np.clip((d - 0.03) / 0.3, 0, 1) ** 0.8
        fade = 1 - np.clip((t - 0.55) / 0.45, 0, 1) ** 1.2
        thresh = np.clip((t - 0.5) / 0.5, 0, 1) * 0.7
        a = np.clip((a - thresh) / max(1e-3, 1 - thresh), 0, 1) * fade * edge
        hot = np.clip(h * 2.5, 0, 1)
        out_a.append(a)
        out_l.append(np.clip(0.6 + 0.4 * np.maximum(hot, _light(d, k=1.4) * 0.6), 0, 1))
    out_a[-1][:] = 0
    return np.stack(out_a), np.stack(out_l)


def flame_loop(seed=21, frames=64, every=2, warm=160, overlap=16, n=192, sources=4, half=0.08, spread=0.13,
               keep_h=0.94, buoyancy=2.2, swirl=3.4, stir=4.0, kick=1.2):
    """A burning flame that loops. `sources` small sources sit side by side at the bottom,
    each flickering and swaying on its own slow noise, so the plume breaks into several
    tongues that lick, merge and split; the heat cools as it rises, so the tips die off.
    After a warm-up, `frames + overlap` frames are recorded and the last `overlap` are
    crossfaded into the first, on the heat field, so the loop has no seam. Returns the heat
    frames (0..1 floats, image orientation). Stirring past about 4, or five sources, makes the
    solver blow up."""
    f = Fluid(n)
    rng = np.random.default_rng(seed)
    f.turb.from_numpy(np.ascontiguousarray(np.transpose(_curl_noise(n, seed + 5, 16), (1, 0, 2))))
    total = warm + (frames + overlap) * every
    knots = rng.uniform(-1, 1, (total // 10 + 4, 2 * sources))
    t = np.arange(total) / 10.0
    i = np.floor(t).astype(int)
    a = t - i
    a = (a * a * (3 - 2 * a))[:, None]
    noise = knots[i] * (1 - a) + knots[i + 1] * a
    caps = []
    for k in range(total):
        for q in range(sources):
            off = (q - (sources - 1) / 2) * spread * n
            flick, sway = noise[k, 2 * q], noise[k, 2 * q + 1]
            f.emit(n / 2 + off + 6 * sway, n * half, 6, 18, 0.85 + 0.35 * flick, 0.8 * sway, kick * (1.0 + 0.2 * flick))
        f.step(0.5, keep_d=0.95, keep_h=keep_h, buoyancy=buoyancy, swirl=swirl, iters=30, stir=stir)
        if k >= warm and (k - warm) % every == 0:
            caps.append(_capture(f)[1])
    caps = caps[: frames + overlap]
    out = []
    for j in range(frames):
        if j < overlap:
            w = j / overlap
            out.append(caps[frames + j] * (1 - w) + caps[j] * w)
        else:
            out.append(caps[j])
    return np.clip(np.stack(out), 0, 1.5).astype(np.float32)

def flame_lick(seed=31, frames=16, every=3, lead=10, flare=14, n=192, half=0.06, buoyancy=2.4, swirl=3.0,
               stir=3.5, kick=1.4, keep_h=0.968):
    """One tongue of flame, start to end, for a OneShot flipbook: a single source flares for
    `flare` steps (after `lead` steps of nothing), then stops, so the tongue rises, breaks off
    the base, thins and dies. The parts a fire's volume is built from: many licks rising out
    of one core flame. Returns the heat frames (0..1 floats, image orientation)."""
    f = Fluid(n)
    rng = np.random.default_rng(seed)
    f.turb.from_numpy(np.ascontiguousarray(np.transpose(_curl_noise(n, seed + 5, 16), (1, 0, 2))))
    total = lead + frames * every
    sway = rng.uniform(-1, 1)
    caps = []
    for k in range(total):
        on = k < lead + flare
        if on:
            ramp = min(1.0, (k + 1) / 4)
            f.emit(n / 2 + 4 * sway, n * half, 6, 18, 1.1 * ramp, 0.6 * sway, kick)
        f.step(0.5, keep_d=0.95, keep_h=keep_h, buoyancy=buoyancy, swirl=swirl, iters=30, stir=stir)
        if k >= lead and (k - lead) % every == every - 1:
            caps.append(_capture(f)[1])
    out = np.stack(caps[:frames])
    out[-1] *= 0
    return np.clip(out, 0, 1.5).astype(np.float32)

SIMS = {"smoke_puff": smoke_puff, "explosion": explosion, "flame_loop": flame_loop, "flame_lick": flame_lick}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("sim", choices=sorted(SIMS))
    ap.add_argument("--seed", type=int)
    ap.add_argument("--arch", default="cpu", choices=["cpu", "metal"])
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)
    _init(ti.metal if args.arch == "metal" else ti.cpu)
    kw = {} if args.seed is None else {"seed": args.seed}
    result = SIMS[args.sim](**kw)
    if isinstance(result, tuple):
        alpha, light = result
        np.savez_compressed(args.out, alpha=alpha.astype(np.float32), light=light.astype(np.float32))
    else:
        alpha = result
        # 8-bit is plenty to cut bands from, and keeps the baked file small in the repo
        np.savez_compressed(args.out, heat=np.round(np.clip(result / 1.5, 0, 1) * 255).astype(np.uint8), scale=np.float32(1.5))
    print(f"{args.sim}: {alpha.shape[0]} frames {alpha.shape[1]}x{alpha.shape[2]} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
