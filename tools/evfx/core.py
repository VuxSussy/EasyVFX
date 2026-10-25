"""Shared pieces of evfx: reading timelines, sampling Roblox sequences, the camera and
the particle simulation.

A timeline is what tests/timeline.luau writes for one preset: every frame of one play
(beams, pieces, lights, screen effects, the camera) plus the emitters that streamed and
the bursts that fired. Particles are not in it: they are re-simulated here from their
emitter settings, the way Roblox documents them, with a fixed seed per particle so a
particle keeps its path from one frame to the next.
"""

import json
import math
import os
import random
import subprocess
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, ".cache", "evfx")
PACK = os.path.join(ROOT, "pack", "textures")
GENERATED = os.path.join(ROOT, "pack", "generated")
CC0 = os.path.join(ROOT, "pack", "cc0")
MESHES = os.path.join(ROOT, "pack", "meshes")

DIRS = {
    "Top": (0, 1, 0),
    "Bottom": (0, -1, 0),
    "Front": (0, 0, -1),
    "Back": (0, 0, 1),
    "Right": (1, 0, 0),
    "Left": (-1, 0, 0),
}
GRIDS = {"Grid2x2": 2, "Grid4x4": 4, "Grid8x8": 8}


def lune():
    for name in ("lune", "lune.exe"):
        for folder in os.environ.get("PATH", "").split(os.pathsep):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                return path
    sys.exit("evfx: lune not found; run `rokit install`")


def _folder(mode, fps):
    return os.path.join(CACHE, "timeline", mode if fps == 30 else f"{mode}-{fps}")


def export(presets=None, mode="hd", root=ROOT, out=None, fps=30, env=None):
    """Runs tests/timeline.luau in `root` and returns the folder it wrote. `fps` is the
    harness frame rate: 30 for the audit, 60 for the beat judge."""
    out = out or _folder(mode, fps)
    os.makedirs(out, exist_ok=True)
    args = [lune(), "run", "tests/timeline.luau", os.path.abspath(out), mode, ",".join(presets or [])]
    env = {**os.environ, "EVFX_FPS": str(fps), **(env or {})}
    # absolute, as Lune runs from the repo root
    env["EVFX_KITS"] = ":".join(kit_dirs())
    done = subprocess.run(args, cwd=root, capture_output=True, text=True, env=env)
    if done.returncode != 0:
        sys.exit("evfx: timeline export failed\n" + done.stdout + done.stderr)
    failed = [line for line in done.stdout.splitlines() if "FAILED" in line]
    if failed:
        sys.exit("evfx: " + "\n".join(failed))
    return out


def load(preset, mode="hd", folder=None, fresh=False, fps=30, env=None):
    folder = folder or _folder(mode, fps)
    path = os.path.join(folder, preset + ".json")
    if fresh or not os.path.exists(path):
        export([preset], mode, out=folder, fps=fps, env=env)
    if not os.path.exists(path):
        sys.exit(f"evfx: no preset named {preset}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def kit_dirs():
    """The directories in EVFX_KITS (separated by ":"): a game's own effects, kept in its own repo
    and loaded with Presets.register. Each holds kits/<kit>.luau, sheets/<preset>.json and
    picks/kit_<kit>.json."""
    return [os.path.abspath(d) for d in os.environ.get("EVFX_KITS", "").split(":") if d]


def kit_sources():
    """What the presets and kits are read from: Presets.luau, then every kit module in EVFX_KITS."""
    out = [os.path.join(ROOT, "src", "Plugin", "Shared", "Presets.luau")]
    for d in kit_dirs():
        folder = os.path.join(d, "kits")
        if os.path.isdir(folder):
            out += sorted(os.path.join(folder, n) for n in os.listdir(folder) if n.endswith(".luau"))
    return out


def preset_ids():
    """Every preset id, in library order, read from Presets.luau and the kits in EVFX_KITS."""
    ids = []
    for path in kit_sources():
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith('id = "'):
                    ids.append(stripped.split('"')[1])
    return ids


# ------------------------------------------------------------------ vectors


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def norm(a):
    m = length(a) or 1.0
    return (a[0] / m, a[1] / m, a[2] / m)


def rot_apply(cf, v):
    """Rotates `v` by a CFrame's components (x, y, z, r00..r22)."""
    return (
        cf[3] * v[0] + cf[4] * v[1] + cf[5] * v[2],
        cf[6] * v[0] + cf[7] * v[1] + cf[8] * v[2],
        cf[9] * v[0] + cf[10] * v[1] + cf[11] * v[2],
    )


def rotate_about(v, axis, angle):
    c, s = math.cos(angle), math.sin(angle)
    return add(add(mul(v, c), mul(cross(axis, v), s)), mul(axis, dot(axis, v) * (1 - c)))


def bezier(p0, p1, p2, p3, t):
    a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
    return tuple(a * p0[i] + b * p1[i] + c * p2[i] + d * p3[i] for i in range(3))


def number_at(seq, t):
    """A NumberSequence's value at `t` (0..1), envelope ignored."""
    if t <= seq[0][0]:
        return seq[0][1]
    for a, b in zip(seq, seq[1:]):
        if a[0] <= t <= b[0]:
            f = (t - a[0]) / max(1e-6, b[0] - a[0])
            return a[1] + (b[1] - a[1]) * f
    return seq[-1][1]


def color_at(seq, t):
    if t <= seq[0][0]:
        return seq[0][1:4]
    for a, b in zip(seq, seq[1:]):
        if a[0] <= t <= b[0]:
            f = (t - a[0]) / max(1e-6, b[0] - a[0])
            return [a[i] + (b[i] - a[i]) * f for i in range(1, 4)]
    return seq[-1][1:4]


# ------------------------------------------------------------------ camera


class Camera:
    """A perspective camera looking from `eye` at `target`, Roblox's vertical FOV."""

    def __init__(self, eye, target, fov=70.0, size=(480, 320)):
        self.eye = tuple(eye)
        self.target = tuple(target)
        self.w, self.h = size
        self.f = norm(sub(target, eye))
        self.r = norm(cross(self.f, (0, 1, 0)))
        self.u = cross(self.r, self.f)
        self.scale = (self.h / 2) / math.tan(math.radians(fov) / 2)

    def project(self, p):
        d = sub(p, self.eye)
        z = dot(d, self.f)
        if z < 0.1:
            return None
        return (self.w / 2 + self.scale * dot(d, self.r) / z, self.h / 2 - self.scale * dot(d, self.u) / z, z)

    def pixels(self, studs, z):
        return self.scale * studs / z


def _points(timeline):
    """Where the effect's pieces, beams and particles are, over the play."""
    out = []
    for frame in timeline["frames"][::2]:
        for beam in frame["beams"]:
            out.append(tuple(beam["p0"]))
            out.append(tuple(beam["p3"]))
        for part in frame["parts"]:
            out.append(tuple(part["cframe"][:3]))
    out.extend(p["pos"] for p in sample_all(timeline))
    return out


def views(timeline, size=(480, 320)):
    """The two cameras every strip uses: close (fits the effect) and far (a game camera)."""
    points = _points(timeline)
    holder = tuple(timeline["holder"][:3])
    if points:
        xs, ys, zs = (sorted(p[i] for p in points) for i in range(3))
        q = lambda v, f: v[min(len(v) - 1, int(f * (len(v) - 1)))]
        lo = (q(xs, 0.08), q(ys, 0.08), q(zs, 0.08))
        hi = (q(xs, 0.92), q(ys, 0.92), q(zs, 0.92))
    else:
        lo = hi = holder
    center = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    span = max(3.0, max(hi[i] - lo[i] for i in range(3)))
    direction = norm((0.62, 0.42, 0.66))
    close = Camera(add(center, mul(direction, span * 0.95 + 2.5)), center, 70, size)
    far = Camera(add(holder, (14, 9, 18)), add(holder, (0, 2.5, 0)), 70, size)
    # a ground effect seen the way the fire pit's reference video sees it: about 30 degrees
    # down, from 16 studs, through a narrow 30-degree lens, so near and far read about the same
    # size and flat decals look flat (Phát, 2026-10-24)
    target = add(holder, (0, -0.6, 0))
    ground = Camera(add(target, mul(norm((0.05, 0.6, 1.0)), 16)), target, 30, size)
    return {"close": close, "far": far, "ground": ground}


# ------------------------------------------------------------------ particles


def _rng(*key):
    return random.Random(zlib.crc32(repr(key).encode()))


def _particle(e, origin_cf, volume, age, rng):
    """One particle of emitter settings `e`, `age` seconds after it was emitted."""
    life = rng.uniform(*e["lifetime"])
    if life <= 0 or age < 0 or age > life:
        return None
    start = tuple(origin_cf[:3])
    if any(volume):
        start = add(start, rot_apply(origin_cf, [rng.uniform(-0.5, 0.5) * volume[i] for i in range(3)]))
    base = rot_apply(origin_cf, DIRS.get(e["direction"], (0, 1, 0)))
    local_x = rot_apply(origin_cf, (1, 0, 0))
    local_z = rot_apply(origin_cf, (0, 0, 1))
    ref = local_x if abs(dot(local_x, base)) < 0.9 else local_z
    ax1 = norm(cross(base, ref))
    ax2 = norm(cross(base, ax1))
    d = rotate_about(base, ax1, math.radians(rng.uniform(-e["spread"][1], e["spread"][1])))
    d = rotate_about(d, ax2, math.radians(rng.uniform(-e["spread"][0], e["spread"][0])))
    speed = rng.uniform(*e["speed"])
    k = e["drag"] * math.log(2) if e["drag"] > 0 else 0.0
    travel = (1 - math.exp(-k * age)) / k if k > 0 else age
    accel = e["accel"]
    pos = add(add(start, mul(d, speed * travel)), mul(accel, 0.5 * age * age))
    vel = add(mul(d, speed * (math.exp(-k * age) if k > 0 else 1.0)), mul(accel, age))
    f = age / life
    rotation = rng.uniform(*e["rotation"]) + rng.uniform(*e["rotSpeed"]) * age
    grid = GRIDS.get(e["flipbook"], 1)
    frames = grid * grid
    if grid > 1 and e.get("flipMode") == "OneShot":
        cell = min(frames - 1, int(f * frames))
    elif grid > 1:
        rate = rng.uniform(*e.get("flipFramerate", [30, 30]))
        start = rng.randrange(frames) if e.get("flipRandom") else 0
        cell = (start + int(age * rate)) % frames
    else:
        cell = 0
    return {
        "pos": pos,
        "vel": vel,
        "dir": base,
        "up_hint": local_z,
        "size": number_at(e["size"], f),
        "squash": number_at(e["squash"], f),
        "transparency": number_at(e["transparency"], f),
        "color": color_at(e["color"], f),
        "rotation": rotation,
        "cell": cell,
        "grid": grid,
        "emitter": e,
    }


def particles_at(timeline, t):
    """Every particle alive `t` seconds into the play, from bursts and streams."""
    out = []
    dt = timeline["frameTime"]
    # each burst and stream is seeded by what it is (its name, texture, time and place), not by
    # where it falls in the timeline's list, so a layer gets the same particles alone as it does
    # inside the whole effect (Phát: the two looked different)
    seen = {}
    for b in timeline["bursts"]:
        ident = (b.get("name"), b.get("texture"), b["frame"], tuple(round(x, 2) for x in b["cframe"][:3]))
        seen[ident] = seen.get(ident, 0) + 1
        age = t - b["frame"] * dt
        if age < 0:
            continue
        for n in range(int(b["count"])):
            p = _particle(b, b["cframe"], b["volume"], age, _rng("b", ident, seen[ident], n))
            if p:
                out.append(p)
    emitters = timeline["emitters"]
    frames = timeline["frames"]
    for key, e in enumerate(emitters, start=1):
        rate = e["rate"]
        if rate <= 0:
            continue
        life_max = e["lifetime"][1]
        for frame in frames:
            ft = frame["t"]
            if ft > t or t - ft > life_max + dt:
                continue
            for stream in frame["streams"]:
                if stream["emitter"] != key:
                    continue
                first = math.ceil((ft - dt) * rate)
                last = math.floor(ft * rate)
                for n in range(first, last + 1):
                    age = t - n / rate
                    ident = (e.get("name"), e.get("texture"), tuple(round(x, 2) for x in stream["cframe"][:3]))
                    p = _particle(e, stream["cframe"], stream["volume"], age, _rng("s", ident, n))
                    if p:
                        out.append(p)
    return out


def sample_all(timeline, every=4):
    """Particles at a few moments, for fitting the close camera."""
    out = []
    frames = timeline["frames"]
    for frame in frames[::every]:
        out.extend(particles_at(timeline, frame["t"]))
    return out


def frame_at(timeline, t):
    frames = timeline["frames"]
    if not frames:
        return None
    best = min(frames, key=lambda f: abs(f["t"] - t))
    return best


def extend(timeline):
    """The timeline padded with empty frames until its last burst particle has died: the
    recorder stops when the runtime's own work ends, but particles live on in Roblox."""
    frames = timeline["frames"]
    if not frames:
        return timeline
    ft = timeline["frameTime"]
    end = max([b["frame"] * ft + max(b["lifetime"]) for b in timeline["bursts"]] + [frames[-1]["t"]])
    extra = int(round((end - frames[-1]["t"]) / ft))
    if extra <= 0:
        return timeline
    last = frames[-1]
    pad = [{**last, "t": last["t"] + (k + 1) * ft, "parts": [], "beams": [], "lights": [], "screens": [], "trails": 0} for k in range(extra)]
    return {**timeline, "frames": frames + pad}


def duration(timeline):
    frames = timeline["frames"]
    return frames[-1]["t"] if frames else 0.0
