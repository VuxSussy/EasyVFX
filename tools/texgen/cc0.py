"""CC0 texture packs, imported into the library (pack/cc0).

Phát lifted decision 4 for CC0 art on 2026-10-24. The rules in cc0.json pick what to take
from each pack (downloaded into .cache/cc0, one folder per pack) and how to normalize it to
the pack convention:

    white   white RGB, the shape in alpha (alpha x brightness): tinted in Roblox, like
            library v4
    luma    grey shading in RGB, alpha kept: smoke and foliage keep their form
    source  the pack's own colour, alpha kept (fire, coloured hand-drawn hits)

Animations become Roblox flipbooks. Roblox plays only 4, 16 or 64 frames, so a sequence is
resampled in time to the nearest of those (frames dropped or held, never blended) and
packed into a 2x2, 4x4 or 8x8 grid. Every texture keeps its source, author, licence and
original path in pack/cc0/manifest.json.

    python tools/texgen cc0 [--dry]
"""

import fnmatch
import glob
import hashlib
import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RULES = os.path.join(HERE, "cc0.json")
SRC = os.path.join(ROOT, ".cache", "cc0")
OUT = os.path.join(ROOT, "pack", "cc0")
GRIDS = {4: 2, 16: 4, 64: 8}


def _load(path):
    img = Image.open(path)
    if img.mode == "P":
        img = img.convert("RGBA")
    return np.asarray(img.convert("RGBA"), np.float32) / 255


def _alpha_from_black(rgba):
    """A texture drawn on black (no real alpha): alpha from its brightest channel."""
    if rgba[..., 3].min() > 0.99:
        a = rgba[..., :3].max(axis=2)
        rgb = rgba[..., :3] / np.maximum(a[..., None], 1e-4)
        return np.dstack([np.clip(rgb, 0, 1), a])
    return rgba


def normalize(rgba, mode):
    rgba = _alpha_from_black(rgba)
    rgb, a = rgba[..., :3], rgba[..., 3]
    lum = rgb.max(axis=2)
    if mode == "white":
        return np.dstack([np.ones_like(rgb), a * lum])
    if mode == "luma":
        g = (rgb @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
        g = g / max(1e-3, float(g[a > 0.1].max()) if (a > 0.1).any() else 1.0)
        return np.dstack([np.repeat(np.clip(g, 0, 1), 3, axis=2), a])
    return rgba


def _resize(rgba, side):
    h, w = rgba.shape[:2]
    k = side / max(h, w)
    if k >= 1:
        return rgba
    img = Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA")
    return np.asarray(img.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS), np.float32) / 255


def _square(rgba):
    h, w = rgba.shape[:2]
    s = max(h, w)
    out = np.zeros((s, s, 4), np.float32)
    out[(s - h) // 2 : (s - h) // 2 + h, (s - w) // 2 : (s - w) // 2 + w] = rgba
    return out


def cells(rgba, cols, rows):
    """A sheet's frames in reading order, dropping trailing empty cells."""
    h, w = rgba.shape[:2]
    out = []
    for r in range(rows):
        for c in range(cols):
            cell = rgba[r * h // rows : (r + 1) * h // rows, c * w // cols : (c + 1) * w // cols]
            out.append(cell)
    while out and out[-1][..., 3].mean() < 0.002:
        out.pop()
    return out


def resample(frames, n):
    """`frames` to `n` frames in time, by nearest frame (held or dropped, never blended)."""
    if len(frames) == n:
        return frames
    idx = np.round(np.linspace(0, len(frames) - 1, n)).astype(int)
    return [frames[i] for i in idx]


def atlas(frames, side):
    n = len(frames)
    grid = GRIDS[n]
    cell = side // grid
    sheet = np.zeros((side, side, 4), np.float32)
    for i, f in enumerate(frames):
        f = _square(f)
        img = Image.fromarray((np.clip(f, 0, 1) * 255).astype(np.uint8), "RGBA").resize((cell, cell), Image.LANCZOS)
        r, c = divmod(i, grid)
        sheet[r * cell : (r + 1) * cell, c * cell : (c + 1) * cell] = np.asarray(img, np.float32) / 255
    return sheet, grid


def _frames_for(n):
    return min(GRIDS, key=lambda k: (abs(k - n), -k))


def _save(rgba, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".png")
    Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA").save(path, optimize=True)
    with open(path, "rb") as f:
        return path, hashlib.sha256(f.read()).hexdigest()


def _slug(text):
    keep = "".join(ch if ch.isalnum() else "_" for ch in text.lower())
    while "__" in keep:
        keep = keep.replace("__", "_")
    return keep.strip("_")


def run(dry=False):
    with open(RULES, encoding="utf-8") as f:
        rules = json.load(f)
    packs = rules["packs"]
    manifest = {"library": "cc0", "note": rules["note"], "textures": {}}
    for rule in rules["rules"]:
        pack = packs[rule["pack"]]
        base = os.path.join(SRC, pack["folder"])
        if not os.path.isdir(base):
            raise SystemExit(f"texgen cc0: {base} is missing; download {pack['url']} and unzip it there")
        files = sorted(p for p in glob.glob(os.path.join(base, rule["glob"]), recursive=True) if "__MACOSX" not in p)
        files = [p for p in files if not any(fnmatch.fnmatch(os.path.basename(p), x) for x in rule.get("skip", []))]
        groups = {}
        if rule["kind"] in ("shape",):
            for p in files:
                groups[os.path.splitext(os.path.basename(p))[0]] = [p]
        elif rule["kind"] == "sequence-folder":
            groups[rule.get("name") or os.path.basename(os.path.dirname(files[0]))] = files
        else:
            for p in files:
                groups[os.path.splitext(os.path.basename(p))[0]] = [p]
        for key, paths in groups.items():
            clean = _slug(key.rsplit("_", 1)[0] if rule["kind"] == "sheet-grid" else key)
            name = f"cc0_{rule['prefix']}_{clean}"
            if rule["kind"] == "shape":
                rgba = _resize(_square(normalize(_load(paths[0]), rule["rgb"])), rule["size"])
                grid, frames = 1, 1
            else:
                if rule["kind"] == "sequence-folder":
                    seq = [normalize(_load(p), rule["rgb"]) for p in paths]
                else:
                    cols, rows = rule.get("grid") or _grid_from_name(key)
                    if "x" not in key.rsplit("_", 1)[-1]:
                        raise SystemExit(f"texgen cc0: {key} has no grid in its name")
                    seq = [normalize(c, rule["rgb"]) for c in cells(_load(paths[0]), cols, rows)]
                n = rule.get("frames") or _frames_for(len(seq))
                rgba, grid = atlas(resample(seq, n), rule["size"])
                frames = n
            role = next((r for stem, r in rule.get("roles", {}).items() if _slug(key).startswith(stem)), rule["role"])
            entry = {
                "id": f"cc0/{rule['prefix']}_{clean}",
                "kind": "shape" if frames == 1 else rule.get("as", "flipbook"),
                "size": [int(rgba.shape[1]), int(rgba.shape[0])],
                "grid": grid,
                "frames": frames,
                "role": role,
                "rgb": rule["rgb"],
                "upload": True,
                "use": rule["use"],
                "source": pack["title"],
                "author": pack["author"],
                "licence": "CC0",
                "url": pack["url"],
                "original": [os.path.relpath(p, base) for p in paths][:4] + (["..."] if len(paths) > 4 else []),
            }
            if dry:
                print(f"{name:<48} {entry['kind']:<8} {entry['size'][0]}x{entry['size'][1]} grid {grid} frames {frames}")
            else:
                _, sha = _save(rgba, name)
                entry["sha256"] = sha
            manifest["textures"][name] = entry
    if not dry:
        with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1)
            f.write("\n")
    return manifest


def _grid_from_name(name):
    """'fire_ring_6x5' to (6, 5)."""
    tail = name.rsplit("_", 1)[-1]
    cols, rows = tail.lower().split("x")
    return int(cols), int(rows)
