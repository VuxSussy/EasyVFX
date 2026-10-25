"""`evfx serve`: a local VFX studio in the browser, for people to look, tune and pick.

    python3 tools/evfx serve [--port 8765] [--host 0.0.0.0]   then open http://127.0.0.1:8765

Pages come from the templates in tools/evfx/web. For each effect with a beat sheet the
studio shows the effect looping, its layers in the grammar's numbers with what breaks
the grammar, and the knobs (tools/evfx/variants.py). Move the knobs and press Render to
see a variant beside the effect as built, then Keep or Drop it. Picks are appended to
tools/evfx/picks/<preset>.json, in the repo: they are the calibration evidence that sets
the grammar's ranges. The server listens on 127.0.0.1 only and never edits a preset;
`--host 0.0.0.0` opens it to the local network (another computer on it then opens
http://<this machine's address>:8765). It has no sign-in, so anyone on that network can open
it and save picks and molds.

Layers (/kit/<kit>): a layer kit (Presets.Kits) laid out one layer per row, each variant
shown alone and inside the effect as it stands with the picks so far. Keep a variant and it
is appended to tools/evfx/picks/kit_<kit>.json; Phát's picks go into the kit by hand.
"""

import hashlib
import http.server
import json
import os
import re
import subprocess
import threading
import time
import urllib.parse

from . import beats, core, grammar, render, variants

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
PICKS = os.path.join(HERE, "picks")
OUT = os.path.join(core.CACHE, "serve")
NAME = re.compile(r"^[a-z0-9_]{1,64}$")
LOCK = threading.Lock()


def _texgen():
    """texgen's modules import each other by plain name, so its folder goes on the path."""
    import sys

    folder = os.path.join(os.path.dirname(HERE), "texgen")
    if folder not in sys.path:
        sys.path.insert(0, folder)
    import bank
    import mold

    return bank, mold


def mold_page():
    bank, mold = _texgen()
    bases = ["blob"] + [i for i in bank.ids() if bank.get(i).get("kind") in ("shape", "sheet", "flipbook")]
    cells = {i: int(bank.get(i).get("grid", 1)) ** 2 for i in bases if i != "blob"}
    names = sorted(f[:-5] for f in os.listdir(mold.MOLDS) if f.endswith(".json")) if os.path.isdir(mold.MOLDS) else []
    return {"bases": bases, "cells": cells, "molds": names, "shading": mold.SHADING}


def _template(name, data):
    with open(os.path.join(WEB, name), encoding="utf-8") as f:
        page = f.read()
    blob = json.dumps(data).replace("</", "<\\/")
    return page.replace("/*DATA*/null", blob)


def _knobs():
    return {k: {kk: v[kk] for kk in ("min", "max", "step", "neutral", "label")} for k, v in variants.KNOBS.items()}


def _clean(knobs):
    out = {}
    for k, spec in variants.KNOBS.items():
        v = (knobs or {}).get(k)
        if v is None or v == "":
            continue
        v = float(v)
        if spec["neutral"] is not None and abs(v - spec["neutral"]) < 1e-9:
            continue
        out[k] = round(min(spec["max"], max(spec["min"], v)), 3)
    return out


def _loop(preset, timeline, knobs, speed):
    """Renders (or reuses) one loop; returns its URL path under /out/."""
    key = hashlib.sha1(json.dumps([preset, knobs, speed], sort_keys=True).encode()).hexdigest()[:12]
    name = f"{preset}-{key}.{speed}.gif"
    path = os.path.join(OUT, name)
    if not os.path.exists(path):
        os.makedirs(OUT, exist_ok=True)
        cams = core.views(timeline, (480, 320))
        span = variants.span(timeline)
        step, hold = (1 / 30, 14) if speed == "real" else (1 / 120, 20)
        blank = render.to_image(render.draw({**timeline, "frames": [], "bursts": [], "emitters": []}, 0, cams["close"])[0])
        frames = [render.to_image(render.draw(timeline, k * step, cams["close"])[0]) for k in range(int(span / step) + 1)]
        frames += [blank] * hold
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=33, loop=0, optimize=True)
    return "/out/" + name


def effect(preset, knobs=None):
    """Everything the studio page shows for one effect, with `knobs` applied."""
    spec = beats.sheet(preset)
    roles = grammar.roles_from_sheet(spec)
    base = core.load(preset, fps=60)
    knobs = _clean(knobs)
    tl = variants.apply(base, roles, knobs) if knobs else base
    rows, _ = grammar.layers(tl, roles)
    found = grammar.judge(rows, None, spec)
    move = spec.get("move")
    return {
        "preset": preset,
        "knobs": knobs,
        "move": move,
        "beats": [{k: b.get(k) for k in ("name", "from", "to", "flash", "shape", "palette")} for b in spec["beats"]],
        "layers": sorted(rows, key=lambda r: (r["delay"], r["name"])),
        "found": found,
        "moved": variants.moved(base, tl, roles) if knobs else {},
        "loops": {s: _loop(preset, tl, knobs, s) for s in ("real", "slow")},
        "seconds": round(variants.span(tl), 3),
    }


def pick(preset, body):
    entry = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "verdict": body["verdict"],
        "knobs": _clean(body.get("knobs")),
        "note": str(body.get("note", ""))[:500],
    }
    if entry["verdict"] not in ("keep", "drop") or not entry["knobs"]:
        raise ValueError("a pick needs verdict keep or drop and at least one knob")
    base = core.load(preset, fps=60)
    roles = grammar.roles_from_sheet(beats.sheet(preset))
    entry["moved"] = variants.moved(base, variants.apply(base, roles, entry["knobs"]), roles)
    os.makedirs(PICKS, exist_ok=True)
    path = os.path.join(PICKS, preset + ".json")
    with LOCK:
        rows = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
        rows.append(entry)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1)
            f.write("\n")
    return {"saved": len(rows), "path": os.path.relpath(path, core.ROOT)}


def picks(preset):
    path = os.path.join(PICKS, preset + ".json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ layer kits

KIT_ID = re.compile(r"^[A-Za-z0-9]{1,32}$")
_kits = {"mtime": None, "data": None}


def kits():
    """Presets.Kits as tests/kits.luau prints it, re-read when Presets.luau or a kit in EVFX_KITS
    changes."""
    mtime = max(os.path.getmtime(p) for p in core.kit_sources())
    with LOCK:
        if _kits["mtime"] != mtime:
            env = {**os.environ, "EVFX_KITS": ":".join(core.kit_dirs())}
            done = subprocess.run([core.lune(), "run", "tests/kits.luau"], cwd=core.ROOT, capture_output=True, text=True, env=env)
            if done.returncode != 0:
                raise RuntimeError("tests/kits.luau failed: " + done.stderr[-400:])
            _kits["data"], _kits["mtime"] = json.loads(done.stdout), mtime
        return _kits["data"]


def _kit(name):
    data = kits()
    if not NAME.match(name or "") or name not in data:
        raise LookupError(f"no layer kit named {name!r}")
    return data[name]


def _kit_picks_path(name):
    # a kit kept in a game's repo (EVFX_KITS, kits/<kit>.luau) keeps its picks there too
    for d in core.kit_dirs():
        if os.path.exists(os.path.join(d, "kits", f"{name}.luau")):
            return os.path.join(d, "picks", f"kit_{name}.json")
    return os.path.join(PICKS, f"kit_{name}.json")


def kit_picks(name):
    path = _kit_picks_path(name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _current(name):
    """The studio's latest pick per layer."""
    out = {}
    for row in kit_picks(name):
        out[row["layer"]] = row["variant"]
    return out


def _seen_path(name):
    # what Phát last looked at: local to this machine, so it lives in the cache, not the repo
    return os.path.join(OUT, f"kit_{name}_seen.json")


def _seen(name):
    path = _seen_path(name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _shas(manifests=None):
    """Each texture's sha256 from the pack manifests (or from given manifest texts)."""
    out = {}
    if manifests is None:
        manifests = []
        for rel in ("pack/generated/manifest.json", "pack/cc0/manifest.json"):
            path = os.path.join(core.ROOT, rel)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    manifests.append(f.read())
    for text in manifests:
        for key, entry in json.loads(text).get("textures", {}).items():
            out[key] = entry.get("sha256")
    return out


def _with_textures(layers, shas):
    """Layers with their texture's checksum, so a redrawn texture shows as a change."""
    return [{**layer, "texture": (shas.get(layer["pack"], "")[:12] if layer.get("pack") else None)} for layer in layers]


def _short(value):
    text = json.dumps(value, separators=(",", " "))
    return text if len(text) <= 48 else text[:45] + "..."


def _diff(old, new):
    """What changed between two variants' layer lists, one line per change, at most 10."""
    lines = []
    if old["note"] != new["note"]:
        lines.append("note: " + new["note"])
    a, b = old["layers"], new["layers"]
    for i in range(max(len(a), len(b))):
        if i >= len(a):
            lines.append(f"+ {b[i].get('name', b[i].get('type', 'layer'))} ({b[i].get('pack', b[i].get('type', ''))})")
            continue
        if i >= len(b):
            lines.append(f"- {a[i].get('name', a[i].get('type', 'layer'))}")
            continue
        label = b[i].get("name", b[i].get("type", f"layer {i + 1}"))
        for key in sorted(set(a[i]) | set(b[i])):
            if key in ("group", "hd") or a[i].get(key) == b[i].get(key):
                continue
            if key == "texture":
                if a[i].get("pack") == b[i].get("pack") and a[i].get(key) is not None:
                    lines.append(f"{label}: texture {b[i].get('pack')} redrawn")
                continue
            lines.append(f"{label}.{key}: {_short(a[i].get(key))} → {_short(b[i].get(key))}")
    return lines[:10] + ([f"... and {len(lines) - 10} more"] if len(lines) > 10 else [])


def _version(kit, shas):
    """A fingerprint of a kit's variants and their textures: the page sends back the one it
    showed, so Mark seen never marks a change that arrived after the page loaded."""
    used = sorted({layer.get("pack") for x in kit["layers"] for v in x["variants"].values() for layer in v["layers"] if layer.get("pack")})
    blob = json.dumps([kit["layers"], [shas.get(k) for k in used]], sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def kit_seen(name, body):
    """Marks one layer (or every layer) as seen: its variants as they are now become the
    baseline the page compares against. Refused when the kit changed since the page loaded."""
    kit = _kit(name)
    if body.get("version") != _version(kit, _shas()):
        raise ValueError("something new arrived since this page loaded: reload to see it before marking it seen")
    snap = _seen(name) or {"variants": {}}
    only = body.get("layer")
    if not only:
        # every layer: the baseline is the kit as it is now, so variants of layers that are gone
        # stop showing as removed
        snap["variants"] = {}
    for layer in kit["layers"]:
        if only and layer["name"] != only:
            continue
        for key in list(snap["variants"]):
            if key.split("/")[0] == layer["name"]:
                del snap["variants"][key]
        shas = _shas()
        for key, v in layer["variants"].items():
            snap["variants"][f"{layer['name']}/{key}"] = {"note": v["note"], "layers": _with_textures(v["layers"], shas)}
    snap["from"] = "marked seen " + time.strftime("%Y-%m-%d %H:%M")
    os.makedirs(OUT, exist_ok=True)
    with LOCK, open(_seen_path(name), "w", encoding="utf-8") as f:
        json.dump(snap, f)
    return {"ok": True}


def kit_page(name):
    kit = _kit(name)
    snap = _seen(name)
    changes = {"new": 0, "changed": 0, "removed": []}
    current = set()
    shas = _shas()
    beat_of = {}
    spec = beats.sheet(kit["preset"])
    for b in spec["beats"]:
        for names in (b.get("layers") or {}).values():
            for n in names:
                beat_of[n] = b["name"]
    layers = []
    for layer in kit["layers"]:
        variants = {}
        for key, v in layer["variants"].items():
            ident = f"{layer['name']}/{key}"
            current.add(ident)
            status, diff = "same", []
            if snap is not None:
                was = snap["variants"].get(ident)
                if was is None:
                    status = "new"
                else:
                    diff = _diff(was, {"note": v["note"], "layers": _with_textures(v["layers"], shas)})
                    status = "changed" if diff else "same"
            if status != "same":
                changes[status] += 1
            variants[key] = {"note": v["note"], "count": v["count"], "status": status, "diff": diff}
        layers.append({"name": layer["name"], "beat": beat_of.get(layer["name"], ""), "variants": variants})
    if snap is not None:
        changes["removed"] = sorted(k for k in snap["variants"] if k not in current)
    return {"kit": name, "preset": kit["preset"], "story": spec.get("story", ""), "layers": layers,
            "kitPicks": kit["picks"], "picks": _current(name), "history": kit_picks(name),
            "changes": changes, "since": (snap or {}).get("from"), "version": _version(kit, shas)}


_SPANS = {}


def _kit_span(name):
    """How long the kit's whole effect plays, from its preset (cached per kit version)."""
    kit = _kit(name)
    key = (name, _version(kit, _shas()))
    if key not in _SPANS:
        _SPANS[key] = variants.span(core.load(kit["preset"], fps=60))
    return _SPANS[key]


def _cams(name):
    """Every kit render uses the same ground camera (the reference's angle), so variants compare."""
    preset = _kit(name)["preset"]
    return core.views(core.load(preset, fps=60), (360, 240))["ground"]


def kit_render(name, layer, variant, mode):
    kit = _kit(name)
    found = next((x for x in kit["layers"] if x["name"] == layer), None)
    if not found or variant not in found["variants"] or mode not in ("solo", "in"):
        raise LookupError("no such layer or variant")
    picks = _current(name) if mode == "in" else {}
    env = {"EVFX_KIT_PICKS": json.dumps({name: picks})} if picks else None
    # the kit's fingerprint covers its layers and their textures, so a redrawn texture renders
    # again (before, only Presets.luau's time did, and the page kept showing the old texture)
    key = hashlib.sha1(json.dumps([layer, variant, mode, picks, _version(kit, _shas()), "ground-cam", "seeded", "full-span", "25fps"], sort_keys=True).encode()).hexdigest()[:12]
    out = f"kit-{name}-{key}.gif"
    path = os.path.join(OUT, out)
    if not os.path.exists(path):
        tid = f"kit__{name}__{layer}__{variant}" + ("__in" if mode == "in" else "")
        folder = os.path.join(core.CACHE, "timeline", f"kit-{key}")
        tl = core.load(tid, folder=folder, fresh=True, fps=60, env=env)
        cam = _cams(name)
        # every card plays the whole effect's length, alone or inside it, so the two loop in step
        span = max(_kit_span(name), variants.span(tl), 0.5)
        # 25 fps: GIF frame times are in hundredths of a second, so 40 ms is exact and every card
        # of every length stays in step
        step = 1 / 25
        # a kit's effect sits on the floor, not on a character: no stand-in body over it
        frames = [render.to_image(render.draw(tl, k * step, cam, body=False)[0]) for k in range(int(span / step) + 1)]
        blank = render.to_image(render.draw({**tl, "frames": [], "bursts": [], "emitters": []}, 0, cam, body=False)[0])
        frames += [blank] * 8
        os.makedirs(OUT, exist_ok=True)
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=40, loop=0, optimize=True)
    return {"gif": "/out/" + out}


def kit_pick(name, body):
    kit = _kit(name)
    layer, variant = str(body.get("layer", "")), str(body.get("variant", ""))
    found = next((x for x in kit["layers"] if x["name"] == layer), None)
    if not found or variant not in found["variants"]:
        raise ValueError("a pick needs a layer and one of its variants")
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "layer": layer, "variant": variant, "note": str(body.get("note", ""))[:500]}
    path = _kit_picks_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with LOCK:
        rows = kit_picks(name)
        rows.append(entry)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1)
            f.write("\n")
    return {"saved": len(rows), "picks": _current(name), "path": os.path.relpath(path, core.ROOT)}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, kind="application/json"):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _preset(self, name):
        if not NAME.match(name or "") or name not in beats.sheets():
            raise LookupError(f"no effect with a beat sheet named {name!r}")
        return name

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        try:
            if not parts:
                data = {"effects": beats.sheets(), "knobs": _knobs(), "kits": sorted(kits())}
                return self._send(200, _template("index.html", data), "text/html; charset=utf-8")
            if parts[0] == "fx" and len(parts) == 2:
                preset = self._preset(parts[1])
                data = {"effect": effect(preset), "knobs": _knobs(), "picks": picks(preset), "plan": [[k, label, knob] for k, label, knob in variants.PLAN if knob and knob[0] != "depth"]}
                return self._send(200, _template("fx.html", data), "text/html; charset=utf-8")
            if parts[0] == "kit" and len(parts) == 2:
                return self._send(200, _template("kit.html", kit_page(parts[1])), "text/html; charset=utf-8")
            if parts == ["mold"]:
                return self._send(200, _template("mold.html", mold_page()), "text/html; charset=utf-8")
            if parts[:2] == ["api", "mold"] and len(parts) == 3 and parts[2] == "base":
                bank, mold = _texgen()
                q = urllib.parse.parse_qs(url.query)
                base = q.get("id", ["blob"])[0]
                if base != "blob":
                    bank.get(base)
                size = min(512, max(64, int(q.get("size", ["256"])[0])))
                return self._send(200, mold.to_png(mold.base_alpha(base, int(q.get("cell", ["0"])[0]), size)), "image/png")
            if parts[:3] == ["api", "mold", "load"] and len(parts) == 4:
                _, mold = _texgen()
                return self._send(200, mold.load(parts[3]))
            if parts[0] == "out" and len(parts) == 2 and re.match(r"^([a-z0-9_]+-[0-9a-f]{12}\.(real|slow)|kit-[a-z0-9_]+-[0-9a-f]{12})\.gif$", parts[1]):
                path = os.path.join(OUT, parts[1])
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        return self._send(200, f.read(), "image/gif")
            return self._send(404, {"error": "not found"})
        except LookupError as e:
            return self._send(404, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": repr(e)})

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        try:
            # a mold carries its whole warp grid, so it may be larger than the other requests
            cap = 4 * 1024 * 1024 if parts[:2] == ["api", "mold"] else 65536
            length = min(int(self.headers.get("Content-Length", 0)), cap)
            body = json.loads(self.rfile.read(length) or b"{}")
            if parts[:2] == ["api", "mold"] and len(parts) == 3:
                _, mold = _texgen()
                if parts[2] == "render":
                    size = min(512, max(64, int(body.get("size", 256))))
                    return self._send(200, mold.to_png(mold.render(body["mold"], size)), "image/png")
                if parts[2] == "save":
                    with LOCK:
                        where = mold.save(str(body.get("name")), body["mold"])
                        tid = mold.register(str(body.get("name")))
                    return self._send(200, {"saved": os.path.relpath(where), "id": tid})
            if parts[:2] == ["api", "kit"] and len(parts) == 4:
                if parts[3] == "render":
                    return self._send(200, kit_render(parts[2], str(body.get("layer")), str(body.get("variant")), str(body.get("mode", "solo"))))
                if parts[3] == "pick":
                    return self._send(200, kit_pick(parts[2], body))
                if parts[3] == "seen":
                    return self._send(200, kit_seen(parts[2], body))
            if parts[:1] == ["api"] and len(parts) == 3:
                preset = self._preset(parts[2])
                if parts[1] == "render":
                    return self._send(200, effect(preset, body.get("knobs")))
                if parts[1] == "pick":
                    return self._send(200, pick(preset, body))
            return self._send(404, {"error": "not found"})
        except (LookupError, ValueError) as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": repr(e)})


def run(port=8765, host="127.0.0.1"):
    server = http.server.ThreadingHTTPServer((host, port), Handler)
    where = "127.0.0.1" if host in ("127.0.0.1", "localhost") else f"{host} (the local network: no sign-in, anyone on it can save picks)"
    print(f"evfx serve: http://127.0.0.1:{port} on {where}  (Ctrl+C stops it)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
