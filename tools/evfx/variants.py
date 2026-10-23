"""Variants of one effect along the grammar's knobs, for Phát to keep or drop.

Each variant changes one knob of the played effect's timeline (never the preset source),
so the only difference you see is that knob. Each records the grammar measure it moved,
so a keep or a drop becomes evidence for that role's range in grammar.json.

    vary    the longest lifetime over the shortest, on dust and shards (mean kept)
    drag    the shards' Drag, scaled (how fast they explode, then stop)
    size    the hit's core, glint and glow sizes, scaled
    life    dust, shards and volume lifetimes, scaled (a longer or shorter tail)
    count   dust and shards counts, scaled
    exits   each role leaves its own way: flashes and shards as they are, base
            shapes soften as they dissolve, dark fades, dust lingers and fades,
            volume and ground disperse slowly; the value slows the calm roles down
    depth   every layer's ZOffset set by the grammar's depth order

`apply` takes any mix of them at once ({"vary": 2, "drag": 0.5}), for `evfx serve`.
"""

import copy

from . import grammar

ROLE_Z = {"dark": -2, "volume": -1, "glow": -0.5, "base": 0, "debris": 0.5, "shards": 1, "dust": 1.5, "glint": 2.5, "core": 3}


def span(timeline):
    """How long the effect plays: the recorded frames, or longer when a knob made
    particles outlive them (the timeline only records until the play ended)."""
    from . import core

    ft = timeline["frameTime"]
    ends = [b["frame"] * ft + max(b["lifetime"]) for b in timeline["bursts"]]
    return max([core.duration(timeline)] + ends)


def _roles(timeline, roles):
    rows, _ = grammar.layers(timeline, roles)
    return {r["name"]: r["role"] for r in rows}


def vary(timeline, roles, v, targets=("dust", "shards")):
    out = copy.deepcopy(timeline)
    for b in out["bursts"]:
        if roles.get(b["name"]) in targets:
            mean = sum(b["lifetime"]) / 2
            b["lifetime"] = [2 * mean / (1 + v), 2 * mean * v / (1 + v)]
    return out


def drag(timeline, roles, k):
    out = copy.deepcopy(timeline)
    for b in out["bursts"]:
        if roles.get(b["name"]) == "shards":
            b["drag"] = b["drag"] * k
    return out


def size(timeline, roles, k, targets=("core", "glint", "glow")):
    out = copy.deepcopy(timeline)
    for b in out["bursts"]:
        if roles.get(b["name"]) in targets:
            b["size"] = [[t, s * k, e * k] for t, s, e in b["size"]]
    return out


def life(timeline, roles, k, targets=("dust", "shards", "volume")):
    out = copy.deepcopy(timeline)
    for b in out["bursts"]:
        if roles.get(b["name"]) in targets:
            b["lifetime"] = [x * k for x in b["lifetime"]]
    return out


def count(timeline, roles, k, targets=("dust", "shards")):
    out = copy.deepcopy(timeline)
    for b in out["bursts"]:
        if roles.get(b["name"]) in targets:
            b["count"] = max(1, int(round(b["count"] * k)))
    return out


def exits(timeline, roles, slow):
    """Role-by-role exits (grammar.json `exits`), with the calm roles' lifetimes
    stretched by `slow`."""
    out = copy.deepcopy(timeline)
    for b in out["bursts"]:
        r = roles.get(b["name"])
        lo = min(k[1] for k in b["transparency"])
        if r == "base":
            b["lifetime"] = [x * (1 + 0.5 * (slow - 1)) for x in b["lifetime"]]
            b["transparency"] = [[0, lo, 0], [0.45, lo, 0], [0.75, 1, 0], [1, 1, 0]]
        elif r == "dark":
            b["transparency"] = [[0, lo, 0], [0.35, lo, 0], [1, 1, 0]]
        elif r == "dust":
            b["lifetime"] = [x * slow * 1.6 for x in b["lifetime"]]
            b["transparency"] = [[0, 0, 0], [0.35, 0, 0], [1, 1, 0]]
            peak = max(k[1] for k in b["size"])
            b["size"] = [[0, peak, 0], [0.6, peak * 0.8, 0], [1, peak * 0.4, 0]]
        elif r in ("volume", "ground"):
            b["lifetime"] = [x * slow * 1.5 for x in b["lifetime"]]
            peak = max(k[1] for k in b["size"])
            first = b["size"][0][1]
            b["size"] = [[0, first, 0], [0.4, peak, 0], [1, peak * 1.35, 0]]
            b["transparency"] = [[0, max(lo, 0.25 if r == "volume" else lo), 0], [0.3, max(lo, 0.3 if r == "volume" else lo), 0], [1, 1, 0]]
    return out


def depth(timeline, roles):
    out = copy.deepcopy(timeline)
    for b in out["bursts"]:
        r = roles.get(b["name"])
        if r in ROLE_Z:
            b["zOffset"] = ROLE_Z[r]
    return out


KNOBS = {
    "vary": {"fn": vary, "min": 1.0, "max": 4.0, "step": 0.1, "neutral": None, "label": "lifetime spread (dust, shards)"},
    "drag": {"fn": drag, "min": 0.25, "max": 4.0, "step": 0.05, "neutral": 1.0, "label": "shard drag x"},
    "size": {"fn": size, "min": 0.5, "max": 2.0, "step": 0.05, "neutral": 1.0, "label": "core, glint, glow size x"},
    "life": {"fn": life, "min": 0.5, "max": 3.0, "step": 0.05, "neutral": 1.0, "label": "dust, shards, volume lifetime x"},
    "count": {"fn": count, "min": 0.5, "max": 3.0, "step": 0.25, "neutral": 1.0, "label": "dust and shard count x"},
    "exits": {"fn": exits, "min": 1.0, "max": 3.0, "step": 0.1, "neutral": None, "label": "role exits, calm roles slowed x"},
}


def apply(timeline, sheet_roles, knobs):
    """The timeline with every knob in `knobs` applied, in KNOBS order. A knob at its
    neutral value (or None) is skipped."""
    roles = _roles(timeline, sheet_roles)
    out = timeline
    for name, spec in KNOBS.items():
        v = knobs.get(name)
        if v is None or v == spec["neutral"]:
            continue
        v = min(spec["max"], max(spec["min"], float(v)))
        out = spec["fn"](out, roles, v)
    return out


def moved(base, changed, sheet_roles):
    """Per layer, the grammar measures that differ between two timelines."""
    a = {r["name"]: r for r in grammar.layers(base, sheet_roles)[0]}
    out = {}
    for r in grammar.layers(changed, sheet_roles)[0]:
        for m in grammar.MEASURES:
            if r.get(m) != a.get(r["name"], {}).get(m):
                out.setdefault(r["name"], {})[m] = r.get(m)
    return out


PLAN = [
    ("base", "as built", None),
    ("vary2", "embers and shards: lifetimes vary 2x", ("vary", 2.0)),
    ("vary3", "embers and shards: lifetimes vary 3x", ("vary", 3.0)),
    ("glide", "shards: drag x0.4, they glide", ("drag", 0.4)),
    ("snap", "shards: drag x2.5, they snap to a stop", ("drag", 2.5)),
    ("small", "core, flare, rays: size x0.7", ("size", 0.7)),
    ("big", "core, flare, rays: size x1.4", ("size", 1.4)),
    ("exits", "each role leaves its own way", ("exits", 1.0)),
    ("exits2", "each role leaves its own way, calm roles twice as slow", ("exits", 2.0)),
    ("depth", "ZOffset by the grammar's depth order", ("depth", None)),
]


def make(timeline, sheet_roles=None):
    """Every variant: (key, label, timeline, the measures it moved per layer)."""
    roles = _roles(timeline, sheet_roles)
    fns = {"vary": vary, "drag": drag, "size": size, "depth": depth}
    base_rows = {r["name"]: r for r in grammar.layers(timeline, sheet_roles)[0]}
    out = []
    for key, label, knob in PLAN:
        if knob is None:
            tl = timeline
        else:
            name, arg = knob
            tl = fns[name](timeline, roles) if arg is None else fns[name](timeline, roles, arg)
        rows = {r["name"]: r for r in grammar.layers(tl, sheet_roles)[0]}
        moved = {}
        for n, r in rows.items():
            for m in grammar.MEASURES:
                if r.get(m) != base_rows[n].get(m):
                    moved.setdefault(n, {})[m] = r.get(m)
        out.append((key, label, knob, tl, moved, rows))
    return out
