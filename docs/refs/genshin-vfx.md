# Genshin Impact VFX: what is known

A desk study (2026-10-24). HoYoverse has published no talk on Genshin's effects. Its talks cover rendering
(fog, god rays, tone mapping) and the open world. So most of this comes from artists who studied or rebuilt
the effects. Each point is marked:

- **official**: from HoYoverse;
- **community**: an artist's breakdown or rebuild;
- **unverified**: searched for, but no source found.

## What HoYoverse said

- **official**: the target look is "fresh, bright, clean, anime-like", not dirty, noisy or dark. They turned down
  ACES tone mapping because it didn't fit, and they lean on a tone curve that shifts hue as values brighten.
  Source: Zhenzhong Yi, Unite Seoul 2020
  ([slides](https://docswell.com/s/UnityJapan/KWRPQ5-210617-unity-dojo20211mihoyozhenzhongyi)).

## Timing

- **community, measured**: hit-stop by weapon, at 60 fps. During it the attacker plays at 1% speed while the world
  keeps moving. Source: [KQM, frames](https://library.keqingmains.com/combat-mechanics/frames).

  | Attack | Hit-stop |
  |---|---|
  | sword, first and second hit | 0.03 s |
  | bow, charged headshot | 0.12 s |
  | claymore, final charged hit | 0.15 s |
  | catalyst | none |

- **community**: a spear hit peaks for 2 or 3 frames, very oversized, built from several elements, then changes
  shape. Source: [Real Time VFX](https://realtimevfx.com/t/recreating-spear-attack-vfx-unity/17964).
- **community**: sparkles use a wide lifetime range (about 2×). Their scale eases in slowly, then grows and shrinks
  fast just before death; the curve is not a sine. Source: [Kurie's Citlali rebuild](https://zenn.dev/kurie/articles/c06bdd7728db12).

## Look

- **community**: colour is a ramp that shifts hue, not a brightening toward white. Source: the same Citlali
  rebuild.
  - A cross sparkle carries a pink gradient on its upper arms only, set just inside the silhouette, with light-blue
    tips.
  - Its glow runs from a pink core to a blue-violet ring, then a darker outer ring. Bloom alone can't make that.
- **community**: dissolves follow the direction of motion, with a noisy edge. Rebuilds of the portals layer
  parallax planes at different speeds. Sources: [HoyoToon](https://github.com/Melioli/HoyoToon/wiki/Using-the-Genshin-Shader),
  [Mona breakdown](https://realtimevfx.com/t/genshin-impact-vfx-mona-magic-breakdown/16874).
- **unverified**:
  - cel ramp counts on effect textures, edge hardness, outlines and posterized alpha;
  - per-element shape rules (Electro jagged, Hydro round);
  - layer counts, and how effects stay readable over a bright world.

## What we take, as code

These go into the grammar (`tools/evfx/grammar.json`) as numbers, not art:

1. **Lifetime spread:** `vary`, the longest lifetime over the shortest, around 2 for sparkles and dust.
2. **Scale curves that ease in, then pop late**, rather than linear growth.
3. **A 2–3 frame oversized peak**, then a change of shape: our core rule and the beat judge's flash rule.
4. **Hit-stop scaled by weapon weight:** 0.03 s for light hits up to 0.15 s for heavy ones. This sits beside the
   motion bible's 50–80 ms light and 100–160 ms heavy.
5. **Layer kits:** core, glow, sparks and ground as separate layers, as in plan §4a.

Out of reach: hand-drawn shapes made for one pose, camera cuts, per-element design and runtime shader work. Roblox
gives particles no custom shaders.
