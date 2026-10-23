"""evfx: see, measure and compare EasyVFX presets without opening Studio.

    python tools/evfx timeline [preset ...] [--mode hd|basic]   re-export timelines (Lune)
    python tools/evfx strip <preset> [--view close|far|both] [--moments 11]
    python tools/evfx gif <preset> [--view close|far] [--fps 15]
    python tools/evfx lineup <preset> <preset> ... [--moments 6]
    python tools/evfx sheet [preset ...] [--view close|far]     every preset at its busiest moment
    python tools/evfx diff <preset>[@ref] <preset>[@ref]       strips and numbers, side by side
    python tools/evfx export <preset>                         per-frame census and the audit, as text
    python tools/evfx phases <preset>[@ref] ...               flash, burst, tail, white core, hues (plan §4)
    python tools/evfx beats [preset ...] [--png]               the beat judge: fix-first list against the beat
                                                              sheet, the references and the move (60 fps)
    python tools/evfx ref <name> [--build]                    a reference's beats and their stats
    python tools/evfx audit [preset ...] [--check | --update] [--no-scores]
    python tools/evfx selftest                                planted bad cases must fail

Timelines are cached in .cache/evfx/timeline/<mode>; pass --fresh to re-export one.
Images go to .cache/evfx/out unless -o is given. docs/agentic-loop.md shows the loop.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evfx import beats, core, measure, refs, render  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

OUT = os.path.join(core.CACHE, "out")
BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline.json")
LABEL = (225, 228, 235)
CELL = (320, 214)


def _out(args, name):
    path = args.out or os.path.join(OUT, name)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path


def _ref_folder(ref, mode):
    """Exports timelines from another git ref, in a throwaway worktree."""
    found = subprocess.run(["git", "rev-parse", "--short", ref], cwd=core.ROOT, capture_output=True, text=True)
    if found.returncode != 0:
        sys.exit(f"evfx: no git ref {ref}")
    commit = found.stdout.strip()
    tree = os.path.join(core.CACHE, "ref", commit)
    out = os.path.join(core.CACHE, "timeline-ref", commit, mode)
    if not os.path.isdir(tree):
        subprocess.run(["git", "worktree", "add", "--detach", tree, commit], cwd=core.ROOT, check=True, capture_output=True)
    for name in ("timeline.luau", "harness.luau"):
        shutil.copyfile(os.path.join(core.ROOT, "tests", name), os.path.join(tree, "tests", name))
    return tree, out


def _load(spec, mode, fresh=False):
    if "@" in spec:
        name, ref = spec.split("@", 1)
        tree, out = _ref_folder(ref, mode)
        path = os.path.join(out, name + ".json")
        if fresh or not os.path.exists(path):
            core.export([name], mode, root=tree, out=out)
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return core.load(spec, mode, fresh=fresh)


def _times(timeline, moments):
    span = core.duration(timeline)
    return [span * k / max(1, moments - 1) for k in range(moments)]


def _cells(timeline, view, moments, size=CELL):
    cams = core.views(timeline, size)
    out = []
    for t in _times(timeline, moments):
        rgb, info = render.draw(timeline, t, cams[view])
        img = render.to_image(rgb)
        d = ImageDraw.Draw(img)
        d.text((6, 4), f"{t:.2f}s", fill=LABEL)
        d.text((6, size[1] - 14), f"{info['particles']}p", fill=LABEL)
        out.append(img)
    return out


def _row(images, label=None, gap=4):
    w = sum(i.width for i in images) + gap * (len(images) - 1)
    h = max(i.height for i in images) + (16 if label else 0)
    row = Image.new("RGB", (w, h), (12, 13, 16))
    if label:
        ImageDraw.Draw(row).text((4, 2), label, fill=LABEL)
    x = 0
    for img in images:
        row.paste(img, (x, 16 if label else 0))
        x += img.width + gap
    return row


def _stack(rows, gap=6):
    w = max(r.width for r in rows)
    h = sum(r.height for r in rows) + gap * (len(rows) - 1)
    sheet = Image.new("RGB", (w, h), (12, 13, 16))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + gap
    return sheet


def _strip_rows(timeline, view, moments, label):
    views = ["close", "far"] if view == "both" else [view]
    return [_row(_cells(timeline, v, moments), f"{label}  {v}") for v in views]


def _line(summary):
    failed = [g for g in summary["gates"] if not g["ok"]]
    peak = summary["peak"]
    text = (
        f"{summary['id']:<16} {summary['seconds']:5.2f}s  particles {peak['particles']:>4}  beams {peak['beams']:>3}  "
        f"pieces {peak['pieces']:>3} (plain {peak['plain']})  lights {peak['lights']}"
    )
    if "scores" in summary:
        s = summary["scores"]
        text += f"  far {s['coverage_far']:.3f}  body {s['body_buried']:.3f}  crisp {s['crisp']:.3f}"
    text += "  " + ("ok" if not failed else "FAIL " + ", ".join(g["name"] for g in failed))
    return text


def cmd_timeline(args):
    folder = core.export(args.presets or None, args.mode)
    print(f"evfx: timelines in {folder}")


def cmd_strip(args):
    timeline = _load(args.preset, args.mode, args.fresh)
    rows = _strip_rows(timeline, args.view, args.moments, args.preset)
    path = _out(args, f"{args.preset.replace('@', '_')}.strip.png")
    _stack(rows).save(path)
    summary, _ = measure.summary(timeline, with_scores=False)
    print(_line(summary))
    print(path)


def cmd_gif(args):
    timeline = _load(args.preset, args.mode, args.fresh)
    cams = core.views(timeline, (400, 268))
    span = core.duration(timeline)
    count = max(2, int(span * args.fps) + 1)
    frames = [render.to_image(render.draw(timeline, span * k / (count - 1), cams[args.view])[0]) for k in range(count)]
    path = _out(args, f"{args.preset.replace('@', '_')}.{args.view}.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / args.fps), loop=0)
    print(path)


def cmd_lineup(args):
    rows = []
    for spec in args.presets:
        timeline = _load(spec, args.mode, args.fresh)
        rows.extend(_strip_rows(timeline, args.view, args.moments, spec))
    path = _out(args, "lineup.png")
    _stack(rows).save(path)
    print(path)


def cmd_diff(args):
    a = _load(args.a, args.mode, args.fresh)
    b = _load(args.b, args.mode, args.fresh)
    rows = _strip_rows(a, args.view, args.moments, args.a) + _strip_rows(b, args.view, args.moments, args.b)
    path = _out(args, "diff.png")
    _stack(rows).save(path)
    sa, _ = measure.summary(a)
    sb, _ = measure.summary(b)
    print(_line(sa))
    print(_line(sb))
    for key in sa["scores"]:
        print(f"  {key:<12} {sa['scores'][key]:.4f} -> {sb['scores'][key]:.4f}")
    print(path)


def _peak_time(timeline):
    rows = measure.census(timeline)
    if not rows:
        return 0.0
    best = max(rows, key=lambda r: r["particles"] + r["beams"] * 2 + r["pieces"] * 2 + r["screens"] * 50)
    return best["t"]


def cmd_sheet(args):
    presets = args.presets or core.preset_ids()
    cells = []
    for preset in presets:
        timeline = _load(preset, args.mode, args.fresh)
        t = _peak_time(timeline)
        cam = core.views(timeline, CELL)[args.view]
        img = render.to_image(render.draw(timeline, t, cam)[0])
        d = ImageDraw.Draw(img)
        d.text((6, 4), preset, fill=LABEL)
        d.text((6, CELL[1] - 14), f"{t:.2f}s", fill=LABEL)
        cells.append(img)
    cols = args.columns
    rows = [_row(cells[i : i + cols]) for i in range(0, len(cells), cols)]
    path = _out(args, f"sheet.{args.view}.png")
    _stack(rows, gap=4).save(path)
    print(path)


def cmd_export(args):
    timeline = _load(args.preset, args.mode, args.fresh)
    summary, rows = measure.summary(timeline)
    lines = [_line(summary), ""]
    for g in summary["gates"]:
        lines.append(f"  {'ok  ' if g['ok'] else 'FAIL'} {g['name']:<18} {g['reason']}")
    lines += ["", "     t  particles beams pieces plain lights screens trails   fov"]
    for r in rows:
        lines.append(
            f"{r['t']:6.3f}  {r['particles']:>9} {r['beams']:>5} {r['pieces']:>6} {r['plain']:>5} {r['lights']:>6} "
            f"{r['screens']:>7} {r['trails']:>6} {r['fov']:>5}"
        )
    base = _out(args, f"{args.preset.replace('@', '_')}.export")
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "frames": rows}, f, indent=1)
    print("\n".join(lines[: len(summary["gates"]) + 2]))
    print(base + ".txt")


def _bar(v, top, width=24):
    n = int(round(width * v / top)) if top > 0 else 0
    return "#" * n + "." * (width - n)


def cmd_phases(args):
    for spec in args.presets:
        timeline = _load(spec, args.mode, args.fresh)
        summary, rows = measure.phases(timeline)
        print(f"{spec}: flash {summary['flash_frames']} frames (target 1-2), burst peak frame {summary['burst_peak_frame']} "
              f"(by 4), tail ends {summary['tail_end']:.2f}s (hit <= 0.6), core white {summary['core_white']:.2f} "
              f"(>= 0.85), hues {summary['hues']} (<= 3), body buried at most {summary['buried_peak']:.2f} (<= 0.6)")
        if args.frames:
            top = max(r["coverage"] for r in rows) or 1
            topl = max(r["lum"] for r in rows) or 1
            print("      t  coverage                  brightness                buried")
            for r in rows:
                print(f"  {r['t']:5.2f}  {_bar(r['coverage'], top)}  {_bar(r['lum'], topl)}  {r['buried']:.2f}")


SEV = {3: (255, 90, 80), 2: (255, 190, 70), 1: (150, 170, 200)}


def _beat_picture(spec, timeline, found, path):
    """The curves with every beat's span, the hit and the recovery's end, then each beat
    at its brightest frame."""
    c = beats.curves(timeline)
    n = len(c["coverage"])
    w, top, row_h = 1200, 150, 16
    rows = len(spec["beats"])
    plot_h = top + rows * row_h + 30
    cams = core.views(timeline, (290, 194))
    tiles = []
    for b in spec["beats"]:
        own = b.get("_curves") or c
        lo, hi = max(0, b["from"]), min(n - 1, max(b["to"], b["from"]))
        at = lo + int(np.argmax(own["lum"][lo : hi + 1])) if hi >= lo else lo
        rgb, _ = render.draw(timeline, at * timeline["frameTime"], cams["close"])
        img = render.to_image(rgb)
        d = ImageDraw.Draw(img)
        mine = [f for f in found if f["beat"] == b["name"]]
        d.rectangle([0, 0, 290, 16], fill=(0, 0, 0))
        d.text((4, 3), f"{b['name']} f{at}" + (f"  {len(mine)} to fix" if mine else ""), fill=SEV[max(f["sev"] for f in mine)] if mine else LABEL)
        tiles.append(img)
    cols = 4
    grid_h = ((len(tiles) + cols - 1) // cols) * 198
    sheet = Image.new("RGB", (w, plot_h + grid_h), (18, 18, 22))
    d = ImageDraw.Draw(sheet)
    x = lambda k: 64 + (w - 84) * k / max(1, n - 1)  # noqa: E731
    for key, colour in (("coverage", (110, 180, 255)), ("white", (245, 245, 245)), ("lum", (255, 200, 90))):
        ys = c[key]
        peak = max(ys) or 1
        pts = [(x(k), 10 + (top - 20) * (1 - v / peak)) for k, v in enumerate(ys)]
        d.line(pts, fill=colour, width=2)
    d.text((68, 4), "coverage", fill=(110, 180, 255))
    d.text((144, 4), "white", fill=(245, 245, 245))
    d.text((194, 4), "brightness", fill=(255, 200, 90))
    for k in range(0, n, 10):
        d.line([(x(k), top - 6), (x(k), top)], fill=(90, 90, 100))
        d.text((x(k) - 6, top + rows * row_h + 4), str(k), fill=(120, 120, 130))
    for i, b in enumerate(spec["beats"]):
        y = top + i * row_h
        colour = (255, 255, 255) if b.get("flash") else (120, 110, 200)
        d.rectangle([x(b["from"]), y + 2, max(x(b["from"]) + 2, x(b["to"])), y + row_h - 3], fill=colour)
        d.text((4, y + 2), b["name"][:9], fill=LABEL)
    move = spec.get("move")
    if move:
        fps = round(1 / timeline["frameTime"])
        hit = -move.get("fire", 0) * fps
        end = hit + (move["active"] + move["recovery"]) * fps
        for k, colour, label in ((hit, (255, 80, 80), "hit"), (end, (255, 160, 60), "recovery ends")):
            if 0 <= k <= n - 1:
                d.line([(x(k), 8), (x(k), top + rows * row_h)], fill=colour, width=1)
                d.text((x(k) + 3, 14 if label == "hit" else 26), label, fill=colour)
    for f in found:
        d.ellipse([x(f["frame"]) - 4, top - 14, x(f["frame"]) + 4, top - 6], fill=SEV[f["sev"]])
    for i, img in enumerate(tiles):
        r, col = divmod(i, cols)
        sheet.paste(img, (6 + col * 298, plot_h + r * 198))
    sheet.save(path, quality=90)


def cmd_beats(args):
    names = args.presets or beats.sheets()
    for name in names:
        spec = beats.sheet(name)
        timeline = core.load(name, args.mode, fresh=args.fresh, fps=60)
        found = beats.judge(spec, timeline)
        text = beats.report(spec, found)
        print(text + "\n")
        base = _out(args, f"{name}.beats")
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write(text + "\n")
        if args.png:
            _beat_picture(spec, timeline, found, base + ".jpg")
            print(base + ".jpg")


def cmd_ref(args):
    ref = refs.build(args.name, args.clip) if args.build else refs.load(args.name)
    print(f"{ref['title']} ({ref['tier']}), {ref['source']}")
    print("  beat         frames      len peak rise half tenth flash hues  calm  top")
    for b in ref["beats"]:
        st = b.get("stats") or {}
        print(f"  {b['name']:<12} f{b['from']:>3}-{b['to']:<5} {st.get('length', 0):>4} {st.get('peak_at', 0):>4} {st.get('rise', 0):>4} "
              f"{st.get('half', 0):>4} {st.get('tenth', 0):>5} {st.get('flash', 0):>5} {st.get('hues', 0):>4} {st.get('calm', 0):>5.2f}  {', '.join(st.get('top', []))}")


def _compare(old, new):
    """Gates that passed in the baseline and fail now, and score changes."""
    worse, better = [], []
    for preset, now in new.items():
        before = old.get(preset)
        if not before:
            for g in now["gates"]:
                if not g["ok"]:
                    worse.append(f"{preset}: new preset fails {g['name']} ({g['reason']})")
            continue
        was = {g["name"]: g["ok"] for g in before["gates"]}
        for g in now["gates"]:
            if was.get(g["name"], True) and not g["ok"]:
                worse.append(f"{preset}: {g['name']} now fails ({g['reason']})")
            elif was.get(g["name"]) is False and g["ok"]:
                better.append(f"{preset}: {g['name']} now passes")
    return worse, better


def cmd_audit(args):
    presets = args.presets or core.preset_ids()
    if args.fresh or not args.presets:
        core.export(presets if args.presets else None, args.mode)
    results = {}
    for preset in presets:
        timeline = core.load(preset, args.mode)
        summary, _ = measure.summary(timeline, with_scores=not args.no_scores)
        results[preset] = summary
        print(_line(summary))
    failing = sum(1 for s in results.values() if any(not g["ok"] for g in s["gates"]))
    print(f"\n{len(results)} presets, {failing} with a failing gate")
    if args.update:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump({"mode": args.mode, "presets": results}, f, indent=1, sort_keys=True)
            f.write("\n")
        print(f"baseline written: {BASELINE}")
    if args.check:
        with open(BASELINE, encoding="utf-8") as f:
            old = json.load(f)["presets"]
        worse, better = _compare(old, results)
        for line in better:
            print("better: " + line)
        for line in worse:
            print("WORSE:  " + line)
        if worse:
            sys.exit(1)
        print("audit: nothing worse than the baseline")


def cmd_selftest(args):
    from evfx import selftest

    sys.exit(selftest.run())


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--mode", default="hd", choices=["hd", "basic"])
    common.add_argument("--fresh", action="store_true", help="re-export timelines before reading them")
    common.add_argument("-o", "--out", help="output file")
    parser = argparse.ArgumentParser(prog="evfx", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(parents=[common], name="timeline")
    p.add_argument("presets", nargs="*")
    p.set_defaults(run=cmd_timeline)

    p = sub.add_parser(parents=[common], name="strip")
    p.add_argument("preset")
    p.add_argument("--view", default="both", choices=["close", "far", "both"])
    p.add_argument("--moments", type=int, default=11)
    p.set_defaults(run=cmd_strip)

    p = sub.add_parser(parents=[common], name="gif")
    p.add_argument("preset")
    p.add_argument("--view", default="close", choices=["close", "far"])
    p.add_argument("--fps", type=int, default=15)
    p.set_defaults(run=cmd_gif)

    p = sub.add_parser(parents=[common], name="lineup")
    p.add_argument("presets", nargs="+")
    p.add_argument("--view", default="close", choices=["close", "far", "both"])
    p.add_argument("--moments", type=int, default=6)
    p.set_defaults(run=cmd_lineup)

    p = sub.add_parser(parents=[common], name="sheet")
    p.add_argument("presets", nargs="*")
    p.add_argument("--view", default="close", choices=["close", "far"])
    p.add_argument("--columns", type=int, default=6)
    p.set_defaults(run=cmd_sheet)

    p = sub.add_parser(parents=[common], name="diff")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--view", default="close", choices=["close", "far", "both"])
    p.add_argument("--moments", type=int, default=8)
    p.set_defaults(run=cmd_diff)

    p = sub.add_parser(parents=[common], name="export")
    p.add_argument("preset")
    p.set_defaults(run=cmd_export)

    p = sub.add_parser(parents=[common], name="phases")
    p.add_argument("presets", nargs="+")
    p.add_argument("--frames", action="store_true", help="print the per-frame curve")
    p.set_defaults(run=cmd_phases)

    p = sub.add_parser(parents=[common], name="beats")
    p.add_argument("presets", nargs="*", help="presets with a sheet in tools/evfx/sheets (all when empty)")
    p.add_argument("--png", action="store_true", help="also draw the beats over the curves, and each beat")
    p.set_defaults(run=cmd_beats)

    p = sub.add_parser(parents=[common], name="ref")
    p.add_argument("name")
    p.add_argument("--build", action="store_true", help="re-measure the beats from the clip in .cache/refs")
    p.add_argument("--clip", help="the clip, when it is not where the reference says")
    p.set_defaults(run=cmd_ref)

    p = sub.add_parser(parents=[common], name="audit")
    p.add_argument("presets", nargs="*")
    p.add_argument("--check", action="store_true", help="fail if a gate that passed in the baseline fails now")
    p.add_argument("--update", action="store_true", help="write the baseline")
    p.add_argument("--no-scores", action="store_true", help="skip the rendered scores (fast)")
    p.set_defaults(run=cmd_audit)

    p = sub.add_parser(parents=[common], name="selftest")
    p.set_defaults(run=cmd_selftest)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
