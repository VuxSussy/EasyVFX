"""The beat judge: an effect read beat by beat against its beat sheet, the references and
the move it plays on, with what to fix first.

A beat sheet (tools/evfx/sheets/<preset>.json) is written before an effect is built
(docs/refs/dissection-lotus-frigid.md, lesson 1): each beat's frames, its one shape, its
palette, its layers by depth, and the reference beat it learns from. Its `move` names the
SE370 move the effect plays on (windup, active and recovery from the game's content, its
style and keywords), so the beats can be timed to the move the way SE370's
docs/motion-bible.md times the body.

The judge renders the effect at 60 frames a second and reads, per beat:
    present, layers   the beat is on screen and its named layers are live in it
    onset             it starts where the sheet says
    flash             a flash beat holds its frames (2) and is white
    key               a beat stays on screen long enough to read (4 frames, the bible)
    palette           its hues are the sheet's, at most three
    depth             its main shape has something behind it and something in front
    ref               its rise, flash and fall against the reference beat
and against the move:
    hit               the hit beat lands on the hit frame
    windup            the wind-up stays quiet, or tells it when the keywords want a tell
    follow            the burst peaks in the follow-through
    tail              the tail against the recovery, as the keywords want
    steps             flipbooks and shell frames step at about 12 a second (on twos)
    keywords          snappy, punchy, crisp, heavy, committed, clean recovery

Severity 3 breaks the beat sheet or the move, 2 is a clear miss, 1 is a dial to look at.
Limits live in tools/evfx/pacing.json.
"""

import hashlib
import json
import os

import numpy as np

from . import core, measure, refs

HERE = os.path.dirname(os.path.abspath(__file__))
SHEETS = os.path.join(HERE, "sheets")
PACING = os.path.join(HERE, "pacing.json")
GRID = {"Grid2x2": 4, "Grid4x4": 16, "Grid8x8": 64}
DEPTHS = ("ground", "back", "main", "line", "dust")


def pacing():
    with open(PACING, encoding="utf-8") as f:
        return json.load(f)


def sheet(preset):
    path = os.path.join(SHEETS, preset + ".json")
    if not os.path.exists(path):
        raise SystemExit(f"evfx: no beat sheet for {preset} (tools/evfx/sheets/{preset}.json)")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sheets():
    return sorted(name[:-5] for name in os.listdir(SHEETS) if name.endswith(".json"))


def only(timeline, names):
    """The timeline with only the named layers: bursts and emitters by name, shells by
    mesh. Beams, lights and screen effects drop out (they have no names to pick by)."""
    keep = set(names)
    frames = [
        {**f, "parts": [p for p in f["parts"] if _short(p.get("meshId")) in keep], "beams": [], "lights": [], "screens": []}
        for f in timeline["frames"]
    ]
    return {
        **timeline,
        "frames": frames,
        "bursts": [b for b in timeline["bursts"] if b["name"] in keep],
        "emitters": [e for e in timeline["emitters"] if e.get("name") in keep],
    }


def curves(timeline, ks=None):
    """Per-frame curves of the close view (measure.phases rows), cached by timeline. With
    `ks`, only those frames are rendered and the rest read as empty."""
    n = len(timeline["frames"])
    ks = sorted(k for k in (ks if ks is not None else range(n)) if 0 <= k < n)
    blob = json.dumps([timeline, ks], sort_keys=True).encode()
    path = os.path.join(core.CACHE, "beats", f"{timeline['id']}-{hashlib.sha1(blob).hexdigest()[:16]}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    _, rows = measure.phases(timeline, ks=ks)
    out = {k: [0.0] * n for k in ("lum", "white", "coverage", "motion")}
    out["hue"] = [[0.0] * 12 for _ in range(n)]
    for k, row in zip(ks, rows):
        for key in out:
            out[key][k] = row[key]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


def _short(asset):
    return (asset or "").split("://")[-1]


def layers(timeline):
    """Every layer the timeline shows, by name: bursts by emitter name, shells by mesh.
    Each is {first, last, rate}: the frames it is live and how many times a second its
    picture changes (a one-shot flipbook's frames over its life, or a shell's frames)."""
    ft = timeline["frameTime"]
    out = {}
    for b in timeline["bursts"]:
        life = max(b["lifetime"])
        row = out.setdefault(b["name"], {"first": b["frame"], "last": 0, "rate": 0.0})
        row["first"] = min(row["first"], b["frame"])
        row["last"] = max(row["last"], b["frame"] + int(round(life / ft)))
        frames = GRID.get(b.get("flipbook") or "", 0)
        if frames and b.get("flipMode") == "OneShot":
            row["rate"] = max(row["rate"], frames / max(1e-3, min(b["lifetime"])))
    shells = {}
    for k, frame in enumerate(timeline["frames"]):
        for part in frame["parts"]:
            name = _short(part.get("meshId")) or part.get("shape") or "part"
            row = out.setdefault(name, {"first": k, "last": k, "rate": 0.0})
            row["first"], row["last"] = min(row["first"], k), max(row["last"], k)
            seen = shells.setdefault(name, {})
            seen.setdefault(k, set()).add(part.get("textureId"))
    for name, by_frame in shells.items():
        frames = sorted(by_frame)
        changes = sum(1 for a, b in zip(frames, frames[1:]) if by_frame[a] != by_frame[b])
        span = (frames[-1] - frames[0] + 1) * ft
        if changes:
            out[name]["rate"] = changes / span
    return out


def shake_frames(timeline):
    frames = timeline["frames"]
    return [k for k in range(1, len(frames)) if frames[k]["camera"] != frames[k - 1]["camera"]]


def _names(layer_map):
    return [name for depth in DEPTHS for name in layer_map.get(depth, [])]


def _near(name, palette):
    """A measured hue is the sheet's when it is a palette hue or one bin either side."""
    k = refs.hue_index(name)
    for want in palette:
        if want in refs.NAMES and min((k - refs.hue_index(want)) % 12, (refs.hue_index(want) - k) % 12) <= 1:
            return True
    return False


def _finding(sev, frame, beat, rule, said, fix):
    return {"sev": sev, "frame": int(frame), "beat": beat, "rule": rule, "said": said, "fix": fix}


def judge(spec, timeline, rules=None):
    """Every finding for one effect, most severe first, then by frame."""
    rules = rules or pacing()
    fps = round(1 / timeline["frameTime"])
    if fps != rules["fps"]:
        raise SystemExit(f"evfx: the beat judge reads {rules['fps']} fps timelines, got {fps}")
    c = curves(timeline)
    live = layers(timeline)
    cov, lum, white = np.array(c["coverage"]), np.array(c["lum"]), np.array(c["white"])
    n = len(cov)
    out = []
    flashes = []
    beats = spec["beats"]

    def window(b):
        return max(0, b["from"]), min(n - 1, max(b["to"], b["from"]))

    listed = set()
    for b in beats:
        a, z = window(b)
        name = b["name"]
        names = _names(b.get("layers", {}))
        own = curves(only(timeline, names), range(a - 6, z + max(30, z - a) + 1)) if names else c
        b["_curves"] = own
        st = refs.stats(own, a, z, b.get("flash", False))
        b["_stats"] = st
        bwhite = np.array(own["white"])
        firsts = []
        for layer in names:
            row = live.get(layer)
            if row is None:
                out.append(_finding(2, a, name, "layers", f"layer {layer} is not in the effect", f"add {layer} or fix its name in the sheet"))
            elif row["last"] < b["from"] - rules["onsetTolerance"] or row["first"] > b["to"] + rules["onsetTolerance"]:
                out.append(_finding(2, row["first"], name, "layers", f"{layer} is live f{row['first']}-{row['last']}, outside the beat (f{b['from']}-{b['to']})", f"set {layer}'s Delay to {a / fps:.3f} s"))
            elif layer not in listed:
                firsts.append(row["first"])
        listed.update(names)
        if np.array(own["coverage"])[a : z + 1].max(initial=0) <= rules["alive"]:
            out.append(_finding(3, b["from"], name, "present", f"nothing on screen in f{b['from']}-{b['to']}", "build the beat or move its layers' Delay into the window"))
            continue
        if firsts and abs(min(firsts) - b["from"]) > rules["onsetTolerance"]:
            late = min(firsts) - b["from"]
            out.append(_finding(2, min(firsts), name, "onset", f"starts f{min(firsts)}, {abs(late)} frames {'late' if late > 0 else 'early'} (sheet f{b['from']})", f"shift the beat's Delays by {-late / fps:+.3f} s"))
        if b.get("flash"):
            flashes.append(b)
            want = b["to"] - b["from"]
            if bwhite[max(0, a - 4) : z + 5].max(initial=0) < 0.002:
                out.append(_finding(2, a, name, "flash", "the flash beat has no white", "push the core to white: brightness up, a white core texture"))
            elif st["flash"] > want:
                out.append(_finding(3 if st["flash"] > want + 1 else 2, a, name, "flash", f"flash holds {st['flash']} frames, want {want}", "shorten the flash layer's Lifetime, or fade it from its first frame"))
        else:
            length = b["to"] - b["from"]
            if length < rules["keyFrames"]:
                out.append(_finding(2, a, name, "key", f"the beat is {length} frames; a key needs {rules['keyFrames']} to read", "hold it longer, or make it a flash"))
        if st["hues"] > rules["maxHues"]:
            out.append(_finding(2, a, name, "palette", f"{st['hues']} hues share the beat (cap {rules['maxHues']})", "drop a colour: one palette per beat"))
        palette = b.get("palette", [])
        stray = [h for h in st["top"] if palette and not _near(h, palette)]
        if stray:
            out.append(_finding(1, a, name, "palette", f"reads {', '.join(st['top'])}; the sheet says {', '.join(palette)}", f"retint the layers that carry {', '.join(stray)}"))
        lm = b.get("layers", {})
        if lm.get("main") and not b.get("flash"):
            if not (lm.get("back") or lm.get("ground")) or not (lm.get("line") or lm.get("dust")):
                missing = "behind it (back or ground)" if not (lm.get("back") or lm.get("ground")) else "in front (line or dust)"
                out.append(_finding(1, a, name, "depth", f"the main shape has nothing {missing}", "add a soft layer behind and a thin one in front (docs/refs/lotus-layers.md)"))
        if b.get("ref"):
            rb = refs.beat(b["ref"])
            rs = rb["stats"]
            if not b.get("flash") and st["rise"] > rs["rise"] + 2:
                out.append(_finding(1, a, name, "ref", f"comes on over {st['rise']} frames; {b['ref']} over {rs['rise']}", "start the main layer at full size and brightness"))
            if rs["length"] and st["length"] and rs["half"] <= 2 * rs["length"]:
                ours = st["half"] / max(1, st["length"])
                theirs = rs["half"] / max(1, rs["length"])
                if abs(ours - theirs) > 0.5 and st["length"] >= rules["keyFrames"]:
                    word = "lets go faster" if ours < theirs else "hangs on longer"
                    out.append(_finding(1, a, name, "ref", f"{word} than {b['ref']}: half-life {ours:.2f} of the beat, theirs {theirs:.2f}", "reshape the fade (Transparency sequence) toward the reference"))

    # Sheet-level: palette and shape change from beat to beat (Lotus).
    body = [b for b in beats if not b.get("flash")]
    if len(body) >= 3:
        for p, q in zip(body, body[1:]):
            if p.get("shape") and p.get("shape") == q.get("shape"):
                out.append(_finding(1, q["from"], q["name"], "shape", f"same shape as {p['name']} ({p['shape']})", "change the shape between beats"))
    for b in flashes:
        fw = max(b["_curves"]["white"][max(0, b["from"] - 4) : b["to"] + 5], default=0)
        for o in body:
            if not (o["from"] <= b["to"] + 30 and o["to"] >= b["from"] - 30):
                continue
            a, z = window(o)
            ow = max(o["_curves"]["white"][a + 2 : z + 1], default=0)
            if fw > 0 and ow > 0.6 * fw:
                out.append(_finding(1, a, o["name"], "white", f"{o['name']} is {ow / fw:.0%} as white as {b['name']}", "keep only flashes white; colour the rest"))
    unplanned = [k for k, row in live.items() if k not in listed and k != "part"]
    for k in unplanned:
        out.append(_finding(1, live[k]["first"], k, "unplanned", f"{k} is in the effect but in no beat", "give it a beat and a depth in the sheet, or cut it"))

    move = spec.get("move")
    if move:
        out += _move(spec, move, c, live, timeline, rules)
    out.sort(key=lambda f: (-f["sev"], f["frame"]))
    return out


def _move(spec, move, c, live, timeline, rules):
    fps = rules["fps"]
    cov = np.array(c["coverage"])
    n = len(cov)
    out = []
    keys = set(move.get("keywords") or rules["styles"].get(move.get("style", ""), []))
    windup, active, recovery = move["windup"], move["active"], move["recovery"]
    total = windup + active + recovery
    share = windup / total
    lo, hi = rules["hitShare"]
    if not lo <= share <= hi:
        out.append(_finding(1, 0, "move", "move", f"the hit is at {share:.2f} of the move (bible: {lo:.2f} to {hi:.2f})", "a motion call, not the effect's: cut the recovery or the wind-up (make it shorter, never faster)"))
    hit = int(round(-move.get("fire", 0.0) * fps))
    end = hit + int(round((active + recovery) * fps))
    hb = next((b for b in spec["beats"] if b.get("hit")), None)
    if hb:
        white = np.array(hb["_curves"]["white"])
        lum = np.array(hb["_curves"]["lum"])
        curve = white if white.max(initial=0) > 0.002 else lum
        look = curve[max(0, hit - 6) : hit + 12]
        if look.max(initial=0) > 0:
            onset = max(0, hit - 6) + int(np.argmax(look >= 0.9 * look.max()))
            if abs(onset - hit) > rules["hitTolerance"]:
                late = onset - hit
                out.append(_finding(3, onset, hb["name"], "hit", f"the hit beat peaks f{onset}, {abs(late)} frames {'after' if late > 0 else 'before'} the hit (f{hit})", f"move the hit layers' Delay by {-late / fps:+.3f} s"))
        if "snappy" in keys:
            st = hb.get("_stats") or {}
            if st.get("rise", 0) > rules["snapRise"]:
                out.append(_finding(2, hb["from"], hb["name"], "snappy", f"the hit comes on over {st['rise']} frames; snappy wants {rules['snapRise']}", "start the hit layers at full size; no grow-in"))
    after = cov[max(0, hit) :]
    peak = max(0, hit) + int(after.argmax()) if len(after) else 0
    planned = [b for b in spec["beats"] if b["from"] < hit]
    before = cov[: max(0, hit)].copy()
    if len(before) and not planned and before.max() > rules["windupQuiet"] * cov.max():
        out.append(_finding(2, int(before.argmax()), "windup", "windup", f"the wind-up covers {before.max() / cov.max():.0%} of the peak (cap {rules['windupQuiet']:.0%})", "keep the wind-up to a small tell; effects never bury the body, or give it a beat in the sheet"))
    tell = bool(planned) or bool(len(before) and before.max() > rules["alive"])
    if keys & {"heavy", "telegraph", "wind-up"} and not tell:
        out.append(_finding(2, 0, "windup", "windup", f"{move.get('style', 'the move')} wants a wind-up tell; the effect starts at the hit", f"add a small glint or charge in the wind-up: fire {windup:.2f} s earlier with the hit beats delayed to match"))
    follow = hit + int(round((active + recovery * rules["followThrough"]) * fps))
    if not hit <= peak <= follow:
        out.append(_finding(2, peak, "burst", "follow", f"the burst peaks f{peak}, outside the follow-through's first part (f{hit}-{follow})", "bring the biggest layers in right after the hit"))
    alive = np.nonzero(cov > rules["alive"])[0]
    tail = int(alive[-1]) if len(alive) else 0
    if keys & {"heavy", "committed"} and tail < end:
        out.append(_finding(2, tail, "tail", "tail", f"the tail ends f{tail}, before the recovery ends (f{end})", "stretch the dust and ground layers to the end of the recovery"))
    clean = end + int(round(rules["cleanAfter"] * fps))
    if "clean recovery" in keys and tail > clean:
        out.append(_finding(1, tail, "tail", "tail", f"the tail runs to f{tail}, past the clean recovery (f{clean})", "cut the lingering layers' Lifetime"))
    if "punchy" in keys:
        shakes = shake_frames(timeline)
        if not any(hit <= k <= hit + rules["shakeWithin"] for k in shakes):
            first = f"first at f{shakes[0]}" if shakes else "none"
            out.append(_finding(2, hit, "hit", "punchy", f"no camera jolt within {rules['shakeWithin']} frames of the hit ({first})", "a Shake on the hit with no Delay"))
    if "crisp" in keys:
        for b in spec["beats"]:
            st = b.get("_stats") or {}
            if not b.get("flash") and st.get("rise", 0) > rules["crispRise"]:
                out.append(_finding(1, b["from"], b["name"], "crisp", f"comes on over {st['rise']} frames; crisp wants {rules['crispRise']}", "shorten the fade-in"))
    for name, row in live.items():
        if row["rate"] > rules["stepRate"] * 1.5:
            out.append(_finding(1, row["first"], name, "steps", f"{name} changes its picture {row['rate']:.0f} times a second; the house look steps on twos ({rules['stepRate']}/s)", "hold each flipbook or shell frame for 1/12 s"))
    return out


def report(spec, found):
    move = spec.get("move")
    head = spec["preset"]
    if move:
        keys = move.get("keywords") or pacing()["styles"].get(move.get("style", ""), [])
        head += f" on {move.get('from', 'a move')} ({move.get('style', '?')}: {', '.join(keys)}; {move['windup']}/{move['active']}/{move['recovery']} s)"
    lines = [head, f"{len(found)} findings, fix first:" if found else "no findings"]
    for f in found:
        lines.append(f"  {f['sev']}  f{f['frame']:<4} {f['beat']:<12} {f['rule']:<9} {f['said']}")
        lines.append(f"  {'':<26}fix: {f['fix']}")
    return "\n".join(lines)
