"""texgen: library v4 as recipes. Draw, check and preview VFX textures without Blender.

    python tools/texgen list                          every id, its kind, size and use
    python tools/texgen build [ids ...]               render into pack/generated (+ manifest.json)
    python tools/texgen build <id> --seed 7 --size 512 --set ease=2 -o out.png    a variant, written elsewhere
    python tools/texgen check [ids ...] [--fresh]     the plan's rules; --fresh also re-renders and compares
    python tools/texgen sheet [-o path] [--tint #rrggbb]   the contact sheet (and the strips, tiled twice)
    python tools/texgen gif <id> [--fps 20]           a flipbook or sheet, frame by frame
    python tools/texgen selftest                      the primitives' maths and one planted bad case per rule
    python tools/texgen cc0 [--dry]                   import the CC0 packs in .cache/cc0 into pack/cc0 (cc0.json)
    python tools/texgen measure <png|id> [--grid N] [--json]      a texture's numbers, cell by cell
    python tools/texgen compare <a> <b> [--grid N] [--grid-b N] [--out overlay.png]   the gap, scored
    python tools/texgen fit <id|recipe:name> <ref.png> --space space.json [--grid N] [--iters K] [-o best.json]

Ids are <family>/<name> (shape, flip, sheet, strip, art, source); a family name picks all
of it. numpy and Pillow only (tools/evfx/requirements.txt). docs/texgen.md has the details.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import bank  # noqa: E402
import checks  # noqa: E402
import sheet  # noqa: E402

CACHE = os.path.join(bank.ROOT, ".cache", "texgen")


def _value(text):
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def _edits(pairs):
    out = {}
    for pair in pairs or []:
        k, _, v = pair.partition("=")
        out[k] = _value(v)
    return out


def _tint(text):
    text = (text or "#ffffff").lstrip("#")
    return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))


def _check_one(tex_id, rgba, meta):
    return checks.check(dict(bank.get(tex_id), frames=meta["frames"]), rgba)


def cmd_list(args):
    for i in bank.resolve(args.ids):
        e = bank.get(i)
        grid = f" {e['grid']}x{e['grid']}" if e.get("grid", 1) > 1 else ""
        print(f"{i:24s} {e['kind']:8s} {e['size']:5d}{grid:5s} {e.get('role', ''):7s} {e.get('use', '')}")


def cmd_build(args):
    names = bank.resolve(args.ids)
    variant = args.seed is not None or args.size or args.set or args.out
    if variant and len(names) != 1:
        sys.exit("texgen: --seed, --size, --set and -o take one id")
    results, bad = [], 0
    for i in names:
        rgba, meta = bank.render(i, seed=args.seed, size=args.size, **_edits(args.set))
        fails = _check_one(i, rgba, meta)
        bad += bool(fails)
        print(f"{i:24s} {meta['size'][0]}x{meta['size'][1]}  " + ("ok" if not fails else "; ".join(fails)))
        results.append((rgba, meta))
    if variant:
        path = args.out or os.path.join(CACHE, bank.filename(names[0]))
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        Image.fromarray(results[0][0], "RGBA").save(path)
        print(f"wrote {os.path.relpath(path)}")
    else:
        bank.write(results)
        print(f"wrote {len(results)} textures to {os.path.relpath(bank.OUT)}")
    return 1 if bad else 0


def cmd_check(args):
    bad = 0
    names = bank.resolve(args.ids)
    clash = [i for i in names if os.path.exists(os.path.join(bank.UPLOADED, bank.filename(i)))]
    for i in clash:
        print(f"{i}: its file name is already taken in pack/textures")
        bad += 1
    for i in names:
        rgba = bank.read(i)
        if rgba is None:
            print(f"{i}: not built (run `texgen build {i}`)")
            bad += 1
            continue
        fails = checks.check(dict(bank.get(i)), rgba)
        if args.fresh:
            fresh, _ = bank.render(i)
            diff = np.abs(fresh[..., 3].astype(int) - rgba[..., 3].astype(int))
            if fresh.shape != rgba.shape or diff.mean() > 0.5 or diff.max() > 24:
                fails.append("stale: the recipe no longer draws the committed file (run `texgen build`)")
        if fails:
            bad += 1
            print(f"{i}: " + "; ".join(fails))
    print(f"{len(names) - bad}/{len(names)} textures pass")
    return 1 if bad else 0


def _items(names, fresh=False):
    out = []
    for i in names:
        rgba = None if fresh else bank.read(i)
        if rgba is None:
            rgba, _ = bank.render(i)
        out.append((i, rgba, checks.check(dict(bank.get(i)), rgba)))
    return out


def cmd_sheet(args):
    items = _items(bank.resolve(args.ids), args.fresh)
    tint = _tint(args.tint)
    path = args.out or os.path.join(CACHE, "sheet.png")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    sheet.contact(items, tint).save(path)
    print(f"wrote {os.path.relpath(path)}")
    strip_items = [(i, rgba) for i, rgba, _ in items if i.startswith("strip/")]
    if strip_items:
        spath = os.path.join(os.path.dirname(path), "strips" + os.path.splitext(path)[1])
        sheet.strips(strip_items, tint).save(spath)
        print(f"wrote {os.path.relpath(spath)}")
    return 0


def cmd_gif(args):
    i = bank.resolve([args.id])[0]
    e = bank.get(i)
    if e.get("grid", 1) < 2:
        sys.exit(f"texgen: {i} has one frame; gif needs a flipbook or a sheet")
    rgba = bank.read(i)
    if rgba is None:
        rgba, _ = bank.render(i)
    path = args.out or os.path.join(CACHE, "gif", bank.filename(i)[:-4] + ".gif")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    sheet.gif(rgba, e["grid"], path, fps=args.fps, tint=_tint(args.tint))
    print(f"wrote {os.path.relpath(path)}")
    return 0


def cmd_cc0(args):
    import cc0

    m = cc0.run(dry=args.dry)
    kinds = {}
    for e in m["textures"].values():
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(f"{len(m['textures'])} CC0 textures {'planned' if args.dry else 'written to pack/cc0'}: {kinds}")


def cmd_measure(args):
    import measure

    r = measure.measure(args.src, args.grid)
    if args.json:
        print(json.dumps(r, indent=1))
    else:
        print(measure.table(r, os.path.basename(args.src)))
    return 0


def cmd_compare(args):
    import measure

    r = measure.compare(args.a, args.b, args.grid, args.grid_b, args.out)
    print(f"{'metric':12s} {'a':>9s} {'b':>9s}  gap (tolerances)")
    for k, v in r["diff"].items():
        flag = "  <<" if abs(v) > 2 else ""
        print(f"{k:12s} {r['a']['mean'][k]:9.3f} {r['b']['mean'][k]:9.3f}  {v:+7.2f}{flag}")
    print(f"score {r['score']:.1f} (sum of squared gaps; 0 is a match)")
    print("shape overlap after alignment (IoU): " + ", ".join(f"{x:.2f}" for x in r["iou"]))
    if args.out:
        print(f"wrote {os.path.relpath(args.out)}")
    return 0


def cmd_fit(args):
    import measure

    with open(args.space, encoding="utf-8") as f:
        space = json.load(f)
    skip = tuple(k for k in (args.skip or "").split(",") if k)
    best = measure.fit(args.target, args.reference, space, args.grid, args.iters, args.refine, skip=skip)
    path = args.out or os.path.join(CACHE, "fit", args.target.replace("/", "_").replace(":", "_") + ".json")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(best, f, indent=1)
    print(f"score {best['score']:.1f}; wrote {os.path.relpath(path)}")
    for k in measure.SCALARS:
        print(f"  {k:12s} fit {best['means'][k]:9.3f}  reference {best['target'][k]:9.3f}")
    params = {k: tuple(v) if isinstance(v, list) else v for k, v in best["params"].items()}
    ours = measure.render_cells(args.target, params, 1, 256)
    ref = measure.load(args.reference)[0]
    png = path[:-5] + ".png"
    measure.overlay(measure.cells(ref, args.grid), ours, best["target"], best["means"], png, names=("reference", "fit"))
    print(f"wrote {os.path.relpath(png)}")
    return 0


def cmd_selftest(args):
    import selftest

    return selftest.run()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="texgen", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("ids", nargs="*")
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("build")
    p.add_argument("ids", nargs="*")
    p.add_argument("--seed", type=int)
    p.add_argument("--size", type=int)
    p.add_argument("--set", action="append", metavar="KNOB=VALUE")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_build)
    p = sub.add_parser("check")
    p.add_argument("ids", nargs="*")
    p.add_argument("--fresh", action="store_true")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("sheet")
    p.add_argument("ids", nargs="*")
    p.add_argument("-o", "--out")
    p.add_argument("--tint")
    p.add_argument("--fresh", action="store_true", help="render instead of reading pack/generated")
    p.set_defaults(fn=cmd_sheet)
    p = sub.add_parser("gif")
    p.add_argument("id")
    p.add_argument("--fps", type=int, default=20)
    p.add_argument("--tint")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_gif)
    p = sub.add_parser("cc0")
    p.add_argument("--dry", action="store_true", help="list what would be written")
    p.set_defaults(fn=cmd_cc0)
    p = sub.add_parser("measure")
    p.add_argument("src", help="a png or a bank id")
    p.add_argument("--grid", type=int, default=1)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_measure)
    p = sub.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--grid", type=int, default=1, help="a's grid (and b's, without --grid-b)")
    p.add_argument("--grid-b", type=int)
    p.add_argument("--out", help="write the overlay sheet here")
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("fit")
    p.add_argument("target", help="a bank id, or recipe:<name> to draw cells straight from a recipe")
    p.add_argument("reference", help="the png to match")
    p.add_argument("--skip", help="metrics to leave out of the score, comma separated (e.g. fill,margin for a tight crop)")
    p.add_argument("--space", required=True, help="json: knob -> [lo, hi] | {int|pair|choice: ...} | a fixed value")
    p.add_argument("--grid", type=int, default=1, help="the reference's grid")
    p.add_argument("--iters", type=int, default=300)
    p.add_argument("--refine", type=int, default=160)
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_fit)
    p = sub.add_parser("selftest")
    p.set_defaults(fn=cmd_selftest)
    args = ap.parse_args(argv)
    try:
        return args.fn(args) or 0
    except bank.BankError as ex:
        sys.exit(f"texgen: {ex}")


if __name__ == "__main__":
    sys.exit(main())
