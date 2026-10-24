"""`evfx serve`: a local VFX studio in the browser, for people to look, tune and pick.

    python3 tools/evfx serve [--port 8765]   then open http://127.0.0.1:8765

Pages come from the templates in tools/evfx/web. For each effect with a beat sheet the
studio shows the effect looping, its layers in the grammar's numbers with what breaks
the grammar, and the knobs (tools/evfx/variants.py). Move the knobs and press Render to
see a variant beside the effect as built, then Keep or Drop it. Picks are appended to
tools/evfx/picks/<preset>.json, in the repo: they are the calibration evidence that sets
the grammar's ranges. The server listens on 127.0.0.1 only and never edits a preset.
"""

import hashlib
import http.server
import json
import os
import re
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
                data = {"effects": beats.sheets(), "knobs": _knobs()}
                return self._send(200, _template("index.html", data), "text/html; charset=utf-8")
            if parts[0] == "fx" and len(parts) == 2:
                preset = self._preset(parts[1])
                data = {"effect": effect(preset), "knobs": _knobs(), "picks": picks(preset), "plan": [[k, label, knob] for k, label, knob in variants.PLAN if knob and knob[0] != "depth"]}
                return self._send(200, _template("fx.html", data), "text/html; charset=utf-8")
            if parts[0] == "out" and len(parts) == 2 and re.match(r"^[a-z0-9_]+-[0-9a-f]{12}\.(real|slow)\.gif$", parts[1]):
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
            length = min(int(self.headers.get("Content-Length", 0)), 65536)
            body = json.loads(self.rfile.read(length) or b"{}")
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


def run(port=8765):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"evfx serve: http://127.0.0.1:{port}  (Ctrl+C stops it)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
