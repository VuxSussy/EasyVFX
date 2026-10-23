# Lotus: the layer map

How [Plebarae's *Lotus*](https://youtu.be/0aWTYOV8VtA) builds depth, beat by beat. Read from two camera angles (pass 1
and pass 2, 612 frames apart) at full resolution. Frame numbers are pass 1 at 60 fps. The beat timings are in
[the dissection](dissection-lotus-frigid.md).

Each layer gets a role from plan §4a and a name, and is listed from back to front:

- **Blend:** `add` (additive, `LightEmission` 1) or `normal` (`LightEmission` 0).
- **Facing:**
  - `bill`: a camera-facing particle;
  - `flat`: lies on the ground or in a plane;
  - `mesh`: a 3D shell;
  - `beam`: a ribbon.

## The pattern

Every beat stacks the same five depths. Most of the craft is in that stack, not in the hand-drawn art:

| Depth | Job | Blend | Examples |
|---|---|---|---|
| 1. **Ground** | ties the beat to the floor | normal or add, flat | splash decal, gold ring ellipse, grass |
| 2. **Back volume** | soft, dark or coloured mass behind, for contrast and size | normal | violet smoke behind the slash, dark halo behind the star |
| 3. **Main shape** | the one readable silhouette of the beat | add, white edge and coloured body | crescents, star, sphere, flower sigil, dome, lotus |
| 4. **Line work** | thin bright lines in front that give motion and crispness | add | ribbons, streaks, tendrils, rim wisps, pillar streaks |
| 5. **Dust** | tiny points over everything, for scale and sparkle | add | sparkles, orbit rings, bokeh, petals, gold dust |

Contrast comes from the back volume and the dark stage. The main shape is never alone: a soft layer sits behind it and
a thin layer in front.

## Beat by beat

### A. Water swirl (f0–60)

| # | Layer | Role | Blend | Facing | What it is |
|---|---|---|---|---|---|
| 1 | GroundSplash | Base | normal-ish | flat | a solid blue painted splash on the floor, with a lighter edge |
| 2 | Haze | Volume | normal | bill | grey-blue smoke in the middle |
| 3 | Tendrils | Base | add | flat cards | thick, wavy blue brush shapes standing around the character |
| 4 | Ribbons | Sparks | add | beam / trail | thin cyan-white swirling ribbons with a pink tint, circling in 3D |
| 5 | Sparkles | Sparks | add | bill | many tiny white and pink points |

### B. Gold ornaments (f75–160)

| # | Layer | Role | Blend | Facing | What it is |
|---|---|---|---|---|---|
| 1 | BodyGlow | Volume | add | bill | a soft gold glow on the character |
| 2 | Coins | Base | add | bill / tilted | gold sigil discs with smoky insides |
| 3 | Chains | Base | add | beam | thin fibrous gold strokes linking the coins |
| 4 | EndFlares | Glint | add | bill | 4-point gold stars where the strokes end |
| 5 | GoldDust | Sparks | add | bill | gold sparkle dust |

### C. Slash wrap (f162–176)

| # | Layer | Role | Blend | Facing | What it is |
|---|---|---|---|---|---|
| 1 | SlashSmoke | Volume | normal / soft add | bill | a violet smoke puff behind the crescents, for depth |
| 2 | Crescents | Base | add | mesh / flat | 2–3 thick crescents at different radii and depths, with a white inner edge and a body going from pink to violet to blue, fibrous at the edges |
| 3 | MotionStreaks | Sparks | add | beam | straight pink and violet speed lines through the middle |
| 4 | Dust | Sparks | add | bill | violet dust |

### D. Dash comet (f176–188)

| # | Layer | Role | Blend | Facing | What it is |
|---|---|---|---|---|---|
| 1 | DarkChunks | Dark | normal | bill | dark blue smoke chunks along the path |
| 2 | CometBody | Base | add | beam | a long body of blue fibrous streaks |
| 3 | CometHead | Core | add | bill | a white-pink crescent head |
| 4 | Shards | Sparks | add | bill (velocity) | blue shards peeling off backward |

### E. Flare (f190–194, 2 + 2 frames)

| # | Layer | Role | Blend | Facing | What it is |
|---|---|---|---|---|---|
| 1 | **DarkHalo** | Dark | normal, black | bill | a solid dark disc about the star's size: the negative space |
| 2 | Bloom | Volume | add | bill | a soft violet glow |
| 3 | Star8 | Core | add | bill | an 8-point star: 4 long spikes, 4 shorter diagonals, a white core with violet edges |
| 4 | Cross4 | Core | add | bill | f194 only: a thinner 4-point cross as the star shrinks |
| 5 | Shards | Sparks | add | bill | blue lightning shards left over from the comet |

### F. Collapse and sphere (f196–222)

| # | Layer | Role | Blend | Facing | What it is |
|---|---|---|---|---|---|
| 1 | SparkBall | Core | add | bill | f196–202: a small pink-white ball with a short trail |
| 2 | Tendrils | Sparks | add | beam | thin curved arcs out from the ball |
| 3 | Sphere | Base | add | mesh | f204–214: a sphere shell with a swirl texture, pink-white turning blue |
| 4 | RimWisps | Sparks | add | beam / flat | blue wisps running along the sphere's rim |

### G. Flower sigil (f220–240)

| # | Layer | Role | Blend | Facing | What it is |
|---|---|---|---|---|---|
| 1 | Bokeh | Volume | add, soft | bill | soft blurry violet discs |
| 2 | FlowerSigil | Base | add | bill | 8 thin petal strokes radiating, blue with white edges |
| 3 | Wisps | Sparks | add | flat | blue swirl strokes breaking outward |
| 4 | OrbitRings | Sparks | add | bill | small hollow pink rings scattered around |
| 5 | Twinkles | Glint | add | bill | 4-point sparkles |

### H. Gold seed (f270–341)

| # | Layer | Role | Blend | Facing | What it is |
|---|---|---|---|---|---|
| 1 | RingStroke | Base | add | bill | a gold calligraphic circle stroke, rotating |
| 2 | Stem | Base | add | beam | a stroke down to the ground, with a flare where it lands |
| 3 | Seed | Core | add | bill | a small gold swirl flipbook on the ground |
| 4 | GoldSparks | Sparks | add | bill | gold sparks rising and falling |

### I. Dome flash and bloom (f343–480)

| # | Layer | Role | Blend | Facing | What it is |
|---|---|---|---|---|---|
| 1 | GroundRing | Base | add | flat | a gold ellipse on the ground with a bright rim |
| 2 | Grass | Dark | normal, dark green | bill | grass blades sprouting around: dark accents near the ground |
| 3 | Dome | Core | add | mesh | f343–345: a blown-out white hemisphere |
| 4 | FringeArc | Glint | add | mesh / bill | a rainbow fringe on the dome's rim, holding about 0.3 s after the dome fades |
| 5 | Pillar | Base | add | mesh / beam | vertical magenta streaks rising and fading upward |
| 6 | Lotus | Base | normal-ish, translucent | mesh | two rings of pink petals with darker outlines, opening upward over about 0.4 s |
| 7 | BaseSparks | Sparks | add | bill | thin white radial spark lines at the base |
| 8 | Petals | Sparks | normal | bill | pink petals drifting outward and down |
| 9 | GoldDust | Sparks | add | bill | gold sparkles |

### J. Calm tail (f480–600)

| # | Layer | Role | Blend | Facing | What it is |
|---|---|---|---|---|---|
| 1 | GroundSwirl | Base | add | flat | gold brush strokes circling on the floor, fading slowly |
| 2 | Grass | Dark | normal | bill | grass holds, then fades |
| 3 | Petals | Sparks | normal | bill | petals keep drifting |
| 4 | GoldDust | Sparks | add | bill | gold dust, barely moving |

## What we can build in our pipeline

Everything above maps onto pieces we generate, apart from the hand-painted look:

| Their layer | Ours |
|---|---|
| crescents, comet head | `mesh/crescent_*` shells with `seq/slash_ribbon`; `flip/slash_erode` |
| star, cross, halo, bloom | `shape/cross_flare`, `shape/godray_fan`, `art/dark_halo`, `shape/core_flash`, and a new 8-point star |
| sphere, dome | `mesh/sphere` shells (a swirl strip on the sphere, a hemisphere dome) |
| pillar | `mesh/cylinder` shell with a vertical streak strip |
| rings on the ground | `art/sigil_*`, `art/floor_streaks`, `flip/shock_ring` lying flat |
| fringe | `art/fringe_ring` |
| flower sigil, orbit rings, bokeh | new: radial petal-stroke sigil, hollow ring, soft bokeh disc |
| calligraphic gold strokes | `art/brush_strokes`, and a new brush ring |
| lotus | new: a generated petal-crown mesh (`meshgen`) carrying a cel petal texture, opened by scale |
| petals, dust, sparkles, shards | `art/petals_cel`, `sheet/embers`, `shape/aniso_shard`, `shape/cross_flare` |
| smoke behind | `flip/smoke_puff` tinted, normal blend |
| grass | new: a sheet of dark blade variants |

## Our rebuild: Bloom Strike (beat sheet)

Lotus's layering and timing, compressed to a game-length move. All the art is generated. Frames are at 60 fps, from
the strike. Emitters are named as below and grouped by beat.

| Beat (group) | Frames | Layers, back to front | Palette |
|---|---|---|---|
| Wrap | f0–14 | SlashSmoke (smoke puff, violet, normal), Crescents (two crescent shells, white to pink, pink to violet), MotionStreaks (a two-way line burst of streaks), Dust | white, pink, violet |
| Flare | f26–28, **2 frames** | DarkHalo (black disc), Bloom (soft violet), Star8 (8-point star), then Cross4 (4-point, 1 frame) | white, violet |
| Sphere | f30–52 | SparkBall, Tendrils, Sphere (a sphere shell, pink-white to blue), RimWisps | pink-white, blue |
| Sigil | f50–96, fading by f100 | Bokeh, FlowerSigil (8 petal strokes, slowly turning), OrbitRings, Twinkles | blue, violet, pink |
| Seed | f78–90, on the ground | RingStroke (gold brush ring), Seed (gold core), GoldSparks | gold |
| Dome | f90–92, **2 frames** | Dome (a white hemisphere shell) | white |
| Bloom | f92–162 | GroundRing (gold ornate sigil, flat), FringeArc (rainbow ring, about 0.3 s), Pillar (cylinder shell of vertical magenta streaks), Lotus (a generated petal-crown mesh with a cel petal, opening), BaseSparks, Petals, GoldDust | magenta, gold, a rainbow rim |
| Tail | f160–240 | GroundSwirl (gold brush ring, flat, slow), Grass (dark blades), Petals and GoldDust drifting, barely moving | gold, pink, dark green |

Weight: a hit-stop on the flare, and a small shake on the dome.
