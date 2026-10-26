---
name: components
description: Choose the Roblox object for each VFX layer (ParticleEmitter, Beam, Trail, Light, Highlight, post effect) and build it within budget. Use when deciding an EasyVFX layer's makeup, when a layer needs many objects, or when asked how a Roblox effect object behaves.
---

# Roblox's own component for each job

The rules and the component table: [sharp VFX](../../../../docs/sharp-vfx.md), rule 1 first. Budgets are the gates in
`tools/evfx/rules.json`.

## Steps

1. **Name the component per layer** from rule 1's table: emitters for mass and glow, one beam per still shape, a
   `Trail` for anything that moves, lights, highlights and post effects for the rest. Count the objects per layer: more
   than a handful of one kind means another component does it in one.
2. **Read both sources** for each component you build on, straight from Roblox's repository:
   - its API reference for its shape (properties, ranges, defaults): the Studio MCP's `get_roblox_docs`, such as
     `classes/Trail`;
   - its guide page for the tips: [creator-docs `content/en-us/effects`](https://github.com/Roblox/creator-docs/tree/main/content/en-us/effects),
     raw at `https://raw.githubusercontent.com/Roblox/creator-docs/main/content/en-us/effects/<page>.md`.
3. **Build it** with the EasyVFX layer or shape that drives it, and check the count with
   `python3 tools/evfx export <preset> --fresh`.

Done when every layer names its component and the export's budget gates pass.

## Gotchas that cost a round

- A steady `Rate` draws nothing at the lowest graphics quality; a loop players must always see is bursts replayed
  every `interval` (sharp-vfx rule 1). Check a take at quality 1 as well as 21.
- An emitter on an `Attachment` emits from a point: `Shape` and its size do nothing. Spread with motion instead
  (wide `spread`, `drag`, then `accel`).
- `Squash` stretches along the velocity only with `orientation = "VelocityParallel"` (a teardrop, a streak).
- A `Ring` is four quarter-arc beams, and four more with `Core`; a thin ripple wants `Core = false`.
- `Projectile`'s default tail is a 20-beam chain; `Tail = "Trail"` with `TrailTime` is one `Trail` whose length follows
  the speed.
- A layer texture made of a thin centre line all but vanishes on a wide beam; use a full-width strip for a body.
- A beam's width runs straight from `Width0` to `Width1`: one beam can flare or taper, not both. Shape the end with
  `Transparency` keypoints on an eased curve.
