"""Pictures of the library for a person to judge: the contact sheet, the strips tiled
twice (a seam shows where they meet) and flipbook GIFs."""

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BACK = (18, 20, 25)
PANEL = (28, 31, 38)
TEXT = (225, 228, 235)
FAIL = (255, 110, 100)
CELL = 240
LABEL = 34
FAMILIES = [("shape", "Shapes"), ("flip", "Erosion flipbooks (4x4)"), ("seq", "Sequences (separate frames, for meshes)"), ("sheet", "Spritesheets (variants)"),
            ("strip", "Tiled strips (shown twice, end to end)"), ("art", "Art tier"), ("source", "Source maps (not uploaded)")]


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def composite(rgba, tint=(255, 255, 255), back=PANEL):
    """The texture over a dark panel, tinted the way the engine would (additive look)."""
    a = rgba[..., 3:4].astype(np.float32) / 255
    rgb = rgba[..., :3].astype(np.float32) * (np.array(tint, np.float32) / 255)
    out = np.array(back, np.float32) * (1 - a) + rgb * a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def tile2(rgba):
    return np.concatenate([rgba, rgba], axis=1)


def _fit(img, w, h):
    img = img.copy()
    img.thumbnail((w, h), Image.LANCZOS)
    return img


def contact(items, tint=(255, 255, 255), title="Library v4"):
    """items: [(id, rgba, fails)]. One row block per family; strips take two cells."""
    cols = 6
    blocks = []
    for fam, name in FAMILIES:
        rows = [it for it in items if it[0].split("/")[0] == fam]
        if rows:
            blocks.append((name, rows))
    layout, y = [], 56
    for name, rows in blocks:
        layout.append(("head", name, 0, y))
        y += 30
        x = 0
        for it in rows:
            span = 2 if it[0].startswith("strip/") else 1
            if x + span > cols:
                x, y = 0, y + CELL + LABEL
            layout.append(("cell", it, x, y))
            x += span
        y += CELL + LABEL + 12
    sheet = Image.new("RGB", (cols * CELL + 16, y), BACK)
    d = ImageDraw.Draw(sheet)
    d.text((8, 12), title, fill=TEXT, font=_font(22))
    small, head = _font(13), _font(16)
    for kind, it, x, yy in layout:
        if kind == "head":
            d.text((8, yy + 4), it, fill=TEXT, font=head)
            continue
        tex_id, rgba, fails = it
        span = 2 if tex_id.startswith("strip/") else 1
        w = span * CELL - 8
        px, py = 8 + x * CELL, yy
        d.rectangle([px, py, px + w, py + CELL - 8], fill=PANEL)
        img = composite(tile2(rgba) if span == 2 else rgba, tint)
        img = _fit(img, w, CELL - 8)
        sheet.paste(img, (px + (w - img.width) // 2, py + (CELL - 8 - img.height) // 2))
        h, ww = rgba.shape[:2]
        label = f"{tex_id}  {ww}x{h}"
        d.text((px + 2, py + CELL - 4), label, fill=TEXT, font=small)
        d.text((px + 2, py + CELL + 12), "FAIL: " + fails[0] if fails else "checks pass", fill=FAIL if fails else (130, 200, 140), font=small)
    return sheet


def strips(items, tint=(255, 255, 255)):
    """Each strip tiled twice at full width, so any seam shows in the middle."""
    w = 1024
    rows = [(i, composite(tile2(rgba), tint)) for i, rgba in items]
    h = sum(r.height // 2 + 34 for _, r in rows) + 16
    out = Image.new("RGB", (w + 16, h), BACK)
    d = ImageDraw.Draw(out)
    y = 8
    for tex_id, img in rows:
        img = img.resize((w, img.height * w // img.width), Image.LANCZOS)
        d.text((8, y), f"{tex_id}   (tiled twice; the join is the vertical centre)", fill=TEXT, font=_font(14))
        out.paste(img, (8, y + 22))
        y += img.height + 34
    return out


def gif(rgba, grid, path, fps=20, scale=320, tint=(255, 255, 255), loops=2):
    h, w = rgba.shape[:2]
    ch, cw = h // grid, w // grid
    frames = []
    for i in range(grid * grid):
        r, c = divmod(i, grid)
        cell = rgba[r * ch : (r + 1) * ch, c * cw : (c + 1) * cw]
        size = (scale, max(1, scale * ch // cw))
        frames.append(composite(cell, tint).resize(size, Image.LANCZOS))
    frames += [composite(np.zeros_like(rgba[:ch, :cw])).resize(size)] * 4
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, optimize=True)
