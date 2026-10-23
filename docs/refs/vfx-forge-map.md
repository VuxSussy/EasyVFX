# VFX Forge's variables, and our version

[VFX Forge](https://docs.zilibobi.dev/vfx-forge/) (zilibobi; the docs are MIT) is a paid Studio plugin plus a free
emit module. Effects are tuned through instance attributes and per-property curves. All 24 docs pages were read on
2026-10-24. Three of them (showcase, new VFX, utilities) are only images or scripts. This page maps their variable
names, then proposes ours: one set of names that the builder writes, the runtime reads, the grammar measures and the
studio turns. Then an agent tunes one vocabulary everywhere.

## Their variables

### On every effect

| Variable | Type | What it does |
|---|---|---|
| `EmitCount` | number | how many times it emits |
| `EmitDelay` | number | seconds before it emits |
| `EmitDuration` | number | spreads the emits over this many seconds |
| `EffectDuration` | NumberRange | how long the effect runs (beam, mesh, bezier) |
| `Enabled` + `Rate` | bool, number | emit continuously, this many per second |
| `SyncPosition` | bool | follow the origin after emitting |
| `DestroyDelay` | number | wait before cleanup (bezier) |

### Curves

Each animated property is a curve, not a fixed number. Every curve takes:
- `Start` and `End` values (the ranges below);
- points drawn on a normalized canvas, or one of 26 built-in cubic bezier presets (in, out, in-out), or a custom
  preset;
- for sequence properties, `Envelope` (the random spread on each keypoint) and `Smoothness` (how many keypoints the
  curve becomes, by Newton–Raphson).

| Effect | Curves |
|---|---|
| Particle | `Transparency` [0, 1], `Size` [0, ∞), `Squash` (−∞, ∞), `TimeScale` (an eased [0, 1] with its own `Duration`) |
| Beam | `Transparency_Base`, `Transparency_Scale` (multiplies it), `Width0`, `Width1`, `Speed` |
| Mesh | `Part_CFrame`, `Part_Transparency`, `Part_Size`, `Part_RotSpeed`, `Mesh_Scale`, `Speed` |
| Mesh decal | `Transparency`, `Color`, `Flipbook_Change` (the easing between flipbook frames) |
| Spin model | `Scale_Curve`, `SpinSpeed_Curve` |
| Bezier | `Easing` (motion along the path) |
| Shockwave ring, line, debris | `Size`, `Transparency` (at the end of life); a line adds `Scale` over its duration |
| Camera shake | `Speed` |

`Speed` is a curve over the whole effect's clock. When it goes negative, the effect plays backwards.

### Per effect type

| Effect | Variables |
|---|---|
| Mesh | Start and End parts set the endpoints of CFrame, size and mesh scale; `SpreadAngle` (Vector2), `MinInitRot` / `MaxInitRot` (Vector3) |
| Mesh decal | `FlipbookEnabled`, `FlipbookTextures` (frame IDs, written by their importer) |
| Bezier | `EmissionDirection`, `Shape`, `ShapeStyle`, `ShapePartial`, `ShapeFace` (in, out, both), `SpreadAngle`, `MirrorPaths`, `MirrorRotation`, `FacePath`, `ArcSpace` (uniform speed), `ProjectileEnabled` / `ProjectileSpeed` / `ProjectileLifetime` / `MatchEndDirection`, and `Hitbox…` (enabled, filter tag and type, collision group, ignore CanCollide) |
| Spin model | `SpinRotation` (Vector3, degrees a second), `SpinDuration` |
| Camera shake | `Amplitude`, `Frequency`, `FadeInTime`, `SustainTime`, `FadeOutTime`, `PositionInfluence`, `RotationInfluence` (Vector3s), `Falloff` (radius) |
| Screen effect | `PartDistance`, `PartScale`, `OffsetPosition`, `OffsetRotation` |
| Shockwave (shared) | `RayDirection`, `RayCollisionGroup`, `FilterTag`, `FilterType`, `IgnoreWater`, `IgnoreCanCollide` |
| Shockwave ring | `Radius`, `Segments`, `Lifetime` (range), `MinSize` / `MaxSize`, `SizeScaleStart` / `SizeScaleEnd` |
| Shockwave line | `Length`, `Direction`, `Duration`, `Rotation` (range), `Lifetime`, sizes as for the ring |
| Shockwave debris | `Amount`, `Lifetime`, `LinearMagnitude`, `AngularMagnitude` (ranges), `MinDirection` / `MaxDirection`, sizes, and `Inheritance…` (take material and colour from the ground: enabled, radius, max results) |

**Tools:**
- curve and effect presets: an effect preset replaces every curve and input it saved;
- a point shifter that keeps the points' times when a duration changes;
- loading a curve back into the editor;
- path visualization for particles, beziers and debris.

**Runtime:** `vfx.emit(...)` returns a handle with a `Finished` promise; it is also exposed as `shared.vfx`. The
runtime uses object pooling and bulk CFrame moves.

## What we have today

| Area | EasyVFX now |
|---|---|
| Emission | `EmitCount`, `EmitDuration` attributes; a layer's `burst`, `delay`, `rate` |
| Curves | raw keypoint lists per layer (`size`, `transparency`, `squash`), with envelopes; no named eases |
| Shells | `Size0` / `Size1`, `Duration`, `Delay`, `SpinDeg`, `Tilt`, `Transparency`, `FadeStart`; frames swap at a fixed rate |
| Shake, hit-stop, punch | `Magnitude`, `Duration`, `Roughness`, `Kick`; `HitStop.Duration`; `Punch.Amount` |
| Whole-effect clock | none (hit-stop freezes it; there is no speed curve) |
| Beziers, rocks, screen parts | none (rocks are particles; plain blocks fail the audit) |

## Our version: a proposal

One vocabulary, the same in four places:
1. preset code;
2. the attributes the builder writes;
3. what the runtime reads;
4. what `evfx grammar` measures and `evfx serve` turns.

Lowercase in presets, PascalCase as attributes, as today.

### 1. Curves with named eases

Every animated property becomes a curve:

```lua
transparency = { from = 0, to = 1, ease = "inCubic", hold = 0.4, envelope = 0.05 }
size = { from = 1.2, to = 0, ease = "outQuad" }
```

- **Ease presets:** `linear`, then `in`, `out` and `inOut` × `sine`, `quad`, `cubic`, `quart`, `expo`, `circ`, `back`
  (22), plus `steps(n)` for the on-twos look.
- **`hold`:** the share of life before the curve starts moving. With it, "hold, then fade" is one line, not five
  keypoints.
- **Building:** the builder turns a curve into a NumberSequence, choosing the keypoint count by a `smooth` tolerance
  (their Smoothness).

This answers the abrupt endings directly. Each grammar role gets a named **exit preset**:

| Exit preset | Roles | Curves |
|---|---|---|
| `flashCut` | core | transparency 0 → 1 over the last 40%, `outQuad` |
| `snapShrink` | shards | size → 0, `inQuad` |
| `holdFade` | base, glint, dark, dust | transparency, `hold = 0.4–0.6`, `inCubic` |
| `gustDisperse` | volume, ground | transparency `hold = 0.3`, `inOutSine`; size × 1.35, `outSine`; life × 1.5 |
| `sinkFade` | debris | gravity, then transparency over the last 15% |

The studio's `exits` knob becomes a choice of these presets, and the grammar reports which preset a layer matches.

### 2. Emission and the effect's clock

- **Keep:** `emitCount`, `emitDelay`, `emitDuration`, and `rate` for streams.
- **Add `duration`** as a range on shells and beams (their `EffectDuration`).
- **Add a whole-effect `speed` curve** (their `Speed`) on the root. Hit-stop, slow motion and Retime all become one
  curve. Hit-stop is `speed` dipping to 0.01 for 0.03–0.15 s. It also fixes the known desync where hit-stop paused
  shells but not particle delays, because every layer reads the same clock.

### 3. Shells, the mesh layer

Rename to their Start/End model, since it reads better for agents:
- `size = { from = Vector3, to = Vector3, ease }`, replacing `Size0` / `Size1`;
- `spin = { rate = Vector3, ease }`, replacing `SpinDeg`;
- `spread` (Vector2) and `initRot = { min, max }` (Vector3s) for per-emit variety;
- `transparency` as a curve, replacing `Transparency` and `FadeStart`;
- `frames = { ease = "steps(6)" }`, replacing the fixed frame rate (their `Flipbook_Change`). On-twos shells become one
  word, and the grammar's `steps` rule can check it.

### 4. Shake as an envelope

Rename to their envelope names:
- `amplitude`, `frequency`;
- `fadeIn`, `sustain`, `fadeOut`, replacing `Duration` and `Kick`;
- `position` and `rotation` influences (Vector3);
- `falloff`.

The motion bible's victim shake ("decaying over the freeze") is then `fadeOut` equal to the hit-stop length.

### 5. Later, as new layer kinds

- **Path layers** (their Bezier): `path = { shape, face, spread, mirror, facePath, uniformSpeed, ease }`, plus
  `projectile = { speed, life }` after the path ends. This covers homing orbs and the beam tutorial's orbit rings.
  Hitboxes stay out, since gameplay owns hits in SE370.
- **Ground pieces** (their shockwave ring, line and debris): `ring = { radius, segments }`, `line = { length,
  direction }`, `debris = { amount, linear, angular, direction }`, with `inherit` from the floor. This needs a call
  first: plain blocks fail the audit today. Inherited, textured rocks may be the exception.
- **Screen parts:** `distance`, `scale`, `offset`.

### 6. In the tools

| Theirs | Ours |
|---|---|
| curve and effect presets | exit presets, plus whole-layer presets in `grammar.json`; the studio applies them |
| point shifter | `retime` keeps every curve's `hold` and ease and scales `duration` |
| path visualization | `evfx` already draws particle paths headless; add path layers when they exist |
| `emit` returns `Finished` | `EasyVFX.PlayLocal` returns a handle with `finished` (for chaining beats) |

## What a user's review asks for

A VFX Forge user's review (pasted by Phát, 2026-10-24) makes four points that match this plan:
- **One system for meshes, beams and particles** is the strength. The grammar already reads all three as layers, and
  this vocabulary keeps them under one set of names.
- **Deeper documentation, and particles that are easier to put in code.** This is the point of one vocabulary and of
  `docs/vfx-grammar.md`. The building blocks the hero set already uses (`heroFlash`, `heroShards`, `heroEmbers`,
  `heroShell`) become public **layer kits**, each documented with its role, knobs and exit preset. Code then composes
  an effect from kits instead of copying emitter tables.
- **Loading curves back** into the editor. Ours is `evfx grammar`, which reads any layer's curves back as a named ease
  and exit.
- **One primary part.** Put a root part at the HumanoidRootPart with everything else welded to it, then clone it, set
  its CFrame and emit. `Builder.create` already builds one root part (`VFX_<Name>`, with `placement.weldTo`), and
  `EasyVFX.PlayLocal(target, at)` plays a copy at a CFrame. The proposal makes this the documented contract: every
  effect is one rig, so playing one is clone, place and emit.

## Order

1. Named-ease curves with `hold`, and the exit presets: they fix the abrupt endings, and the grammar can name a
   layer's exit.
2. The whole-effect `speed` clock: hit-stop and Retime on one clock, which fixes the desync.
3. The shell renames, with `frames.ease`.
4. The shake envelope.
5. Path layers and ground pieces, after a call on rocks.
