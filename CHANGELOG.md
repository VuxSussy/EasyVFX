# Changelog

All notable changes to EasyVFX are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
