--!strict
--[[
	EasyVFX runtime  (installed by the EasyVFX plugin as ReplicatedStorage.EasyVFX)

	Plays effects made with the EasyVFX plugin. You never have to edit this file.

	For scripters:
		local EasyVFX = require(game.ReplicatedStorage.EasyVFX)
		EasyVFX.Play(workspace.Part.VFX_Explosion)          -- play an effect where it is
		EasyVFX.Play("VFX_Explosion", CFrame.new(0, 5, 0))  -- play a copy somewhere else
		EasyVFX.SetEnabled(effect, false)                    -- turn looping layers off

	How it works:
	  * Called on the server, Play() asks every client to play the effect (one small
	    RemoteEvent). Particles, beams and meshes are then created and animated on each
	    client, which is what the Roblox DevForum recommends for smooth, lag-free VFX.
	  * Called on a client (or in Studio edit mode for previews) it plays locally.
	  * Emitters follow the community attribute convention: EmitCount, EmitDelay and
	    EmitDuration, so effects stay compatible with other emit tools.
	  * "Shape" layers (Configuration objects with a Kind attribute) are crisp,
	    procedural pieces built from Beams and Neon parts: Ring, Slash, Lines, Bolt,
	    Orb, Debris and Crater.
]]

local CollectionService = game:GetService("CollectionService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local EasyVFX = {}
EasyVFX.Version = 3
EasyVFX.Tag = "EasyVFX"
-- 0.25 .. 1. Multiplies particle, line and rock counts. Lowered automatically on the
-- client when the player picks a low graphics level.
EasyVFX.Quality = 1

local KAPPA = 4 / 3 -- Bezier arc factor, used as KAPPA * tan(angle / 4)
local GRAVITY = 70
local MAX_SHAPE_COUNT = 64

------------------------------------------------------------------------------------
-- Small helpers
------------------------------------------------------------------------------------

local function num(inst: Instance, name: string, default: number): number
	local v = inst:GetAttribute(name)
	return if type(v) == "number" then v else default
end

local function vec(inst: Instance, name: string, default: Vector3): Vector3
	local v = inst:GetAttribute(name)
	return if typeof(v) == "Vector3" then v else default
end

local function col(inst: Instance, name: string, default: Color3): Color3
	local v = inst:GetAttribute(name)
	return if typeof(v) == "Color3" then v else default
end

local function str(inst: Instance, name: string, default: string): string
	local v = inst:GetAttribute(name)
	return if type(v) == "string" and v ~= "" then v else default
end

local function bool(inst: Instance, name: string, default: boolean): boolean
	local v = inst:GetAttribute(name)
	return if type(v) == "boolean" then v else default
end

local function lerp(a: number, b: number, t: number): number
	return a + (b - a) * t
end

local function ease(alpha: number, style: string): number
	if style == "Linear" then
		return alpha
	elseif style == "In" then
		return alpha * alpha * alpha
	elseif style == "InOut" then
		return if alpha < 0.5 then 4 * alpha ^ 3 else 1 - (-2 * alpha + 2) ^ 3 / 2
	elseif style == "Back" then
		local c1, c3 = 1.70158, 2.70158
		return 1 + c3 * (alpha - 1) ^ 3 + c1 * (alpha - 1) ^ 2
	end
	return 1 - (1 - alpha) ^ 3 -- "Out"
end

local function rad(v: Vector3): CFrame
	return CFrame.Angles(math.rad(v.X), math.rad(v.Y), math.rad(v.Z))
end

local function originOf(root: Instance): CFrame
	if root:IsA("BasePart") then
		return root.CFrame
	elseif root:IsA("Attachment") then
		return root.WorldCFrame
	elseif root:IsA("Model") then
		return root:GetPivot()
	end
	return CFrame.identity
end

------------------------------------------------------------------------------------
-- Animation driver: one loop for every running piece of every effect
------------------------------------------------------------------------------------

type Anim = {
	t: number,
	delay: number,
	duration: number,
	started: boolean,
	start: (() -> ())?,
	step: (alpha: number, dt: number) -> (),
	finish: (() -> ())?,
}

local active: { Anim } = {}
local driverRunning = false

local function finishAnim(a: Anim)
	if a.finish then
		local ok, err = pcall(a.finish :: any)
		if not ok then
			warn("[EasyVFX] " .. tostring(err))
		end
	end
end

local function runDriver()
	if driverRunning then
		return
	end
	driverRunning = true
	task.spawn(function()
		while #active > 0 do
			local dt = task.wait()
			local i = 1
			while i <= #active do
				local a = active[i]
				a.t += dt
				local keep = true
				if a.t >= a.delay then
					if not a.started then
						a.started = true
						if a.start then
							local ok, err = pcall(a.start :: any)
							if not ok then
								warn("[EasyVFX] " .. tostring(err))
								keep = false
							end
						end
					end
					if keep then
						local alpha = math.clamp((a.t - a.delay) / a.duration, 0, 1)
						local ok, err = pcall(a.step :: any, alpha, dt)
						if not ok then
							warn("[EasyVFX] " .. tostring(err))
						end
						keep = ok and alpha < 1
					end
				end
				if keep then
					i += 1
				else
					active[i] = active[#active]
					active[#active] = nil
					finishAnim(a)
				end
			end
		end
		driverRunning = false
	end)
end

local function addAnim(
	delay: number,
	duration: number,
	start: (() -> ())?,
	step: (alpha: number, dt: number) -> (),
	finish: (() -> ())?
)
	table.insert(active, {
		t = 0,
		delay = math.max(0, delay),
		duration = math.max(0.016, duration),
		started = false,
		start = start,
		step = step,
		finish = finish,
	})
	runDriver()
end

------------------------------------------------------------------------------------
-- Where temporary pieces live. Inside the camera they are local-only, are never
-- saved with the place and never get in the way of gameplay raycasts.
------------------------------------------------------------------------------------

local function liveFolder(): Instance
	local parent: Instance = Workspace.CurrentCamera or Workspace
	local existing = parent:FindFirstChild("EasyVFX_Live")
	if existing then
		return existing
	end
	local folder = Instance.new("Folder")
	folder.Name = "EasyVFX_Live"
	folder.Archivable = false
	folder.Parent = parent
	return folder
end

local function newPart(cf: CFrame): Part
	local p = Instance.new("Part")
	p.Name = "VFXPiece"
	p.Anchored = true
	p.CanCollide = false
	p.CanTouch = false
	p.CanQuery = false
	p.CastShadow = false
	p.Locked = true
	p.Archivable = false
	p.Transparency = 1
	p.Size = Vector3.new(0.2, 0.2, 0.2)
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.CFrame = cf
	return p
end

local function newAttachment(parent: Instance): Attachment
	local a = Instance.new("Attachment")
	a.Archivable = false
	a.Parent = parent
	return a
end

type Style = {
	color0: Color3,
	color1: Color3,
	glow: number,
	brightness: number,
	fade0: number,
	fadeStart: number,
	ease: string,
	core: boolean,
	coreColor: Color3,
	texture: string,
	zOffset: number,
}

local function readStyle(cfg: Instance): Style
	return {
		color0 = col(cfg, "Color0", Color3.new(1, 1, 1)),
		color1 = col(cfg, "Color1", col(cfg, "Color0", Color3.new(1, 1, 1))),
		glow = math.clamp(num(cfg, "Glow", 1), 0, 1),
		brightness = num(cfg, "Brightness", 1),
		fade0 = math.clamp(num(cfg, "Transparency", 0), 0, 1),
		fadeStart = math.clamp(num(cfg, "FadeStart", 0.35), 0, 0.99),
		ease = str(cfg, "Ease", "Out"),
		core = bool(cfg, "Core", true),
		coreColor = col(cfg, "CoreColor", Color3.new(1, 1, 1)),
		texture = str(cfg, "Texture", ""),
		zOffset = num(cfg, "ZOffset", 0),
	}
end

local function fadeAt(style: Style, alpha: number): number
	if alpha <= style.fadeStart then
		return style.fade0
	end
	local f = (alpha - style.fadeStart) / (1 - style.fadeStart)
	return lerp(style.fade0, 1, f * f)
end

local function newBeam(parent: Instance, a0: Attachment, a1: Attachment, style: Style, isCore: boolean): Beam
	local b = Instance.new("Beam")
	b.Archivable = false
	b.Attachment0 = a0
	b.Attachment1 = a1
	b.FaceCamera = true
	b.Segments = 12
	b.LightEmission = style.glow
	b.LightInfluence = 0
	b.Brightness = if isCore then style.brightness * 1.5 else style.brightness
	b.Color = ColorSequence.new(if isCore then style.coreColor else style.color0)
	b.ZOffset = style.zOffset + (if isCore then 0.05 else 0)
	if style.texture ~= "" and not isCore then
		b.Texture = style.texture
		b.TextureMode = Enum.TextureMode.Stretch
	end
	b.Parent = parent
	return b
end

-- Random perpendicular basis for a direction.
local function basis(dir: Vector3): (Vector3, Vector3)
	local up = if math.abs(dir.Y) < 0.95 then Vector3.yAxis else Vector3.xAxis
	local u = dir:Cross(up).Unit
	local v = dir:Cross(u).Unit
	return u, v
end

local function randomDir(rng: Random, mode: string, cone: number): Vector3
	if mode == "Ring" then
		local a = rng:NextNumber(0, math.pi * 2)
		return Vector3.new(math.cos(a), 0, math.sin(a))
	elseif mode == "Up" or mode == "Forward" or mode == "Down" then
		local axis = if mode == "Up" then Vector3.yAxis elseif mode == "Down" then -Vector3.yAxis else -Vector3.zAxis
		local u, v = basis(axis)
		local a = rng:NextNumber(0, math.pi * 2)
		local spread = math.rad(cone) * math.sqrt(rng:NextNumber())
		return (axis * math.cos(spread) + (u * math.cos(a) + v * math.sin(a)) * math.sin(spread)).Unit
	end
	local d = Vector3.new(rng:NextNumber(-1, 1), rng:NextNumber(-1, 1), rng:NextNumber(-1, 1))
	return if d.Magnitude > 0.01 then d.Unit else Vector3.yAxis
end

local function scaledCount(cfg: Instance, name: string, default: number, quality: number): number
	return math.clamp(math.floor(num(cfg, name, default) * quality + 0.5), 1, MAX_SHAPE_COUNT)
end

local function groundBelow(position: Vector3, ignore: { Instance }): (Vector3, Enum.Material, Color3)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = ignore
	params.IgnoreWater = true
	local hit = Workspace:Raycast(position + Vector3.new(0, 3, 0), Vector3.new(0, -60, 0), params)
	if hit then
		local color = Color3.fromRGB(110, 110, 115)
		local inst = hit.Instance
		if inst:IsA("BasePart") and not inst:IsA("Terrain") then
			color = inst.Color
		elseif inst:IsA("Terrain") then
			local ok, c = pcall(function()
				return (inst :: Terrain):GetMaterialColor(hit.Material)
			end)
			if ok then
				color = c
			end
		end
		local material = hit.Material
		if material == Enum.Material.Air or material == Enum.Material.Water then
			material = Enum.Material.Slate
		end
		return hit.Position, material, color
	end
	return position - Vector3.new(0, 3, 0), Enum.Material.Slate, Color3.fromRGB(110, 110, 115)
end

-- Moves a CFrame down onto the ground under it (keeps its rotation).
local function snapToGround(cf: CFrame, ignore: { Instance }): CFrame
	local hit = groundBelow(cf.Position, ignore)
	return cf.Rotation + hit + Vector3.new(0, 0.15, 0)
end

------------------------------------------------------------------------------------
-- Shape layers. Each returns how long it runs (delay included).
------------------------------------------------------------------------------------

type Ctx = { root: Instance, origin: CFrame, quality: number, rng: Random, ignore: { Instance } }

local Shapes: { [string]: (cfg: Instance, ctx: Ctx) -> number } = {}

-- Expanding circle(s) made of 4 curved beams. Count + Step make tunnels of rings.
Shapes.Ring = function(cfg, ctx)
	local count = math.clamp(math.floor(num(cfg, "Count", 1)), 1, 16)
	local stagger = num(cfg, "Stagger", 0.06)
	local stepOffset = vec(cfg, "Step", Vector3.zero)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.5)
	local r0, r1 = num(cfg, "Radius0", 0.5), num(cfg, "Radius1", 8)
	local w0, w1 = num(cfg, "Width0", 1), num(cfg, "Width1", 0.1)
	local spin = num(cfg, "Spin", 0)
	local style = readStyle(cfg)
	local base = ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero))
	if bool(cfg, "Ground", false) then
		base = snapToGround(base, ctx.ignore)
	end
	local tilt = rad(vec(cfg, "Tilt", Vector3.zero))

	for i = 0, count - 1 do
		local cf = base * CFrame.new(stepOffset * i) * tilt
		local carrier = newPart(cf)
		local atts: { Attachment } = {}
		local beams: { Beam } = {}
		local cores: { Beam } = {}
		for k = 1, 4 do
			atts[k] = newAttachment(carrier)
		end
		for k = 1, 4 do
			beams[k] = newBeam(carrier, atts[k], atts[k % 4 + 1], style, false)
			if style.core then
				cores[k] = newBeam(carrier, atts[k], atts[k % 4 + 1], style, true)
			end
		end
		local function step(alpha: number)
			local e = ease(alpha, style.ease)
			local r = math.max(0.01, lerp(r0, r1, e))
			local w = math.max(0, lerp(w0, w1, e))
			local rot = math.rad(spin) * alpha
			for k = 1, 4 do
				local th = (k - 1) * math.pi / 2 + rot
				local p = Vector3.new(math.cos(th) * r, 0, math.sin(th) * r)
				local t = Vector3.new(-math.sin(th), 0, math.cos(th))
				atts[k].CFrame = CFrame.fromMatrix(p, t, Vector3.yAxis)
			end
			local c = r * KAPPA * math.tan(math.pi / 8)
			local tr = NumberSequence.new(fadeAt(style, alpha))
			local color = ColorSequence.new(style.color0:Lerp(style.color1, e))
			for k = 1, 4 do
				local b = beams[k]
				b.CurveSize0, b.CurveSize1 = c, c
				b.Width0, b.Width1 = w, w
				b.Transparency = tr
				b.Color = color
				local cb = cores[k]
				if cb then
					cb.CurveSize0, cb.CurveSize1 = c, c
					cb.Width0, cb.Width1 = w * 0.35, w * 0.35
					cb.Transparency = tr
				end
			end
		end
		step(0)
		addAnim(delay + stagger * i, duration, function()
			carrier.Parent = liveFolder()
		end, step, function()
			carrier:Destroy()
		end)
	end
	return delay + stagger * (count - 1) + duration
end

-- Anime crescent slash: a curved, tapered ribbon that sweeps and fades.
Shapes.Slash = function(cfg, ctx)
	local count = math.clamp(math.floor(num(cfg, "Count", 1)), 1, 12)
	local stagger = num(cfg, "Stagger", 0.07)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.45)
	local radius = num(cfg, "Radius", 5)
	local arc = math.rad(math.clamp(num(cfg, "Arc", 160), 10, 300))
	local width = num(cfg, "Width", 1.5)
	local sweep = math.rad(num(cfg, "Sweep", 50))
	local randomTilt = num(cfg, "RandomTilt", 0)
	local tailFade = math.clamp(num(cfg, "TailFade", 0.75), 0, 1)
	local style = readStyle(cfg)
	local base = ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero)) * rad(vec(cfg, "Tilt", Vector3.zero))
	local N = 6

	for i = 0, count - 1 do
		local roll = if randomTilt > 0 then ctx.rng:NextNumber(-randomTilt, randomTilt) else 0
		local yaw = if randomTilt > 0 then ctx.rng:NextNumber(-randomTilt, randomTilt) * 0.4 else 0
		local cf = base * CFrame.Angles(0, math.rad(yaw), math.rad(roll))
		local carrier = newPart(cf)
		local atts: { Attachment } = {}
		local beams: { Beam } = {}
		local cores: { Beam } = {}
		for k = 0, N do
			atts[k + 1] = newAttachment(carrier)
		end
		for k = 1, N do
			beams[k] = newBeam(carrier, atts[k], atts[k + 1], style, false)
			if style.core then
				cores[k] = newBeam(carrier, atts[k], atts[k + 1], style, true)
			end
		end
		local function step(alpha: number)
			local e = ease(alpha, style.ease)
			local reveal = math.min(1, alpha / 0.3)
			reveal = 1 - (1 - reveal) ^ 2
			local span = arc * math.max(0.02, reveal)
			local r = radius * (1 + 0.15 * e)
			local start = -math.pi / 2 - arc / 2
			local s = span / N
			local c = r * KAPPA * math.tan(s / 4)
			carrier.CFrame = cf * CFrame.Angles(0, lerp(-sweep / 2, sweep / 2, e), 0)
			for k = 0, N do
				local th = start + s * k
				local p = Vector3.new(math.cos(th) * r, 0, math.sin(th) * r)
				local t = Vector3.new(-math.sin(th), 0, math.cos(th))
				atts[k + 1].CFrame = CFrame.fromMatrix(p, t, Vector3.yAxis)
			end
			local base_t = fadeAt(style, alpha)
			local color = ColorSequence.new(style.color0, style.color1)
			for k = 1, N do
				-- k = N is the leading edge: widest near the head, sharp at both tips
				local f0 = (k - 1) / N
				local f1 = k / N
				local w0 = width * math.sin(math.pi * f0 ^ 0.8)
				local w1 = width * math.sin(math.pi * f1 ^ 0.8)
				local t0 = lerp(base_t, 1, (1 - f0) * tailFade)
				local t1 = lerp(base_t, 1, (1 - f1) * tailFade)
				local b = beams[k]
				b.CurveSize0, b.CurveSize1 = c, c
				b.Width0, b.Width1 = w0, w1
				b.Transparency = NumberSequence.new(t0, t1)
				b.Color = color
				local cb = cores[k]
				if cb then
					cb.CurveSize0, cb.CurveSize1 = c, c
					cb.Width0, cb.Width1 = w0 * 0.3, w1 * 0.3
					cb.Transparency = NumberSequence.new(t0, t1)
				end
			end
		end
		step(0)
		addAnim(delay + stagger * i, duration, function()
			carrier.Parent = liveFolder()
		end, step, function()
			carrier:Destroy()
		end)
	end
	return delay + stagger * (count - 1) + duration
end

-- Sharp needle streaks that shoot out (impact lines, speed lines, sparks).
Shapes.Lines = function(cfg, ctx)
	local count = scaledCount(cfg, "Count", 12, ctx.quality)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.35)
	local stagger = num(cfg, "Stagger", 0.05)
	local mode = str(cfg, "Mode", "Sphere")
	local cone = num(cfg, "Cone", 30)
	local d0, d1 = num(cfg, "Distance0", 0.5), num(cfg, "Distance1", 10)
	local length = num(cfg, "Length", 5)
	local width = num(cfg, "Width", 0.35)
	local style = readStyle(cfg)
	local base = ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero))
	if bool(cfg, "Ground", false) then
		base = snapToGround(base, ctx.ignore)
	end
	local cf = base * rad(vec(cfg, "Tilt", Vector3.zero))
	local carrier = newPart(cf)
	local longest = 0
	local remaining = count

	for _ = 1, count do
		local dir = randomDir(ctx.rng, mode, cone)
		local len = length * ctx.rng:NextNumber(0.6, 1.2)
		local far = d1 * ctx.rng:NextNumber(0.7, 1.1)
		local myDelay = delay + ctx.rng:NextNumber(0, stagger)
		local myDuration = duration * ctx.rng:NextNumber(0.8, 1.2)
		local a0, a1, a2 = newAttachment(carrier), newAttachment(carrier), newAttachment(carrier)
		local b1 = newBeam(carrier, a0, a1, style, false)
		local b2 = newBeam(carrier, a1, a2, style, false)
		local c1 = if style.core then newBeam(carrier, a0, a1, style, true) else nil
		local c2 = if style.core then newBeam(carrier, a1, a2, style, true) else nil
		for _, b in { b1, b2, c1, c2 } :: { any } do
			b.Enabled = false
		end
		local function step(alpha: number)
			local e = ease(alpha, style.ease)
			local tail = lerp(d0, far, e)
			local head = tail + len * (1 - alpha) ^ 0.6
			a0.CFrame = CFrame.new(dir * tail)
			a1.CFrame = CFrame.new(dir * ((tail + head) / 2))
			a2.CFrame = CFrame.new(dir * head)
			local tr = NumberSequence.new(fadeAt(style, alpha))
			local color = ColorSequence.new(style.color0:Lerp(style.color1, e))
			b1.Width0, b1.Width1 = 0, width
			b2.Width0, b2.Width1 = width, 0
			b1.Transparency, b2.Transparency = tr, tr
			b1.Color, b2.Color = color, color
			if c1 and c2 then
				c1.Width0, c1.Width1 = 0, width * 0.35
				c2.Width0, c2.Width1 = width * 0.35, 0
				c1.Transparency, c2.Transparency = tr, tr
			end
		end
		step(0)
		addAnim(myDelay, myDuration, function()
			for _, b in { b1, b2, c1, c2 } :: { any } do
				b.Enabled = true
			end
		end, step, function()
			remaining -= 1
			if remaining <= 0 then
				carrier:Destroy() -- last line done: remove everything at once
			else
				for _, inst in { b1, b2, c1, c2, a0, a1, a2 } :: { any } do
					inst:Destroy()
				end
			end
		end)
		longest = math.max(longest, myDelay + myDuration)
	end
	carrier.Parent = liveFolder()
	return longest
end

-- Zig-zag lightning that re-shapes itself every few frames.
Shapes.Bolt = function(cfg, ctx)
	local count = math.clamp(math.floor(num(cfg, "Count", 1)), 1, 8)
	local stagger = num(cfg, "Stagger", 0.08)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.35)
	local from = vec(cfg, "From", Vector3.new(0, 30, 0))
	local to = vec(cfg, "To", Vector3.zero)
	local segments = math.clamp(math.floor(num(cfg, "Segments", 8)), 2, 24)
	local jitter = num(cfg, "Jitter", 2)
	local width = num(cfg, "Width", 0.6)
	local flicker = math.max(0.02, num(cfg, "Flicker", 0.05))
	local style = readStyle(cfg)
	local cf = ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero))
	local dir = to - from
	local u, v = basis(if dir.Magnitude > 0.01 then dir.Unit else Vector3.yAxis)

	for i = 0, count - 1 do
		local carrier = newPart(cf)
		local atts: { Attachment } = {}
		local beams: { Beam } = {}
		local cores: { Beam } = {}
		for k = 0, segments do
			atts[k + 1] = newAttachment(carrier)
		end
		for k = 1, segments do
			beams[k] = newBeam(carrier, atts[k], atts[k + 1], style, false)
			beams[k].Segments = 1
			if style.core then
				cores[k] = newBeam(carrier, atts[k], atts[k + 1], style, true)
				cores[k].Segments = 1
			end
		end
		local timer = math.huge
		local sideOffset = (u * ctx.rng:NextNumber(-1, 1) + v * ctx.rng:NextNumber(-1, 1)) * jitter * i
		local function reshape()
			for k = 0, segments do
				local f = k / segments
				local p = from:Lerp(to, f)
				local amount = math.sin(math.pi * f) * jitter
				local off = (u * ctx.rng:NextNumber(-1, 1) + v * ctx.rng:NextNumber(-1, 1)) * amount
				atts[k + 1].CFrame = CFrame.new(p + off + sideOffset * math.sin(math.pi * f))
			end
		end
		local function step(alpha: number, dt: number)
			timer += dt
			if timer >= flicker then
				timer = 0
				reshape()
			end
			local tr = fadeAt(style, alpha)
			if ctx.rng:NextNumber() < 0.15 then
				tr = math.min(1, tr + 0.5)
			end
			local seq = NumberSequence.new(tr)
			local color = ColorSequence.new(style.color0:Lerp(style.color1, alpha))
			local w = width * (1 - alpha * 0.5)
			for k = 1, segments do
				local b = beams[k]
				b.Width0, b.Width1 = w, w
				b.Transparency = seq
				b.Color = color
				local cb = cores[k]
				if cb then
					cb.Width0, cb.Width1 = w * 0.35, w * 0.35
					cb.Transparency = seq
				end
			end
		end
		step(0, math.huge)
		addAnim(delay + stagger * i, duration, function()
			carrier.Parent = liveFolder()
		end, step, function()
			carrier:Destroy()
		end)
	end
	return delay + stagger * (count - 1) + duration
end

-- A glowing Neon (or ForceField) part that grows and fades: flashes, pillars, shields.
Shapes.Orb = function(cfg, ctx)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.3)
	local s0, s1 = num(cfg, "Size0", 0.5), num(cfg, "Size1", 6)
	local stretch = vec(cfg, "Stretch", Vector3.one)
	local length = num(cfg, "Length", 0) -- fixed X size (cylinder pillars)
	local shapeName = str(cfg, "Shape", "Ball")
	local materialName = str(cfg, "Material", "Neon")
	local spin = vec(cfg, "SpinDeg", Vector3.zero)
	local style = readStyle(cfg)
	local cf = ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero)) * rad(vec(cfg, "Tilt", Vector3.zero))

	local part = newPart(cf)
	local okShape, shape = pcall(function()
		return (Enum.PartType :: any)[shapeName]
	end)
	part.Shape = if okShape and shape then shape else Enum.PartType.Ball
	local okMat, material = pcall(function()
		return (Enum.Material :: any)[materialName]
	end)
	part.Material = if okMat and material then material else Enum.Material.Neon
	part.Color = style.color0
	local function step(alpha: number)
		local e = ease(alpha, style.ease)
		local s = math.max(0.05, lerp(s0, s1, e))
		local size = stretch * s
		part.Size = if length > 0 then Vector3.new(length, size.Y, size.Z) else size
		part.CFrame = cf * CFrame.Angles(math.rad(spin.X * alpha), math.rad(spin.Y * alpha), math.rad(spin.Z * alpha))
		part.Transparency = fadeAt(style, alpha)
		part.Color = style.color0:Lerp(style.color1, e)
	end
	step(0)
	addAnim(delay, duration, function()
		part.Parent = liveFolder()
	end, step, function()
		part:Destroy()
	end)
	return delay + duration
end

-- Rocks thrown out of the ground. Simple ballistic motion (no physics cost).
Shapes.Debris = function(cfg, ctx)
	local count = scaledCount(cfg, "Count", 10, ctx.quality)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 2)
	local sizeMin, sizeMax = num(cfg, "SizeMin", 0.4), num(cfg, "SizeMax", 1.2)
	local force = num(cfg, "Force", 30)
	local radius = num(cfg, "Radius", 2)
	local origin = (ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero))).Position

	addAnim(delay, 0.016, nil, function()
		local ground, material, color = groundBelow(origin, ctx.ignore)
		for _ = 1, count do
			local a = ctx.rng:NextNumber(0, math.pi * 2)
			local out = Vector3.new(math.cos(a), 0, math.sin(a))
			local size = ctx.rng:NextNumber(sizeMin, sizeMax)
			local rock = newPart(CFrame.new(ground + out * ctx.rng:NextNumber(0, radius) + Vector3.new(0, size / 2, 0)))
			rock.Transparency = 0
			rock.Size = Vector3.new(size, size * ctx.rng:NextNumber(0.6, 1), size * ctx.rng:NextNumber(0.7, 1.1))
			rock.Material = material
			rock.Color = color
			local pos = rock.CFrame.Position
			local vel = out * force * ctx.rng:NextNumber(0.3, 0.7) + Vector3.new(0, force * ctx.rng:NextNumber(0.6, 1.1), 0)
			local rot = rock.CFrame.Rotation
			local spinAxis = randomDir(ctx.rng, "Sphere", 0)
			local spinSpeed = ctx.rng:NextNumber(4, 12)
			local landed = false
			local baseSize = rock.Size
			addAnim(0, duration * ctx.rng:NextNumber(0.85, 1.15), function()
				rock.Parent = liveFolder()
			end, function(alpha, dt)
				if not landed then
					vel -= Vector3.new(0, GRAVITY * dt, 0)
					pos += vel * dt
					rot = CFrame.fromAxisAngle(spinAxis, spinSpeed * dt) * rot
					if pos.Y <= ground.Y + baseSize.Y / 2 and vel.Y < 0 then
						pos = Vector3.new(pos.X, ground.Y + baseSize.Y / 2, pos.Z)
						landed = true
					end
				end
				local shrink = if alpha > 0.75 then 1 - (alpha - 0.75) / 0.25 else 1
				rock.Size = baseSize * math.max(0.05, shrink)
				rock.CFrame = CFrame.new(pos) * rot
			end, function()
				rock:Destroy()
			end)
		end
	end)
	return delay + duration * 1.15
end

-- A ring of rocks bursting out of the ground, then sinking back.
Shapes.Crater = function(cfg, ctx)
	local count = scaledCount(cfg, "Count", 12, ctx.quality)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 2.5)
	local radius = num(cfg, "Radius", 6)
	local sizeMin, sizeMax = num(cfg, "SizeMin", 1.2), num(cfg, "SizeMax", 2.4)
	local lean = num(cfg, "Lean", 35)
	local origin = (ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero))).Position

	addAnim(delay, 0.016, nil, function()
		local ground, material, color = groundBelow(origin, ctx.ignore)
		for k = 1, count do
			local a = (k / count) * math.pi * 2 + ctx.rng:NextNumber(-0.15, 0.15)
			local out = Vector3.new(math.cos(a), 0, math.sin(a))
			local s = ctx.rng:NextNumber(sizeMin, sizeMax)
			local size = Vector3.new(s * 1.2, s * ctx.rng:NextNumber(0.8, 1.3), s * 0.9)
			local pos = ground + out * radius * ctx.rng:NextNumber(0.85, 1.1)
			local final = CFrame.lookAt(pos, pos + out)
				* CFrame.Angles(math.rad(-lean + ctx.rng:NextNumber(-10, 10)), 0, math.rad(ctx.rng:NextNumber(-15, 15)))
			local rock = newPart(final)
			rock.Transparency = 0
			rock.Size = size
			rock.Material = material
			rock.Color = color
			addAnim(k * 0.004, duration, function()
				rock.Parent = liveFolder()
			end, function(alpha)
				local rise
				if alpha < 0.08 then
					rise = ease(alpha / 0.08, "Back")
				elseif alpha > 0.8 then
					rise = 1 - ease((alpha - 0.8) / 0.2, "In")
				else
					rise = 1
				end
				rock.CFrame = final - Vector3.new(0, size.Y * (1 - rise), 0)
			end, function()
				rock:Destroy()
			end)
		end
	end)
	return delay + duration
end

------------------------------------------------------------------------------------
-- Playing an effect
------------------------------------------------------------------------------------

local pulseTokens: { [Instance]: number } = setmetatable({}, { __mode = "k" }) :: any

local function setOn(inst: Instance, on: boolean)
	if inst:IsA("ParticleEmitter") or inst:IsA("Beam") or inst:IsA("Trail") or inst:IsA("Light") or inst:IsA("Highlight") then
		(inst :: any).Enabled = on
	elseif inst:IsA("BasePart") then
		inst.Transparency = if on then num(inst, "BaseTransparency", 0) else 1
	end
end

-- Turn something on for `duration` seconds after `delay`, handling overlapping plays.
local function pulse(inst: Instance, delay: number, duration: number)
	local token = (pulseTokens[inst] or 0) + 1
	pulseTokens[inst] = token
	if inst:IsA("Light") and bool(inst, "FlashFade", true) then
		local light = inst :: Light
		local baseBrightness = num(light, "BaseBrightness", light.Brightness)
		light:SetAttribute("BaseBrightness", baseBrightness)
		addAnim(delay, duration, function()
			light.Enabled = true
		end, function(alpha)
			if pulseTokens[light] == token then
				light.Brightness = baseBrightness * (1 - alpha) ^ 2
			end
		end, function()
			if pulseTokens[light] == token then
				light.Enabled = false
				light.Brightness = baseBrightness
			end
		end)
		return
	end
	task.delay(delay, function()
		if pulseTokens[inst] == token and inst.Parent then
			setOn(inst, true)
		end
	end)
	task.delay(delay + duration, function()
		if pulseTokens[inst] == token and inst.Parent then
			setOn(inst, false)
		end
	end)
end

-- Your own Blender/Studio mesh: a hidden template part that gets copied and animated.
local function playMesh(template: BasePart, ctx: Ctx): number
	local delay = num(template, "EmitDelay", 0)
	local duration = num(template, "AnimDuration", 0.5)
	local scale0, scale1 = num(template, "Scale0", 0.6), num(template, "Scale1", 1.4)
	local spin = vec(template, "SpinDeg", Vector3.new(0, 90, 0))
	local fade0 = num(template, "BaseTransparency", 0)
	local local_ = originOf(ctx.root):ToObjectSpace(template.CFrame)
	local baseSize = template.Size
	local copy = template:Clone()
	for _, d in copy:GetDescendants() do
		if d:IsA("BaseScript") then
			d:Destroy()
		end
	end
	copy.Archivable = false
	copy.Anchored = true
	copy.CanCollide = false
	copy.CanTouch = false
	copy.CanQuery = false
	copy.CastShadow = false
	local cf = ctx.origin * local_
	local function step(alpha: number)
		local e = ease(alpha, "Out")
		copy.Size = baseSize * lerp(scale0, scale1, e)
		copy.CFrame = cf * CFrame.Angles(math.rad(spin.X * e), math.rad(spin.Y * e), math.rad(spin.Z * e))
		copy.Transparency = if alpha < 0.35 then fade0 else lerp(fade0, 1, ((alpha - 0.35) / 0.65) ^ 2)
	end
	step(0)
	addAnim(delay, duration, function()
		copy.Parent = liveFolder()
	end, step, function()
		copy:Destroy()
	end)
	return delay + duration
end

local function findByName(name: string): Instance?
	for _, inst in CollectionService:GetTagged(EasyVFX.Tag) do
		if inst.Name == name then
			return inst
		end
	end
	return nil
end

-- Plays an effect on this machine only. Returns how long it lasts.
function EasyVFX.PlayLocal(target: Instance | string, at: CFrame?): number
	local root: Instance? = if typeof(target) == "string" then findByName(target) else target
	if not root or not root.Parent then
		return 0
	end
	if at then
		-- Play a temporary copy somewhere else.
		local copy = root:Clone()
		for _, d in copy:GetDescendants() do
			if d:IsA("JointInstance") or d:IsA("WeldConstraint") or d:IsA("BaseScript") then
				d:Destroy()
			end
		end
		copy:RemoveTag(EasyVFX.Tag)
		copy.Archivable = false
		if copy:IsA("BasePart") then
			copy.Anchored = true
			copy.CFrame = at
		elseif copy:IsA("Model") then
			copy:PivotTo(at)
		end
		copy.Parent = liveFolder()
		local length = EasyVFX.PlayLocal(copy)
		local maxLife = 0
		for _, d in copy:GetDescendants() do
			if d:IsA("ParticleEmitter") then
				maxLife = math.max(maxLife, d.Lifetime.Max)
			end
		end
		task.delay(length + maxLife + 0.5, function()
			copy:Destroy()
		end)
		return length
	end

	local ignore: { Instance } = { liveFolder(), root }
	local model = root:FindFirstAncestorOfClass("Model")
	if model then
		table.insert(ignore, model)
	end
	for _, p in Players:GetPlayers() do
		if p.Character then
			table.insert(ignore, p.Character)
		end
	end
	local ctx: Ctx = {
		root = root,
		origin = originOf(root),
		quality = math.clamp(EasyVFX.Quality, 0.25, 1),
		rng = Random.new(),
		ignore = ignore,
	}

	local length = 0
	for _, d in root:GetDescendants() do
		local delay = num(d, "EmitDelay", 0)
		local duration = d:GetAttribute("EmitDuration")
		if d:IsA("ParticleEmitter") then
			local count = d:GetAttribute("EmitCount")
			if type(count) == "number" and count > 0 then
				local n = math.max(1, math.floor(count * ctx.quality + 0.5))
				if delay > 0 then
					task.delay(delay, function()
						if d.Parent then
							d:Emit(n)
						end
					end)
				else
					d:Emit(n)
				end
				length = math.max(length, delay + d.Lifetime.Max)
			end
			if type(duration) == "number" and duration > 0 then
				pulse(d, delay, duration)
				length = math.max(length, delay + duration + d.Lifetime.Max)
			end
		elseif d:IsA("Beam") or d:IsA("Trail") or d:IsA("Light") or d:IsA("Highlight") then
			if type(duration) == "number" and duration > 0 then
				pulse(d, delay, duration)
				length = math.max(length, delay + duration)
			end
		elseif d:IsA("Configuration") then
			local kind = d:GetAttribute("Kind")
			local shape = if type(kind) == "string" then Shapes[kind] else nil
			if shape then
				local ok, result = pcall(shape, d, ctx)
				if ok then
					length = math.max(length, result)
				else
					warn("[EasyVFX] " .. d:GetFullName() .. ": " .. tostring(result))
				end
			end
		elseif d:IsA("BasePart") then
			if d:GetAttribute("VFX_Mesh") then
				length = math.max(length, playMesh(d, ctx))
			elseif type(duration) == "number" and duration > 0 then
				pulse(d, delay, duration)
				length = math.max(length, delay + duration)
			end
		end
	end
	return length
end

local playEvent: RemoteEvent? = nil

-- Plays an effect for everyone (server) or locally (client / Studio preview).
function EasyVFX.Play(target: Instance | string, at: CFrame?): number
	if RunService:IsRunning() and RunService:IsServer() then
		local root: Instance? = if typeof(target) == "string" then findByName(target) else target
		if root and playEvent then
			playEvent:FireAllClients(root, at)
		end
		return 0
	end
	return EasyVFX.PlayLocal(target, at)
end

-- Turns the always-on layers (looping emitters, beams, lights...) on or off.
function EasyVFX.SetEnabled(root: Instance, on: boolean)
	for _, d in root:GetDescendants() do
		if d:GetAttribute("EmitCount") == nil and d:GetAttribute("EmitDuration") == nil and d:GetAttribute("VFX_Layer") ~= nil then
			setOn(d, on)
		end
	end
end

-- True when the effect has pieces that only show when played (bursts, shapes...).
function EasyVFX.HasBursts(root: Instance): boolean
	for _, d in root:GetDescendants() do
		if d:GetAttribute("EmitCount") ~= nil or d:GetAttribute("EmitDuration") ~= nil or d:GetAttribute("VFX_Mesh") then
			return true
		end
		if d:IsA("Configuration") and d:GetAttribute("Kind") ~= nil then
			return true
		end
	end
	return false
end

------------------------------------------------------------------------------------
-- No-code triggers. Started by the two tiny scripts the plugin installs.
------------------------------------------------------------------------------------

local function triggerPart(root: Instance): BasePart?
	local parent = root.Parent
	if parent and parent:IsA("BasePart") then
		return parent
	elseif parent and parent:IsA("Model") then
		return parent.PrimaryPart or parent:FindFirstChildWhichIsA("BasePart")
	elseif root:IsA("BasePart") then
		return root
	end
	return nil
end

local function watchTagged(setup: (root: Instance) -> (() -> ())?)
	local cleanups: { [Instance]: () -> () } = {}
	local function stop(root: Instance)
		local c = cleanups[root]
		cleanups[root] = nil
		if c then
			c()
		end
	end
	local function start(root: Instance)
		stop(root)
		local c = setup(root)
		if c then
			cleanups[root] = c
		end
	end
	local function added(root: Instance)
		start(root)
		root:GetAttributeChangedSignal("VFX_Trigger"):Connect(function()
			if CollectionService:HasTag(root, EasyVFX.Tag) then
				start(root)
			end
		end)
	end
	CollectionService:GetInstanceAddedSignal(EasyVFX.Tag):Connect(added)
	CollectionService:GetInstanceRemovedSignal(EasyVFX.Tag):Connect(stop)
	for _, root in CollectionService:GetTagged(EasyVFX.Tag) do
		task.spawn(added, root)
	end
end

function EasyVFX.InitServer()
	local existing = script:FindFirstChild("PlayEvent")
	if existing and existing:IsA("RemoteEvent") then
		playEvent = existing
	else
		local remote = Instance.new("RemoteEvent")
		remote.Name = "PlayEvent"
		remote.Parent = script
		playEvent = remote
	end

	watchTagged(function(root)
		local trigger = str(root, "VFX_Trigger", "Always")
		local part = triggerPart(root)
		if not part then
			return nil
		end
		local cooldown = num(root, "VFX_Cooldown", 1)
		local last = -math.huge
		local function fire(player: Player?)
			if os.clock() - last < cooldown then
				return
			end
			last = os.clock()
			EasyVFX.Play(root)
		end

		if trigger == "Touch" then
			local playersOnly = bool(root, "VFX_PlayersOnly", true)
			if part == root then
				part.CanTouch = true
			end
			local conn = part.Touched:Connect(function(hit)
				local character = hit:FindFirstAncestorOfClass("Model")
				local player = character and Players:GetPlayerFromCharacter(character)
				if playersOnly and not player then
					return
				end
				fire(player)
			end)
			return function()
				conn:Disconnect()
			end
		elseif trigger == "Click" then
			local detector = Instance.new("ClickDetector")
			detector.Name = "EasyVFX_Click"
			detector.MaxActivationDistance = num(root, "VFX_Distance", 32)
			detector.Parent = part
			local conn = detector.MouseClick:Connect(fire)
			return function()
				conn:Disconnect()
				detector:Destroy()
			end
		elseif trigger == "Prompt" then
			local prompt = Instance.new("ProximityPrompt")
			prompt.Name = "EasyVFX_Prompt"
			prompt.ActionText = str(root, "VFX_PromptText", "Use")
			prompt.ObjectText = ""
			prompt.HoldDuration = 0
			prompt.RequiresLineOfSight = false
			prompt.MaxActivationDistance = num(root, "VFX_Distance", 12)
			prompt.Parent = if root:IsA("BasePart") then root else part
			local conn = prompt.Triggered:Connect(fire)
			return function()
				conn:Disconnect()
				prompt:Destroy()
			end
		end
		return nil
	end)
end

function EasyVFX.InitClient()
	local function readQuality()
		local ok, level = pcall(function()
			return UserSettings():GetService("UserGameSettings").SavedQualityLevel.Value
		end)
		if ok and type(level) == "number" and level > 0 then
			EasyVFX.Quality = math.clamp(level / 7, 0.35, 1)
		else
			EasyVFX.Quality = 1
		end
	end
	readQuality()
	pcall(function()
		UserSettings():GetService("UserGameSettings"):GetPropertyChangedSignal("SavedQualityLevel"):Connect(readQuality)
	end)

	local remote = script:WaitForChild("PlayEvent", 30)
	if remote and remote:IsA("RemoteEvent") then
		remote.OnClientEvent:Connect(function(root: Instance?, at: CFrame?)
			if root then
				EasyVFX.PlayLocal(root, at)
			end
		end)
	end

	-- Looping effects run on each client so the network stays quiet.
	watchTagged(function(root)
		local trigger = str(root, "VFX_Trigger", "Always")
		local loops = trigger == "Loop" or (trigger == "Always" and EasyVFX.HasBursts(root))
		if not loops then
			return nil
		end
		local running = true
		task.spawn(function()
			task.wait(math.random() * 0.3)
			while running and root.Parent do
				local length = EasyVFX.PlayLocal(root)
				task.wait(math.max(0.2, num(root, "VFX_Interval", math.max(1, length))))
			end
		end)
		return function()
			running = false
		end
	end)
end

return EasyVFX
