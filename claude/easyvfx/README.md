# The easyvfx plugin

Claude Code skills for making Roblox VFX with EasyVFX. They hold the craft; a game's own plugin adds its taste (style,
budgets, who uploads) and points here.

| Skill | For |
|---|---|
| `/easyvfx:effect` | One effect from its story to the person's picks, layer by layer |
| `easyvfx:story` | The story and beat sheet: one thread, one direction, real timing, both ways |
| `easyvfx:components` | Roblox's own component for each layer, read from its API reference and creator-docs guide |
| `easyvfx:preview` | Line-ups, strips and GIFs without Studio, and checking them before showing |
| `easyvfx:texture` | Making or tuning a texture with texgen, the texture alone first |

## Loading it

From a checkout of this repository:

```
/plugin marketplace add ./claude
/plugin install easyvfx@easyvfx
```

A game that keeps EasyVFX as a submodule loads it in place from its `.claude/settings.json`:

```json
"extraKnownMarketplaces": {
  "easyvfx": { "source": { "source": "directory", "path": "./tools/easyvfx/claude" } }
},
"enabledPlugins": { "easyvfx@easyvfx": true }
```
