--[[
	Plays presets with the real runtime under Lune and writes what exists at a chosen
	moment (beam curves, neon parts, rocks, and every particle burst with its emitter
	settings) to JSON. tools/blender_preview.py turns that into a Cycles render.

	lune run tests/snapshot.luau <out.json> [basic|hd]
]]

local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local roblox = require("@lune/roblox")
local H = require("./harness")
H.install()

local Builder = H.require("Shared/Builder")
local EasyVFX = H.require("Runtime/EasyVFX")

local out = process.args[1] or "snapshot.json"
local mode = process.args[2] or "hd"

local PACK_KEYS = {
	"slash_arc", "slash_fiber", "slash_clean", "slash_glow", "slash_core", "spark_star", "spark_streak",
	"glow_soft", "ring_wave", "flip_slash", "flip_impact", "flip_smoke", "flip_electric",
}
local assets = nil
if mode == "hd" then
	assets = {}
	for _, key in PACK_KEYS do
		assets[key] = "pack://" .. key
	end
end

local shots = {
	{ id = "slash", frames = 5 },
	{ id = "multi_slash", frames = 9 },
	{ id = "impact", frames = 4 },
	{ id = "ground_slam", frames = 7 },
	{ id = "explosion", frames = 6 },
	{ id = "lightning", frames = 4 },
	{ id = "energy_blast", frames = 7 },
	{ id = "shockwave", frames = 9 },
	{ id = "level_up", frames = 10 },
}

-- Optional timeline: lune run tests/snapshot.luau out.json hd slash 3,6,9,12
if process.args[3] then
	shots = {}
	for f in (process.args[4] or "4,8,12"):gmatch("%d+") do
		table.insert(shots, { id = process.args[3], frames = tonumber(f) })
	end
end

local function v3(v)
	return { v.X, v.Y, v.Z }
end

local function c3(c)
	return { c.R, c.G, c.B }
end

local function cf(c)
	local x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 = c:GetComponents()
	return { x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 }
end

local function numSeq(seq)
	local out = {}
	for _, kp in seq.Keypoints do
		table.insert(out, { kp.Time, kp.Value })
	end
	return out
end

local function colSeq(seq)
	local out = {}
	for _, kp in seq.Keypoints do
		table.insert(out, { kp.Time, kp.Value.R, kp.Value.G, kp.Value.B })
	end
	return out
end

local function enumName(e)
	return tostring(e):match("[^%.]+$")
end

local function liveFolder()
	return (H.workspace.CurrentCamera or H.workspace):FindFirstChild("EasyVFX_Live")
end

local result = { mode = mode, frameTime = H.FRAME, shots = {} }
for _, shot in shots do
	local holder = roblox.Instance.new("Part")
	holder.Anchored = true
	holder.Size = roblox.Vector3.new(4, 4, 4)
	holder.CFrame = roblox.CFrame.new(0, 2, 0)
	holder.Parent = H.workspace
	local root = Builder.create(Builder.defaultParams(shot.id), {
		cframe = holder.CFrame,
		size = holder.Size,
		parent = holder,
		weldTo = holder,
	}, assets)
	H.emitLog = {}
	H.recordEmits = true
	local startFrame = H.frame
	math.randomseed(42) -- same random choices for every frame of a timeline
	EasyVFX.PlayLocal(root)
	while H.frame - startFrame < shot.frames do
		H.task.wait()
	end
	local now = H.frame
	H.recordEmits = false

	local beams, parts, bursts = {}, {}, {}
	local folder = liveFolder()
	if folder then
		for _, d in folder:GetDescendants() do
			if d:IsA("Beam") and d.Enabled and d.Attachment0 and d.Attachment1 then
				local carrier = d.Attachment0.Parent
				local cf0 = carrier.CFrame * d.Attachment0.CFrame
				local cf1 = carrier.CFrame * d.Attachment1.CFrame
				table.insert(beams, {
					p0 = v3(cf0.Position),
					a0 = v3(cf0.RightVector),
					p3 = v3(cf1.Position),
					a1 = v3(cf1.RightVector),
					c0 = d.CurveSize0,
					c1 = d.CurveSize1,
					w0 = d.Width0,
					w1 = d.Width1,
					transparency = numSeq(d.Transparency),
					color = colSeq(d.Color),
					light = d.LightEmission,
					brightness = d.Brightness,
				})
			elseif d:IsA("BasePart") and d.Name == "VFXPiece" and d.Transparency < 1 then
				table.insert(parts, {
					cframe = cf(d.CFrame),
					size = v3(d.Size),
					shape = enumName(d.Shape),
					material = enumName(d.Material),
					color = c3(d.Color),
					t = d.Transparency,
				})
			end
		end
	end
	for _, rec in H.emitLog do
		local e = rec.emitter
		table.insert(bursts, {
			name = e.Name,
			count = rec.count,
			age = (now - rec.frame) * H.FRAME,
			cframe = cf(rec.cframe),
			volume = v3(rec.size),
			texture = tostring(e.Texture),
			flipbook = enumName(e.FlipbookLayout),
			flipMode = enumName(e.FlipbookMode),
			size = numSeq(e.Size),
			squash = numSeq(e.Squash),
			transparency = numSeq(e.Transparency),
			color = colSeq(e.Color),
			lifetime = { e.Lifetime.Min, e.Lifetime.Max },
			speed = { e.Speed.Min, e.Speed.Max },
			spread = { e.SpreadAngle.X, e.SpreadAngle.Y },
			accel = v3(e.Acceleration),
			drag = e.Drag,
			rotation = { e.Rotation.Min, e.Rotation.Max },
			rotSpeed = { e.RotSpeed.Min, e.RotSpeed.Max },
			orientation = enumName(e.Orientation),
			direction = enumName(e.EmissionDirection),
			lightEmission = e.LightEmission,
			brightness = e.Brightness,
			zOffset = e.ZOffset,
		})
	end
	table.insert(result.shots, { id = shot.id, frame = shot.frames, beams = beams, parts = parts, bursts = bursts })
	print(("%-13s beams=%3d parts=%3d bursts=%3d"):format(shot.id, #beams, #parts, #bursts))
	for _ = 1, 300 do
		H.task.wait()
		local f = liveFolder()
		if not f or #f:GetChildren() == 0 then
			break
		end
	end
	for _ = 1, 40 do
		H.task.wait()
	end
	holder:Destroy()
end

fs.writeFile(out, serde.encode("json", result))
print("wrote " .. out)
