# Plan: real VFX art for EasyVFX and SE370

Status: planned, calls made (2026-10-23, §7). Nothing here is built; next: step 1, texgen and library v4. Read with [the agentic loop](agentic-loop.md) (PR #8), which is
how every step below is judged.

**The gap.** The 45 presets are geometry and a 19-texture pack: crisp, but they read as Roblox. Seen against the
references below, three building blocks are missing:

- **Texture art:** noise, erosion dissolves, variety sheets, tiling strips.
- **Meshes:** shells for slashes, cones and shockwaves.
- **An effect grammar:** timing, value, colour and shape language, the parts that make a hit read as Zenless Zone Zero
  rather than a particle demo.

This plan says what to take from each reference, what Roblox can and can't do today, the workaround for each missing
piece, and the order to build it in.

## 1. References

**Video A:** VFX Apprentice, *Textures, Meshes, Shaders* (2024).

- An effect is many layered textures, never one.
- **Texture kinds:**
  - **Shapes:** core flash, glow, sparks.
  - **Flipbooks:** frames in a grid.
  - **Spritesheets:** variants, not a sequence, so the eye catches no repeat.
  - **Tiled textures:** for scrolling.
  - **Noise and erosion maps:** they drive how a shape breaks up and dissolves, instead of fading it evenly.
- **Meshes** are canvases that give depth: spheres, cylinders, cones, crescents, spirals, the camera-facing quad.
- **Shaders** tell the story (pan, scale, colour over time, erosion, distortion, vertex offset): a beginning, middle and
  end.

**Video B:** Le Lu, *VFX Texture Creation: The Ultimate Guide* (2025).

- Don't make what you can find: Simon Schreibt's *Textures for VFX* database collects free packs, with credit.
- Generators beat painting for common shapes: polar conversion, tiling, spark, sun, lightning and fire presets, noise.
- **Krita:** symmetry and the multibrush for stars and rings, wrap-around for tiling, a duplicated layer blurred for
  glow, the morphological filter for dissolves.
- Engines bake noise nodes to images; ours is the Python generator.

**Video C:** Zenless Zone Zero, Phát's capture (2026-10-23, 1080p60, 106 s, a mech agent, purple theme).

Measured: screen-brightness spikes last 1–5 frames at 60 fps (17–83 ms). A heavy hit, frame by frame at 60 fps:

| Phase | Frames (60 fps) | What happens |
|---|---|---|
| Anticipation | 0–10 (≈170 ms) | the always-on purple emissive trim; small charge glints at the weapon; sparks converging |
| Impact | 12–13 (≈33 ms) | a **warm white-gold** flash, the complement of the purple theme; radial god-ray spikes; a lens-flare cross; hit-stop |
| Burst | 14–18 | a screen-filling **purple** radial burst; camera push and radial motion blur; **chromatic aberration** fringes; long pink **anisotropic shards** with white cores flying outward |
| Follow-through | 20–36 (≈300 ms) | very long, thin **light streaks** (the dash) with a lightning fringe and a white core; **crescent afterimage arcs**; a **black ink slash stroke** across the bright frame; dust and glints that linger |

**The grammar it shows:**

- **Value first:** white-hot cores everywhere, heavy bloom.
- **Colour:** one theme hue, a white core, a complementary flash, a black ink accent.
- **Shape:** long, thin and anisotropic. Streaks, shards and arcs, almost no round blobs.
- **Time:** a 2-frame flash, a 5-frame burst, a 300 ms tail. Nothing lingers.
- **Camera:** sells the hit with shake, FOV push, blur and RGB split.

We take its grammar, never its assets or frames.

**Video D:** MaskedFaces, *Roblox VFX Basics: Simple Fire* (2024). One fire, five `ParticleEmitter`s on one
attachment, each with a role:

- **Base flame:** a OneShot fire flipbook; lifetime 1–1.5 s; rotation random over 360; speed 3; spread 15.
- **Volume:** the same layer with spread 45.
- **Hot core:** small, the only one with `LightEmission`.
- **Dark layer:** behind the base, for depth.
- **Sparks:** small, fast, rising.

Shape comes from curves over each particle's life: size shrinks as it rises, `Squash` rises at the end, transparency
fades with a pop. Body layers use **normal blending** (`LightEmission` 0, `LightInfluence` 0, low `Brightness`, a
saturated colour) and stay solid instead of pastel; only cores, flashes and sparks are additive. This matches the
SE370 VFX bible's tested rule.

**Video E:** Hazaze, *Frigid Rush* (2024, 20 s; an ice skill made entirely in Roblox Studio, timed in Moon Animator).
The **good** tier: a sound grammar with plain art.

- **The beat:** a twinkle **glint** on the target, a calm near-empty beat (≈270 ms), then a 2-frame world-space white
  flash.
- **The ground tells the element:** a flat frost-sigil decal and radial floor streaks.
- **The tail:** thin hard **crescents** that hang ≈0.6 s; slow ice petals and snow sparkles.
- **Rainbow fringe baked into textures and colour sequences:** a world-space chromatic fake that needs no post effect.
- **Palette:** white dominant, the element colour only at the core.

**Video F:** Fa5our, an AI-made "anime VFX in Roblox" attempt (2026). The **refuse** tier, and the failure our own loop
risks:

- plain parts as art (voxel cubes, black slabs, a building);
- thick constant-width neon rings and tubes;
- no flash, burst or tail: effects appear and stay;
- one saturated hue flooding the screen, no white core, the sky and lighting swapped;
- effects burying the characters, with title cards carrying the impact;
- round uniform blobs;
- floating rings with no ground contact.

**Video G:** Plebarae, *Roblox VFX: Lotus* (2025, 35 s). The **target** tier.

- **Restraint:** a dark neutral stage and no screen flash at all (zero flash runs; average screen brightness 0.12–0.17
  throughout). All the brilliance is local.
- **Palette discipline:** each move has one hue pair (gold and violet, magenta and gold, blue and white), never more
  than about three colours.
- **Bespoke painted art:**
  - a lotus mesh with cel-style outlined petals;
  - ornate gold sigil coins;
  - calligraphic, tapered, fibrous brush strokes;
  - sprouting grass.
- **Story-shaped timing** (the lotus, 50 ms cells): a gold seed (≈100 ms), then a white dome flash with a rainbow
  fringe (≈150 ms), then a magenta light pillar while the lotus blooms (≈0.5 s). After that, a gold ground ring, petals
  drifting and a long calm fade to gold dust. It is long, but it never feels long, because the tail barely moves.
- **Contrast tricks:** a dark halo ring behind the big 4-point flare (negative space); sparse tiny stars and rings;
  anisotropic sparks.
- **One motif across every move:** flowers, gold ornaments, sparkles.

## 2. What Roblox can do (October 2026)

Roblox has no custom shaders. Community "shaders" (Penumbra, RoShader) run on the CPU or are bundles of effects; no
2025–26 release changed particles or added GPU shaders. What exists:

| Need | Native | Workaround | Verdict |
|---|---|---|---|
| Hot core flash, glow | `ParticleEmitter` additive (`LightEmission` 1), crisp core texture | `BloomEffect` intensity pulse for 2 frames | ✔ |
| God-ray spikes, burst | flipbook spike burst; a fan of `Beam`s | — | ✔ |
| Lens-flare cross | `FacingCamera` particle with a crisp cross texture | — | ✔ |
| Anisotropic shards | `VelocityParallel` + `Squash` + a streak texture | — | ✔ |
| Long light streaks, dash | `Trail` or chained `Beam`s with a tiling texture (`Wrap`, `TextureSpeed`) | — | ✔ |
| Lightning fringe | zig-zag `Beam` chains; an electric flipbook | — | ✔ |
| Crescent afterimages | flat particles (`VelocityPerpendicular`) with a crescent flipbook; curved `Beam`s | a crescent `MeshPart` fading by `Transparency` | ✔ |
| Black ink stroke | a `Beam` or flat particle with `LightEmission` 0 (normal blend), black | EasyVFX's *Dark style* | ✔ |
| Emissive trim, glowing weapon | `SurfaceAppearance` emissive mask; `EmissiveStrength` and `EmissiveTint` are scriptable, so trim can pulse | `Neon` parts | ✔ new |
| Rim flash on the hit target | `Highlight` (255 slots) | — | ✔ |
| Dissolve, erosion | no shader | **baked erosion flipbooks** (frame k keeps the noise above k/N) | ✔ baked |
| Colour punch | `ColorCorrectionEffect` for 2–3 frames | `ColorGradingEffect` has only a tonemapper preset | ✔ |
| Radial / motion blur | no | a speed-line `ScreenGui` overlay for 2–3 frames; global `BlurEffect` for 1–2 frames; upgraded radial `UIGradient` (Studio beta, can't ship yet) | ~ fake |
| Chromatic aberration | no | two extra copies of the flash and shard layers, red and cyan, offset a few hundredths of a stud, 2 frames | ~ fake, cheap |
| Heat distortion | no refraction | a `Glass` shell (quality-dependent) | ~ weak |
| Texture panning on meshes | `SurfaceAppearance` isn't scriptable | `Texture` objects (`OffsetStudsU/V` animate) or flipbooks | ~ |
| Vertex offset, true shaders | no | `EditableMesh` / `EditableImage` on the CPU: one image updates per frame, opt-in per game; SE370's Core never requires them | ✗ |

Hard limits to design around:

- **Bloom is global:** pulsing it brightens the whole world for those frames.
- **Fewer particles at low quality:** low graphics quality cuts particle counts, so the core must read with the
  extras gone.
- **No sort control between particle systems** beyond `ZOffset`.
- **A beam's colour changes per segment:** its `Segments` must cover its keypoints.

## 3. Asset pipeline

1. **`tools/texgen`, pure Python** (numpy and Pillow; `tools/texgen/lib.py` is drafted and parked on
   `feat/texture-generator`).
   - **Primitives:**
     - tileable Perlin fBm, ridged and Worley noise;
     - domain warp;
     - signed-distance shapes (star, ring, crescent, needle, polygon);
     - polar wrap;
     - erosion;
     - atlas packing.
   - **Every texture follows the pack convention:** white RGB, shape in alpha.
   - **Checks:**
     - tiled textures match at their edges;
     - flipbook sizes divide by the grid;
     - single sprites fade to zero before the border;
     - power-of-two sizes up to 1024;
     - a dissolve's last frame is empty.
   - **Output:** a contact sheet and flipbook GIFs, so a texture can be judged before any upload.
2. **Library v4,** the textures the references show and we lack:

   | Kind | Textures |
   |---|---|
   | Shapes | crisp core flash, cross flare, god-ray fan, anisotropic shard, ink stroke |
   | Erosion flipbooks (4×4) | dissolving burst, smoke puff (domain-warped), flame tongue loop, shock ring that thins and erodes, slash that erodes from its tail, dust ring |
   | Spritesheets | rock chunks (flat debris instead of plain blocks), embers, bolt variants |
   | Tiled strips | energy streak, fire band, lightning fringe, wind stroke (the last two re-checked for seams) |
   | Source maps (not uploaded) | fBm, ridged, Worley |
   | **Art tier** (from E and G) | calligraphic brush strokes (tapered signed-distance curves with fibrous noise); radial ornaments and sigils (polar repetition, the multibrush idea in code); cel-style petals and shards with an outline stroke; a rainbow-fringe ring (world-space chromatic); element ground sigils (frost, flame, storm); radial floor streaks; a dark halo ring for negative space |

3. **Meshes.** Crescent shells (wide and thin), cone, sphere shell, torus, cylinder, generated offline (Blender script
   or a Python OBJ writer). They fade by `Transparency`, scroll with `Texture` objects, and are tinted white-alpha.
   **Petal and bloom meshes** (G's lotus) come from a generator too: petals as separate `MeshPart`s that rotate open,
   or one skinned mesh with bones, which Roblox animates. These bespoke meshes are where Phát's eye, or a teammate's
   hand, still matters most.
4. **Third-party packs:** references only, never shipped (§7, call 4).
5. **Uploads:** images and meshes through a ledger script like `clips.py`. Every version is a new id, and Phát sees
   the contact sheet before any upload (§7, call 5).

## 4. The effect grammar as rules

What makes the ZZZ hit work becomes checks in `evfx` and a template in the presets:

| Rule | Read from | First value |
|---|---|---|
| Flash length | screen and luminance spike | 1–2 frames at 30 fps (ZZZ: 2 at 60) |
| Burst peak | coverage curve | by frame 4 at 30 fps |
| Tail | last live pixel | ≤ 0.6 s for a hit, ≤ 1.2 s for a finisher |
| White core | the brightest 2% of effect pixels | near white |
| Theme and accent | hue histogram of effect pixels | one theme hue, plus optional complementary flash and black ink |
| Anisotropy | the share of particles that are streaks (stretched by `Squash` and `VelocityParallel`) | most of a hit's particles |
| Reads at distance | far-view coverage and contrast | from the audit's `coverage_far` |
| Doesn't bury the body | `body_buried` | ≤ 0.6 at peak for hits |

`evfx` also gets a **reference envelope**: the ZZZ hit's brightness and coverage curve over time, extracted from Phát's
capture. A preset's own curve is drawn against it, so "feels like ZZZ" becomes a measured shape, not just a word.

## 4a. Particles

Most of an effect is `ParticleEmitter`s, so they get their own grammar.

**Layer roles** (D, E, G). A preset names each emitter's role, and the audit reads them:

| Role | Job | Blend |
|---|---|---|
| Glint | a telegraph on the target or weapon before the hit; a crisp cross flare | additive |
| Core | the white-hot centre; 1–2 frames on a hit | additive |
| Base | the main shape: a flipbook, OneShot | normal, saturated |
| Volume | fullness: the base with a wider spread | normal |
| Dark | depth and value contrast, or an ink stroke or halo | normal, dark |
| Sparks | life and direction: anisotropic shards, embers, petals | additive |

**Rules:**

- Only glints, cores and sparks are additive; body layers use normal blending.
- Shape comes from curves over each particle's life (size, squash, transparency), not from more particles.
- Hits use one big core, a short burst of 8–16 stretched shards with high `Drag` (they explode, then stop), and a slow
  sparse tail.
- **Hit-stop:** the runtime sets `TimeScale` 0 on its emitters while a hit-stop holds. Today they keep moving.
- **Quality:** the core and base must read with sparks and volume culled (low graphics quality).
- **SE370:** its effect rows need a keyed particle layer (rate, size and colour following Eclipse keys), not only a
  runtime `Emit` kind, before the exporter (step 5) can carry these presets.

**evfx gaps to close first** (they block judging the rock spritesheet and the charge-up):

- emitter `Shape`, `ShapeStyle`, `ShapeInOut` and `ShapePartial`;
- the random envelope on keypoints;
- `FlipbookStartRandom`;
- `VelocityInheritance` and `LockedToPart`;
- `TimeScale` and `ZOffset`.

## 4b. Three bars

The loop judges an effect against three tiers, each with checks:

| Tier | Reference | Passes when |
|---|---|---|
| **Refuse** | F | nothing below fires (every anti-pattern check passes) |
| **Good** | E | the grammar rules of §4 pass, and the role and blending rules of §4a hold |
| **Target** | G | the Lotus rubric below, read by the agent from the strip and confirmed by Phát's KEEP |

**Anti-pattern checks** (one planted bad case each in `evfx selftest`):

| Anti-pattern | Check |
|---|---|
| Plain parts as art | `plain_pieces` (exists) |
| Constant-width neon | beams and trails whose width doesn't taper; `Neon` parts used as lines |
| No phases | the phase detector: a 1–2 frame flash, a burst peak by frame 4, a hit's tail at most 0.6 s |
| Hue flood, no white core | palette: the brightest 2% near white; one theme hue plus an accent, at most three hues |
| Buries the body | `body_buried` (exists), capped for hits |
| Blobs instead of shapes | anisotropy: the share of particles that are stretched streaks |
| World swaps | any change to `Lighting` or the sky outside the screen-space roadmap |
| Floating rings | soft: a ground hit leaves a decal or floor streaks |

**The Lotus rubric:**

- **Restraint:** mean screen luminance never jumps; the glow is local.
- **Palette:** one hue pair per move, plus white.
- **Contrast:** the effect stands out against the stage, using negative space (halos, ink).
- **Motif:** one motif across the soul's moves (call 2's accent, taken from the soul bearer).
- **Calm tail:** low motion energy after the burst.

evfx measures what it can (hue count, local contrast, mean luminance, tail motion energy); the agent reads the rest
from the strip.

**Expectation:**

- **Good is reachable:** the loop can reliably hit the Good tier.
- **Target where art can be generated:** strokes, sigils, flares, rings and outlined petals can reach the Target tier.
- **Phát's eye for bespoke meshes:** for those, like the lotus, Phát's eye or a teammate's hand closes the gap.

## 5. Build order (one PR each, each judged by `evfx`)

1. **texgen and library v4,** with the art tier (strokes, sigils, outlined petals, fringe ring, ground sigils). Readback: the contact sheet, tiling and flipbook checks, and before/after strips of three
   presets that switch to v4 textures (slash, impact, ground slam).
2. **The mesh set.** Readback: crescent and cone shells in `evfx` strips, then one Studio capture.
3. **ZZZ-grammar hero set:** rebuild **Hit Impact**, **Ground Slam** and **Crescent Slash** with the four phases
   above: white core, element body, soul accent. Ground Slam's plain rocks become flat rock-chunk spritesheets with a
   dust ring and cracks. Readback: the grammar gates pass, the envelope sits close to the ZZZ curve, and the #8 gates
   these touch now pass (impact-frame flash length, Ground Slam's plain pieces and length).
4. **`evfx` art metrics:**
   - the emitter gaps of §4a, first;
   - the anti-pattern checks and the measurable Lotus rubric of §4b;
   - hue and palette;
   - anisotropy;
   - a phase detector;
   - the reference envelope;
   - the Studio accuracy capture (`TimeScale` 0 freezes);
   - graphics-quality levels.
5. **SE370 adapter:** export presets to `src/content/Effects` rows (vfx-18), shapes as `Emit` kinds, and a cue on one
   SE370 move.
6. **The rest of the library:** each preset rebuilt in grammar order (hits first, then elements, then ambient).

**Roadmap, not now (call 3):** screen-space effects. Fake chromatic split, speed-line overlay, a 1-2 frame blur and
the heavy-hit screen burst of call 1, all behind a "Reduce screen effects" setting.

## 6. Risks

- **Bloom pulses are global** and can wash out the world; keep them to 2 frames and cap the intensity.
- **Phones:** many additive layers at low quality. Every hero effect gets a cost readback with ten copies, and its core
  must read with the extras culled.
- **ZZZ is a reference only:** no frames, textures or exact shapes are copied; the grammar is.
- **Fakes can look cheap.** Screen-space fakes are on the roadmap only (call 3); when they come, they stay opt-in until
  Phát has seen them in Studio.

## 7. Decisions (Phát, 2026-10-23)

1. **Screen-wide moments: your own heavy hits only, on the roadmap.** Your own heavy hits may add a 2-3 frame screen
   burst on your screen only; teammates' hits never touch your screen; finishers keep the full screen moment. This
   amends SE370's vfx-3. Built with the screen-space roadmap (call 3), not now.
2. **Colour: element body, soul accent.**
   - **Core:** always white.
   - **Body and edge:** the gem's element palette, as SE370's vfx-2 already has it.
   - **Accent:** the soul's own colour and motif, taken from its soul bearer's look. It covers afterimages, trails, ink
     strokes and the complementary flash.
   - **Boss souls:** one that carries an element adds that element as a second layer.
3. **Screen-space effects: roadmap.** Refine the skill and ability effects themselves first. The fake RGB split, speed
   lines and blur wait.
4. **Third-party textures: references only.** Packs (Schreibt's database and others) are studied for ideas and never
   shipped. Every texture is ours: generated, or painted by the team.
5. **Uploads: a ledger script like `clips.py`.** It is a dry run by default and sends from the Mac with the keychain
   key. It keeps a ledger of every texture and mesh id and version, since an image can't be overwritten in place. SE370's
   `AGENTS.md` gets an exception for VFX images and meshes, and Phát sees the contact sheet before any upload.
6. **First hero set: Hit Impact, Ground Slam, Crescent Slash.** Crescent Slash is built in EasyVFX now and wired to
   SE370 after the starter sword's reanimation (vfx-5).

## 8. Patterns from earshot

[earshot](https://github.com/Leonxlnx/earshot) gives coding agents ears for sound, the same job evfx does for effects;
Phát uses it on his Mac. What carries over, most valuable first:

| earshot | evfx equivalent | Why |
|---|---|---|
| `match` / `rank`: how well a description fits, as a z-score against a vocabulary, with a strong / plausible / weak verdict | a local image-embedding model (CLIP-style, CPU) scores frames against phrases ("hard white flash", "soft round smoke blob", "thick neon tube") | "matches the brief" as a number; picks the best of a line-up; names anti-patterns |
| `profile` + `critique`: a profile built from admired work, then a scorecard with "fix first" | profiles from G, E and C (flash length, palette, luminance curve, tail motion, coverage); `evfx critique` with fixes at timestamps | limits come from references, not hand-set `rules.json` values |
| `forge`: make in code, improve by listening | texgen recipe or preset → render → score against a reference set → adjust the knobs | the loop runs without a person until KEEP/DROP |
| `sfx` bank as code, rendered by id with knobs (`--dur`, `--apex`, `--pitch`), audited | library v4 as recipes with knobs (size, timing, hue), each audited | variants without new files |
| `kit` with measured sync points | effects measured against the animation's markers (the flash lands on the active frame) | timing to the move |
| `describe`: what it sounds like, in words | what a frame looks like, in words: tags plus the closest alternative readings | an agent can read a strip in text |
| `find`: the best moments in a long recording | the peak moments in a reference capture | builds reference sets from videos automatically |
| `timeline`: a listening transcript | a viewing transcript: per frame, events, phases, peaks, coverage | the effect's story as text |
| `sheet`: an annotated PNG for agents that read images | strips annotated with phases, census curves and the reference envelope | one image carries the numbers |
| `ab` / `compare`: differences in words | `evfx diff` that says what changed ("flash 3 frames longer, palette +1 hue") | before/after without guessing |
| `measure`: objective numbers, no models | the census and gates (exist) | stays the fast, model-free layer |
| `realness`: real recording or code-synthesized | a "reads as procedural / cheap" detector, trained on references against bad examples (F) | catches the generic look |
| `fit`: a recording into a code recipe with knobs | a reference texture or flipbook fitted to a texgen recipe | turns an admired shape into something we can vary |
| calibration: held-out evidence behind every verdict | each score validated on held-out reference and bad clips | the verdicts can be trusted |
| MCP server | `evfx` as an MCP server | agents call it the way they call earshot |

**For SE370's sound:** sounds are still stubs (sound-M4). earshot itself could be the sound side of this pipeline,
paired with evfx: one cue list, both checked against the same animation markers.
