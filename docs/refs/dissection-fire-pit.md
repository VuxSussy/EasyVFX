# Dissection: Stylized Fire Pit (r010, the target mix)

[Daryll Española, *Stylized Fire Pit*](https://www.artstation.com/artwork/oAq83O), Unreal. This is the clip shared by
VFX Apprentice: 128 frames at 30 fps (4.27 s), stepped one frame at a time. Its frames and art stay local. This page
takes only its timing, its layers and its shape language.

It's a burst that settles into a loop: a short, violent ignition hands off to a small steady fire within about
0.8 s. Frames are 30 fps from the start of the clip, so f8 is 0.27 s.

## Beats

| Beat | Frames | Length | What is on screen |
|---|---|---|---|
| Lead-in | f0–6 | 0.20 s | nothing: a dark blue-grey stage |
| Tell | f7 | **1 frame** | a small red glow dome on the ground, with a few sparks shooting straight up |
| Strike | f8–9 | **2 frames** | big diagonal white-orange light streaks slamming into the ground spot, as if something fell onto it |
| Flash | f10 | **1 frame** | a wide flat ellipse of light across the ground, and sparks thrown outward |
| Burst | f11–15 | 0.17 s | chunky flame tongues spread out flat and sideways from a white-hot core; the hex cracks appear (f12) and glow |
| Rise | f16–23 | 0.27 s | the tongues peel upward; one tall flame column leans and thins; dark smoke puffs appear around the base and drift out; sparks rise and drift |
| Collapse | f24–30 | 0.23 s | the fire shrinks to a small pile on the cracks; smoke thins away; embers float |
| Loop | f31 on | steady | small flames lick up and die on the cracks, a tongue peeling off every few frames; the cracks glow steadily; a few embers and faint smoke |

## Layers, back to front

| Layer | Role | When | How it looks and moves |
|---|---|---|---|
| Ground glow | glow | f7 on | a soft red disc lighting the floor under the fire, brightest in the burst, then steady and dim |
| Hex cracks | ground | f12 on | a flat decal of glowing cracks (cells of a Voronoi pattern): hot orange lines with a red edge, steady in the loop |
| Smoke puffs | volume | f14–30 | dark grey, soft, only a few; they appear at the base during the rise, drift outward and up slowly, and thin away. Realistic in their softness, few in number |
| Strike streaks | glint | f8–9 | long tapered diagonal light streaks converging on the spot: 2 frames |
| Ground flash | core | f10 | a flat, wide white-orange ellipse: 1 frame |
| Burst tongues | base | f11–23 | chunky stylized flame tongues (a few big shapes, hard edges, 3 value bands: white core, yellow-orange body, red tips) thrown outward, then rising and peeling |
| Loop flames | base | f24 on | the same tongue language, smaller: a looping flipbook of licking flames sitting on the cracks |
| Sparks | dust | f7 on | small red-orange points: thrown out in the burst, then rising slowly and drifting in the loop; uneven lifetimes |

## What makes it work

- **The violent part is 0.5 s; the calm part is everything after.** The tell, strike and flash take 4 frames. The
  burst and rise take about 0.4 s. Then it settles into a loop that can run for as long as the game needs.
- **Flashes are 1–2 frames** (f7, f8–9, f10), each a different shape: a glow dome, then streaks, then a flat ellipse.
  That's three different shapes in four frames, so the ignition reads as an event, not a fade-in.
- **The shape language is stylized:** a few big flame tongues with hard edges and 3 value bands. **The touches are
  realistic:** soft dark smoke, a soft floor glow and drifting sparks. That's the mix.
- **The palette is one fire ramp:** white, yellow, orange, red, dark red. The smoke is the only cool or dark element,
  for contrast.
- **The ground carries it:** the cracks and the floor glow make the fire belong to the spot.
- **The exits are graceful:** tongues peel and thin rather than vanish, smoke thins away, and sparks drift and fade.

## For our library

| Layer kit | Texture or recipe | Timing to copy |
|---|---|---|
| `fire.tell` | a small ground glow dome plus a few up-sparks | 1 frame, at -0.1 s before the strike |
| `fire.strike` | tapered light streaks converging (`shape/aniso_shard` or a new streak fan) | 2 frames |
| `fire.groundFlash` | a flat ellipse flash (`shape/core_flash`, flat) | 1 frame |
| `fire.burstTongues` | a stylized flame flipbook (3 bands, hard edges): **new generator** | 0.17 s out, then 0.27 s rising and peeling (exit: peel and thin) |
| `fire.loop` | a looping stylized flame flipbook, smaller: **new generator** | loops; one tongue peels every few frames |
| `fire.cracks` | a hex-crack glow decal: **new recipe** (Voronoi edges) | appears at the burst; steady |
| `fire.floorGlow` | a soft disc, flat | peaks in the burst, then dims to steady |
| `fire.smoke` | a few soft dark puffs (CC0 wispy smoke or a stylized 2-tone puff), normal blend | from the rise; drift and thin (`gustDisperse`) |
| `fire.sparks` | `sheet/embers` | burst outward, then rise and drift; lifetimes vary about 2x |
