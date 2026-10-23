"""What open Roblox VFX do, in the grammar's numbers.

`evfx study` reads .cache/vfxstudy/emitters.json: the emitter settings of openly
published Roblox effects (the sources are listed in grammar.json `open.sources`). That
file and the effects stay in .cache, untracked; only numbers were read from them, never
textures, and nothing of theirs goes into a preset. Each emitter gets a role (by its name,
then by its numbers) and the grammar's measures, then per role the middle of the spread
(15th to 85th percentile) is printed beside the grammar's ranges. `--write` stores those
spreads in grammar.json under each role's `open`, as evidence for the ranges.
"""

import json
import os
import re

import numpy as np

from . import core, grammar

DATA = os.path.join(core.CACHE, "..", "vfxstudy", "emitters.json")
WORDS = [
    (r"glow|light|bloom", "glow"),
    (r"flash|core|bright|impact\d|boom", "core"),
    (r"star|glare|flare|spec|twinkle", "glint"),
    (r"ring|circle|wave|shock", "base"),
    (r"dark", "dark"),
    (r"smoke|dust|cloud|sand|dirt|mist", "volume"),
    (r"rock|debri|chip|tile|cube|chunk|bigbois|smolbois", "debris"),
    (r"spark|shard|blade|string|line|streak|hit", "shards"),
    (r"dot|ember|particle|emission", "dust"),
]


def _seq(keys):
    return [[k[0], k[1], k[2] if len(k) > 2 else 0] for k in keys]


def burst(e):
    """An open emitter in the timeline's burst shape, or None when it streams."""
    if not all(k in e for k in ("Size", "Transparency", "Lifetime", "Speed")):
        return None
    count = e.get("EmitCount")
    if count is None and e.get("Rate", 0) > 0 and e.get("Enabled", True):
        return None
    return {
        "name": e["name"],
        "count": count or 1,
        "frame": 0,
        "lifetime": e["Lifetime"],
        "speed": e["Speed"],
        "drag": e.get("Drag", 0),
        "spread": e.get("SpreadAngle", [0, 0]),
        "size": _seq(e["Size"]),
        "transparency": _seq(e["Transparency"]),
        "accel": e.get("Acceleration", [0, 0, 0]),
        "lightEmission": e.get("LightEmission", 0),
        "zOffset": e.get("ZOffset", 0),
        "orientation": e.get("Orientation"),
        "texture": "",
    }


def role(row):
    name = row["name"].lower()
    for pattern, r in WORDS:
        if re.search(pattern, name):
            return r
    return grammar.guess(row)


def rows(path=DATA):
    if not os.path.exists(path):
        raise SystemExit(f"evfx: {path} is missing; the open VFX study collects it (docs/vfx-grammar.md)")
    with open(path, encoding="utf-8") as f:
        effects = json.load(f)
    out = []
    for fx in effects:
        layers = []
        for e in fx["emitters"]:
            b = burst(e)
            if b is None:
                continue
            row = grammar.particle(b, 1 / 60)
            row["role"] = role(dict(row, _size=row["_size"]))
            layers.append(row)
        if not layers:
            continue
        for r in layers:
            r["size"] = round(r.pop("_size") / grammar.BODY, 3)
            r["reach"] = round(r.pop("_travel") / grammar.BODY, 3)
            r["effect"] = fx["effect"]
            r["source"] = fx["source"]
        out += layers
    return out


SPREAD = ("life", "vary", "stop", "reach", "spread", "size", "grow", "fade", "solid", "light")


def spreads(all_rows):
    by = {}
    for r in all_rows:
        by.setdefault(r["role"], []).append(r)
    out = {}
    for name, rs in by.items():
        row = {"n": len(rs)}
        for k in SPREAD:
            vals = [r[k] for r in rs if r.get(k) is not None]
            if len(vals) >= 3:
                row[k] = [round(float(np.percentile(vals, 15)), 3), round(float(np.percentile(vals, 85)), 3)]
        out[name] = row
    return out


def report(sp, g):
    lines = []
    for name, role in g["roles"].items():
        o = sp.get(name, {})
        lines.append(f"{name} ({o.get('n', 0)} open emitters)")
        for k in SPREAD:
            mine = role["ranges"].get(k)
            if k in o or mine:
                lines.append(f"  {k:<7} grammar {str(mine):<16} open {o.get(k)}")
    return "\n".join(lines)
