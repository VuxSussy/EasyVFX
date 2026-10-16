"""Removes dark fringes from VFX textures (edge padding / color bleed).

Renderers write black RGB into fully transparent pixels. Roblox filters textures
bilinearly and builds mipmaps from straight (not premultiplied) alpha, so that
black leaks into every soft edge: glows get a grey rim and effects look dirty and
"pixelated" as soon as they are a little far from the camera.

This pushes the color of the visible pixels outward into the transparent ones
(push-pull fill), leaving alpha untouched. Textures that are white with the
shape in alpha (all of pack/textures) simply become white everywhere.

    pip install pillow numpy
    python tools/fix_texture_edges.py pack/textures/*.png          # in place
    python tools/fix_texture_edges.py in.png --out fixed.png
"""

import argparse

import numpy as np
from PIL import Image


def downsample(rgb, w):
    h2, w2 = (rgb.shape[0] + 1) // 2, (rgb.shape[1] + 1) // 2
    pad_rgb = np.zeros((h2 * 2, w2 * 2, 3), np.float64)
    pad_w = np.zeros((h2 * 2, w2 * 2), np.float64)
    pad_rgb[: rgb.shape[0], : rgb.shape[1]] = rgb * w[..., None]
    pad_w[: w.shape[0], : w.shape[1]] = w
    s_rgb = pad_rgb.reshape(h2, 2, w2, 2, 3).sum(axis=(1, 3))
    s_w = pad_w.reshape(h2, 2, w2, 2).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(s_w[..., None] > 0, s_rgb / s_w[..., None], 0)
    return out, np.minimum(s_w, 1.0)


def bleed(rgb, weight):
    """Fills low-weight pixels with the weighted average of their surroundings."""
    if min(rgb.shape[:2]) <= 1 or weight.min() >= 1.0:
        return rgb
    small_rgb, small_w = downsample(rgb, weight)
    filled = bleed(small_rgb, small_w)
    up = filled.repeat(2, axis=0).repeat(2, axis=1)[: rgb.shape[0], : rgb.shape[1]]
    return rgb * weight[..., None] + up * (1 - weight[..., None])


def fix(path, out_path, threshold):
    img = Image.open(path).convert("RGBA")
    a = np.asarray(img).astype(np.float64) / 255.0
    rgb, alpha = a[..., :3], a[..., 3]
    if not (alpha > threshold).any():
        return False
    # Pixels clearly visible keep their color; everything else is rebuilt.
    weight = np.clip((alpha - threshold) / (0.5 - threshold), 0, 1)
    new_rgb = bleed(rgb, weight)
    out = np.dstack([new_rgb, alpha])
    Image.fromarray(np.round(out * 255).astype(np.uint8), "RGBA").save(out_path, optimize=True)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+")
    ap.add_argument("--out", help="output file (only with one input); default: overwrite")
    ap.add_argument("--threshold", type=float, default=0.02, help="alpha below this counts as empty")
    args = ap.parse_args()
    if args.out and len(args.images) != 1:
        ap.error("--out needs exactly one input image")
    for path in args.images:
        changed = fix(path, args.out or path, args.threshold)
        print(("fixed   " if changed else "skipped ") + path)


if __name__ == "__main__":
    main()
