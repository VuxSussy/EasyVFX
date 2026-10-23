"""The rules every texture must pass before anyone sees it in Studio (plan §3).

    fails = checks.check(entry, rgba)    # [] when it passes, else one line per failure

- power of two, at most 1024, on both sides;
- white RGB (shape in alpha), unless the entry allows colour;
- a flipbook or sheet divides by its grid, and a flipbook has grid x grid frames;
- sprites (each frame of a flipbook or sheet, each shape and decal) fade to zero before
  their border, so nothing clips when the engine scales them;
- strips tile along their length and fade at their top and bottom; sources tile both ways;
- a dissolve's last frame is empty.
"""

import numpy as np

BORDER = 2 / 255  # the most alpha allowed on a sprite's border
EMPTY = 1 / 255  # the most alpha allowed anywhere in a dissolve's last frame
SEAM = 2.5  # a tiled edge may differ at most this many times the texture's typical neighbour difference
SPRITES = ("shape", "decal", "flipbook", "sheet")


def _pot(n):
    return n > 0 and n & (n - 1) == 0


def cells(alpha, grid):
    h, w = alpha.shape
    ch, cw = h // grid, w // grid
    return [alpha[r * ch : (r + 1) * ch, c * cw : (c + 1) * cw] for r in range(grid) for c in range(grid)]


def border_max(cell, width=None):
    width = width or max(1, cell.shape[0] // 128)
    return float(max(cell[:width].max(), cell[-width:].max(), cell[:, :width].max(), cell[:, -width:].max()))


def seam(alpha, axis):
    """How much a tiled edge jumps, against the texture's own pixel-to-pixel change."""
    a = alpha if axis == 1 else alpha.T
    edge = np.abs(a[:, 0] - a[:, -1]).mean()
    inner = np.abs(np.diff(a, axis=1)).mean()
    return float(edge / max(inner, 1e-4)), float(edge)


def check(entry, rgba):
    fails = []
    h, w = rgba.shape[:2]
    alpha = rgba[..., 3].astype(np.float32) / 255
    kind = entry["kind"]
    grid = int(entry.get("grid", 1))
    if not (_pot(w) and _pot(h) and w <= 1024 and h <= 1024):
        fails.append(f"size {w}x{h}: both sides must be powers of two, at most 1024")
    if entry.get("rgb") != "spectrum" and (rgba[..., :3] != 255).any():
        fails.append("RGB is not white: the shape belongs in alpha")
    if alpha.max() < 0.25:
        fails.append(f"nearly empty: peak alpha {alpha.max():.2f}")
    if grid > 1 and (w % grid or h % grid):
        fails.append(f"size {w}x{h} does not divide by its {grid}x{grid} grid")
        return fails
    frames = cells(alpha, grid)
    if kind == "flipbook" and entry.get("frames", grid * grid) != grid * grid:
        fails.append(f"{entry['frames']} frames for a {grid}x{grid} grid")
    if kind in SPRITES:
        for i, c in enumerate(frames):
            b = border_max(c)
            if b > BORDER:
                where = f"frame {i}" if grid > 1 else "sprite"
                fails.append(f"{where} reaches its border (alpha {b:.3f}): fade it before the edge")
                break
    if entry.get("dissolve") and frames[-1].max() > EMPTY:
        fails.append(f"dissolve's last frame is not empty (alpha {frames[-1].max():.3f})")
    if kind in ("strip", "source"):
        ratio, edge = seam(alpha, 1)
        if ratio > SEAM and edge > 1 / 255:
            fails.append(f"left and right edges don't match (seam {ratio:.1f}x the texture's own change)")
    if kind == "source":
        ratio, edge = seam(alpha, 0)
        if ratio > SEAM and edge > 1 / 255:
            fails.append(f"top and bottom edges don't match (seam {ratio:.1f}x)")
    if kind == "strip":
        top = float(max(alpha[:2].max(), alpha[-2:].max()))
        if top > BORDER:
            fails.append(f"strip reaches its top or bottom edge (alpha {top:.3f})")
    return fails
