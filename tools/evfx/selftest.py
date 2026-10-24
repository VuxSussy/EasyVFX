"""evfx selftest: every gate must fail its planted bad case, and the maths must match
Roblox's documented behaviour. Runs without Lune or Studio, so CI runs it on every push."""

import math

import numpy as np

from . import beats, core, grammar, measure, refs, render

IDENTITY = [0, 2, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]
SEQ1 = [[0, 1, 0], [1, 1, 0]]
WHITE = [[0, 1, 1, 1], [1, 1, 1, 1]]


def emitter(**over):
    e = {
        "name": "Test",
        "texture": "",
        "flipbook": "None",
        "flipMode": "Loop",
        "flipFramerate": [30, 30],
        "size": SEQ1,
        "squash": [[0, 0, 0], [1, 0, 0]],
        "transparency": [[0, 0, 0], [1, 0, 0]],
        "color": WHITE,
        "lifetime": [0.4, 0.4],
        "speed": [10, 10],
        "spread": [0, 0],
        "accel": [0, 0, 0],
        "drag": 0,
        "rotation": [0, 0],
        "rotSpeed": [0, 0],
        "orientation": "FacingCamera",
        "direction": "Top",
        "shape": "Box",
        "lightEmission": 1,
        "lightInfluence": 0,
        "brightness": 1,
        "zOffset": 0,
        "lockedToPart": False,
        "timeScale": 1,
        "rate": 0,
    }
    e.update(over)
    return e


def frame(t, **over):
    f = {"t": t, "beams": [], "parts": [], "streams": [], "lights": [], "screens": [], "trails": 0, "camera": IDENTITY, "fov": 70}
    f.update(over)
    return f


def timeline(frames=12, **over):
    tl = {
        "version": 1,
        "id": "planted",
        "kind": "burst",
        "frameTime": 1 / 30,
        "holder": IDENTITY,
        "fovHome": 70,
        "frames": [frame(k / 30) for k in range(1, frames + 1)],
        "emitters": [],
        "bursts": [dict(emitter(), count=5, frame=0, cframe=IDENTITY, volume=[0, 0, 0])],
        "leftover": 0,
    }
    tl.update(over)
    return tl


SCREEN = {"className": "ColorCorrectionEffect", "brightness": 0.5, "contrast": 0, "saturation": 0, "tint": [1, 1, 1]}
ROCK = {"cframe": IDENTITY, "size": [1, 1, 1], "shape": "Block", "material": "Slate", "color": [0.4, 0.4, 0.4], "t": 0, "className": "Part"}


def gate(tl, name):
    rows = measure.census(tl)
    for g, ok, reason in measure.gates(tl, rows, measure.rules()):
        if g == name:
            return ok, reason
    raise KeyError(name)


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def clean_case_passes_every_gate():
    tl = timeline()
    failed = [g for g, ok, _ in measure.gates(tl, measure.census(tl), measure.rules()) if not ok]
    assert not failed, failed


@check
def long_screen_flash_fails():
    tl = timeline()
    for f in tl["frames"][:6]:
        f["screens"] = [SCREEN]
    ok, reason = gate(tl, "flash.frames")
    assert not ok and "6 frames" in reason, reason


@check
def too_many_flashes_fail():
    tl = timeline(frames=30)
    for k in (0, 6, 12, 18, 24):
        tl["frames"][k]["screens"] = [SCREEN]
    ok, reason = gate(tl, "flash.rate")
    assert not ok, reason


@check
def effect_that_never_ends_fails():
    ok, reason = gate(timeline(leftover=3), "ends_clean")
    assert not ok and "3 left behind" in reason, reason


@check
def effect_that_lasts_too_long_fails():
    ok, reason = gate(timeline(frames=150), "ends_clean")
    assert not ok and "lasts 5.00 s" in reason, reason


@check
def over_budget_fails():
    tl = timeline()
    tl["bursts"][0]["count"] = 1000
    ok, reason = gate(tl, "budget.particles")
    assert not ok and "peak 1000" in reason, reason


@check
def plain_blocks_fail():
    tl = timeline()
    tl["frames"][0]["parts"] = [ROCK, ROCK]
    ok, reason = gate(tl, "plain_pieces")
    assert not ok and "peak 2" in reason, reason


@check
def an_emissive_shell_frame_is_not_a_plain_block():
    shell = dict(ROCK, className="MeshPart", material="SmoothPlastic", emissive=3)
    tl = timeline()
    tl["frames"][0]["parts"] = [shell]
    ok, reason = gate(tl, "plain_pieces")
    assert ok, reason
    tl["frames"][0]["parts"] = [dict(shell, emissive=None)]
    ok, reason = gate(tl, "plain_pieces")
    assert not ok, "a plastic mesh without an emissive mask passed as glowing"


@check
def particle_flies_at_its_speed():
    p = core._particle(emitter(), IDENTITY, [0, 0, 0], 0.25, core._rng("x"))
    assert abs(p["pos"][1] - (2 + 2.5)) < 1e-6, p["pos"]


@check
def drag_halves_speed_every_one_over_drag_seconds():
    p = core._particle(emitter(drag=5, lifetime=[1, 1]), IDENTITY, [0, 0, 0], 0.2, core._rng("x"))
    assert abs(core.length(p["vel"]) - 5) < 1e-6, p["vel"]


@check
def particle_is_gone_after_its_lifetime():
    assert core._particle(emitter(), IDENTITY, [0, 0, 0], 0.41, core._rng("x")) is None


@check
def four_beziers_make_a_circle():
    r = 3.0
    k = r * 4 / 3 * math.tan(math.pi / 8)
    worst = 0.0
    for q in range(4):
        a0, a1 = q * math.pi / 2, (q + 1) * math.pi / 2
        p0 = (r * math.cos(a0), 0, r * math.sin(a0))
        p3 = (r * math.cos(a1), 0, r * math.sin(a1))
        t0 = (-math.sin(a0), 0, math.cos(a0))
        t1 = (-math.sin(a1), 0, math.cos(a1))
        p1, p2 = core.add(p0, core.mul(t0, k)), core.sub(p3, core.mul(t1, k))
        for s in range(11):
            p = core.bezier(p0, p1, p2, p3, s / 10)
            worst = max(worst, abs(math.hypot(p[0], p[2]) - r) / r)
    assert worst < 0.001, worst


@check
def sequences_interpolate():
    seq = [[0, 0, 0], [0.5, 1, 0], [1, 0, 0]]
    assert core.number_at(seq, 0.25) == 0.5 and core.number_at(seq, 0.75) == 0.5


@check
def particles_are_the_same_every_run():
    tl = timeline()
    a = [p["pos"] for p in core.particles_at(tl, 0.1)]
    b = [p["pos"] for p in core.particles_at(tl, 0.1)]
    assert a == b and len(a) == 5


@check
def a_glowing_particle_lights_the_screen_where_it_is():
    tl = timeline()
    tl["bursts"][0].update(speed=[0, 0], size=[[0, 2, 0], [1, 2, 0]])
    cam = core.Camera((0, 2, 10), (0, 2, 0), 70, (160, 120))
    lit, _ = render.draw(tl, 0.1, cam, body=False)
    dark, _ = render.draw(tl, 0.5, cam, body=False)
    centre = lit[55:65, 75:85].mean()
    assert centre - dark[55:65, 75:85].mean() > 0.3, centre
    assert np.abs(lit[:20] - dark[:20]).max() < 0.08



@check
def a_mesh_draws_its_texture_where_it_is_and_only_once():
    cam = core.Camera((0, 0, 10), (0, 0, 0), 70, (160, 120))
    quad = np.array([[-2, -2, 0], [2, -2, 0], [2, 2, 0], [-2, 2, 0]], np.float64)
    uvs = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], np.float64)
    tris = np.array([[0, 1, 2], [0, 2, 3]])
    tex = np.zeros((8, 8), np.float32)
    tex[:, 4:] = 1  # the right half of the texture
    one = render.Canvas(cam)
    render.draw_mesh(one, quad, uvs, tris, tex, (1, 1, 1), 1.0, 1.0)
    two = render.Canvas(cam)
    render.draw_mesh(two, quad, uvs, np.concatenate([tris, tris[:, ::-1]]), tex, (1, 1, 1), 1.0, 1.0)
    assert one.glow[60, 90].max() > 0.9 and one.glow[60, 70].max() < 0.05, "texture lands on the wrong half"
    assert np.allclose(one.glow, two.glow), "a two-sided shell lights twice"
    assert one.glow[:20].max() == 0, "the mesh spills outside its quad"


# The beat judge (tools/evfx/beats.py) --------------------------------------------


def hit_timeline(frame_at=0, life=1.5, frames=40):
    """60 fps: one white flash named Core, `life` frames long, fired at `frame_at`. A
    particle shows on every frame its age is within its lifetime, so 1.5 frames shows 2."""
    burst = dict(emitter(name="Core", speed=[0, 0], size=[[0, 3, 0], [1, 3, 0]], lifetime=[life / 60] * 2),
                 count=1, frame=frame_at, cframe=IDENTITY, volume=[0, 0, 0])
    tl = timeline(id="planted_hit", frameTime=1 / 60, bursts=[burst])
    tl["frames"] = [frame(k / 60) for k in range(frames)]
    return tl


def hit_sheet(**move):
    spec = {"preset": "planted_hit", "beats": [
        {"name": "Hit", "from": 0, "to": 2, "flash": True, "hit": True, "palette": [], "layers": {"main": ["Core"]}},
    ]}
    if move:
        spec["move"] = {"windup": 0.1, "active": 0.08, "recovery": 0.3, "style": "Duelist", "fire": 0, **move}
    return spec


def rules_of(found):
    return {f["rule"] for f in found}


@check
def a_two_frame_flash_on_the_hit_passes():
    found = beats.judge(hit_sheet(keywords=["snappy"]), hit_timeline())
    assert not rules_of(found) & {"flash", "hit", "present", "layers", "snappy"}, found


@check
def a_held_flash_fails():
    found = beats.judge(hit_sheet(), hit_timeline(life=7))
    assert any(f["rule"] == "flash" and f["sev"] >= 2 for f in found), found


@check
def a_late_hit_fails():
    found = beats.judge(hit_sheet(keywords=[]), hit_timeline(frame_at=5))
    assert any(f["rule"] == "hit" and f["sev"] == 3 for f in found), found


@check
def a_missing_layer_fails():
    spec = hit_sheet()
    spec["beats"][0]["layers"]["line"] = ["Ghost"]
    assert any(f["rule"] == "layers" and "Ghost" in f["said"] for f in beats.judge(spec, hit_timeline())), "Ghost not reported"


@check
def heavy_with_no_wind_up_tell_fails():
    found = beats.judge(hit_sheet(keywords=["heavy"]), hit_timeline())
    assert "windup" in rules_of(found), found


@check
def beat_stats_read_rise_fall_and_flash():
    lum = [0, 0, 0, 0.5, 1, 1, 0.8, 0.6, 0.4, 0.2, 0.05, 0, 0, 0, 0, 0]
    white = [0, 0, 0, 0, 1, 1, 0.3, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    curves = {"lum": lum, "white": white, "motion": [0.1] * 16, "hue": [[1] + [0] * 11] * 16}
    st = refs.stats(curves, 3, 9, flash=True)
    assert st["peak_at"] == 1 and st["rise"] == 1, st
    assert st["half"] == 4 and st["tenth"] == 6, st
    assert st["flash"] == 2 and st["top"] == ["red"], st


# The VFX grammar (tools/evfx/grammar.py) ------------------------------------------


@check
def drag_travel_matches_the_half_life():
    # Drag 1 halves speed every second: in 1 s a 10 stud/s particle covers 10 / (2 ln 2)
    assert abs(grammar.travel(10, 1, 1) - 10 / (2 * math.log(2))) < 1e-6
    assert grammar.travel(10, 0, 0.5) == 5
    assert abs(grammar.stop_time(1) - math.log(10) / math.log(2)) < 1e-9


@check
def fade_point_reads_half_transparency():
    assert abs(grammar.fade_point([[0, 0], [1, 1]]) - 0.5) < 1e-9
    assert grammar.fade_point([[0, 0], [1, 0]]) == 1.0
    assert grammar.fade_point([[0, 0.6], [1, 1]]) == 0


@check
def a_slow_soft_core_breaks_the_grammar():
    tl = hit_timeline(life=12)
    tl["bursts"].append(dict(tl["bursts"][0], name="Ring", lifetime=[0.3, 0.3], size=[[0, 6, 0], [1, 6, 0]], frame=1))
    rows, _ = grammar.layers(tl)
    rules = {f["rule"] for f in grammar.judge(rows)}
    assert "core.life" in rules, rules


@check
def exits_read_cut_fade_shrink_and_disperse():
    assert grammar.exit_of([[0, 0], [1, 0]], [[0, 1], [1, 2]])[0] == "cut"
    assert grammar.exit_of([[0, 0], [0.5, 0], [1, 1]], [[0, 1], [1, 1]]) == ("fade", 0.5, 0.0)
    assert grammar.exit_of([[0, 0], [1, 0]], [[0, 1], [1, 0]])[0] == "shrink"
    assert grammar.exit_of([[0, 0.2], [0.3, 0.3], [1, 1]], [[0, 1], [1, 2]])[0] == "disperse"


def run():
    failed = 0
    for fn in CHECKS:
        try:
            fn()
            print(f"evfx selftest: ok   {fn.__name__}")
        except Exception as err:  # noqa: BLE001
            failed += 1
            print(f"evfx selftest: FAIL {fn.__name__}: {err!r}")
    print(f"evfx selftest: {len(CHECKS) - failed} passed, {failed} failed")
    return 1 if failed else 0
