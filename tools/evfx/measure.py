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
        plain = sum(1 for p in frame["parts"] if not render.glows(p))
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


def phases(timeline, limits=None, ks=None):
    """The grammar of plan §4, read frame by frame from the close view: how many frames
    the flash holds (the view's added brightness at least half its peak, the way the ZZZ
    capture was measured), the frame the burst peaks, when the tail ends, whether the
    brightest pixels are white, how many hues the effect uses and the most of the body
    it buries. `ks` limits the rows to those frame indices. Returns (summary, rows)."""
    limits = limits or rules(timeline.get("id"))
    lit, bright = limits["scores"]["lit"], limits["scores"]["bright"]
    cams = core.views(timeline)
    step = timeline.get("frameTime", 1 / 30)
    count = int(round(core.duration(timeline) / step)) + 1
    empty = render.draw({**timeline, "frames": [], "bursts": [], "emitters": []}, 0, cams["close"])[0]
    rows, hue_hist, last = [], np.zeros(12), empty
    for k in ks if ks is not None else range(count):
        t = k * step
        rgb, info = render.draw(timeline, t, cams["close"])
        diff = np.abs(rgb - empty).mean(axis=2)
        mask = diff > lit
        white = mask & (rgb.min(axis=2) > 0.85)
        row = {"t": round(t, 3), "coverage": float(mask.mean()), "white": float(white.mean()),
               "lum": float(np.clip(rgb - empty, 0, None).mean()), "core": 0.0, "buried": 0.0,
               "motion": float(np.abs(rgb - last).mean()), "hue": [0.0] * 12}
        last = rgb
        if mask.sum() > 20:
            px = rgb[mask]
            top = px[np.argsort(px.mean(axis=1))[-max(1, len(px) // 50):]]
            row["core"] = float(top.min(axis=1).mean())
            mx, mn = px.max(axis=1), px.min(axis=1)
            sat = (mx - mn) / np.maximum(mx, 1e-4)
            col = px[(sat > 0.35) & (mx > 0.2)]
            if len(col):
                r, g, b = col[:, 0], col[:, 1], col[:, 2]
                hue = (np.degrees(np.arctan2(np.sqrt(3) * (g - b), 2 * r - g - b)) % 360) // 30
                counts = np.bincount(hue.astype(int), minlength=12)[:12]
                hue_hist += counts
                row["hue"] = [round(float(c), 4) for c in counts / counts.sum()]
        body = info["body"]
        if body is not None and body.any():
            row["buried"] = float((diff[body] > bright).mean())
        rows.append(row)
    cov = np.array([r["coverage"] for r in rows])
    lum = np.array([r["lum"] for r in rows])
    flash = int((lum >= 0.5 * lum.max()).sum()) if len(lum) and lum.max() > 0.002 else 0
    alive = np.nonzero(cov > 0.003)[0]
    share = hue_hist / max(1, hue_hist.sum())
    peak = int(cov.argmax()) if len(cov) else 0
    summary = {
        "flash_frames": flash,
        "burst_peak_frame": peak,
        "tail_end": round(float(alive[-1] * step), 3) if len(alive) else 0.0,
        "core_white": round(rows[peak]["core"], 3) if rows else 0.0,
        "hues": int((share >= 0.08).sum()),
        "buried_peak": round(max((r["buried"] for r in rows), default=0.0), 3),
    }
    return summary, rows
