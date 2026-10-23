--[[
	Plays presets with the real runtime under Lune and records every frame of one play:
	beams, visible pieces, lights, screen effects, the camera, every emitter that streams,
	and every burst with the frame it fired. tools/evfx renders and audits the result.

	lune run tests/timeline.luau <out-dir> [basic|hd] [preset,preset,...]

	Writes <out-dir>/<preset>.json. A burst preset plays until nothing is left (at most
	MAX_SECONDS); a loop preset streams for LOOP_SECONDS.
]]

local fs = require("@lune/fs")
local process = require("@lune/process")
local serde = require("@lune/serde")
local roblox = require("@lune/roblox")
local H = require("./harness")
H.install()

local Builder = H.require("Shared/Builder")
local Presets = H.require("Shared/Presets")
local DefaultAssets = H.require("Shared/DefaultAssets")
local EasyVFX = H.require("Runtime/EasyVFX")

local LOOP_SECONDS = 2
local MAX_SECONDS = 8
local SEED = 42

local outDir = process.args[1] or ".cache/evfx/timeline"
local mode = process.args[2] or "hd"
local only: { [string]: boolean }? = nil
if process.args[3] and process.args[3] ~= "" then
	only = {}
	for id in process.args[3]:gmatch("[^,]+") do
		(only :: any)[id] = true
	end
end

local assets: { [string]: string }? = nil
if mode == "hd" then
	assets = {}
	for key in DefaultAssets do
		(assets :: any)[key] = "pack://" .. key
	end
end

local steps: { [string]: (number) -> () } = {}
roblox.implementMethod("RunService", "BindToRenderStep", function(_rs, name, _priority, f)
	steps[name] = f
end)
roblox.implementMethod("RunService", "UnbindFromRenderStep", function(_rs, name)
	steps[name] = nil
end)

local camera = H.workspace.CurrentCamera
if not camera then
	camera = roblox.Instance.new("Camera")
	camera.Parent = H.workspace
	H.workspace.CurrentCamera = camera
end
local CAMERA_HOME = roblox.CFrame.lookAt(roblox.Vector3.new(16, 12, 20), roblox.Vector3.new(0, 1.5, 0))
local FOV_HOME = 70

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
		table.insert(out, { kp.Time, kp.Value, kp.Envelope })
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

local function worldOf(inst: Instance): (any, any)
	local parent = inst.Parent
	if parent and parent:IsA("Attachment") then
		local carrier = parent.Parent
		if carrier and carrier:IsA("BasePart") then
			return carrier.CFrame * parent.CFrame, roblox.Vector3.new(0, 0, 0)
		end
		return parent.CFrame, roblox.Vector3.new(0, 0, 0)
	elseif parent and parent:IsA("BasePart") then
		return parent.CFrame, parent.Size
	end
	return roblox.CFrame.new(), roblox.Vector3.new(0, 0, 0)
end

local function emitterInfo(e: ParticleEmitter)
	return {
		name = e.Name,
		texture = tostring(e.Texture),
		flipbook = enumName(e.FlipbookLayout),
		flipMode = enumName(e.FlipbookMode),
		flipFramerate = { e.FlipbookFramerate.Min, e.FlipbookFramerate.Max },
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
		shape = enumName(e.Shape),
		lightEmission = e.LightEmission,
		lightInfluence = e.LightInfluence,
		brightness = e.Brightness,
		zOffset = e.ZOffset,
		lockedToPart = e.LockedToPart,
		timeScale = e.TimeScale,
		rate = e.Rate,
	}
end

local function beamInfo(d: Beam)
	local a0, a1 = d.Attachment0 :: Attachment, d.Attachment1 :: Attachment
	local w0 = select(1, worldOf(a0 :: any)) * a0.CFrame
	local w1 = select(1, worldOf(a1 :: any)) * a1.CFrame
	if a0.Parent and not a0.Parent:IsA("BasePart") then
		w0 = a0.WorldCFrame
	end
	if a1.Parent and not a1.Parent:IsA("BasePart") then
		w1 = a1.WorldCFrame
	end
	return {
		p0 = v3(w0.Position),
		a0 = v3(w0.RightVector),
		p3 = v3(w1.Position),
		a1 = v3(w1.RightVector),
		c0 = d.CurveSize0,
		c1 = d.CurveSize1,
		w0 = d.Width0,
		w1 = d.Width1,
		faceCamera = d.FaceCamera,
		segments = d.Segments,
		texture = tostring(d.Texture),
		textureMode = enumName(d.TextureMode),
		textureLength = d.TextureLength,
		transparency = numSeq(d.Transparency),
		color = colSeq(d.Color),
		lightEmission = d.LightEmission,
		brightness = d.Brightness,
	}
end

local function partInfo(d: BasePart)
	return {
		cframe = cf(d.CFrame),
		size = v3(d.Size),
		shape = if d:IsA("Part") then enumName((d :: Part).Shape) else d.ClassName,
		material = enumName(d.Material),
		color = c3(d.Color),
		t = d.Transparency,
		className = d.ClassName,
	}
end

local function lightInfo(l: Light)
	local where = select(1, worldOf(l :: any))
	return {
		className = l.ClassName,
		pos = v3(where.Position),
		brightness = l.Brightness,
		range = if l:IsA("PointLight") or l:IsA("SpotLight") or l:IsA("SurfaceLight") then (l :: any).Range else 0,
		color = c3(l.Color),
	}
end

local function screenInfo(s: Instance)
	if s:IsA("ColorCorrectionEffect") then
		return {
			className = s.ClassName,
			brightness = s.Brightness,
			contrast = s.Contrast,
			saturation = s.Saturation,
			tint = c3(s.TintColor),
		}
	end
	return { className = s.ClassName }
end

local function scan(roots: { Instance }, record)
	local seen: { [Instance]: boolean } = {}
	for _, root in roots do
		for _, d in root:GetDescendants() do
			if not seen[d] then
				seen[d] = true
				record(d)
			end
		end
	end
end

local function capture(root: Instance, emitters: { any })
	local frame = {
		beams = {},
		parts = {},
		streams = {},
		lights = {},
		screens = {},
		trails = 0,
		camera = cf(camera.CFrame),
		fov = camera.FieldOfView,
	}
	local roots: { Instance } = { root }
	local live = camera:FindFirstChild("EasyVFX_Live") or H.workspace:FindFirstChild("EasyVFX_Live")
	if live then
		table.insert(roots, live)
	end
	scan(roots, function(d)
		if d:IsA("Beam") then
			if d.Enabled and d.Attachment0 and d.Attachment1 then
				table.insert(frame.beams, beamInfo(d))
			end
		elseif d:IsA("Trail") then
			if d.Enabled then
				frame.trails += 1
			end
		elseif d:IsA("ParticleEmitter") then
			if d.Enabled and d.Rate > 0 then
				local key = d:GetAttribute("EvfxKey")
				if typeof(key) ~= "number" then
					table.insert(emitters, emitterInfo(d))
					key = #emitters
					d:SetAttribute("EvfxKey", key)
				end
				local where, volume = worldOf(d)
				table.insert(frame.streams, { emitter = key, cframe = cf(where), volume = v3(volume) })
			end
		elseif d:IsA("Light") then
			if d.Enabled and d.Brightness > 0 then
				table.insert(frame.lights, lightInfo(d))
			end
		elseif d:IsA("BasePart") then
			if d.Transparency < 1 and d ~= root then
				table.insert(frame.parts, partInfo(d))
			end
		elseif d:IsA("PostEffect") then
			if d.Enabled then
				table.insert(frame.screens, screenInfo(d))
			end
		end
	end)
	for _, s in camera:GetChildren() do
		if s:IsA("PostEffect") and s.Enabled then
			table.insert(frame.screens, screenInfo(s))
		end
	end
	return frame
end

local function leftover(): number
	local n = 0
	for _, parent in { camera, H.workspace } do
		for _, live in parent:GetChildren() do
			if live.Name == "EasyVFX_Live" then
				n += #live:GetDescendants()
			end
		end
	end
	return n
end

local function record(preset)
	local holder = roblox.Instance.new("Part")
	holder.Anchored = true
	holder.Transparency = 1
	holder.Size = roblox.Vector3.new(4, 4, 4)
	holder.CFrame = roblox.CFrame.new(0, 2, 0)
	holder.Parent = H.workspace
	camera.CFrame = CAMERA_HOME
	camera.FieldOfView = FOV_HOME
	table.clear(steps)
	math.randomseed(SEED)
	local root = Builder.create(Builder.defaultParams(preset.id), {
		cframe = holder.CFrame,
		size = holder.Size,
		parent = holder,
		weldTo = holder,
	}, assets)
	H.emitLog = {}
	H.recordEmits = true
	local start = H.frame
	local loop = preset.kind == "loop"
	if loop then
		EasyVFX.SetEnabled(root, true)
	end
	EasyVFX.PlayLocal(root)
	local emitters, frames = {}, {}
	local limit = math.floor((if loop then LOOP_SECONDS else MAX_SECONDS) / H.FRAME + 0.5)
	local quiet = 0
	local done = false
	H.onFrame = function(now: number)
		if done or now - start > limit then
			return
		end
		for _, f in steps do
			f(H.FRAME)
		end
		local frame = capture(root, emitters)
		frame.t = (now - start) * H.FRAME
		table.insert(frames, frame)
		local busy = #frame.beams + #frame.parts + #frame.streams + #frame.lights + #frame.screens + frame.trails
		local emitted = 0
		for _, rec in H.emitLog do
			if rec.frame >= now - 1 then
				emitted += 1
			end
		end
		if not loop and busy == 0 and leftover() == 0 and emitted == 0 and next(steps) == nil then
			quiet += 1
			done = quiet >= 3
		else
			quiet = 0
		end
	end
	while not done and H.frame - start < limit do
		H.tick()
	end
	H.onFrame = nil
	H.recordEmits = false
	local bursts = {}
	for _, rec in H.emitLog do
		local info = emitterInfo(rec.emitter)
		info.count = rec.count
		info.frame = rec.frame - start
		info.cframe = cf(rec.cframe)
		info.volume = v3(rec.size)
		table.insert(bursts, info)
	end
	local result = {
		version = 1,
		id = preset.id,
		kind = preset.kind,
		category = preset.category,
		style = preset.style,
		mode = mode,
		seed = SEED,
		frameTime = H.FRAME,
		holder = cf(holder.CFrame),
		cameraHome = cf(CAMERA_HOME),
		fovHome = FOV_HOME,
		frames = frames,
		emitters = emitters,
		bursts = bursts,
		leftover = leftover(),
		boundSteps = (function()
			local n = 0
			for _ in steps do
				n += 1
			end
			return n
		end)(),
	}
	if loop then
		EasyVFX.SetEnabled(root, false)
	end
	for _ = 1, 300 do
		H.tick()
		for _, f in steps do
			f(H.FRAME)
		end
		if leftover() == 0 and next(steps) == nil then
			break
		end
	end
	holder:Destroy()
	return result
end

H.setMode("client")
H.lockstep = true
fs.writeDir(outDir)
local count = 0
for _, preset in Presets.List do
	if not only or (only :: any)[preset.id] then
		local ok, result = pcall(record, preset)
		if ok then
			fs.writeFile(outDir .. "/" .. preset.id .. ".json", serde.encode("json", result))
			count += 1
			print(
				("%-16s frames=%3d bursts=%3d streams=%2d leftover=%d"):format(
					preset.id,
					#result.frames,
					#result.bursts,
					#result.emitters,
					result.leftover
				)
			)
		else
			print(("%-16s FAILED %s"):format(preset.id, tostring(result)))
		end
	end
end
print(("wrote %d presets to %s"):format(count, outDir))
