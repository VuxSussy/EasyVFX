"""A Luau script that shows the mesh set in Studio without uploading anything.

    python tools/meshgen studio [-o folder]   (run 00.luau first, then each shot)

It builds each shell with EditableMesh and its texture frames with EditableImage (from
pack/meshes and pack/generated), then lays out a static strip in edit mode: the slash
ribbon's frames on crescent shells side by side, Neon next to SmoothPlastic, and the
cone with its wind strip. Run it in the command bar or through an MCP execute call.
Studio-only (EditableMesh and EditableImage run on the CPU).
"""

import base64
import os

import numpy as np
from PIL import Image

import shells

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GEN = os.path.join(ROOT, "pack", "generated")
MESHES = os.path.join(ROOT, "pack", "meshes")

# (label, mesh, texture, position, material, colour)
SHOTS = [
    ("wide f00 Neon", "mesh_crescent_wide", "seq_slash_ribbon_00", (0, 6, 0), "Neon", (255, 214, 64)),
    ("wide f04 Neon", "mesh_crescent_wide", "seq_slash_ribbon_04", (12, 6, 0), "Neon", (255, 214, 64)),
    ("wide f08 Neon", "mesh_crescent_wide", "seq_slash_ribbon_08", (24, 6, 0), "Neon", (255, 214, 64)),
    ("wide f12 Neon", "mesh_crescent_wide", "seq_slash_ribbon_12", (36, 6, 0), "Neon", (255, 214, 64)),
    ("wide f00 Plastic", "mesh_crescent_wide", "seq_slash_ribbon_00", (0, 6, 14), "SmoothPlastic", (255, 214, 64)),
    ("thin f04 Neon", "mesh_crescent_thin", "seq_slash_ribbon_04", (12, 6, 14), "Neon", (255, 120, 20)),
    ("cone wind Neon", "mesh_cone", "strip_wind_stroke", (24, 4, 14), "Neon", (255, 214, 64)),
    ("torus energy Neon", "mesh_torus", "strip_energy_streak", (36, 6, 14), "Neon", (120, 200, 255)),
]
TEX_MAX = 256  # textures are halved for the script's size; enough to judge in Studio


def _image(name):
    img = Image.open(os.path.join(GEN, name + ".png")).convert("RGBA")
    scale = min(1.0, TEX_MAX / max(img.size))
    if scale < 1:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    return img.width, img.height, base64.b64encode(img.tobytes()).decode()


def _mesh(name):
    with open(os.path.join(MESHES, name + ".obj"), encoding="utf-8") as f:
        verts, uvs, tris = shells.from_obj(f.read())
    v = ",".join(f"{x:.4f},{y:.4f},{z:.4f}" for x, y, z in verts)
    t = ",".join(f"{u:.4f},{w:.4f}" for u, w in uvs)
    f_ = ",".join(str(i + 1) for i in tris.reshape(-1))
    return v, t, f_


def chunks():
    """The script in pieces small enough for one execute call each: a setup that keeps its
    helpers in _G.EVFX_PREVIEW, then one piece per shot."""
    setup = ["-- EasyVFX mesh-set preview (tools/meshgen studio). Edit mode only; nothing is uploaded.",
             'local AssetService = game:GetService("AssetService")',
             "local P = {}",
             "_G.EVFX_PREVIEW = P",
             "local B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'",
             "local DEC = {}",
             "for i = 1, 64 do DEC[string.byte(B64, i)] = i - 1 end",
             "function P.decode(s)",
             "\tlocal n = #s",
             "\tlocal pad = (string.sub(s, -2) == '==' and 2) or (string.sub(s, -1) == '=' and 1) or 0",
             "\tlocal out = buffer.create(n // 4 * 3 - pad)",
             "\tlocal o = 0",
             "\tfor i = 1, n, 4 do",
             "\t\tlocal a, b, c, d = string.byte(s, i, i + 3)",
             "\t\tlocal v = DEC[a] * 262144 + DEC[b] * 4096 + (DEC[c] or 0) * 64 + (DEC[d] or 0)",
             "\t\tbuffer.writeu8(out, o, v // 65536); o += 1",
             "\t\tif o < buffer.len(out) then buffer.writeu8(out, o, v // 256 % 256); o += 1 end",
             "\t\tif o < buffer.len(out) then buffer.writeu8(out, o, v % 256); o += 1 end",
             "\tend",
             "\treturn out",
             "end",
             "function P.nums(s) local t = {} for x in string.gmatch(s, '[^,]+') do table.insert(t, tonumber(x)) end return t end",
             SETUP_BODY]
    pieces = ["\n".join(setup) + "\nreturn 'setup ok'\n"]
    for label, m, tex, pos, mat, col in SHOTS:
        v, t, f_ = _mesh(m)
        w, h, b = _image(tex)
        size_y = 2 if "crescent" in m else 6
        pieces.append(f"""local P = _G.EVFX_PREVIEW
local AssetService = game:GetService("AssetService")
local ok, err = pcall(function()
	local em = P.mesh('{m}', P.nums('{v}'), P.nums('{t}'), P.nums('{f_}'))
	local part = AssetService:CreateMeshPartAsync(Content.fromObject(em))
	part.Name = "{label}"
	part.Anchored = true
	part.Size = Vector3.new(9, {size_y}, 9)
	part.CFrame = CFrame.new({pos[0]}, {pos[1]}, {pos[2]}) * CFrame.Angles(math.rad(70), 0, 0)
	part.Material = Enum.Material.{mat}
	part.Color = Color3.fromRGB({col[0]}, {col[1]}, {col[2]})
	part.TextureContent = Content.fromObject(P.image({w}, {h}, '{b}'))
	part.Parent = P.folder
end)
return "{label}: " .. (if ok then "ok" else tostring(err))
""")
    return pieces


SETUP_BODY = r'''
P.built = {}
function P.mesh(name, v, t, f)
	if P.built[name] then
		return P.built[name]
	end
	local em = AssetService:CreateEditableMesh()
	local vids, uids = {}, {}
	for i = 1, #v, 3 do
		table.insert(vids, em:AddVertex(Vector3.new(v[i], v[i + 1], v[i + 2])))
	end
	for i = 1, #t, 2 do
		table.insert(uids, em:AddUV(Vector2.new(t[i], t[i + 1])))
	end
	for i = 1, #f, 3 do
		local a, b, c = f[i], f[i + 1], f[i + 2]
		local face = em:AddTriangle(vids[a], vids[b], vids[c])
		em:SetFaceUVs(face, { uids[a], uids[b], uids[c] })
	end
	P.built[name] = em
	return em
end
function P.image(w, h, data)
	local img = AssetService:CreateEditableImage({ Size = Vector2.new(w, h) })
	img:WritePixelsBuffer(Vector2.zero, Vector2.new(w, h), P.decode(data))
	return img
end
local old = workspace:FindFirstChild("MeshPreview")
if old then old:Destroy() end
P.folder = Instance.new("Folder")
P.folder.Name = "MeshPreview"
P.folder.Parent = workspace
local stage = Instance.new("Part")
stage.Name = "Backdrop"
stage.Anchored = true
stage.Size = Vector3.new(70, 40, 1)
stage.CFrame = CFrame.new(18, 10, -10)
stage.Color = Color3.fromRGB(22, 24, 30)
stage.Material = Enum.Material.SmoothPlastic
stage.Parent = P.folder
'''


def main(folder=None):
    folder = folder or os.path.join(ROOT, ".cache", "meshgen", "studio")
    os.makedirs(folder, exist_ok=True)
    for k, text in enumerate(chunks()):
        path = os.path.join(folder, f"{k:02d}.luau")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {os.path.relpath(path)} ({len(text) // 1024} KB)")
    return 0
