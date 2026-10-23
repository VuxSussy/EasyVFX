"""The VFX grammar: what a good effect is, as numbers an agent can read and tune.

An effect is layers, each with a role (grammar.json `roles`): core, glint, base, volume,
dark, shards, dust or ground (plan §4a and the Lotus layer map, docs/refs/lotus-layers.md).
A layer's role comes from a beat sheet's `roles`, else from its name (grammar.json
`names`, since presets name emitters by role), else from its numbers. Each layer is read
from the builder's own output (the timeline the runtime played) and turned into measures
that don't depend on how big the effect is, so a sword hit and a meteor compare:

    count     particles it emits
    delay     seconds after the effect starts
    life      mean lifetime, seconds
    vary      longest lifetime over shortest (Genshin-style sparkles run about 2)
    stop      seconds until drag has cut its speed to a tenth (none without drag)
    reach     how far a particle travels in its life, in bodies (a character is 5 studs)
    spread    spread angle, degrees
    size      its largest size, in bodies
    grow      end size over start size
    fade      share of its life before it is half transparent
    solid     how opaque it gets at most (1 - lowest transparency)
    light     LightEmission (1 additive, 0 normal)
    z         ZOffset

Sizes are in bodies, not over the effect's own size: effects are made to sit on a
character, and it lets open effects without a base layer compare. grammar.json holds, per
role, the range each measure should sit in, where each range came from, and the
structure rules (how many layers a beat stacks, which roles, their order in depth).
"""

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GRAMMAR = os.path.join(HERE, "grammar.json")
BODY = 5.0
MEASURES = ("count", "delay", "life", "vary", "stop", "reach", "spread", "size", "grow", "fade", "solid", "light", "z")


def load():
    with open(GRAMMAR, encoding="utf-8") as f:
        return json.load(f)


def save(g):
    """Writes grammar.json with each role's lists on one line, so a diff reads."""
    def one(v):
        return json.dumps(v, ensure_ascii=False)

    lines = ["{", f' "_about": {one(g["_about"])},', ' "roles": {']
    roles = list(g["roles"].items())
    for i, (name, r) in enumerate(roles):
        lines.append(f'  "{name}": {{')
        lines.append(",\n".join(f'   "{k}": {one(v)}' for k, v in r.items()))
        lines.append("  }" + ("," if i < len(roles) - 1 else ""))
    lines.append(" },")
    lines.append(f' "names": {one(g["names"])},')
    lines.append(' "structure": {')
    lines.append(",\n".join(f'  "{k}": {one(v)}' for k, v in g["structure"].items()))
    lines.append(" },")
    lines.append(' "openSources": [')
    lines.append(",\n".join("  " + one(x) for x in g["openSources"]))
    lines.append(" ]")
    lines.append("}")
    with open(GRAMMAR, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _seq_at(seq, t):
    for (t0, v0, *_), (t1, v1, *_) in zip(seq, seq[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * ((t - t0) / max(1e-9, t1 - t0))
    return seq[-1][1] if t >= seq[-1][0] else seq[0][1]


def travel(speed, drag, life, accel=0.0):
    """Distance a particle covers in `life` seconds. Roblox's Drag halves the speed every
    1 / Drag seconds, so speed(t) = v0 * 2^(-Drag t)."""
    if drag > 0:
        k = drag * math.log(2)
        d = speed * (1 - math.exp(-k * life)) / k
    else:
        d = speed * life
    return d + 0.5 * accel * life * life


def stop_time(drag):
    return math.log(10) / (drag * math.log(2)) if drag > 0 else None


def fade_point(transparency):
    """Share of the life before transparency first reaches 0.5."""
    for (t0, v0, *_), (t1, v1, *_) in zip(transparency, transparency[1:]):
        if v1 >= 0.5 > v0 or v0 >= 0.5:
            if v0 >= 0.5:
                return t0
            return t0 + (t1 - t0) * ((0.5 - v0) / max(1e-9, v1 - v0))
    return 1.0


def particle(b, frame_time):
    """A burst emitter's raw numbers, before scaling."""
    life = sum(b["lifetime"]) / 2
    speed = sum(abs(x) for x in b["speed"]) / 2
    sizes = [k[1] for k in b["size"]]
    accel = math.sqrt(sum(a * a for a in b["accel"]))
    return {
        "name": b["name"],
        "kind": "particle",
        "count": b["count"],
        "delay": round(b["frame"] * frame_time, 3),
        "life": round(life, 3),
        "vary": round(max(b["lifetime"]) / max(1e-3, min(b["lifetime"])), 2),
        "stop": None if stop_time(b["drag"]) is None else round(stop_time(b["drag"]), 3),
        "_travel": travel(speed, b["drag"], life, accel),
        "spread": max(b["spread"]),
        "_size": max(sizes),
        "grow": round(sizes[-1] / max(1e-3, sizes[0]), 2) if sizes[0] > 1e-3 else None,
        "fade": round(fade_point(b["transparency"]), 3),
        "solid": round(1 - min(k[1] for k in b["transparency"]), 3),
        "light": b["lightEmission"],
        "z": b["zOffset"],
        "texture": b.get("texture", ""),
        "facing": b.get("orientation"),
    }


def layers(timeline, roles=None, grammar=None):
    """Every layer of a played effect with its measures. `roles` maps layer names to
    roles (a beat sheet's `roles`); the rest come from grammar.json `names`, then from
    the numbers."""
    names = {**(grammar or load()).get("names", {}), **(roles or {})}
    ft = timeline["frameTime"]
    out = {}
    for b in timeline["bursts"]:
        row = particle(b, ft)
        if b["name"] in out:
            out[b["name"]]["count"] += row["count"]
            continue
        out[b["name"]] = row
    for k, frame in enumerate(timeline["frames"]):
        for part in frame["parts"]:
            name = (part.get("meshId") or "").split("://")[-1] or part.get("shape") or "part"
            size = max(part["size"])
            row = out.setdefault(name, {"name": name, "kind": "shell", "count": 1, "delay": round(k * ft, 3), "_first": k, "_last": k, "_size": size, "light": 1, "z": 0})
            row["_last"] = k
            row["_size"] = max(row["_size"], size)
    for row in out.values():
        if row["kind"] == "shell":
            row["life"] = round((row.pop("_last") - row.pop("_first") + 1) * ft, 3)
        row["role"] = names.get(row["name"]) or guess(row)
    mains = [r["_size"] for r in out.values() if r["role"] == "base"]
    scale = max(mains) if mains else max((r["_size"] for r in out.values()), default=1.0)
    for row in out.values():
        row["_size"] /= BODY
        if "_travel" in row:
            row["_travel"] /= BODY
    for row in out.values():
        row["size"] = round(row.pop("_size"), 3)
        if "_travel" in row:
            row["reach"] = round(row.pop("_travel"), 3)
    return list(out.values()), scale


def guess(row):
    """A role from the numbers alone, for a layer whose name isn't in the grammar."""
    if row["kind"] == "shell":
        return "base"
    if row["life"] <= 0.1 and row.get("count", 1) <= 2:
        return "core"
    if row["light"] < 0.5:
        return "dark" if row.get("count", 1) <= 3 else "volume"
    if row.get("facing") in ("VelocityParallel", "VelocityPerpendicular") or (row.get("stop") or 9) < 0.6:
        return "shards"
    if row.get("count", 1) >= 6:
        return "dust"
    return "base"


def roles_from_sheet(spec):
    """A beat sheet's role overrides: each beat may carry {"roles": {layer: role}}."""
    out = {}
    for b in (spec or {}).get("beats", []):
        out.update(b.get("roles", {}))
    return out


def judge(rows, grammar=None, spec=None):
    """Findings for one effect's layers: a measure outside its role's range, ZOffsets out
    of depth order, beats stacking too few or too many layers. Each finding is
    {sev, layer, rule, said, want}."""
    g = grammar or load()
    out = []
    for r in rows:
        role = g["roles"].get(r["role"])
        if not role:
            continue
        for key, (lo, hi) in role["ranges"].items():
            v = r.get(key)
            if v is None:
                continue
            if lo is not None and v < lo:
                out.append({"sev": 2, "layer": r["name"], "rule": f"{r['role']}.{key}", "said": f"{key} {v} is under {lo}", "want": f"{lo}-{hi}"})
            elif hi is not None and v > hi:
                out.append({"sev": 2, "layer": r["name"], "rule": f"{r['role']}.{key}", "said": f"{key} {v} is over {hi}", "want": f"{lo}-{hi}"})
    order = g["structure"]["depthOrder"]
    zs = {}
    for r in rows:
        if r["role"] in order and r["kind"] == "particle":
            zs.setdefault(r["role"], []).append((r["z"], r["name"]))
    for a, b in zip(order, order[1:]):
        if a in zs and b in zs:
            hi_a = max(zs[a])
            lo_b = min(zs[b])
            if hi_a[0] > lo_b[0]:
                out.append({"sev": 1, "layer": f"{hi_a[1]}/{lo_b[1]}", "rule": "depth", "said": f"{a} {hi_a[1]} (z {hi_a[0]}) sits in front of {b} {lo_b[1]} (z {lo_b[0]})", "want": " < ".join(order)})
    if spec:
        lo, hi = g["structure"]["beatLayers"]
        for b in spec.get("beats", []):
            n = sum(len(v) for v in b.get("layers", {}).values())
            if not b.get("flash") and not lo <= n <= hi:
                out.append({"sev": 1, "layer": b["name"], "rule": "stack", "said": f"beat {b['name']} stacks {n} layers", "want": f"{lo}-{hi}"})
    out.sort(key=lambda f: (-f["sev"], f["layer"]))
    return out


COLUMNS = ("role", "count", "delay", "life", "vary", "stop", "reach", "spread", "size", "grow", "fade", "solid", "light", "z")


def table(rows, found):
    bad = {(f["layer"], f["rule"].split(".")[-1]) for f in found}
    head = f"  {'layer':<20}" + "".join(f"{c:>8}" for c in COLUMNS)
    lines = [head]
    for r in sorted(rows, key=lambda r: (r["delay"], r["name"])):
        cells = []
        for c in COLUMNS:
            v = r.get(c)
            text = "-" if v is None else (v if isinstance(v, str) else f"{v:g}")
            cells.append(f"{text + ('!' if (r['name'], c) in bad else ''):>8}")
        lines.append(f"  {r['name'][:20]:<20}" + "".join(cells))
    return "\n".join(lines)
