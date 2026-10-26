---
name: preview
description: See and judge an EasyVFX effect without Studio: line-ups of a layer's takes, frame strips, GIFs, gates. Use after building or changing an effect, before showing it to anyone, and when a render looks wrong.
---

# Headless preview

The loop, its gates and what each command draws: [the agentic loop](../../../../docs/agentic-loop.md). Run the tools
from an EasyVFX checkout; a game's kits load through `EVFX_KITS=<dir>[:<dir>]`.

## Steps

1. **Export fresh.** `python3 tools/evfx export <preset> --fresh` for every preset you touched, and every kit take you
   will render (`kit__<kit>__<Layer>__<Take>__in`); each needs its own fresh export, or it renders the old build.
2. **Render to judge**, with a fixed camera framing the whole effect, the same for every take, so size and height
   compare honestly. The default `close` camera fits each effect to the frame and hides how tall it really is.
   - A layer's takes: one row per take, the moments across.
   - The flow: the whole effect at moments spaced to catch every handoff, including the fast ones (a fall is a few
     frames).
   - Label every image in large, high-contrast text in its corner: the person must not have to zoom.
3. **Look before you send.** Read every image yourself. Check that each layer draws, that each handoff starts where
   the last beat ended, and that takes differ visibly. Fix and re-render first.
4. **Show.** Send the strips and a GIF (real speed, and half speed for anything under a second), copied to the
   project's references folder.

Done when every image you send has been looked at and its gates pass.

## What it can't see

Studio's lighting, Bloom and texture filtering are approximated; highlights are counted, not drawn; the body
standing in the spot is a grey capsule, so an effect inside the body (a jet between the feet) shows here but is hidden
in the game. Say which of these a pick depends on.
