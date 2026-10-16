# Changelog

All notable changes to EasyVFX are listed here. Versions follow [Semantic Versioning](https://semver.org/).

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
