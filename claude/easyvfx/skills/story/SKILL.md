---
name: story
description: Write an EasyVFX effect's story and beat sheet before building it, or rewrite one whose beats don't connect. Use when starting an effect, porting an old one, or when the person says the effect reads as random pieces or goes up and down.
---

# Story and beat sheet

The sheet's format, the beat judge and its fields: [beats](../../../../docs/agentic-loop.md#beats).

## Steps

1. **Reference.** When the effect replaces an old one, capture the old one first (a frame strip of it playing) and
   show it, so the person can point at what to keep. When it is new, find the person's references and say what each one
   teaches.
2. **Story.** One paragraph, start to end, in motion words: gather, compress, sag, release, fall, burst, spread,
   settle. Then check it:
   - **One thread.** The same material carries from beat to beat. Each beat starts where the last ended: the same
     place, size and colour. A column that pours into the orb, the orb that tightens to the falling drop's size, the
     drop that lands in the pool the body then rises from.
   - **One direction.** The flow moves one way (down, up, in, out), turning at most once, smoothly. Up then down then
     up again reads as a zigzag.
   - **Real timing.** Name the phenomenon each beat imitates and borrow its timing: a drop of water swells, sags, snaps
     and falls faster and faster; rings on water spread fast, then slow.
   - **Both ways.** When the effect has a reverse (arrive and leave, equip and unequip), write it as the same beats
     played backwards, and build each layer so its partner mirrors it in time.
3. **Agree.** Show the story, and two to four alternative flows when the person is unsure, as a storyboard rather
   than prose. They pick; the story is the decision.
4. **Sheet.** One `sheets/<preset>.json` per preset, every sheet with the same story. Each beat: `from` and `to` in
   60 fps frames, `shape`, `palette`, `layers`, `roles`, `why` per layer, `phenomena` where one applies, and an
   `intent` in the story's words.

Done when the person has accepted the story and `python3 tools/evfx beats <preset>` reads every sheet.
