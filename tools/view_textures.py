"""Contact sheet of white-alpha textures, tinted and additively blended on a dark
background (roughly how Roblox shows them with LightEmission = 1).

usage: python3 view_textures.py <textures_dir> <out.png> [hex_color]
"""
import glob
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

src, out = sys.argv[1], sys.argv[2]
tint = tuple(int(sys.argv[3][i : i + 2], 16) for i in (0, 2, 4)) if len(sys.argv) > 3 else (255, 200, 60)
files = sorted(glob.glob(os.path.join(src, "*.png")))
CELL_W, CELL_H = 520, 300
cols = 3
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (CELL_W * cols, CELL_H * rows), (18, 20, 26))
for i, f in enumerate(files):
    im = Image.open(f).convert("RGBA")
    im.thumbnail((CELL_W - 20, CELL_H - 40))
    a = im.getchannel("A")
    # tint: white core stays whiter where alpha is high (like additive overexposure)
    col = Image.new("RGB", im.size, tint)
    hot = Image.eval(a, lambda v: max(0, v - 170) * 3)
    lum = Image.merge("RGB", [a, a, a])
    tinted = ImageChops.multiply(lum, col)
    tinted = ImageChops.add(tinted, Image.merge("RGB", [hot, hot, hot]))
    glow = tinted.filter(ImageFilter.GaussianBlur(8))
    cell = Image.new("RGB", (CELL_W, CELL_H), (18, 20, 26))
    x, y = (CELL_W - im.width) // 2, (CELL_H - 20 - im.height) // 2 + 4
    layer = Image.new("RGB", (CELL_W, CELL_H))
    layer.paste(tinted, (x, y))
    glayer = Image.new("RGB", (CELL_W, CELL_H))
    glayer.paste(glow, (x, y))
    cell = ImageChops.add(ImageChops.add(cell, layer), glayer)
    ImageDraw.Draw(cell).text((8, CELL_H - 18), os.path.basename(f), fill=(200, 205, 215))
    sheet.paste(cell, ((i % cols) * CELL_W, (i // cols) * CELL_H))
sheet.save(out)
print("saved", out)
