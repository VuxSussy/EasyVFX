# Dissection: Elemental Projectile Study (r011, a target anchor)

[Iris Sebirot, *Elemental Projectile Study*](https://www.artstation.com/artwork/P6lbvB), Unreal. This is the clip
shared by VFX Apprentice: 183 frames at 30 fps (6.1 s), stepped one frame at a time. It shows two projectiles held in
place and looping, fire in front and water behind. Its frames stay local. This page takes only its structure and timing.

## The fire projectile, back to front

| Layer | Role | How it looks and moves |
|---|---|---|
| Floor glow | glow | a warm orange pool of light under the head, steady |
| Smoke tail | volume | a dark purple-red smoky tail behind the body, normal blend, soft. It trails and thins away |
| Body | base | a solid, smooth teardrop shell: white-hot at the head, then yellow, orange, red and dark red toward the tail. Its outline slowly breathes and morphs (about a 1 s cycle), so it never reads as a fixed sprite |
| Inner swirl | line | darker red curved bands moving through the body from head to tail, which give it motion inside a smooth shape |
| Peeling ribbons | shards | single curled flame ribbons that peel off the top of the body, slide back along it and thin away, a new one about every 10–12 frames (0.35–0.4 s). One at a time, never a crowd |
| Sparks | dust | a few tiny yellow points inside and behind the body |

## The water projectile

The same structure in a different element: a pale cyan glowing head; a body that darkens to deep blue; dark blue
droplet chunks that break off and fall behind instead of ribbons; a cool floor glow.

## What makes it work

- **One solid shape with motion inside** reads better than many particles. The body is a single smooth form whose
  outline morphs slowly while bands move through it.
- **One thing peels off at a time,** on a steady beat (0.35–0.4 s). That gives life without noise.
- **The colour is a ramp along the body:** white-hot head, the element's colours, then dark at the tail. Dark smoke
  behind the fire gives the contrast.
- **The element is told by its secondaries:** ribbons for fire, droplet chunks for water. The bodies are built alike.
- **The stylized-realistic mix:** smooth painted shapes and bands (stylized), with soft glow, soft smoke and a light
  pool on the floor (realistic).

## For our library

| Layer kit | How in Roblox | Timing |
|---|---|---|
| `projectile.body` | a mesh shell (a teardrop) with a gradient texture, tinted by a ramp, scaled and squashed on a slow cycle | outline morph about 1 s, looping |
| `projectile.swirl` | a scrolling band texture on the same shell, or a second shell slightly larger | bands move head to tail, about 0.5 s each |
| `projectile.peel` | one ribbon particle at a time (`Rate` about 2.7/s), curled texture, `VelocityParallel` backward, thinning exit | one every 0.35–0.4 s, lives about 0.5 s |
| `projectile.tail` | dark soft smoke, normal blend, emitted backward, `gustDisperse` exit | continuous; each puff lives about 0.6 s |
| `projectile.sparks` | `sheet/embers`, a few | lifetimes vary about 2x |
| `projectile.floorGlow` | a flat soft disc below, or a PointLight | steady |
