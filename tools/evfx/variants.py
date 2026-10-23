"""Variants of one effect along the grammar's knobs, for Phát to keep or drop.

Each variant changes one knob of the played effect's timeline (never the preset source),
so the only difference you see is that knob. Each records the grammar measure it moved,
so a keep or a drop becomes evidence for that role's range in grammar.json.

    vary    the longest lifetime over the shortest, on dust and shards (mean kept)
    drag    the shards' Drag, scaled (how fast they explode, then stop)
    size    the hit's core, glint and glow sizes, scaled
    depth   every layer's ZOffset set by the grammar's depth order
"""

import copy

from . import grammar

ROLE_Z = {"dark": -2, "volume": -1, "glow": -0.5, "base": 0, "debris": 0.5, "shards": 1, "dust": 1.5, "glint": 2.5, "core": 3}


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


def depth(timeline, roles):
    out = copy.deepcopy(timeline)
    for b in out["bursts"]:
        r = roles.get(b["name"])
        if r in ROLE_Z:
            b["zOffset"] = ROLE_Z[r]
    return out


PLAN = [
    ("base", "as built", None),
    ("vary2", "embers and shards: lifetimes vary 2x", ("vary", 2.0)),
    ("vary3", "embers and shards: lifetimes vary 3x", ("vary", 3.0)),
    ("glide", "shards: drag x0.4, they glide", ("drag", 0.4)),
    ("snap", "shards: drag x2.5, they snap to a stop", ("drag", 2.5)),
    ("small", "core, flare, rays: size x0.7", ("size", 0.7)),
    ("big", "core, flare, rays: size x1.4", ("size", 1.4)),
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
