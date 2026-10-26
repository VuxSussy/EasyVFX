---
name: effect
description: Make or rework one Roblox VFX effect with EasyVFX, from its story to the person's picks, layer by layer. Use when asked to build, restyle, port or tune an effect (a hit, a spell, an aura, a pickup, a spawn, a teleport), or when a look reads wrong.
---

# One effect, story to picks

The person picks; you build, look and propose. Every step below ends on its criterion before the next starts.

## 1. Story

Run `easyvfx:story`. Done when the person has accepted the story and the beat sheet is written.

## 2. Layers

Decide the layers yourself: as few as the story allows, each with one job, each on the Roblox component for that job
(`easyvfx:components`). One texture or one beam doing two jobs beats two layers. Done when every layer has a name,
a component, a job in the story, and its object count fits the budget.

## 3. Build as a kit

Write the effect as a kit: an `order`, every layer's takes (`A`, `B`, `C`, each with a `note` saying what it is), and
`picks` ([kits](../../../../docs/agentic-loop.md#kits-kept-in-your-own-repo)). Timing lives in named constants the takes
share, so a handoff moves with the beat it follows. Done when `python3 tools/evfx export <preset> --fresh` passes every
gate.

## 4. Look, then show one layer at a time

Run `easyvfx:preview`. Fix what you see before showing anything: a layer that draws nothing, a handoff that jumps, a take
that looks like its neighbour. Then show one layer's takes, every other layer at its pick, and ask for that layer's pick
with the ask tool. Variations are always of one layer, never of the whole effect. Done when every layer has a pick.

## 5. Whole effect

Show the picked effect as a frame strip and a GIF, at real speed and half speed. Feedback becomes a new take, a new
layer pick, or back to step 1 when it is the story that is wrong ("random stuff going on", "zigzag"). Done when the
person accepts the whole.

## 6. Record

The kit's picks and the beat sheet's `status` say what was picked and when. The effect has not been seen in Studio
until it has: say so.
