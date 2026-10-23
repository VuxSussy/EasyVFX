# The VFX grammar

What a good effect is, written as numbers an agent can read, tune and check against the code it writes. It covers
how many layers an effect has, what each one does, and how each one moves, lives and fades. The art in the textures
comes second. Phát, 2026-10-24: "focus less on the individual art itself and based on code".

```bash
python3 tools/evfx grammar [preset ...]   # every layer: its role and numbers, and what breaks the grammar
python3 tools/evfx study [--write]        # what openly published Roblox effects do, per role
```

## Layers and roles

Every emitter or shell is a layer with one role. A role comes from the first of these that applies:

1. the beat sheet's `roles`;
2. the layer's name (`grammar.json` `names`; presets name emitters by role);
3. its numbers.

| Role | Job | Blend |
|---|---|---|
| core | the white-hot centre of the hit, on for 2 to 6 frames, on top | additive |
| glint | a crisp flare, star or ray fan on the hit, or a telegraph before it | additive |
| glow | a soft additive disc around the core or behind a shape: light, not mass | additive |
| base | the one readable silhouette of the beat: a flipbook, a ring, a shell | either |
| volume | fullness behind the base: smoke, a wider spread | normal |
| dark | value contrast: a dark halo, ink, a shadow behind the bright layers | normal, dark |
| shards | direction and snap: stretched sparks that explode and stop | additive |
| dust | tiny points over everything for scale and sparkle; calm, lingering | additive |
| debris | heavy chunks thrown by the hit: gravity, they land | normal |
| ground | ties the beat to the floor: rings, decals, dust rings | either |

These are plan §4a's roles plus glow. §4a's sparks are split three ways, because their numbers differ: shards stop
in a fraction of a second, dust drifts for seconds, and debris falls. Ground comes from the Lotus layer map.

## The measures

Each layer is read from what the builder actually built and the runtime played (the timeline), not from the preset
source. So every helper, default and multiplier is already applied.

| Measure | What it is |
|---|---|
| `count` | particles emitted |
| `delay` | seconds after the effect starts |
| `life` | mean lifetime, seconds |
| `vary` | longest lifetime over the shortest |
| `stop` | seconds until drag cuts the speed to a tenth (Roblox's `Drag` halves it every 1/`Drag` s) |
| `reach` | how far a particle travels in its life, in bodies (a character is 5 studs) |
| `spread` | spread angle, degrees |
| `size` | its largest size, in bodies |
| `grow` | end size over start size (0 shrinks to nothing) |
| `fade` | share of its life before it is half transparent |
| `solid` | how opaque it gets at most |
| `light` | `LightEmission` (1 is additive, 0 normal) |
| `z` | `ZOffset` |

Sizes are in bodies rather than relative to the effect, because effects are made to sit on a character. It also
lets an effect with no base layer compare with one that has.

## Where the ranges come from

`tools/evfx/grammar.json` gives each role a range for each measure, a `source` saying why, and `open`: the middle 70%
of what open effects do. The three sources are weighed this way:

1. **References for taste:**
   - Lotus and Frigid Rush ([dissection](refs/dissection-lotus-frigid.md), [layers](refs/lotus-layers.md));
   - Genshin ([study](refs/genshin-vfx.md)).

   They set the core's 2–6 frames, the lingering dust and the lifetime spread of about 2×.
2. **Open Roblox effects for craft:** `evfx study` reads the emitter settings of 50 openly published effects
   (`grammar.json` `openSources`: Roblox's own kits, the DevForum's ImpactVFX and others). The numbers only, never a
   texture. It sets the physics the references can't show: how long smoke and debris live, how hard drag stops
   sparks, gravity, `LightEmission` on smoke. These effects are common practice, not the target. So where they differ
   from the references, as when their glows hold 0.2–0.9 s, the references win. Their emit counts come from scripts,
   so `count` comes from plan §4a instead. The dataset stays in `.cache/vfxstudy`.
3. **Phát's picks:** variants he keeps or drops become ranges that win over both (to come).

## Structure

- **Depth order:** `ZOffset` should not decrease from dark through volume, glow, base, debris, shards and dust to
  glint and core. Ground and shells lie on their own surfaces.
- **Layers per beat:** 3 to 6 for a short hit. Lotus stacks 4 to 9.

Pacing is the [beat judge](agentic-loop.md#beats)'s job: beats, flashes and the move's timing from the motion bible.
The grammar is each layer's numbers.

## What it says today

| Preset | Out of the grammar |
|---|---|
| `impact_v4` | 4: embers' lifetimes too even, an opaque ink, shards drawn over embers, a one-layer tail |
| `slash_v4` | 3: embers too even, shards over embers, a two-layer scatter beat |
| `ground_slam_v4` | 4: embers too even, a slightly oversized flare, an opaque volume, shards over embers |
| `bloom_strike` | 20, among them a 0.2 s core on the seed, an opaque dark halo, grass with no role of its own |

No preset is changed here.
