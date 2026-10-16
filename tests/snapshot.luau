--[[
	Captures the procedural shapes of some presets mid-animation and writes their
	geometry (beam Bezier curves, parts) to JSON so tools/render_snapshot.py can draw
	a preview image. Lets us eyeball rings/slashes/bolts without opening Studio.

	lune run tests/snapshot.luau <outfile.json>
]]

local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local roblox = require("@lune/roblox")
local task = require("@lune/task")
local H = require("./harness")
H.install()

local Builder = H.require("Shared/Builder")
local EasyVFX = H.require("Runtime/EasyVFX")

local out = process.args[1] or "snapshot.json"
local shots = {
	{ id = "slash", frames = 5 },
	{ id = "multi_slash", frames = 7 },
	{ id = "impact", frames = 4 },
	{ id = "energy_blast", frames = 7 },
	{ id = "ground_slam", frames = 6 },
	{ id = "lightning", frames = 3 },
	{ id = "explosion", frames = 3 },
	{ id = "level_up", frames = 8 },
	{ id = "magic_circle", frames = 10 },
}

local function v3(v)
	return { v.X, v.Y, v.Z }
end

local function c3(c)
	return { c.R, c.G, c.B }
end

local function liveFolder()
	return (H.workspace.CurrentCamera or H.workspace):FindFirstChild("EasyVFX_Live")
end

local result = {}
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
	})
	EasyVFX.PlayLocal(root)
	for _ = 1, shot.frames do
		task.wait()
	end
	local beams, parts = {}, {}
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
					t0 = d.Transparency.Keypoints[1].Value,
					t1 = d.Transparency.Keypoints[#d.Transparency.Keypoints].Value,
					color = c3(d.Color.Keypoints[1].Value),
					color1 = c3(d.Color.Keypoints[#d.Color.Keypoints].Value),
					light = d.LightEmission,
				})
			elseif d:IsA("BasePart") and d.Name == "VFXPiece" and d.Transparency < 1 then
				table.insert(parts, {
					pos = v3(d.CFrame.Position),
					size = v3(d.Size),
					shape = tostring(d.Shape),
					material = tostring(d.Material),
					color = c3(d.Color),
					t = d.Transparency,
					right = v3(d.CFrame.RightVector),
				})
			end
		end
	end
	table.insert(result, { id = shot.id, beams = beams, parts = parts })
	print(("%-13s beams=%3d parts=%3d"):format(shot.id, #beams, #parts))
	for _ = 1, 200 do
		task.wait()
		local f = liveFolder()
		if not f or #f:GetChildren() == 0 then
			break
		end
	end
	holder:Destroy()
end

fs.writeFile(out, serde.encode("json", result))
print("wrote " .. out)
