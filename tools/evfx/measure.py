"""The census, gates and scores of a timeline.

Gates are pass or fail with a reason (budget, ends clean, flash length and rate, plain
blocks). Scores are numbers to compare before and after (how much of the far view an
effect covers, how much of the body it buries, how crisp its edges are). Limits live in
tools/evfx/rules.json, never in code; a preset may override them under "presets".
"""

import json
import os

import numpy as np
from PIL import Image, ImageFilter

from . import core, render

RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.json")
GLOWING = render.GLOWING


def rules(preset=None):
    with open(RULES, encoding="utf-8") as f:
        data = json.load(f)
    if preset and preset in data.get("presets", {}):
        merged = dict(data)
        for key, value in data["presets"][preset].items():
            if isinstance(value, dict):
                merged[key] = {**data.get(key, {}), **value}
            else:
                merged[key] = value
        return merged
    return data


def census(timeline):
    """One row per frame: what is live."""
    rows = []
    for frame in timeline["frames"]:
        t = frame["t"]
        plain = sum(1 for p in frame["parts"] if p["material"] not in GLOWING)
        rows.append(
            {
                "t": t,
                "particles": len(core.particles_at(timeline, t)),
                "beams": len(frame["beams"]),
                "pieces": len(frame["parts"]),
                "plain": plain,
                "lights": len(frame["lights"]),
                "screens": len(frame["screens"]),
                "trails": frame["trails"],
                "fov": round(frame["fov"] - timeline["fovHome"], 2),
            }
        )
    return rows


def _runs(flags):
    runs, current = [], 0
    for on in flags:
        if on:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return runs


def gates(timeline, rows, limits):
    """Each gate: (name, ok, reason)."""
    out = []
    budget = limits["budget"]
    for key, cap in budget.items():
        peak = max((r[key] for r in rows), default=0)
        out.append((f"budget.{key}", peak <= cap, f"peak {peak} (cap {cap})"))
    if timeline["kind"] == "burst":
        seconds = core.duration(timeline)
        left = timeline["leftover"]
        cap = limits["burstSeconds"]
        ok = left == 0 and seconds <= cap
        reason = f"lasts {seconds:.2f} s (cap {cap}), {left} left behind"
        out.append(("ends_clean", ok, reason))
    screens = _runs([r["screens"] > 0 for r in rows])
    longest = max(screens, default=0)
    out.append(("flash.frames", longest <= limits["flashFrames"], f"longest screen flash {longest} frames (cap {limits['flashFrames']})"))
    seconds = max(core.duration(timeline), timeline["frameTime"])
    rate = len(screens) / seconds if seconds >= 1 else len(screens)
    out.append(
        (
            "flash.rate",
            rate <= limits["flashesPerSecond"],
            f"{len(screens)} screen flashes in {seconds:.2f} s (cap {limits['flashesPerSecond']}/s)",
        )
    )
    plain = max((r["plain"] for r in rows), default=0)
    out.append(("plain_pieces", plain <= limits["plainPieces"], f"peak {plain} plain blocks (cap {limits['plainPieces']})"))
    return out


def _luminance(rgb):
    return rgb.mean(axis=2)


def scores(timeline, limits, moments=None):
    """Rendered scores over a few moments: far coverage, body buried, crispness."""
    cams = core.views(timeline)
    count = moments or limits["moments"]
    span = core.duration(timeline)
    times = [span * k / max(1, count - 1) for k in range(count)]
    lit = limits["scores"]["lit"]
    bright = limits["scores"]["bright"]
    empty_far = render.draw({**timeline, "frames": [], "bursts": [], "emitters": []}, 0, cams["far"])[0]
    empty_close = render.draw({**timeline, "frames": [], "bursts": [], "emitters": []}, 0, cams["close"])[0]
    coverage, buried, crisp = 0.0, 0.0, []
    for t in times:
        far, _ = render.draw(timeline, t, cams["far"])
        diff = np.abs(far - empty_far).mean(axis=2)
        coverage = max(coverage, float((diff > lit).mean()))
        close, info = render.draw(timeline, t, cams["close"])
        cdiff = np.abs(close - empty_close).mean(axis=2)
        body = info["body"]
        if body is not None and body.any():
            buried = max(buried, float((cdiff[body] > bright).mean()))
        effect = cdiff > lit
        if effect.sum() > 50:
            lum = _luminance(close)
            blur = np.asarray(Image.fromarray((lum * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)), np.float32) / 255.0
            hf = np.abs(lum - blur)[effect].mean()
            crisp.append(float(hf / max(1e-3, lum[effect].mean())))
    return {
        "coverage_far": round(coverage, 4),
        "body_buried": round(buried, 4),
        "crisp": round(float(np.mean(crisp)) if crisp else 0.0, 4),
    }


def summary(timeline, with_scores=True):
    limits = rules(timeline["id"])
    rows = census(timeline)
    peak = {k: max((r[k] for r in rows), default=0) for k in ("particles", "beams", "pieces", "plain", "lights", "screens")}
    result = {
        "id": timeline["id"],
        "kind": timeline["kind"],
        "seconds": round(core.duration(timeline), 3),
        "peak": peak,
        "gates": [{"name": n, "ok": ok, "reason": r} for n, ok, r in gates(timeline, rows, limits)],
    }
    if with_scores:
        result["scores"] = scores(timeline, limits)
    return result, rows
