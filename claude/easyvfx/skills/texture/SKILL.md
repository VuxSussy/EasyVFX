---
name: texture
description: Make or tune an EasyVFX texture with texgen (a strip for a beam or trail, a particle shape, a flipbook). Use when no texture in the pack fits a layer, or when a texture's look is wrong.
---

# Textures with texgen

Recipes, the bank, checks and the stylized generators: [texgen](../../../../docs/texgen.md). Licences for borrowed art:
[the CC0 library](../../../../docs/cc0-library.md).

## Steps

1. **Look in the pack first**: a contact sheet of the candidates on dark, labelled with their names and sizes. Use one
   when it fits.
2. **Tune the texture alone**, never inside the effect: build variants with `python3 tools/texgen build <id> --set
   key=value -o <file>`, show them side by side on dark, change one knob a round, and keep each round's file. Strips
   stay even along their length and tile; taper and fade belong to the beam's or trail's own properties.
3. **Settle it in the bank**: the picked knobs in `tools/texgen/bank.json`, `python3 tools/texgen build <id>`, and the
   `use` line saying what it is for and who picked it.
4. **Then the effect**: render the effect with the new texture once the texture itself is accepted.

Done when the texture is in the bank, built into `pack/generated`, and the effect using it has been shown.
