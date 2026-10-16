# How VFX Studio works (and what EasyVFX took from it)

Notes from taking apart **VFX Studio v3.9.3** (Creator Store plugin by XxOmqxXNerd), installed locally, to learn how a popular Roblox VFX tool is built. The plugin file was unpacked with Lune (`roblox.deserializeModel`) and read; **no code was copied** into EasyVFX. Every feature below was re-implemented from scratch in EasyVFX's own runtime and style.

## What is inside

| Part | Size | Notes |
|---|---|---|
| Plugin UI and logic (`Modules/Core`, `Panels`, `UI`, `Shared`) | ~120 modules, ~35k lines | Plain, readable Luau, not obfuscated |
| Bundled libraries (`Defaults/Scripts`) | ~300 modules | Knit, Promise, TopbarPlus, Cmdr, SmartBone, Iris, VoxBreaker, a Bezier module |
| Mesh library (`Defaults/Meshes`) | ~570 MeshParts | Shockwaves (`Shock`, `InwardShockwave`), spirals, wind, whirls, spheres, rocks, chains |
| GUI | ~3,500 instances | Dock panel with floating sub-panels |

It does not ship particle presets inside the plugin: effects come from the user's own work, a saved library (`userVFXData`, `savedVFX`) and the mesh library.

## The effect model

VFX Studio does not have its own effect format. It decorates ordinary instances with **attributes** and plays them:

1. **Emit convention.** On every `ParticleEmitter`, `Beam`, `Trail` and `Sound` inside the selection, it reads:
   - `EmitDelay`: wait before starting.
   - `EmitDuration`: for emitters, `Enabled` for that long. For beams and trails, a clone is enabled for that long.
   - `EmitCount`: for emitters, `:Emit(n)`.

   EasyVFX already used the same convention, so effects from either tool play in the other.
2. **Property sequences.** Any attribute named `<Property>Sequence` that holds a `NumberSequence` animates that property over `EmitDuration`, or else the emitter lifetime. Examples: `TransparencySequence` on a part or beam, `Width0Sequence`, or `ScaleSequence` for `Size` / `Model:ScaleTo`. The envelope adds randomness, and the property is put back afterwards. This is the main way it animates meshes and parts without code.
3. **Tween steps** (`TweenData` Configuration, JSON or attributes). These move the object along a path, then can fire an "on completion" action. The path can be:
   - Linear
   - Arc: a quadratic Bezier with height, skew and random offset
   - Randomized: jittered waypoints
   - Manual: user-drawn Bezier points
4. **Camera data** (`CameraData` Configuration):
   - *Shake* steps use the EZ Camera Shaker model: magnitude, roughness, fade in/out, and position/rotation influence.
   - *Impact frames* are `ColorCorrectionEffect` templates (brightness, contrast, saturation, tint, delay, duration). They are cloned into `Lighting` for a few frames.
5. **Global edit sliders** work on any selected effect, not just its own:
   - *Retime:* `Lifetime`/`Rate` are divided by the multiplier. `Speed`, `Drag`, `FlipbookFramerate`, `RotSpeed` and `TextureSpeed` are multiplied. `Acceleration` is multiplied twice (squared). `EmitDelay` is rescaled.
   - *Scale:* `Size` keypoints, `Speed`, `Acceleration`, beam `Width0/1` and `CurveSize0/1`.
   - *Color:* an HSL shift applied to every `ColorSequence`.
6. **Code generator.** It writes a ready-to-paste script that triggers the selected effect with the emit convention, for use in tools and animation events.

## What EasyVFX added because of it

| VFX Studio idea | EasyVFX version |
|---|---|
| `<Property>Sequence` attributes | Supported by the runtime on any instance inside a `VFX_` part. Values restore afterwards, and overlapping plays keep the true original (stored in `VFXBase_*` attributes). |
| Camera shake steps | `Shake` shape: smooth noise on the camera after the camera scripts, distance falloff, fade in/out. Client only, never the Studio editor camera. |
| Impact frames | `Impact` shape with three styles: `Flash` (tinted), `Mono` (black and white punch), `Invert` (negative frame, `Contrast = -2`). Parented to the camera so it is local, and never stacked. |
| Arc tween paths | `Projectile` shape: a head flying along a quadratic Bezier arc with a tapered, seamless trail, plus layers that fire at the hit point. |
| Spiral and whirl meshes | `Spiral` shape: helix strands built from beams. No mesh upload needed, and sharp at any distance. |

New presets built from them: **Fireball**, **Impact Frame**, **Tornado** and **Charge Up**. Ground Slam, Explosion and Lightning Strike gained camera shake.

## What EasyVFX does differently on purpose

- **Client-side runtime.** VFX Studio plays effects inside Studio and generates a server-or-client script. EasyVFX installs one runtime that always renders on clients, with one RemoteEvent from the server.
- **One animation loop.** VFX Studio uses one `Heartbeat` connection per tweened property. EasyVFX drives every running piece from a single loop.
- **Geometry instead of a mesh library.** The meshes need the plugin's own uploaded assets. EasyVFX builds rings, slashes, spirals and trails from Beams, so nothing has to be uploaded.
