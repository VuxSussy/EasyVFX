# Dissection: Lotus and Frigid Rush, frame by frame

Two references from [the plan](../plan-real-vfx.md) §1, downloaded and stepped through at 60 fps (2026-10-23):

- **G:** [Plebarae, *Roblox VFX: Lotus*](https://youtu.be/0aWTYOV8VtA): 35 s, 1080p60, a dark stage, one move played three
  times from different angles. The **target** tier.
- **E:** [Hazaze, *Frigid Rush*](https://youtu.be/2fwT64lFtao): 20 s, 1080p60, a daylight stage, one move played twice.
  The **good** tier.

Their art is theirs: these notes take timing, structure and shape language, never frames or textures (call 4). The
clips and the contact sheets stay in `.cache/refs`, untracked.

Frame numbers are at 60 fps ("f190" is 3.167 s). "2 frames" means 33 ms.

## Lotus (pass 1, 0–10 s)

The move is a chain of seven beats. Each beat has a single job and hands off to the next within one or two frames. The
stage stays dark: the mean screen brightness never goes above 0.24, and the brightest beat lights only 5.5% of the
pixels.

| Beat | Frames | Length | What is on screen | Colour |
|---|---|---|---|---|
| 1. Water swirl | f0–60 | 1.0 s | a flat blue swirl on the ground around the character, thin bright arcs, sparkles | azure, blue, a violet edge |
| 2. Gold ornaments | f75–160 | 1.4 s | gold sigil coins on gold strokes flung around the body, small violet orbs | gold (95%) |
| 3. Slash wrap | f162–176 | 0.23 s | two or three thick crescents wrap the character: a white core, a pink body, a violet edge, a fibrous brush texture | white, pink, violet |
| 4. Dash streak | f176–188 | 0.20 s | a long comet flies off: a white-pink head, a body of blue and violet fibrous streaks, sparks peeling off | blue, violet, white head |
| 5. **Flare** | **f190–192** | **2 frames** | a huge 8-point star: long horizontal and vertical spikes, four shorter diagonals, a violet bloom, and a **dark halo disc behind it** (negative space) | white, violet |
| 6. Collapse, then dome | f194–222 | 0.47 s | a 1-frame 4-point cross; it collapses to a small pink spark with a thin trail (f196–202); a soft pink-white sphere swells (f204–214) and turns into a blue sphere crackling with electric fibres (f216–222) | pink, white, then blue |
| 7. Sigil bloom | f224–240+ | 0.3 s, fading | the sphere resolves into a violet six- to eight-petal flower sigil of thin rays, ringed by small orbit dots | violet, azure |
| 8. Gold seed | f270–341 | 1.2 s | a gold orb in a gold ring, gold calligraphic strokes swirling into it, gold dust falling; it shrinks to a small gold seed on the ground | gold |
| 9. **Dome flash** | **f343–345** | **2 frames** | a blown-out white hemisphere on the ground where the seed was; a thin ray drops onto the seed one frame before (f341) | white |
| 10. Rainbow and pillar | f347–365 | 0.3 s | the dome fades with a **rainbow fringe on its rim**; a magenta light pillar rises; a gold ring lights the ground | magenta, gold, rainbow |
| 11. Lotus | f355–480 | about 2 s | a cel-outlined pink lotus (a mesh) opens upward over about 0.4 s inside the pillar; pink petals drift off; grass sprouts around the base | magenta (56%), gold (35%) |
| 12. Calm tail | f480–600 | about 2 s | the lotus fades; a gold ground glow and gold dust and petals linger, barely moving | gold (85%) |

What makes it read as "target":

- **The two flashes last exactly 2 frames each** (f190–192 and f343–345). Everything else is coloured.
- **Each beat swaps the palette:** blue, then gold, then pink and violet, then gold, then magenta and gold. At most three
  hues ever share the screen.
- **Negative space is on purpose:** a dark halo behind the flare, a dark stage, and every element small and sharp.
- **Shapes change their nature beat to beat:** crescents, then a comet, a star, a sphere, a flower sigil, a seed, a dome,
  a pillar, a flower mesh. No two beats share a shape.
- **The tail is long but calm:** about 4 s of lotus and gold dust that barely moves.
- **Mesh art carries the hero moment:** a cel-outlined lotus mesh, not particles.

## Frigid Rush (pass 1, 1.5–9.5 s)

A daylight stage, so its effects are white and cyan over a bright scene. The structure is a dash, then a quiet stretch,
then one big hit.

| Beat | Frames | Length | What is on screen |
|---|---|---|---|
| 1. Wind-up | f90–120 | 0.5 s | thin white curved wind arcs circle the character |
| 2. Needle glints | f125–131 | 2–3 frames each | single thin white needle streaks on the contact line, one after another |
| 3. Contact burst | f133–139 | 0.1 s | a cyan-white burst at the contact; a spherical shell with a **rainbow (chromatic) fringe**; a long cyan beam with a white core tapering off across the screen; white droplets |
| 4. Wind shell | f139–155 | 0.27 s | the fringed shell holds, with cyan wispy crescents swirling around it; 4-point star sparkles |
| 5. Hanging crescents | f155–171 | 0.28 s | thin, hard white crescents hang around the pair; then a **reticle glint** (a ring with a cross) on the target |
| 6. Quiet | f180–400 | 3.7 s | small glints and a ground-ring blip (f240–255); the target is launched; almost nothing on screen |
| 7. **Flash** | **f408–410** | **2 frames** | a full-screen white flash with radial streaks bursting from the hit |
| 8. Reveal | f412–418 | 0.13 s | the flash recedes and reveals a **frost sigil decal on the ground** (concentric rings and spokes); a cyan core glows on the target; white shards and petal-like flakes fly; light rays rise; a rainbow fringe at the edge for one frame |
| 9. Sigil holds | f420–434 | 0.23 s | the sigil glows with radial floor streaks; flakes drift |
| 10. Fade | f434–462 | 0.47 s | the sigil fades slowly and its rim drifts out a little; snow sparkles linger |

Measured from the per-frame curves:

- **The flash is 2 frames;** the white share falls to half by f421 (0.22 s) and to a tenth by f434 (0.43 s).
- **The dash burst** stays above half its peak brightness for 11 frames (0.18 s) and is gone by about 0.45 s.
- **The calm before the hit is about 3.7 s** of near silence, and that's what makes the 2-frame flash land.

What makes it read as "good":

- **One element tells the element:** frost reads from the ground sigil and the flakes, not from tinting everything blue.
- **White does the work;** cyan sits only at the cores.
- **Thin, hard shapes:** needles, crescents, a reticle. Nothing is a soft blob.
- **Chromatic fringes** on the shell and the flash rim, baked into the art rather than done as a screen effect.

## What this means for our effects

1. **Write a beat sheet before building.** For each effect, list the beats like the tables above: frames, one shape per
   beat, one palette per beat, and where the 2-frame flash sits. Phát approves the sheet; the build matches it beat by
   beat; evfx checks the frame counts.
2. **Flashes are exactly 2 frames,** local on a dark stage (Lotus) or full screen only on the big hit (Frigid, and our
   call 1). Ours were reading 5–7 frames.
3. **Change shape between beats.** Our hits keep one shape language from start to end: a star, a burst, shards. Lotus
   goes crescent, comet, star, sphere, sigil.
4. **Negative space:** a dark halo behind the flare, and small sharp elements instead of big glows.
5. **Calm, long tails** (Lotus: 2–4 s of nearly still gold dust; Frigid: a 0.5 s sigil fade) instead of particles that
   keep moving.
6. **Ground decals carry the element:** the frost sigil, the gold ring. We have `art/ground_*` and `art/floor_streaks`
   already.
7. **Mesh hero shapes:** the lotus mesh and the spherical shells. That's our mesh set (step 2) plus bespoke meshes.
8. **Chromatic fringe rims:** `art/fringe_ring` exists; it belongs on shells and flash rims.
