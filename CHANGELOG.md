# Changelog

All notable changes to EasyVFX are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### The VFX grammar
- `evfx grammar` reads every layer of a played effect as a role (core, glint, glow, base, volume, dark, shards, dust,
  debris, ground) plus its numbers: count, delay, lifetime and its spread, drag stop, reach, spread, size, growth,
  fade, opacity, blend and z. Sizes are in character heights. It lists what falls outside the role's ranges
  (`tools/evfx/grammar.json`, docs/vfx-grammar.md).
- The ranges come from the references (Lotus, Frigid Rush, a new Genshin study in `docs/refs/genshin-vfx.md`) and
  from `evfx study`, which reads the emitter numbers of 50 openly published Roblox effects. Only numbers are read; the
  dataset stays in `.cache`.

### The beat judge
- `evfx beats` judges an effect beat by beat against a beat sheet (`tools/evfx/sheets`) and prints what to fix first,
  with frames. It checks the sheet's beats, flashes, palettes and depths and compares each beat with a reference
  beat. When the sheet names an SE370 move, it also times the beats to that move by SE370's motion bible: the hit
  frame, a quiet or telling wind-up, the burst in the follow-through, the tail against the recovery, and the style's
  keywords. `--png` draws it.
- `evfx ref` cuts Lotus and Frigid Rush into beats and measures their shape. Only the cut and the numbers are
  committed (`tools/evfx/references`).
- Timelines can be exported at 60 fps (`EVFX_FPS=60`); `phases` rows carry per-frame hue and motion.
- Sheets for `slash_v4`, `impact_v4` and `ground_slam_v4` (drafts, on Chop, Barge and Cleave) and for the
  `bloom_strike` study.

### Bloom Strike: Lotus's layering on generated art
- `docs/refs/dissection-lotus-frigid.md` steps through Lotus and Frigid Rush at 60 fps: beats, frames, shapes,
  palettes. `docs/refs/lotus-layers.md` maps every Lotus beat's layers back to front, each with a role, blend and
  facing, and finds the five depths each beat stacks: ground, back volume, main shape, line work, dust.
- `bloom_strike` rebuilds that layering on generated art in a 4 s move. Emitters are named by role and grouped by
  beat, with two 2-frame flashes:
  - wrap: crescent shells over violet smoke;
  - flare: 8-point star over a dark halo, then a cross;
  - sphere shell, then a flower sigil with orbit rings and bokeh;
  - gold seed, then the dome flash and a rainbow ring;
  - a pillar and a blooming lotus-crown mesh over a gold ground ring;
  - a calm gold swirl, petals and grass.

  It is hidden in the plugin until library v4 is uploaded.
- New texgen recipes: `shape/star8`, `shape/hollow_ring`, `shape/bokeh`, `art/flower_sigil`, `art/brush_ring`,
  `art/petal_single`, `strip/pillar_streaks`, `strip/dome_glow`, `sheet/grass`. New meshes: `mesh/dome` and
  `mesh/lotus`, a petal crown dressed by one petal texture.
- Found on the way: a hit-stop pauses shells but not particle emit delays, so a multi-beat preset skips it.
  Layers in one group share an attachment, placed by the group's first layer.

### Shells on SurfaceAppearance
- In Studio, a MeshPart's `TextureID` alpha doesn't cut it out, and only a plugin may set a `SurfaceAppearance`'s
  colour map. The `shell` layer now bakes one frame MeshPart per texture frame under a hidden lead, each with its own
  `SurfaceAppearance`: alpha cut out, emissive mask. The runtime shows one frame at a time and drives tint, emissive
  and fade. `slash_v4` uses 8 frames per shell.
- `meshgen studio` writes a chunked Luau preview that builds the shells with `EditableMesh` and `EditableImage`, so
  they can be seen in Studio without an upload. `docs/meshgen.md` has the Studio shots.
- evfx draws an emissive shell frame as glowing, and doesn't count it as a plain block.
- The halftone on Studio previews of the slash shells is aliasing from `EditableImage`s, which have no mipmaps, not
  the alpha (an A/B is in `docs/meshgen.md`). `seq/slash_ribbon` gains `alpha` and `fibres` knobs; texgen checks accept
  `"rgb": "luma"` (grey detail for mesh frames).
- `Builder.previewContent` lets a Studio preview hand the builder `EditableMesh` and `EditableImage` content for assets
  not uploaded yet (empty in the plugin and in games). `meshgen studio --play` writes the data to bake `slash_v4` with
  the real builder and play it with the runtime in an edit Studio.

### The mesh set (`tools/meshgen`)
- `tools/meshgen` writes six shells as OBJ in `pack/meshes`, not uploaded: crescent (wide and thin), cone, sphere,
  torus and cylinder. Each is a recipe with knobs, and `check` and `selftest` run in `tools/check.sh`.
  `docs/meshgen.md` explains it.
- A `shell` layer builds a hidden template MeshPart through `AssetService:CreateMeshPartAsync`. The runtime clones it,
  grows, turns and fades it, and swaps its `TextureID` through a sequence of frames.
- texgen gains the `sequence` kind (frames saved as separate images, for meshes) and `seq/slash_ribbon`, 16 frames of
  a slash that erodes from its tail.
- `slash_v4` now sweeps on two crescent shells instead of flat particles; `ground_slam_v4` throws up a cone shell.
- evfx draws pack meshes with their textures (a small rasterizer with perspective-correct UVs).

### Hero set, first pass (v4)
- `impact_v4`, `ground_slam_v4` and `slash_v4` rebuild Hit Impact, Ground Slam and Crescent Slash on library v4 in
  Zenless Zone Zero's grammar: a 2-frame white core with a cross flare, god rays and a dark halo; a burst that peaks by
  frame 4; shards with high drag and a two-way line burst; an ink accent; a few slow embers. Emitters are named by role
  and grouped by beat. The originals are unchanged, so both versions can be compared side by side.
- Ground Slam v4 has no plain blocks and lasts 0.57 s instead of 3.23 s, and both of the original's failing gates
  pass. The three v4 presets use no beams (56, 88 and 68 before).
- A preset's `needs` names a texture it can't do without; the plugin hides the preset until that texture has an
  uploaded ID, so the hero set stays out of the library until library v4 is uploaded.
- `evfx phases` reads flash, burst, tail, white core, hues and body coverage frame by frame.
- `flip/shock_ring`'s trail is thinner, so a flat ring reads hollow from early on.

### Texture generator and library v4 (`tools/texgen`)
- `tools/texgen` draws VFX textures in Python (numpy and Pillow, no Blender): `list`, `build`, `sheet`, `gif`, `check`
  and `selftest`. Each texture is a recipe in `tools/texgen/bank.json`, rendered by id with knobs (size, seed, timing,
  hue). `docs/texgen.md` explains it.
- Library v4, 31 textures in `pack/generated` (not uploaded): shapes (core flash, cross flare, god-ray fan, shard,
  ink stroke), 4x4 erosion flipbooks (burst, smoke, flame loop, shock ring, slash eroding from its tail, dust ring),
  spritesheets (rock chunks, embers, bolts), tiled strips (energy, fire, lightning, wind), the art tier (brush
  strokes, two sigils, cel petals and shards, a rainbow-fringe ring, frost, flame and storm ground sigils, floor
  streaks, a dark halo) and three source noise maps.
- `tools/check.sh` and CI run `texgen selftest` and `texgen check --fresh`.
- `evfx` reads `pack/generated` after `pack/textures`, so presets can be judged on v4 textures before upload.
- `docs/plan-real-vfx.md` gains reference H (Ampro's slash and hit) and its particle rules: emitters named by role and
  grouped by beat, emit by count, keypoint envelopes, the two-way line burst, the flat slash, an "Emit and preview"
  button for Studio.

### Headless agentic loop (`tools/evfx`)
- `tests/timeline.luau` records every frame of one play under Lune (beams, pieces, lights, screen effects, FOV,
  streaming emitters, bursts). The harness gains an opt-in lockstep mode (`Harness.lockstep`, `Harness.tick`,
  `Harness.onFrame`, a virtual `os.clock`): every waiting coroutine advances one frame per tick, so a play is
  byte-identical from run to run. Without it, each coroutine's `task.wait` advanced the shared clock, so effects
  measured about twice their real length. The existing tests don't use it and are unchanged.
- `tools/evfx` (numpy and Pillow, no Blender): `strip`, `gif`, `lineup`, `sheet`, `diff` (with `preset@ref`), `export`,
  `audit` and `selftest`. Particles are re-simulated from their emitter settings with a fixed seed per particle.
- The audit's gates (budget, ends clean, flash length and rate, plain blocks) read `tools/evfx/rules.json`;
  `tools/evfx/baseline.json` records today's results, and `tools/check.sh` and CI fail if a gate gets worse.
  12 of 45 presets fail a gate today (impact-frame flashes over 3 frames, chained-beam counts over 96, plain rocks).
- `tools/render_snapshot.py` is removed: it no longer read the snapshot's format. `docs/agentic-loop.md` shows the loop.

### Rough and missing-HD effects fixed
- Slashes keep their sharp `Slash` blade (hot edge, eroding tail) in HD as well. Before, HD replaced it with soft particle crescents. HD now adds v3 on top:
  - star twinkles thrown off the blade;
  - a hit spark (`hit_star` + `flip_hitspark`);
  - weight (hit-stop, FOV punch, kick).
  - This applies to Crescent Slash, Slash Flurry, Shadow Slash and Lightning Slash. Lightning Slash also gets the electric flipbook.
- `Whirl` no longer stretches one textured beam over a long arc, which twisted and showed blunt white blocks. Each stroke is a smooth, comet-tapered chain, and the new `Strands` attribute (1-4) turns it into a bundle of thin lines.
- Wind Vortex was rebuilt with two strand layers, flung grit, a soft core glow, a ground ring and a dust ring. The glass ball and black squares are gone.
- Laser has an HD body with energy pulses running down it, a muzzle flare and a burning hit point.
- Weapon Trail has an HD fibrous slash streak, a white-hot tip trail and glints along the blade.
- Beams and trails accept a pack texture (`packTexture`, `textureMode`, `textureLength`, `textureSpeed`). Runtime version 11.

### Weight and sharper hits
- New runtime tools:
  - `HitStop` shape and `EasyVFX.HitStop(seconds)`: effects hold their frame; tracks registered with `EasyVFX.TrackHitStop` slow down.
  - `Punch` shape: FOV punch.
  - `Shake` with `Kick = true`: full strength on the first frame, fast decay.
  - `Ease = "Circ"`.
- An impact kit (hit spark, hard ring, hit-stop, punch, kick) on 11 hit presets.
- New Create blocks: Hit spark, Hit-stop, Camera punch. Camera shake is now a kick, and Impact frame has speed lines.
- v3 Blender textures: `hit_star`, `flip_hitspark`, `ring_hard`, `speed_lines`, `stroke_wind`, `arc_electric`.
  - With a texture, `Streak` and `Crackle` draw each stroke as one textured beam.
  - All six are uploaded and built in (`DefaultAssets.luau`), so they are on with HD.
- `docs/impact.md` covers the research and the tools. Runtime version 10 (includes the relocation fix below).


### Library organized by purpose
- Categories are now about what an effect is for: Slashes, Impacts & Explosions, Projectiles/Beams/Dashes, Auras & Buffs, Circles & Portals, Elements, Environment, My Effects.
- **All** shows one titled section per category, with its count.
- The look is a separate filter: All styles or Dark Fantasy. Dark fantasy presets carry `style = "dark"`.

### Effects inspired by reference clips
- New shapes:
  - `Whirl`: a spinning disc of tapered brush strokes.
  - `Streak`: a dash line that wipes in and erodes, with an optional dark afterimage.
  - `Crackle`: flickering electric zig-zags along an arc.
- New presets: Lightning Slash, Flash Step, Wind Vortex.


### HD (v2) by default
- The plugin now uses the uploaded HD pack (13 public image IDs, `Shared/DefaultAssets.luau`) out of the box. Before, every effect stayed in basic quality (v1) until you imported the pack or pasted IDs.
- Turning HD off is remembered (`"off"`), and a new **Turn on HD (built-in pack)** button brings it back. Scan pack and Paste IDs still work for your own uploads.
- In HD, soft smoke and blast puffs become the pack's 4x4 flipbooks (`flip_smoke`, `flip_impact`), so Smoke, Fog, Fire, Explosion and the dark fantasy smoke are HD too.
- Existing effects in a place keep the quality they were built with; **Apply to all effects** in the HD card upgrades them.
### Fixed
- Playing an effect at a new CFrame now moves and rotates child mesh templates with the root. Temporary copied parts are anchored and do not collide, touch or block raycasts. Source effects stay unchanged.

### Eclipse Animator: vibe → edit → asset
- `EasyVFX.BindAnimation(track, character)` plays effects at animation markers:
  - `EasyVFX` markers carry an effect name (with an optional body part, offset and rotation).
  - `EclipseVFX` markers are Eclipse Animator's own; when they point at an EasyVFX effect, the whole effect plays, including shapes, shakes and impact frames.
  - `EasyVFX.PlayMarker` and `EasyVFX.ParseMarker` are available on their own.
- `EclipseBridge` writes Eclipse Animator's own event-track format (`EclipseEvents`, version 8) plus the markers Eclipse exports. AI-made cues therefore open, and can be edited, in Eclipse.
  - Checked against Eclipse's code: its `Events.load` reads the cues back, and its `Events.export` writes the same markers.
- While Studio is in edit mode, the plugin exposes `ServerStorage.EasyVFX_Authoring` (Builder, Presets, Custom, EclipseBridge, Runtime) for AI agents and command-bar scripts. It is never saved with the place.
- `docs/eclipse-animator.md`: the flow, the format and an agent recipe. Runtime version 8.


### Sharper slashes
- The `Slash` shape was rebuilt as a real blade:
  - **Shape:** the outer edge is one clean arc, and the width grows inwards to peak near the head and end in a needle tip, with a long thin tail. It used to be a symmetric "banana" band.
  - **Color:** three tones across the blade (deep shade on the inner edge, main-color body, white-hot outer edge) instead of a flat band with a white stripe in the middle.
  - **Timing:** a fast wipe-in, then the tail erodes towards the head, so the tips stay sharp. 12 segments cover only the visible part of the arc.
- Wider default slash widths (Crescent Slash 2, Slash Flurry 1.6, Shadow Slash 2.6). Runtime version 7. See `docs/slash-before-after.png`.


### Dark fantasy
- New **Dark Fantasy** category with 8 presets: Shadow Slash, Soul Flame, Blood Burst, Void Rift, Cursed Sigil, Necrotic Aura, Soul Release, Ash & Embers.
- Dark bodies with bright edges: shapes accept `Glow = 0` (unlit, opaque) together with `CoreGlow` and a `core` color for the thin additive core. A new `"x"` (void) color token gives a near-black tinted by the second color.
- `docs/dark-fantasy-vfx.md`: what Souls, Elden Ring, Diablo IV, Hollow Knight and Blasphemous do, the rules the presets follow, and where to find VFX material legally.

### Make your own effects
- New **Create** tab: build effects from 16 blocks, each with a color, a dark style, delay, size and amount. Save them to **My Effects**, edit, delete, and share or import them with `EVFX1:` codes, which are validated and clamped.
- Custom effects are ordinary presets once registered, so the library, Customize tab, triggers and favorites all work with them. Each placed effect stores its definition (`VFX_CustomDef`) and is re-learned in other places.


### New ways to make effects
- `Spiral` shape: twisting helix strands made of beams (tornadoes, charge-ups, vortexes).
- `Projectile` shape: a glowing head flying along an arc with a tapered trail; pair it with hit layers.
- `Shake` shape: camera shake with fade in/out and distance falloff. Client only; never moves the Studio editor camera.
- `Impact` shape: anime impact frames (`Flash`, `Mono`, `Invert`), local to each client and never stacked.
- `<Property>Sequence` attributes: any instance inside an effect can animate a numeric property (or `Scale`) with a NumberSequence. This is the same convention VFX Studio uses, so its effects play in EasyVFX.
- New presets: Fireball, Impact Frame, Tornado, Charge Up. Ground Slam, Explosion and Lightning Strike now shake the camera.

### Sharper effects
- Chained beams no longer use `FaceCamera`. The runtime turns their shared attachments towards the camera every frame, which removes the notch at every joint of slashes, rings, needles, lightning (now with mitered corners), spirals and trails.
- Slash and projectile gradients run across the whole ribbon instead of restarting on every segment.
- Pack textures are edge-padded: no more black RGB under transparent pixels bleeding into soft edges (`tools/fix_texture_edges.py`; the Blender script now writes clean textures). The whole pack was re-rendered with Blender 5.2: the PNGs went from 3.5 MB to 1.4 MB and `EasyVFX_Pack.fbx` from 3.7 MB to 2.0 MB, with the same object names.

### Fixes
- The template copies of `EasyVFXServer` / `EasyVFXClient` inside the plugin ran during playtests despite `Enabled = false`. They started the runtime a second time on clients and errored on the server. They now do nothing while inside the plugin.

### Docs
- `docs/sharp-vfx.md`: rules for crisp, non-pixelated Roblox VFX, with Studio screenshots.
- `docs/vfx-studio-analysis.md`: how the VFX Studio plugin works and what EasyVFX re-implemented.

## [1.0.0] - 2026-10-16

First public release.

### Plugin
- 30 no-code effects in five categories (Combat, Magic, Elements, World, Light), built from crisp procedural geometry: Bezier beam rings, crescent slashes, needle lines, lightning bolts, neon orbs, crater and debris rocks.
- Dock panel in English (default) and Vietnamese, following Studio's light/dark theme: library with search and categories, live sliders, color swatches, favorites, undo for every action and a 3-step guide.
- Triggers: always on, repeat, on touch, on click, on key E (ProximityPrompt) and from a script.

### HD quality
- Optional HD tier using a texture pack rendered in Blender (`pack/EasyVFX_Pack.fbx`): fibrous slash, dissolve/impact/smoke/electric flipbooks, sharp sparks, noisy shockwave ring and UV-mapped slash meshes.
- HD card to scan an imported pack or paste image IDs; IDs are remembered across places.
- 8 presets get dedicated HD layers; the rest swap soft built-in textures for sharp ones.

### Runtime
- Effects play on each client; the server only sends one RemoteEvent per trigger.
- Automatic quality scaling at low graphics settings, one shared animation loop, temporary pieces kept out of saves and raycasts.
- Compatible with the community `EmitCount` / `EmitDelay` / `EmitDuration` attributes.
- Scripting API: `EasyVFX.Play`, `EasyVFX.SetEnabled`.

### Development
- MIT license.
- Toolchain pinned in `rokit.toml`; GitHub Actions CI builds the plugin, runs a strict type check and the Lune test suites (1229 builder/runtime checks, 857 UI checks) on every push and pull request.
- Tagging `v*` publishes a GitHub release with `EasyVFX.rbxmx` and `EasyVFX_Pack.fbx`.
- `tools/check.sh` now fails when the type check reports errors (it previously passed regardless).
