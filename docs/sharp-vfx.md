# Making Roblox VFX sharp (not blurry, not pixelated)

These rules come from testing EasyVFX in Roblox Studio and measuring its texture pack. Each one says what goes wrong, why, and what EasyVFX does about it.

## 1. Use Roblox's own component for each job

Roblox has one effect object for each kind of look ([Effects](https://github.com/Roblox/creator-docs/blob/main/content/en-us/effects/index.md)). Each is drawn by the engine and costs one object. Imitating one with a pile of others costs many objects and still looks worse, because the engine already handles the motion, the fade and the joints. Pick the component first, then build the look on it:

| The look | Use | Not |
|---|---|---|
| Soft mass, glow, smoke, sparks, flashes, decals lying on the ground | `ParticleEmitter` | parts or beams |
| A fixed shape between two points: a column, a band, a ring, an arc, a bolt | `Beam` (curved, textured, tapered in its properties) | a chain of beams where one beam can follow the path |
| A streak behind something that **moves**: a falling drop, a projectile, a dash, a blade | `Trail` on the moving attachments | a chain of beams re-placed every frame |
| Light on the world round the effect | `PointLight` (`SpotLight`, `SurfaceLight` when it has a direction or a face) | a glowing particle on the floor alone |
| A character or object glowing as a whole: forming, dissolving, marked | `Highlight` | particles stuck on its parts |
| The whole screen: bloom, a flash of colour, a blur | post effects (`BloomEffect`, `ColorCorrectionEffect`) | a camera-sized part |

A `Trail`'s length is its attachments' speed times its `Lifetime`, so it is short while the thing is slow and long once it is fast, which is what makes a fall or a throw feel natural. A chain of beams has a fixed length unless it is rebuilt every frame. The arrival's falling drop first used `Projectile`'s 20-beam tail, then one `Trail` (`Tail = "Trail"`; Phát, 2026-10-26: "the 20 beam for trail is bad"). When a look needs more than a handful of one component, check whether another component does it in one.

**A loop that must always show is made of bursts, not a steady `Rate`.** At the lowest graphics quality Roblox
draws no `Rate` emission at all, while `Emit` bursts still draw (SE370's arrival waypoint vanished in a Studio take at
quality Level01 and drew in full at Level21, 2026-10-26). Give such a layer `burst = N` and the preset an `interval`;
the runtime replays a looping preset's bursts every `VFX_Interval`. Keep `Rate` for ambient detail that may thin out
on low-end devices.

**Read both sources before building on a component**, straight from Roblox's repository (no local copy, so it is never stale):

- **The API reference**, for its shape: every property, its type, range and default. It is what the Studio MCP's
  `get_roblox_docs` tool returns (`classes/Trail`, `classes/Beam`, `classes/ParticleEmitter`, `classes/Highlight`, ...),
  generated from [`content/en-us/reference/engine`](https://github.com/Roblox/creator-docs/tree/main/content/en-us/reference/engine).
- **The guide pages**, for the tips and tricks the reference leaves out: how a property looks, what it is good for,
  its limits. They are in [`content/en-us/effects`](https://github.com/Roblox/creator-docs/tree/main/content/en-us/effects)
  (`particle-emitters.md`, `beams.md`, `trails.md`, `light-sources.md`, `highlighting.md`, `index.md`); read one raw at
  `https://raw.githubusercontent.com/Roblox/creator-docs/main/content/en-us/effects/<page>.md`. `get_roblox_docs` cannot
  reach these.



## 2. Get the hard edges from geometry, not from textures

A texture is a fixed grid of pixels. Blow a 256 px particle up to half the screen and every texel becomes a visible block, or a blur. Edges made from **geometry** are different: Beam ribbons, Neon/ForceField parts and meshes are rasterized at screen resolution, so they stay crisp at any size and distance.

- EasyVFX builds rings, slashes, needles, lightning, spirals and projectile trails from curved **Beams**, and flashes and cores from **Neon** parts.
- Textures, when used, carry only *soft* detail (glow falloff, strands, noise). The silhouette comes from the geometry.

## 3. One shape, one beam

The pitfall an agent trips on most (Phát, 2026-10-26, after the fire pit and the wind kit): drawing one
continuous shape out of many beams. Every joint is somewhere it can show a notch, a step, a restarted
texture or a gradient band, and a chain of short straight beams reads as a broken line however well its
joints are matched. Reach for one beam first:

- **One curved beam covers an arc of up to about 200 degrees.** A cubic Bezier stays within about 2% of a
  circle over a semicircle: set `CurveSize0` and `CurveSize1` to `4/3 · tan(arc / 4) · radius` along
  each end's tangent (`Band`).
- **One beam bends into an S** with both curve sizes along the same axis: a ribbon winding up a pillar
  (a drop's beam layer, `curve0`, `curve1`).
- **The texture does the flowing.** A still beam with its texture scrolling (`TextureSpeed`) reads as
  moving wind or energy, with no joints and nothing to update each frame.
- **Taper and fade in the beam's properties** (`Width0`, `Width1`, `Transparency`), never in a second
  beam. A Beam has a width at each end only, so a band pinched at both ends needs either a fade at
  both ends of one beam or two beams; prefer the fade.
- **Volume is several whole beams overlapping**, each a little off in radius, height and speed, not one
  shape cut into pieces.

A moving tail is never a chain: it is a `Trail` (rule 1). Chain beams only when one cannot follow a still path at all (a helix of several turns, a zig-zag bolt, a full circle as arcs), and
then share their attachments as in rule 4. Count the beams per shape before building: more than one
for one continuous stroke needs a reason.

## 4. Chained beams must share camera-facing attachments (no `FaceCamera`)

![FaceCamera vs shared frames](beam-seams.png)

*Real Studio render. Left: 12 beams with `FaceCamera = true`; every joint shows a notch. Right: the same helix with `FaceCamera = false` and attachments oriented consistently: one seamless ribbon.*

With `FaceCamera = true`, each Beam turns towards the camera **on its own**, so two beams meeting at an attachment have different width directions at the joint. That leaves a notch or step at every joint, the "jagged" look on curved slashes and rings.

What EasyVFX does instead (`ribbonFrame` in the runtime):
- `FaceCamera = false` on every beam.
- Each frame, every attachment gets X = the path tangent (the axis `CurveSize` bends along) and Y = `tangent × (camera − point)`. A beam's width follows its attachments' Y axes.
- Neighbouring beams share the attachment, so they meet exactly, and the ribbon still faces the camera.
- For zig-zag lightning the tangent at a corner is the average of the two segments (a **miter joint**), so the bolt bends cleanly instead of overlapping.

## 5. One gradient across a chain, not one per segment

`ColorSequence.new(a, b)` on every segment restarts the gradient at each joint, which shows as color bands. Give each segment its slice of the overall gradient: `a:Lerp(b, f0)` to `a:Lerp(b, f1)`. The same goes for `Transparency` and `Width`: compute them from the position along the whole chain.

## 6. Clean texture edges (edge padding)

Renderers (Blender Cycles included) write **black RGB into fully transparent pixels**. Roblox filters textures bilinearly and builds mipmaps from straight alpha, so that black bleeds into every soft edge. The result is a grey or dark rim, and a dirty, crunchy look once the effect is a bit away from the camera.

The EasyVFX pack measured 0.01–0.22 RGB in its transparent areas. `tools/fix_texture_edges.py` pushes the visible color outwards (push-pull fill) without touching alpha, and `blender/make_vfx_pack.py` now writes white RGB everywhere, because every pack texture is white with the shape in alpha. The pack was re-rendered that way: the PNGs went from 3.5 MB to 1.4 MB and the FBX from 3.7 MB to 2.0 MB.

```bash
python tools/fix_texture_edges.py pack/textures/*.png
```

## 7. Spend texture resolution where it shows

- Roblox images are at most **1024 × 1024**, and lower graphics settings load smaller mips.
- A 4×4 flipbook on a 1024 sheet leaves **256 px per frame**. That is fine for small or fast bursts (impacts, sparks), but blurry on a big slow effect. Use `Grid2x2` (512 px frames) or a single texture for anything that fills the screen.
- Strip textures for beams and trails only need detail across their width. A 1024 × 64 strip stretched along a beam stays crisp, because filtering along a smooth gradient is invisible.
- Don't stretch a small soft particle to be huge. Make a bigger texture, or use an Orb part.

## 8. Glow without mush

- `LightEmission = 1`, `LightInfluence = 0` for additive, self-lit glow.
- Use a white core plus a colored rim (two beams) instead of one flat color. The bright core reads as "hot" and keeps the edge defined.
- `Brightness > 1` on beams and particles, together with a `Bloom` effect in Lighting, gives an anime-style glow without blurry textures. The plugin has a button that adds Bloom.
- Use `ZOffset` to keep cores in front of rims so they don't flicker when they sort.

## 9. Motion sells sharpness

- Fast in, slow out (`Out` easing). A white flash first, then the main color, then gone within about 0.35 s. Long, slow fades make effects look soft.
- Sparks: square texture, `VelocityParallel` orientation and negative `Squash`, so they are needles, not dots.
- A 2–4 frame **impact frame** (`Impact` shape) and a short **camera shake** (`Shake` shape) make a hit read as crisp, even when the particles themselves are simple.

## Checklist

- [ ] Each look is on Roblox's own component for it: emitters for mass, beams for still shapes, trails for anything that moves, lights, highlights and post effects for the rest.
- [ ] Silhouettes come from Beams, Neon or meshes; textures only add soft detail.
- [ ] One continuous shape is one beam (curved, textured, tapered in its properties); a chain only where one beam can't follow the path.
- [ ] Chained beams use shared, camera-facing attachments (no `FaceCamera`).
- [ ] Gradients run across the whole chain, not per segment.
- [ ] Textures are edge-padded (`tools/fix_texture_edges.py`).
- [ ] Flipbook frame size matches how large the effect gets on screen.
- [ ] Additive glow with a white core; Bloom in Lighting.
- [ ] Fast timing; impact frame and shake on big hits.
