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

3. **Meshes.** Crescent shells (wide and thin), cone, sphere shell, torus, cylinder, generated offline (Blender script
   or a Python OBJ writer). They fade by `Transparency`, scroll with `Texture` objects, and are tinted white-alpha.
4. **Third-party packs** (Schreibt's database): open, see §7.
5. **Uploads:** images and meshes through a ledger like `clips.py` (create once, keep the id, record versions). Open,
   see §7.

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

## 5. Build order (one PR each, each judged by `evfx`)

1. **texgen and library v4.** Readback: the contact sheet, tiling and flipbook checks, and before/after strips of three
   presets that switch to v4 textures (slash, impact, ground slam).
2. **The mesh set.** Readback: crescent and cone shells in `evfx` strips, then one Studio capture.
3. **ZZZ-grammar hero set:** rebuild **Hit Impact**, **Ground Slam** and **Crescent Slash** with the four phases
   above: white core, element body, soul accent. Ground Slam's plain rocks become flat rock-chunk spritesheets with a
   dust ring and cracks. Readback: the grammar gates pass, the envelope sits close to the ZZZ curve, and the #8 gates
   these touch now pass (impact-frame flash length, Ground Slam's plain pieces and length).
4. **`evfx` art metrics:**
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
