# meshgen: the mesh set as recipes

`tools/meshgen` writes the shells of plan [§3](plan-real-vfx.md#3-asset-pipeline) step 2 as OBJ files, in Python with
numpy only, the way [texgen](texgen.md) writes textures. Each shell is a recipe with knobs in
`tools/meshgen/shells.py`, listed in `tools/meshgen/bank.json`, and written to `pack/meshes/<family>_<name>.obj` with
a `manifest.json` for the ledger script. Nothing is uploaded yet.

```bash
python3 tools/meshgen list
python3 tools/meshgen build            # pack/meshes
python3 tools/meshgen check            # the rules, and the files still match their recipes
python3 tools/meshgen sheet -o docs/meshes/sheet.png
```

![The mesh set](meshes/sheet.png)

| Mesh | Use |
|---|---|
| `mesh/crescent_wide`, `mesh/crescent_thin` | slash shells: a band swept around an arc, pointed at both ends, tilted into a shallow cone for depth |
| `mesh/cone` | a burst thrown up from the ground |
| `mesh/sphere` | a dome flash or a shield |
| `mesh/torus` | a ring that keeps its thickness at any angle |
| `mesh/cylinder` | a light pillar or a beam's body |

## Rules

- At most 5000 triangles (Roblox allows 20000).
- No degenerate triangles.
- UVs in 0..1: u along the shell (a slash's tail to its tip, or around a ring), v across it.
- The shell fits the box -0.5..0.5 with its largest side 1, since Roblox scales a mesh's bounds to its MeshPart's
  Size.
- Two-sided: every triangle has a reversed twin, because `MeshPart.DoubleSided` can't be set from a script.

## In presets

A `shell` layer names a mesh and its texture frames:

```lua
{ type = "shell", hd = true, mesh = "mesh_crescent_wide", frames = { "seq_slash_ribbon_00", ... },
  attrs = { Size0 = Vector3.new(8, 1.2, 8), Size1 = ..., Duration = 0.3, SpinDeg = ..., Tilt = ..., Offset = ... },
  color0 = "w", color1 = "p" }
```

- **Building:** a script can't set `MeshId`, so the builder makes a hidden template MeshPart with
  `AssetService:CreateMeshPartAsync` (plugins may call it).
- **Playing:** the runtime clones the template. The clone grows from `Size0` to `Size1`, turns by `SpinDeg` and fades.
  It also swaps `TextureID` through the frames, since a mesh can't play a flipbook atlas.
- **Frames:** texgen's `sequence` kind writes frames as separate images (`seq/slash_ribbon` gives 16).
- **Before upload:** without uploaded IDs the layer is skipped.
- **evfx:** draws `pack://` meshes from `pack/meshes`, with perspective-correct UVs and two-sided coverage counted
  once.
