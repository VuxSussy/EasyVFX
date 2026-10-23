"""Reference clips, cut into beats and measured, for the beat judge.

A reference is a video someone else made (plan §1). Its frames and its art stay in
.cache/refs, untracked (call 4); what is committed is the cut and the numbers measured from
it, in tools/evfx/references/<name>.json: where each beat starts and ends (60 fps frames, from
docs/refs/dissection-lotus-frigid.md) and, per beat, the same stats the judge reads from our
own render. `evfx ref <name> --build` re-measures them from the clip.

Every stat is about shape, not level, so a dark stage and our grey render compare:
    length    frames in the beat
    peak_at   frames from the beat's start to its brightest frame
    rise      frames from 10% to 90% of the peak (how hard it comes on)
    half      frames from the peak until it falls under half (how fast it lets go)
    tenth     frames from the peak until it falls under a tenth
    flash     frames the white share holds within 10% of its peak, over what was there
              before (flash beats; Lotus's flare reads 2)
    hues      hue bins holding at least 8% of the coloured pixels
    top       the hue names holding at least 15%
    calm      frame-to-frame change over brightness (low is still)
"""

import json
import os
import subprocess

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(HERE, "references")
NAMES = ["red", "gold", "yellow", "lime", "green", "spring", "cyan", "azure", "blue", "violet", "magenta", "pink"]


def hue_index(name):
    return NAMES.index(name)


def measure_clip(path):
    """Per-frame curves of a clip at its own frame rate, downscaled: brightness, white
    share, frame change and a 12-bin hue histogram of the saturated pixels. Cached as
    <clip>.npz beside the clip."""
    cached = os.path.splitext(path)[0] + ".npz"
    if os.path.exists(cached) and os.path.getmtime(cached) >= os.path.getmtime(path):
        z = np.load(cached)
        return {"lum": z["lum"], "white": z["white"], "motion": z["diff"], "hue": z["hue"]}
    w, h = 320, 180
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
        check=True,
    ).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3).astype(np.float32) / 255
    hi, lo, lum = frames.max(3), frames.min(3), frames.mean(3)
    sat = np.where(hi > 0.05, (hi - lo) / np.maximum(hi, 1e-4), 0)
    r, g, b = frames[..., 0], frames[..., 1], frames[..., 2]
    hue = np.degrees(np.arctan2(np.sqrt(3) * (g - b), 2 * r - g - b)) % 360
    hist = np.zeros((len(frames), 12))
    for i in range(len(frames)):
        m = (sat[i] > 0.4) & (hi[i] > 0.35)
        if m.any():
            hist[i] = np.bincount((hue[i][m] // 30).astype(int), minlength=12)[:12] / m.sum()
    diff = np.concatenate([[0], np.abs(np.diff(lum, axis=0)).mean((1, 2))])
    np.savez_compressed(
        cached, lum=lum.mean((1, 2)), sat=sat.mean((1, 2)), bright=(hi > 0.8).mean((1, 2)),
        white=(lo > 0.8).mean((1, 2)), diff=diff, hue=hist, n=len(frames),
    )
    return measure_clip(path)


def _run_through(flags, at):
    """Length of the run of True in `flags` that contains index `at`."""
    if at < 0 or at >= len(flags) or not flags[at]:
        return 0
    lo = hi = at
    while lo > 0 and flags[lo - 1]:
        lo -= 1
    while hi < len(flags) - 1 and flags[hi + 1]:
        hi += 1
    return hi - lo + 1


def stats(curves, a, b, flash=False, base=0.0):
    """The stats of one beat, frames a to b inclusive, from per-frame curves: `lum`
    (added brightness), `white`, `motion` and `hue` (rows of 12 shares)."""
    lum = np.asarray(curves["lum"], float) - base
    white = np.asarray(curves["white"], float)
    motion = np.asarray(curves["motion"], float)
    hue = np.asarray(curves["hue"], float)
    n = len(lum)
    a, b = max(0, a), min(n - 1, b)
    out = {"length": b - a, "peak_at": 0, "rise": 0, "half": 0, "tenth": 0, "flash": 0, "hues": 0, "top": [], "calm": 0.0}
    if b < a:
        return out
    seg = lum[a : b + 1]
    peak = a + int(seg.argmax())
    m = lum[peak]
    if m <= 1e-4:
        return out
    out["peak_at"] = peak - a
    start = max(0, a - 6)
    before = lum[start : peak + 1]
    up10 = start + int(np.argmax(before >= 0.1 * m))
    up90 = start + int(np.argmax(before >= 0.9 * m))
    out["rise"] = max(0, up90 - up10)
    end = min(n, b + max(30, b - a) + 1)
    after = lum[peak:end]
    below = np.nonzero(after < 0.5 * m)[0]
    out["half"] = int(below[0]) if len(below) else len(after)
    below = np.nonzero(after < 0.1 * m)[0]
    out["tenth"] = int(below[0]) if len(below) else len(after)
    if flash:
        lo, hi = max(0, a - 4), min(n, b + 5)
        before = white[max(0, a - 30) : a - 3] if a > 3 else white[:0]
        w = white[lo:hi] - (float(np.median(before)) if len(before) else 0.0)
        if len(w) and w.max() > 1e-4:
            at = int(w.argmax())
            out["flash"] = _run_through(w >= 0.9 * w.max(), at)
    share = hue[a : b + 1].mean(axis=0)
    if share.sum() > 0:
        share = share / share.sum()
        out["hues"] = int((share >= 0.08).sum())
        out["top"] = [NAMES[k] for k in np.argsort(share)[::-1] if share[k] >= 0.15]
    out["calm"] = round(float(motion[a : b + 1].mean() / max(1e-4, seg.mean())), 3)
    return out


def load(name):
    path = os.path.join(FOLDER, name + ".json")
    if not os.path.exists(path):
        raise SystemExit(f"evfx: no reference named {name} (tools/evfx/references)")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def beat(spec):
    """'lotus:flare' to that beat of that reference, with its stats."""
    name, _, key = spec.partition(":")
    for row in load(name)["beats"]:
        if row["name"] == key:
            return row
    raise SystemExit(f"evfx: reference {name} has no beat {key}")


def build(name, clip=None):
    """Re-measures every beat of a reference from its clip and writes the stats back."""
    ref = load(name)
    from . import core

    clip = clip or os.path.join(core.ROOT, ref["clip"])
    if not os.path.exists(clip):
        raise SystemExit(f"evfx: {clip} is missing; download the reference first ({ref['source']})")
    curves = measure_clip(clip)
    base = float(np.percentile(curves["lum"], 5))
    for row in ref["beats"]:
        row["stats"] = stats(curves, row["from"], row["to"], row.get("flash", False), base)
    with open(os.path.join(FOLDER, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(ref, f, indent=1)
        f.write("\n")
    return ref
