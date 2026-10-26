--!strict
--[[
	EasyVFX runtime  (installed by the EasyVFX plugin as ReplicatedStorage.EasyVFX)

	Plays effects made with the EasyVFX plugin. You never have to edit this file.

	For scripters:
		local EasyVFX = require(game.ReplicatedStorage.EasyVFX)
		EasyVFX.Play(workspace.Part.VFX_Explosion)          -- play an effect where it is
		EasyVFX.Play("VFX_Explosion", CFrame.new(0, 5, 0))  -- play a copy somewhere else
		EasyVFX.SetEnabled(effect, false)                    -- turn looping layers off
		EasyVFX.BindAnimation(track, character)              -- fire effects at animation markers

	How it works:
	  * Called on the server, Play() asks every client to play the effect (one small
	    RemoteEvent). Particles, beams and meshes are then created and animated on each
	    client, which is what the Roblox DevForum recommends for smooth, lag-free VFX.
	  * Called on a client (or in Studio edit mode for previews) it plays locally.
	  * Emitters follow the community attribute convention: EmitCount, EmitDelay and
	    EmitDuration, so effects stay compatible with other emit tools.
	  * "Shape" layers (Configuration objects with a Kind attribute) are crisp,
	    procedural pieces built from Beams and Neon parts: Ring, Slash, Lines, Bolt,
	    Orb, Debris, Crater and Jet.
]]

local CollectionService = game:GetService("CollectionService")
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local EasyVFX = {}
EasyVFX.Version = 11
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
	elseif style == "Circ" then
		-- circular out: the fastest start, a long glide (slashes, shockwaves)
		return math.sqrt(1 - (alpha - 1) ^ 2)
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
	scale: number,
}

local active: { Anim } = {}
-- The effect clock: every delayed emit, pulse and animation of a play runs on this driver,
-- so a hit-stop or an effect's VFX_TimeScale moves all of it together (docs/vfx-grammar.md,
-- "Curves and exits"). playScale is the time scale of the play being set up; addAnim takes it.
local playScale = 1
-- Emitters of plays still running, so a hit-stop can freeze their particles too.
local liveEmitters: { [ParticleEmitter]: boolean } = setmetatable({}, { __mode = "k" }) :: any
local driverRunning = false
-- Hit-stop: while os.clock() < frozenUntil every running effect holds its frame.
local frozenUntil = 0

-- True while an instance is still in the game. Reading a destroyed one is safe in Roblox
-- (Parent is nil) but raises in some hosts, so the effect clock's callbacks ask this.
local function alive(inst: Instance): boolean
	local ok, parent = pcall(function()
		return inst.Parent
	end)
	return ok and parent ~= nil
end

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
			if os.clock() < frozenUntil then
				dt = 0
			end
			local i = 1
			while i <= #active do
				local a = active[i]
				a.t += dt * a.scale
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
		scale = playScale,
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
	coreGlow: number,
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
		-- Dark effects: Glow = 0 gives an opaque, unlit body (black really covers the
		-- scene), while CoreGlow keeps the thin core additive and bright.
		coreGlow = math.clamp(num(cfg, "CoreGlow", num(cfg, "Glow", 1)), 0, 1),
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
	-- Not FaceCamera: each Beam would turn to the camera on its own, so chained
	-- beams show a notch at every joint. Instead every step orients the shared
	-- attachments towards the camera (ribbonFrame), which gives one seamless,
	-- camera-facing ribbon. Its width follows the attachments' Y axes.
	b.FaceCamera = false
	b.Segments = 12
	b.LightEmission = if isCore then style.coreGlow else style.glow
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

-- Where the camera is, in a carrier's local space.
local function eyeIn(carrier: BasePart): Vector3
	local camera = Workspace.CurrentCamera
	local world = if camera then camera.CFrame.Position else carrier.Position + Vector3.new(0, 1000, 0)
	return carrier.CFrame:PointToObjectSpace(world)
end

-- Attachment frame for a camera-facing ribbon: X follows the path (the axis Beam
-- curves bend along), Y (the width) is perpendicular to both the path and the
-- view direction. Neighbouring beams share the attachment, so they meet exactly.
local function ribbonFrame(p: Vector3, tangent: Vector3, eye: Vector3): CFrame
	local x = if tangent.Magnitude > 1e-5 then tangent.Unit else Vector3.xAxis
	local y = x:Cross(eye - p)
	if y.Magnitude < 1e-5 then
		y = x:Cross(if math.abs(x.Y) < 0.99 then Vector3.yAxis else Vector3.zAxis)
	end
	y = y.Unit
	return CFrame.fromMatrix(p, x, y, x:Cross(y))
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

-- `roll` and `roll2` are random numbers drawn once per play that every shape shares, so shapes
-- can turn together
type Ctx = { root: Instance, origin: CFrame, quality: number, rng: Random, roll: number, roll2: number, ignore: { Instance } }

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
			local eye = eyeIn(carrier)
			for k = 1, 4 do
				local th = (k - 1) * math.pi / 2 + rot
				local p = Vector3.new(math.cos(th) * r, 0, math.sin(th) * r)
				local t = Vector3.new(-math.sin(th), 0, math.cos(th))
				atts[k].CFrame = ribbonFrame(p, t, eye)
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

-- Anime crescent slash: a blade-shaped crescent that wipes in fast, then erodes from
-- the tail towards the head.
--   * The outer edge is one clean arc; the width grows inwards, peaks near the head
--     and ends in a needle tip, with a long thin tail (not a symmetric banana).
--   * Three tones across the blade, like anime slashes: a deep shade along the inner
--     edge, the main-color body (gradient tail -> head) and a thin white-hot edge on
--     the outer rim. Beams can't fade across their width, so the glow itself is left
--     to Bloom instead of a flat, muddy halo ribbon.
--   * All segments cover only the visible part of the arc, so the curve and tips stay
--     smooth while it erodes.
local SLASH_PEAK = 0.736 ^ 1.4 * (1 - 0.736) ^ 0.5

local function bladeWidth(g: number): number
	g = math.clamp(g, 0, 1)
	return (g ^ 1.4) * (1 - g) ^ 0.5 / SLASH_PEAK
end

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
	local N = 12
	-- width multiplier, inward offset of the ribbon's center (x width), core look
	local layers = {
		{ key = "body", widthK = 1, offK = 0.5, isCore = false, on = true },
		{ key = "inner", widthK = 0.38, offK = 0.8, isCore = false, on = style.glow > 0.05 },
		{ key = "edge", widthK = 0.26, offK = 0.13, isCore = true, on = style.core },
	}

	for i = 0, count - 1 do
		local roll = if randomTilt > 0 then ctx.rng:NextNumber(-randomTilt, randomTilt) else 0
		local yaw = if randomTilt > 0 then ctx.rng:NextNumber(-randomTilt, randomTilt) * 0.4 else 0
		local cf = base * CFrame.Angles(0, math.rad(yaw), math.rad(roll))
		local carrier = newPart(cf)
		local chains = {}
		for _, layer in layers do
			if layer.on then
				local atts: { Attachment } = {}
				local beams: { Beam } = {}
				for k = 0, N do
					atts[k + 1] = newAttachment(carrier)
				end
				for k = 1, N do
					local b = newBeam(carrier, atts[k], atts[k + 1], style, layer.isCore)
					b.Segments = 8
					-- keep the body and the shade saturated; only the edge is white-hot
					if layer.key == "body" then
						b.Brightness = style.brightness * 0.65
					elseif layer.key == "inner" then
						b.Brightness = style.brightness * 0.8
						b.ZOffset = style.zOffset + 0.05
					elseif layer.key == "edge" then
						b.Brightness = style.brightness * 2
						b.ZOffset = style.zOffset + 0.1
					end
					beams[k] = b
				end
				table.insert(chains, { layer = layer, atts = atts, beams = beams })
			end
		end
		local start = -math.pi / 2 - arc / 2
		local function step(alpha: number)
			local e = ease(alpha, style.ease)
			-- fast wipe in, then the tail eats towards the head
			local head = 1 - (1 - math.min(1, alpha / 0.2)) ^ 3
			local tail = math.clamp((alpha - 0.3) / 0.7, 0, 1) ^ 1.5
			local spanF = math.max(0.002, head - tail)
			local r = radius * (1 + 0.08 * e)
			local fadeOut = math.clamp((alpha - 0.75) / 0.25, 0, 1) ^ 2
			local baseT = lerp(style.fade0, 1, fadeOut)
			local thin = 1 - 0.35 * tail
			carrier.CFrame = cf * CFrame.Angles(0, lerp(-sweep / 2, sweep / 2, e), 0)
			local eye = eyeIn(carrier)
			local dTheta = arc * spanF / N
			local kappa = KAPPA * math.tan(dTheta / 4)
			for _, chain in chains do
				local layer = chain.layer
				local rc = table.create(N + 1, 0)
				local wk = table.create(N + 1, 0)
				for k = 0, N do
					local g = k / N
					local w = width * bladeWidth(g) * thin
					wk[k + 1] = w
					rc[k + 1] = r - w * layer.offK
					local th = start + arc * (tail + spanF * g)
					local p = Vector3.new(math.cos(th) * rc[k + 1], 0, math.sin(th) * rc[k + 1])
					local t = Vector3.new(-math.sin(th), 0, math.cos(th))
					chain.atts[k + 1].CFrame = ribbonFrame(p, t, eye)
				end
				for k = 1, N do
					local g0, g1 = (k - 1) / N, k / N
					local b = chain.beams[k]
					b.CurveSize0, b.CurveSize1 = rc[k] * kappa, rc[k + 1] * kappa
					b.Width0, b.Width1 = wk[k] * layer.widthK, wk[k + 1] * layer.widthK
					-- the tail end is a little see-through; everything fades together at the end
					local t0 = lerp(baseT, 1, ((1 - g0) ^ 3) * tailFade * 0.6)
					local t1 = lerp(baseT, 1, ((1 - g1) ^ 3) * tailFade * 0.6)
					if layer.key == "inner" then
						b.Transparency = NumberSequence.new(t0, t1)
						local deep = style.color1:Lerp(Color3.new(0, 0, 0), 0.3)
						b.Color = ColorSequence.new(deep:Lerp(style.color0, g0 * 0.35), deep:Lerp(style.color0, g1 * 0.35))
					elseif layer.key == "edge" then
						b.Transparency = NumberSequence.new(t0, t1)
						b.Color = ColorSequence.new(style.coreColor:Lerp(style.color0, (1 - g0) * 0.6), style.coreColor:Lerp(style.color0, (1 - g1) * 0.6))
					else
						b.Transparency = NumberSequence.new(t0, t1)
						-- one gradient across the whole blade: second color at the tail, main at the head
						b.Color = ColorSequence.new(style.color1:Lerp(style.color0, g0), style.color1:Lerp(style.color0, g1))
					end
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
			local eye = eyeIn(carrier)
			a0.CFrame = ribbonFrame(dir * tail, dir, eye)
			a1.CFrame = ribbonFrame(dir * ((tail + head) / 2), dir, eye)
			a2.CFrame = ribbonFrame(dir * head, dir, eye)
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

-- A chain of camera-facing beams through `count + 1` attachments on `carrier`
-- (the building block of Whirl, Streak and Crackle).
local function beamChain(carrier: BasePart, count: number, style: Style, isCore: boolean): ({ Attachment }, { Beam })
	local atts: { Attachment } = {}
	local beams: { Beam } = {}
	for k = 0, count do
		atts[k + 1] = newAttachment(carrier)
	end
	for k = 1, count do
		beams[k] = newBeam(carrier, atts[k], atts[k + 1], style, isCore)
	end
	return atts, beams
end

-- With a Texture, a chain shows one beam from its first to its last attachment, so
-- the texture (a brush stroke, an electric arc) spans the whole stroke once instead
-- of repeating on every segment. The segment beams stay as the untextured fallback.
local function texturedSpan(carrier: BasePart, atts: { Attachment }, beams: { Beam }, cores: { Beam }?, style: Style): Beam?
	if style.texture == "" then
		return nil
	end
	for _, b in beams do
		b.Enabled = false
	end
	if cores then
		for _, b in cores do
			b.Enabled = false
		end
	end
	local b = newBeam(carrier, atts[1], atts[#atts], style, false)
	b.Segments = 24
	return b
end

-- Whirl: a tilted disc of brush-stroke arcs spinning around the center (wind
-- vortex, cyclone kick, spinning slash). Every stroke is tapered at both ends and
-- has its own radius, length and speed, so it reads as a swirl, not a ring. With
-- Strands > 1 each stroke is a bundle of thin lines (anime wind) instead of one
-- band. Strokes are always smooth segment chains: one textured Bezier beam over a
-- long arc twists and shows blunt, square ends, so Whirl ignores Texture.
Shapes.Whirl = function(cfg, ctx)
	local strokes = math.clamp(math.floor(num(cfg, "Count", 6)), 1, 16)
	local strands = math.clamp(math.floor(num(cfg, "Strands", 1)), 1, 4)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.9)
	local r0, r1 = num(cfg, "Radius0", 2), num(cfg, "Radius1", 6)
	local width = num(cfg, "Width", 0.7)
	local arcMin, arcMax = math.rad(num(cfg, "ArcMin", 70)), math.rad(num(cfg, "ArcMax", 200))
	local spin = math.rad(num(cfg, "Spin", 540))
	local grow = num(cfg, "Grow", 0.35)
	local style = readStyle(cfg)
	local base = ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero))
	if bool(cfg, "Ground", false) then
		base = snapToGround(base, ctx.ignore)
	end
	base *= rad(vec(cfg, "Tilt", Vector3.zero))
	local N = 10
	local carrier = newPart(base)
	local list = {}
	for i = 1, strokes do
		local radius = lerp(r0, r1, (i - 0.5) / strokes) * ctx.rng:NextNumber(0.9, 1.1)
		local arc = ctx.rng:NextNumber(arcMin, arcMax)
		local phase = ctx.rng:NextNumber(0, math.pi * 2)
		local speed = ctx.rng:NextNumber(0.75, 1.25)
		local lift = ctx.rng:NextNumber(-0.15, 0.15) * r1
		local w = width * ctx.rng:NextNumber(0.6, 1.2)
		for s = 1, strands do
			-- the main strand carries the hot core; the others are thinner, shorter
			-- and slightly off-radius, trailing behind it
			local main = s == 1
			local atts, beams = beamChain(carrier, N, style, false)
			local cores = if style.core and main then select(2, beamChain(carrier, N, style, true)) else nil
			table.insert(list, {
				atts = atts,
				beams = beams,
				cores = cores,
				radius = radius + (if main then 0 else ctx.rng:NextNumber(-1, 1) * w * 1.6),
				arc = arc * (if main then 1 else ctx.rng:NextNumber(0.45, 0.85)),
				phase = phase - (if main then 0 else ctx.rng:NextNumber(0.05, 0.35)),
				speed = speed,
				lift = lift,
				width = if main then w else w * ctx.rng:NextNumber(0.3, 0.55),
				fade = if main then 0 else ctx.rng:NextNumber(0.15, 0.4),
			})
		end
	end
	local function step(alpha: number)
		local e = ease(alpha, style.ease)
		-- in fast, hold, then thin out and fade
		local env = math.min(1, alpha / 0.15) * (1 - math.clamp((alpha - 0.65) / 0.35, 0, 1) ^ 1.5)
		local eye = eyeIn(carrier)
		for _, sd in list do
			local tr = lerp(1, lerp(style.fade0, 1, sd.fade), env)
			local r = sd.radius * (1 + grow * e)
			local start = sd.phase + spin * e * sd.speed
			local dTheta = sd.arc / N
			local c = r * KAPPA * math.tan(dTheta / 4)
			for k = 0, N do
				local th = start + dTheta * k
				local p = Vector3.new(math.cos(th) * r, sd.lift * math.sin(th * 0.5), math.sin(th) * r)
				local t = Vector3.new(-math.sin(th), 0, math.cos(th))
				sd.atts[k + 1].CFrame = ribbonFrame(p, t, eye)
			end
			for k = 1, N do
				local g0, g1 = (k - 1) / N, k / N
				-- a comet: thin tail, full just behind the head, sharp point at the head
				local w0 = sd.width * (math.sin(math.pi * g0 ^ 1.6) ^ 0.8) * env
				local w1 = sd.width * (math.sin(math.pi * g1 ^ 1.6) ^ 0.8) * env
				local b = sd.beams[k]
				b.CurveSize0, b.CurveSize1 = c, c
				b.Width0, b.Width1 = w0, w1
				b.Transparency = NumberSequence.new(lerp(tr, 1, (1 - g0) ^ 2 * 0.85), lerp(tr, 1, (1 - g1) ^ 2 * 0.85))
				b.Color = ColorSequence.new(style.color1:Lerp(style.color0, g0), style.color1:Lerp(style.color0, g1))
				local cb = sd.cores and sd.cores[k]
				if cb then
					cb.CurveSize0, cb.CurveSize1 = c, c
					cb.Width0, cb.Width1 = w0 * 0.3, w1 * 0.3
					cb.Transparency = b.Transparency
				end
			end
		end
	end
	step(0)
	addAnim(delay, duration, function()
		carrier.Parent = liveFolder()
	end, step, function()
		carrier:Destroy()
	end)
	return delay + duration
end

-- Streak: a straight dash line from Offset to To that wipes in almost instantly,
-- then erodes from the tail (flash step, lunge, piercing thrust). With Smear > 0 a
-- wider unlit dark ribbon lingers behind it (the afterimage of a fast dash).
Shapes.Streak = function(cfg, ctx)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.35)
	local from = vec(cfg, "Offset", Vector3.zero)
	local to = vec(cfg, "To", Vector3.new(0, 0, -20))
	local width = num(cfg, "Width", 0.6)
	local smear = num(cfg, "Smear", 0)
	local style = readStyle(cfg)
	local cf = ctx.origin * rad(vec(cfg, "Tilt", Vector3.zero))
	local N = 8
	local carrier = newPart(cf)
	local dir = to - from
	local smearAtts, smearBeams
	if smear > 0 then
		local dark = table.clone(style)
		dark.glow, dark.coreGlow = 0, 0
		dark.color0, dark.color1 = Color3.fromRGB(10, 8, 14), Color3.fromRGB(10, 8, 14)
		smearAtts, smearBeams = beamChain(carrier, N, dark, false)
	end
	local atts, beams = beamChain(carrier, N, style, false)
	local cores = if style.core then select(2, beamChain(carrier, N, style, true)) else nil
	local span = texturedSpan(carrier, atts, beams, cores, style)
	local function place(chain: { Attachment }, a: number, b: number, eye: Vector3)
		for k = 0, N do
			local f = lerp(a, b, k / N)
			chain[k + 1].CFrame = ribbonFrame(from + dir * f, dir, eye)
		end
	end
	local function step(alpha: number)
		local head = 1 - (1 - math.min(1, alpha / 0.12)) ^ 3
		local tail = math.clamp((alpha - 0.2) / 0.8, 0, 1) ^ 1.3
		local eye = eyeIn(carrier)
		place(atts, tail, head, eye)
		for k = 1, N do
			local g0, g1 = (k - 1) / N, k / N
			-- needle tip at the head, thin at the tail
			local w0 = width * math.sin(math.pi * math.min(1, g0 * 1.15)) ^ 0.6
			local w1 = width * math.sin(math.pi * math.min(1, g1 * 1.15)) ^ 0.6
			local b = beams[k]
			b.Width0, b.Width1 = w0, w1
			b.Transparency = NumberSequence.new(lerp(style.fade0, 1, (1 - g0) * 0.7), lerp(style.fade0, 1, (1 - g1) * 0.7))
			b.Color = ColorSequence.new(style.color1:Lerp(style.color0, g0), style.color1:Lerp(style.color0, g1))
			local cb = cores and cores[k]
			if cb then
				cb.Width0, cb.Width1 = w0 * 0.35, w1 * 0.35
				cb.Transparency = b.Transparency
			end
		end
		if span then
			span.Width0, span.Width1 = width * 1.8, width * 1.8
			span.Transparency = NumberSequence.new(lerp(style.fade0, 1, 0.35), style.fade0)
			span.Color = ColorSequence.new(style.color1, style.color0)
		end
		if smearAtts and smearBeams then
			-- the smear starts where the dash started and lingers longer
			local sTail = math.clamp((alpha - 0.35) / 0.65, 0, 1)
			place(smearAtts, sTail, head * 0.97, eye)
			local fade = math.clamp((alpha - 0.5) / 0.5, 0, 1)
			for k = 1, N do
				local g0, g1 = (k - 1) / N, k / N
				local b = smearBeams[k]
				b.Width0 = width * smear * math.sin(math.pi * g0) ^ 0.5
				b.Width1 = width * smear * math.sin(math.pi * g1) ^ 0.5
				b.Transparency = NumberSequence.new(lerp(0.25, 1, fade), lerp(0.25, 1, fade))
			end
		end
	end
	step(0)
	addAnim(delay, duration, function()
		carrier.Parent = liveFolder()
	end, step, function()
		carrier:Destroy()
	end)
	return delay + duration
end

-- Jet: one textured beam shooting up out of Offset, turned by Tilt, the texture a whole
-- jet stretched over it (TextureMode Stretch), base at Attachment0. It flashes in (Brightness
-- times Flash, falling back over FlashFor of its life), then narrows from Width0 to Width1
-- as it stretches from Length0 to Length1, and fades from FadeStart (the fire pit's jets).
Shapes.Jet = function(cfg, ctx)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.1)
	local from = vec(cfg, "Offset", Vector3.zero)
	local length0 = num(cfg, "Length0", 4)
	local length1 = num(cfg, "Length1", 8)
	local width0 = num(cfg, "Width0", 3)
	local width1 = num(cfg, "Width1", 1)
	local flash = num(cfg, "Flash", 2)
	local flashFor = math.max(0.01, num(cfg, "FlashFor", 0.3))
	local style = readStyle(cfg)
	-- Offset is where the base sits in the effect's own space; Tilt turns the jet about it. A set
	-- of jets keeps its shape and changes as one each play, with the same random numbers for every
	-- jet: Sway (degrees) tips the whole set within its own plane (about the effect's Z axis), and
	-- Mirror 1 flips it left for right half the time. It never turns edge-on to the view, so the
	-- jets never fold into each other
	local sway = (ctx.roll - 0.5) * num(cfg, "Sway", 0)
	local flip = if num(cfg, "Mirror", 0) > 0 and ctx.roll2 < 0.5 then math.pi else 0
	local turn = CFrame.Angles(0, flip, 0) * CFrame.Angles(0, 0, math.rad(sway))
	local carrier = newPart(ctx.origin * CFrame.new(from) * turn * rad(vec(cfg, "Tilt", Vector3.zero)))
	local a0, a1 = newAttachment(carrier), newAttachment(carrier)
	local b = Instance.new("Beam")
	b.Archivable = false
	b.Attachment0, b.Attachment1 = a0, a1
	b.FaceCamera = true
	b.Segments = 12
	b.LightEmission = style.glow
	b.LightInfluence = 0
	b.Color = ColorSequence.new(style.color0)
	b.ZOffset = style.zOffset
	b.Texture = style.texture
	b.TextureMode = Enum.TextureMode.Stretch
	b.TextureLength = 1
	b.Parent = carrier
	local function step(alpha: number)
		local grow = ease(alpha, style.ease)
		a1.CFrame = CFrame.new(0, lerp(length0, length1, grow), 0)
		local w = lerp(width0, width1, grow)
		b.Width0, b.Width1 = w, w
		b.Brightness = style.brightness * lerp(flash, 1, math.min(1, alpha / flashFor))
		local fade = fadeAt(style, alpha)
		b.Transparency = NumberSequence.new(fade)
	end
	step(0)
	addAnim(delay, duration, function()
		carrier.Parent = liveFolder()
	end, step, function()
		carrier:Destroy()
	end)
	return delay + duration
end

-- Crackle: short electric arcs that jump along a crescent (the electricity running
-- over a lightning slash) or around a center. Each arc is a small zig-zag that
-- re-shapes and flickers every few frames.
Shapes.Crackle = function(cfg, ctx)
	local count = scaledCount(cfg, "Count", 8, ctx.quality)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.45)
	local radius = num(cfg, "Radius", 5)
	local arc = math.rad(math.clamp(num(cfg, "Arc", 160), 10, 360))
	local length = num(cfg, "Length", 1.6)
	local jitter = num(cfg, "Jitter", 0.5)
	local width = num(cfg, "Width", 0.12)
	local flicker = math.max(0.02, num(cfg, "Flicker", 0.05))
	local style = readStyle(cfg)
	local cf = ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero)) * rad(vec(cfg, "Tilt", Vector3.zero))
	local SEG = 4
	local carrier = newPart(cf)
	local arcs = {}
	for _ = 1, count do
		local atts, beams = beamChain(carrier, SEG, style, false)
		local cores = if style.core then select(2, beamChain(carrier, SEG, style, true)) else nil
		for _, b in beams do
			b.Segments = 1
		end
		if cores then
			for _, b in cores do
				b.Segments = 1
			end
		end
		local span = texturedSpan(carrier, atts, beams, cores, style)
		if span then
			span.Segments = 1
		end
		table.insert(arcs, { atts = atts, beams = beams, cores = cores, span = span, pts = {}, timer = math.huge, on = true })
	end
	local start = -math.pi / 2 - arc / 2
	local function reshape(a)
		local th = start + arc * ctx.rng:NextNumber()
		local r = radius * ctx.rng:NextNumber(0.85, 1.05)
		local center = Vector3.new(math.cos(th) * r, 0, math.sin(th) * r)
		local tangent = Vector3.new(-math.sin(th), 0, math.cos(th))
		local side = Vector3.new(math.cos(th), 0, math.sin(th))
		for k = 0, SEG do
			local f = k / SEG - 0.5
			local off = (side * ctx.rng:NextNumber(-1, 1) + Vector3.yAxis * ctx.rng:NextNumber(-1, 1)) * jitter * math.sin(math.pi * (f + 0.5))
			a.pts[k + 1] = center + tangent * f * length + off
		end
		a.on = ctx.rng:NextNumber() > 0.2
	end
	local function step(alpha: number, dt: number)
		local eye = eyeIn(carrier)
		local tr = fadeAt(style, alpha)
		for _, a in arcs do
			a.timer += dt
			if a.timer >= flicker then
				a.timer = 0
				reshape(a)
			end
			for k = 1, SEG + 1 do
				local prev = a.pts[math.max(1, k - 1)]
				local nxt = a.pts[math.min(SEG + 1, k + 1)]
				a.atts[k].CFrame = ribbonFrame(a.pts[k], nxt - prev, eye)
			end
			local t = if a.on then tr else 1
			local seq = NumberSequence.new(t)
			for k = 1, SEG do
				local b = a.beams[k]
				b.Width0, b.Width1 = width, width
				b.Transparency = seq
				b.Color = ColorSequence.new(style.color0)
				local cb = a.cores and a.cores[k]
				if cb then
					cb.Width0, cb.Width1 = width * 0.4, width * 0.4
					cb.Transparency = seq
				end
			end
			if a.span then
				-- the texture carries the zig-zag; the strip is about 8:1
				a.span.Width0, a.span.Width1 = length * 0.3, length * 0.3
				a.span.Transparency = seq
				a.span.Color = ColorSequence.new(style.color0)
			end
		end
	end
	step(0, math.huge)
	addAnim(delay, duration, function()
		carrier.Parent = liveFolder()
	end, step, function()
		carrier:Destroy()
	end)
	return delay + duration
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
		local pts: { Vector3 } = {}
		local function reshape()
			for k = 0, segments do
				local f = k / segments
				local p = from:Lerp(to, f)
				local amount = math.sin(math.pi * f) * jitter
				local off = (u * ctx.rng:NextNumber(-1, 1) + v * ctx.rng:NextNumber(-1, 1)) * amount
				pts[k + 1] = p + off + sideOffset * math.sin(math.pi * f)
			end
		end
		local function step(alpha: number, dt: number)
			timer += dt
			if timer >= flicker then
				timer = 0
				reshape()
			end
			-- Mitered joints: each corner faces halfway between its two segments.
			local eye = eyeIn(carrier)
			for k = 1, segments + 1 do
				local prev = pts[math.max(1, k - 1)]
				local nxt = pts[math.min(segments + 1, k + 1)]
				atts[k].CFrame = ribbonFrame(pts[k], nxt - prev, eye)
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

-- 0 outside [lo, hi], 1 inside, with a soft edge of `soft` on both sides.
local function window(f: number, lo: number, hi: number, soft: number): number
	local a = math.clamp((f - lo) / soft, 0, 1)
	local b = math.clamp((hi - f) / soft, 0, 1)
	return math.min(a, b)
end

-- Twisting strands climbing a helix: tornadoes, charge-ups, vortex portals.
-- Pure geometry (curved Beams), so it stays razor sharp at any distance.
Shapes.Spiral = function(cfg, ctx)
	local strands = math.clamp(math.floor(num(cfg, "Count", 3)), 1, 8)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.9)
	local turns = math.clamp(num(cfg, "Turns", 2), 0.25, 8)
	local height = num(cfg, "Height", 8)
	local r0, r1 = num(cfg, "Radius0", 1), num(cfg, "Radius1", 3)
	local width = num(cfg, "Width", 0.5)
	local spin = math.rad(num(cfg, "Spin", 360))
	local trail = math.clamp(num(cfg, "TrailLength", 0.55), 0.05, 1)
	local style = readStyle(cfg)
	local base = ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero))
	if bool(cfg, "Ground", false) then
		base = snapToGround(base, ctx.ignore)
	end
	base *= rad(vec(cfg, "Tilt", Vector3.zero))
	local N = math.clamp(math.floor(turns * 8 + 0.5), 4, 32)
	local dTheta = turns * 2 * math.pi / N

	local carrier = newPart(base)
	local strandsData = {}
	for s = 1, strands do
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
		table.insert(strandsData, { atts = atts, beams = beams, cores = cores, phase = (s - 1) / strands * 2 * math.pi })
	end

	local function step(alpha: number)
		local e = ease(alpha, style.ease)
		-- The head climbs to the top, then the tail follows and the strand is gone.
		local head = math.min(1, alpha / 0.6) * (1 + trail)
		local tail = head - trail
		local rot = spin * e
		local tr = fadeAt(style, alpha)
		local color = ColorSequence.new(style.color0:Lerp(style.color1, e))
		local eye = eyeIn(carrier)
		for _, sd in strandsData do
			for k = 0, N do
				local f = k / N
				local th = sd.phase + rot + dTheta * k
				local r = lerp(r0, r1, f)
				local p = Vector3.new(math.cos(th) * r, height * f, math.sin(th) * r)
				local dr = (r1 - r0) / N
				local tangent = Vector3.new(
					-math.sin(th) * r * dTheta + math.cos(th) * dr,
					height / N,
					math.cos(th) * r * dTheta + math.sin(th) * dr
				)
				sd.atts[k + 1].CFrame = ribbonFrame(p, tangent, eye)
			end
			local c = lerp(r0, r1, 0.5) * KAPPA * math.tan(dTheta / 4)
			for k = 1, N do
				local f0, f1 = (k - 1) / N, k / N
				local v0 = window(f0, tail, head, 0.12)
				local v1 = window(f1, tail, head, 0.12)
				-- Taper towards the strand's tail and head, and to a point at the top.
				local w0 = width * math.sin(math.pi * math.clamp((f0 - tail) / trail, 0, 1)) * v0 * math.min(1, (1 - f0) / 0.15)
				local w1 = width * math.sin(math.pi * math.clamp((f1 - tail) / trail, 0, 1)) * v1 * math.min(1, (1 - f1) / 0.15)
				local t0, t1 = lerp(1, tr, v0), lerp(1, tr, v1)
				local b = sd.beams[k]
				b.CurveSize0, b.CurveSize1 = c * lerp(r0, r1, f0) / lerp(r0, r1, 0.5), c * lerp(r0, r1, f1) / lerp(r0, r1, 0.5)
				b.Width0, b.Width1 = w0, w1
				b.Transparency = NumberSequence.new(t0, t1)
				b.Color = color
				local cb = sd.cores[k]
				if cb then
					cb.CurveSize0, cb.CurveSize1 = b.CurveSize0, b.CurveSize1
					cb.Width0, cb.Width1 = w0 * 0.3, w1 * 0.3
					cb.Transparency = b.Transparency
				end
			end
		end
	end
	step(0)
	addAnim(delay, duration, function()
		carrier.Parent = liveFolder()
	end, step, function()
		carrier:Destroy()
	end)
	return delay + duration
end

-- Band: wide bands of textured wind (or energy) swinging round the centre: the ribbons that
-- wrap a tornado, a swirl round a landing (Phát's wind kit, 2026-10-26). Each band is a curved
-- Beam over an arc of at most 200 degrees, its texture one tile stretched along it
-- (TextureMode Stretch; TextureLength repeats it), scrolling with TextureSpeed. A cubic Bezier
-- stays within about 2% of a circle over a semicircle. Count bands share the layer, spread
-- round the circle, each a little off in radius, height, width and speed, so together they
-- have volume.
--   Orient "Wrap": the width stands along the axis, a band round a column. "Flat": the width
--   lies outward, a band on the ground (arcs of 120 degrees or less, or the ribbon twists).
--   Radius0 -> Radius1 and Rise0 -> Rise1 (the head's height over the tail's, a helix) over
--   Duration; Spin turns the set. Width is the band's widest; Taper is the tail's share of it
--   and Head the head's. A Beam has a width at each end only, so a band pinched at both ends
--   (Head below 1) is two Beams meeting at its middle, where both are widest: they share that
--   attachment, so the curve and the width carry on through it, and each carries one tile of a
--   texture that tiles, so the texture does too.
Shapes.Band = function(cfg, ctx)
	local count = math.clamp(math.floor(num(cfg, "Count", 2)), 1, 8)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.6)
	local r0, r1 = num(cfg, "Radius0", 2), num(cfg, "Radius1", 4)
	local arc = math.rad(math.clamp(num(cfg, "Arc", 160), 10, 200))
	local rise0, rise1 = num(cfg, "Rise0", 0), num(cfg, "Rise1", 0)
	local width = num(cfg, "Width", 1)
	local taper = math.clamp(num(cfg, "Taper", 0.25), 0, 1)
	local head = math.clamp(num(cfg, "Head", 1), 0, 1)
	local pinched = head < 1
	local spin = math.rad(num(cfg, "Spin", 360))
	local jitter = math.clamp(num(cfg, "Jitter", 0.15), 0, 1)
	local flat = str(cfg, "Orient", "Wrap") == "Flat"
	local textureSpeed = num(cfg, "TextureSpeed", 0)
	local textureLength = math.max(0.05, num(cfg, "TextureLength", 1))
	local style = readStyle(cfg)
	local base = ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero))
	if bool(cfg, "Ground", false) then
		base = snapToGround(base, ctx.ignore)
	end
	base *= rad(vec(cfg, "Tilt", Vector3.zero))

	local carrier = newPart(base)
	local bands = {}
	for i = 1, count do
		local speed = 1 + (ctx.rng:NextNumber() * 2 - 1) * jitter
		local atts = { newAttachment(carrier), newAttachment(carrier) }
		if pinched then
			table.insert(atts, newAttachment(carrier))
		end
		local beams = {}
		for k = 1, #atts - 1 do
			local b = Instance.new("Beam")
			b.Archivable = false
			b.Attachment0, b.Attachment1 = atts[k], atts[k + 1]
			b.FaceCamera = false
			b.Segments = if pinched then 24 else 40
			b.LightEmission = style.glow
			b.LightInfluence = 0
			b.Brightness = style.brightness
			b.ZOffset = style.zOffset + i * 0.01
			if style.texture ~= "" then
				b.Texture = style.texture
				b.TextureMode = Enum.TextureMode.Stretch
				b.TextureLength = textureLength
			end
			b.TextureSpeed = textureSpeed * speed
			b.Parent = carrier
			beams[k] = b
		end
		table.insert(bands, {
			atts = atts,
			beams = beams,
			phase = (i - 1) / count * 2 * math.pi + ctx.rng:NextNumber(-0.3, 0.3),
			radius = 1 + (ctx.rng:NextNumber() * 2 - 1) * jitter,
			lift = (ctx.rng:NextNumber() * 2 - 1) * jitter * width,
			width = 1 + (ctx.rng:NextNumber() * 2 - 1) * jitter,
			speed = speed,
		})
	end

	-- a point on the band's circle at angle th and height h, and the way the band runs there
	local function frame(r: number, th: number, h: number, dh: number): CFrame
		local p = Vector3.new(math.cos(th) * r, h, math.sin(th) * r)
		local along = Vector3.new(-math.sin(th) * r * arc, dh, math.cos(th) * r * arc).Unit
		local across = if flat then Vector3.new(math.cos(th), 0, math.sin(th)) else Vector3.yAxis
		across = (across - along * across:Dot(along)).Unit
		return CFrame.fromMatrix(p, along, across, along:Cross(across))
	end

	local function step(alpha: number)
		local e = ease(alpha, style.ease)
		local fade = fadeAt(style, alpha)
		for _, band in bands do
			local r = lerp(r0, r1, e) * band.radius
			local dh = lerp(rise0, rise1, e)
			local th0 = band.phase + spin * e * band.speed
			local spans = #band.beams
			-- handles for a circle: KAPPA * tan(angle / 4) of the radius, lengthened by the rise
			local c = KAPPA * math.tan(arc / spans / 4) * math.sqrt(r * r + (dh / arc) ^ 2)
			for k, att in band.atts do
				local f = (k - 1) / spans
				att.CFrame = frame(r, th0 + arc * f, band.lift + dh * f, dh)
			end
			local w = width * band.width
			for k, b in band.beams do
				b.CurveSize0, b.CurveSize1 = c, c
				if not pinched then
					b.Width0, b.Width1 = w * taper, w
					b.Transparency = NumberSequence.new({
						NumberSequenceKeypoint.new(0, 1),
						NumberSequenceKeypoint.new(0.3, lerp(fade, 1, 0.35)),
						NumberSequenceKeypoint.new(0.85, fade),
						NumberSequenceKeypoint.new(1, lerp(fade, 1, 0.6)),
					})
					b.Color = ColorSequence.new(style.color0, style.color1)
				elseif k == 1 then
					b.Width0, b.Width1 = w * taper, w
					b.Transparency = NumberSequence.new({
						NumberSequenceKeypoint.new(0, 1),
						NumberSequenceKeypoint.new(0.6, lerp(fade, 1, 0.25)),
						NumberSequenceKeypoint.new(1, fade),
					})
					b.Color = ColorSequence.new(style.color0, style.color0:Lerp(style.color1, 0.5))
				else
					b.Width0, b.Width1 = w, w * head
					b.Transparency = NumberSequence.new({
						NumberSequenceKeypoint.new(0, fade),
						NumberSequenceKeypoint.new(0.6, lerp(fade, 1, 0.2)),
						NumberSequenceKeypoint.new(1, 1),
					})
					b.Color = ColorSequence.new(style.color0:Lerp(style.color1, 0.5), style.color1)
				end
			end
		end
	end
	step(0)
	addAnim(delay, duration, function()
		carrier.Parent = liveFolder()
	end, step, function()
		carrier:Destroy()
	end)
	return delay + duration
end

-- A glowing ball flying along an arc with a tapered ribbon behind it (fireballs,
-- thrown energy, homing shots). Pair it with Ring/Lines layers whose Delay equals
-- this Duration and whose Offset equals To for the hit.
Shapes.Projectile = function(cfg, ctx)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.6)
	local from = vec(cfg, "Offset", Vector3.zero)
	local to = vec(cfg, "To", Vector3.new(0, 0, -30))
	local arcHeight = num(cfg, "ArcHeight", 4)
	local headSize = num(cfg, "HeadSize", 1.2)
	local width = num(cfg, "Width", 0.9)
	-- Halo = false drops the ForceField shell round the head: in a dark room it reads as a black
	-- outline (the arrival in the VFX room, 2026-10-26)
	local haloOn = bool(cfg, "Halo", true)
	local span = math.clamp(num(cfg, "TrailLength", 0.25), 0.02, 0.9)
	local K = 10
	local style = readStyle(cfg)
	local cf = ctx.origin * rad(vec(cfg, "Tilt", Vector3.zero))
	local mid = from:Lerp(to, 0.5)
	local dir = to - from
	local upish = if dir.Magnitude > 0.01 and math.abs(dir.Unit.Y) > 0.95 then Vector3.xAxis else Vector3.yAxis
	local control = mid + upish * arcHeight * 2 -- quadratic Bezier peak = arcHeight
	local function at(t: number): Vector3
		local u = 1 - t
		return from * (u * u) + control * (2 * u * t) + to * (t * t)
	end

	local carrier = newPart(cf)
	local core = newPart(cf)
	core.Shape = Enum.PartType.Ball
	core.Material = Enum.Material.Neon
	core.Color = style.coreColor
	core.Parent = carrier
	local halo = newPart(cf)
	halo.Shape = Enum.PartType.Ball
	halo.Material = Enum.Material.ForceField
	halo.Color = style.color0
	halo.Parent = carrier
	-- Tail = "Trail": a Roblox Trail on the head instead of the beam chain. Its length is the head's
	-- speed times TrailTime, so it is short while the head is slow and long once it is fast, as a
	-- falling drop's streak (Phát, 2026-10-26); it tapers and fades along its length
	if str(cfg, "Tail", "Beams") == "Trail" then
		local life = num(cfg, "TrailTime", 0.12)
		local a0, a1 = Instance.new("Attachment"), Instance.new("Attachment")
		a0.Position, a1.Position = Vector3.new(width / 2, 0, 0), Vector3.new(-width / 2, 0, 0)
		a0.Parent, a1.Parent = core, core
		local trail = Instance.new("Trail")
		trail.Attachment0, trail.Attachment1 = a0, a1
		trail.FaceCamera = true
		trail.Lifetime = life
		trail.MinLength = 0.05
		trail.WidthScale = NumberSequence.new(1, 0)
		trail.Transparency = NumberSequence.new(style.fade0, 1)
		trail.Color = ColorSequence.new(style.color0, style.color1)
		trail.LightEmission = style.glow
		trail.LightInfluence = 0
		trail.Brightness = style.brightness
		trail.Parent = core
		local total = duration + life
		local function step(alpha: number)
			local s = alpha * total / duration
			local arrived = s >= 1
			core.CFrame = cf * CFrame.new(at(ease(math.min(1, s), style.ease)))
			halo.CFrame = core.CFrame
			core.Size = Vector3.one * (if arrived then 0.05 else headSize * 0.55)
			halo.Size = Vector3.one * (if arrived then 0.05 else headSize)
			core.Transparency = if arrived then 1 else style.fade0
			halo.Transparency = if arrived or not haloOn then 1 else lerp(style.fade0, 1, 0.35)
		end
		step(0)
		addAnim(delay, total, function()
			carrier.Parent = liveFolder()
		end, step, function()
			carrier:Destroy()
		end)
		return delay + total
	end
	local atts: { Attachment } = {}
	local beams: { Beam } = {}
	local cores: { Beam } = {}
	for j = 0, K do
		atts[j + 1] = newAttachment(carrier)
	end
	for j = 1, K do
		beams[j] = newBeam(carrier, atts[j], atts[j + 1], style, false)
		if style.core then
			cores[j] = newBeam(carrier, atts[j], atts[j + 1], style, true)
		end
	end

	local total = duration * (1 + span)
	local function step(alpha: number)
		local s = alpha * (1 + span)
		local headT = ease(math.min(1, s), style.ease)
		local arrived = s >= 1
		local p = at(headT)
		core.CFrame = cf * CFrame.new(p)
		halo.CFrame = core.CFrame
		local pulse = 1 + 0.12 * math.sin(alpha * 60)
		core.Size = Vector3.one * (if arrived then 0.05 else headSize * 0.55 * pulse)
		halo.Size = Vector3.one * (if arrived then 0.05 else headSize * pulse)
		core.Transparency = if arrived then 1 else style.fade0
		halo.Transparency = if arrived or not haloOn then 1 else lerp(style.fade0, 1, 0.35)
		local eye = eyeIn(carrier)
		for j = 0, K do
			local t = math.clamp(s - span * j / K, 0, 1)
			local pt = at(ease(t, style.ease))
			local ahead = at(ease(math.min(1, t + 0.01), style.ease))
			local behind = at(ease(math.max(0, t - 0.01), style.ease))
			atts[j + 1].CFrame = ribbonFrame(pt, ahead - behind, eye)
		end
		local fade = fadeAt(style, math.max(0, s - 1) / span)
		for j = 1, K do
			local f0, f1 = (j - 1) / K, j / K
			local b = beams[j]
			b.Width0, b.Width1 = width * (1 - f0) ^ 1.5, width * (1 - f1) ^ 1.5
			b.Transparency = NumberSequence.new(lerp(fade, 1, f0), lerp(fade, 1, f1))
			b.Color = ColorSequence.new(style.color0:Lerp(style.color1, f0), style.color0:Lerp(style.color1, f1))
			local cb = cores[j]
			if cb then
				cb.Width0, cb.Width1 = b.Width0 * 0.35, b.Width1 * 0.35
				cb.Transparency = b.Transparency
			end
		end
	end
	step(0)
	addAnim(delay, total, function()
		carrier.Parent = liveFolder()
	end, step, function()
		carrier:Destroy()
	end)
	return delay + total
end

-- Camera shake. Every running shake adds smooth noise to the camera right after
-- the camera scripts move it, and fades with distance from the effect.
type Shake = { t: number, delay: number, duration: number, magnitude: number, roughness: number,
	fadeIn: number, fadeOut: number, position: Vector3, range: number, seed: number, rotation: number,
	kick: boolean }
local shakes: { Shake } = {}
-- FOV punches: { t, delay, duration, amount } (degrees; negative zooms in)
local punches: { { t: number, delay: number, duration: number, amount: number } } = {}
local appliedFov = 0
local shakeBound = false

local function shakeOffset(dt: number): CFrame
	local camera = Workspace.CurrentCamera
	if not camera then
		return CFrame.identity
	end
	local pos, rot = Vector3.zero, Vector3.zero
	local i = 1
	while i <= #shakes do
		local s = shakes[i]
		s.t += dt
		local life = s.t - s.delay
		if life >= s.duration then
			shakes[i] = shakes[#shakes]
			shakes[#shakes] = nil
		else
			if life >= 0 then
				local env = math.min(1, life / math.max(1e-3, s.fadeIn))
				env = math.min(env, math.clamp((s.duration - life) / math.max(1e-3, s.fadeOut), 0, 1))
				if s.kick then
					-- a hit: full strength on the first frame, gone fast
					env = (1 - life / s.duration) ^ 2.5
				end
				local dist = (camera.CFrame.Position - s.position).Magnitude
				local fall = math.clamp(1 - dist / s.range, 0, 1)
				local amount = s.magnitude * env * fall * fall
				local x = life * s.roughness
				local n = Vector3.new(
					math.noise(x, s.seed, 0.5),
					math.noise(s.seed, x, 1.5),
					math.noise(2.5, s.seed, x)
				)
				pos += n * amount * 0.15
				rot += n * amount * s.rotation
			end
			i += 1
		end
	end
	return CFrame.new(pos) * CFrame.Angles(math.rad(rot.X), math.rad(rot.Y), math.rad(rot.Z))
end

local function ensureShakeLoop()
	if shakeBound then
		return
	end
	shakeBound = true
	RunService:BindToRenderStep("EasyVFX_Shake", Enum.RenderPriority.Camera.Value + 1, function(dt)
		local camera = Workspace.CurrentCamera
		if #shakes == 0 and #punches == 0 then
			if camera and appliedFov ~= 0 then
				camera.FieldOfView -= appliedFov
				appliedFov = 0
			end
			RunService:UnbindFromRenderStep("EasyVFX_Shake")
			shakeBound = false
			return
		end
		if camera then
			camera.CFrame *= shakeOffset(dt)
			-- FOV punch: snap to the offset, ease back (applied as a delta so other
			-- scripts can still change the FOV)
			local fov = 0
			local i = 1
			while i <= #punches do
				local pch = punches[i]
				pch.t += dt
				local life = pch.t - pch.delay
				if life >= pch.duration then
					punches[i] = punches[#punches]
					punches[#punches] = nil
				else
					if life >= 0 then
						fov += pch.amount * (1 - life / pch.duration) ^ 3
					end
					i += 1
				end
			end
			camera.FieldOfView += fov - appliedFov
			appliedFov = fov
		end
	end)
end

Shapes.Shake = function(cfg, ctx)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.5)
	-- Never shake the Studio editor camera: only in a running game, on a client.
	if RunService:IsRunning() and RunService:IsClient() then
		table.insert(shakes, {
			t = 0,
			delay = delay,
			duration = duration,
			magnitude = num(cfg, "Magnitude", 1) * ctx.quality ^ 0.5,
			roughness = num(cfg, "Roughness", 14),
			fadeIn = num(cfg, "FadeIn", 0.04),
			fadeOut = num(cfg, "FadeOut", duration * 0.7),
			position = (ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero))).Position,
			range = num(cfg, "Range", 80),
			seed = ctx.rng:NextNumber(0, 1000),
			rotation = num(cfg, "Rotation", 1),
			kick = bool(cfg, "Kick", false),
		})
		ensureShakeLoop()
	end
	return delay + duration
end

-- FOV punch: the camera zooms in (negative Amount) or out by a few degrees on the
-- hit and eases back. Client only, like Shake.
Shapes.Punch = function(cfg, ctx)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.25)
	if RunService:IsRunning() and RunService:IsClient() then
		table.insert(punches, { t = 0, delay = delay, duration = duration, amount = math.clamp(num(cfg, "Amount", -6), -30, 30) })
		ensureShakeLoop()
	end
	return delay + duration
end

-- Hit-stop: every running effect holds its frame for a few hundredths of a second
-- on a heavy hit (50-100 ms reads as weight; longer reads as lag), and animation
-- tracks registered with EasyVFX.TrackHitStop slow down with them.
local hitStopTracks: { [AnimationTrack]: boolean } = setmetatable({}, { __mode = "k" }) :: any

function EasyVFX.TrackHitStop(track: AnimationTrack)
	hitStopTracks[track] = true
end

function EasyVFX.HitStop(seconds: number)
	local length = math.clamp(seconds, 0, 0.3)
	frozenUntil = math.max(frozenUntil, os.clock() + length)
	-- particles freeze with the driver; each emitter's own time scale comes back after
	for e in liveEmitters do
		if alive(e) then
			if e:GetAttribute("VFX_BaseTimeScale") == nil then
				e:SetAttribute("VFX_BaseTimeScale", e.TimeScale)
			end
			e.TimeScale = 0
		end
	end
	task.delay(length, function()
		if os.clock() + 1e-3 < frozenUntil then
			return -- a later hit-stop is still holding; it restores them
		end
		for e in liveEmitters do
			local base = alive(e) and e:GetAttribute("VFX_BaseTimeScale")
			if type(base) == "number" then
				e.TimeScale = base
				e:SetAttribute("VFX_BaseTimeScale", nil)
			end
		end
	end)
	for track in hitStopTracks do
		if track.IsPlaying then
			local speed = track.Speed
			track:AdjustSpeed(speed * 0.05)
			task.delay(length, function()
				if track.IsPlaying then
					track:AdjustSpeed(speed)
				end
			end)
		end
	end
end

Shapes.HitStop = function(cfg, _ctx)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.07)
	addAnim(delay, 0.016, function()
		EasyVFX.HitStop(duration)
	end, function() end)
	return delay + duration
end

-- Impact frame: a few frames of full-screen color correction on the hit, the
-- anime "flash". Style = Flash (bright tint), Mono (black & white punch) or
-- Invert (negative frame).
local impactToken = 0

Shapes.Impact = function(cfg, ctx)
	local delay = num(cfg, "Delay", 0)
	local duration = num(cfg, "Duration", 0.12)
	local styleName = str(cfg, "Style", "Flash")
	local strength = math.clamp(num(cfg, "Strength", 1), 0, 2)
	local tint = if bool(cfg, "UseColor", true) then col(cfg, "Color0", Color3.new(1, 1, 1)) else Color3.new(1, 1, 1)
	local range = num(cfg, "Range", 120)
	local origin = (ctx.origin * CFrame.new(vec(cfg, "Offset", Vector3.zero))).Position
	local target = { brightness = 0.25, contrast = 0.3, saturation = 0.2 }
	if styleName == "Mono" then
		target = { brightness = 0.1, contrast = 1.2, saturation = -1 }
	elseif styleName == "Invert" then
		target = { brightness = 0, contrast = -2, saturation = -1 }
		tint = Color3.new(1, 1, 1)
	end
	local cc: ColorCorrectionEffect? = nil
	local overlay: ImageLabel? = nil
	local speedLines = str(cfg, "SpeedLines", "")
	local myToken = 0
	local function current(): ColorCorrectionEffect?
		return if impactToken == myToken then cc else nil
	end
	addAnim(delay, duration, function()
		local camera = Workspace.CurrentCamera
		if not camera or (camera.CFrame.Position - origin).Magnitude > range then
			return
		end
		-- Impact frames never stack: the newest one replaces any still showing.
		local previous = camera:FindFirstChild("EasyVFX_Impact")
		if previous then
			previous:Destroy()
		end
		local effect = Instance.new("ColorCorrectionEffect")
		effect.Name = "EasyVFX_Impact"
		effect.Archivable = false
		effect.Parent = camera
		cc = effect
		-- manga speed lines over the whole screen (needs the HD pack's speed_lines)
		local player = Players.LocalPlayer
		if speedLines ~= "" and player and RunService:IsRunning() then
			local gui = player:FindFirstChildOfClass("PlayerGui")
			if gui then
				local old = gui:FindFirstChild("EasyVFX_SpeedLines")
				if old then
					old:Destroy()
				end
				local screen = Instance.new("ScreenGui")
				screen.Name = "EasyVFX_SpeedLines"
				screen.IgnoreGuiInset = true
				screen.ResetOnSpawn = false
				screen.DisplayOrder = 50
				local image = Instance.new("ImageLabel")
				image.BackgroundTransparency = 1
				image.Image = speedLines
				image.ImageColor3 = if styleName == "Invert" then Color3.new(0, 0, 0) else Color3.new(1, 1, 1)
				image.AnchorPoint = Vector2.new(0.5, 0.5)
				image.Position = UDim2.fromScale(0.5, 0.5)
				image.Size = UDim2.fromScale(1.4, 1.4)
				image.SizeConstraint = Enum.SizeConstraint.RelativeXX
				image.Parent = screen
				screen.Parent = gui
				overlay = image
			end
		end
		impactToken += 1
		myToken = impactToken
	end, function(alpha)
		local effect = current()
		if not effect then
			return -- not shown (out of range) or replaced by a newer impact
		end
		if overlay then
			overlay.ImageTransparency = math.clamp(alpha / 0.9, 0.15, 1) ^ 0.7
			overlay.Size = UDim2.fromScale(1.4 + 0.25 * alpha, 1.4 + 0.25 * alpha)
		end
		-- Hold for the first 60%, then snap back quickly.
		local k = strength * (if alpha < 0.6 then 1 else (1 - (alpha - 0.6) / 0.4) ^ 2)
		effect.Brightness = target.brightness * k
		effect.Contrast = target.contrast * (if styleName == "Invert" then (if alpha < 0.6 then 1 else 0) else k)
		effect.Saturation = target.saturation * k
		effect.TintColor = Color3.new(1, 1, 1):Lerp(tint, math.min(1, k))
	end, function()
		local effect = current()
		if effect then
			effect:Destroy()
		end
		if overlay and overlay.Parent then
			(overlay.Parent :: Instance):Destroy()
		end
	end)
	return delay + duration
end

------------------------------------------------------------------------------------
-- Property sequences: any instance inside an effect can carry a NumberSequence
-- attribute named <Property>Sequence (TransparencySequence, BrightnessSequence,
-- Width0Sequence, ScaleSequence...). When the effect plays, that property follows
-- the curve over EmitDuration (or the emitter lifetime / AnimDuration / 1 s) and
-- then goes back to its value. Same convention as other Roblox emit tools.
------------------------------------------------------------------------------------

local function sampleSequence(seq: NumberSequence, t: number, jitter: number): number
	local kps = seq.Keypoints
	if t <= kps[1].Time then
		return kps[1].Value + kps[1].Envelope * jitter
	end
	for i = 1, #kps - 1 do
		local a, b = kps[i], kps[i + 1]
		if t <= b.Time then
			local f = if b.Time - a.Time > 1e-6 then (t - a.Time) / (b.Time - a.Time) else 1
			return lerp(a.Value, b.Value, f) + lerp(a.Envelope, b.Envelope, f) * jitter
		end
	end
	local last = kps[#kps]
	return last.Value + last.Envelope * jitter
end

local function playSequences(inst: Instance, ctx: Ctx): number
	local longest = 0
	for attrName, value in inst:GetAttributes() do
		if typeof(value) ~= "NumberSequence" or #attrName <= 8 or attrName:sub(-8) ~= "Sequence" then
			continue
		end
		local prop = attrName:sub(1, -9)
		local isScale = prop == "Scale"
		local okRead, current = pcall(function()
			return if isScale then nil else (inst :: any)[prop]
		end)
		if not isScale and (not okRead or (type(current) ~= "number" and typeof(current) ~= "NumberRange")) then
			continue
		end
		-- The untouched value and a play counter live in attributes, so overlapping
		-- plays (or a preview cut short) never mistake a mid-animation value for it.
		local baseName, tokenName = "VFXBase_" .. prop, "VFXSeq_" .. prop
		local original: any = inst:GetAttribute(baseName)
		if original == nil then
			original = if isScale then (if inst:IsA("BasePart") then inst.Size elseif inst:IsA("Model") then inst:GetScale() else nil) else current
			if original == nil then
				continue
			end
			inst:SetAttribute(baseName, original)
		end
		local token = num(inst, tokenName, 0) + 1
		inst:SetAttribute(tokenName, token)
		local function mine(): boolean
			return inst.Parent ~= nil and inst:GetAttribute(tokenName) == token
		end
		local delay = num(inst, "EmitDelay", 0)
		local duration = num(inst, "EmitDuration", 0)
		if duration <= 0 then
			duration = if inst:IsA("ParticleEmitter") then inst.Lifetime.Max else num(inst, "AnimDuration", 1)
		end
		local jitter = ctx.rng:NextNumber(-1, 1)
		local seq = value :: NumberSequence
		local function apply(v: number?)
			pcall(function()
				if isScale then
					if inst:IsA("BasePart") then
						inst.Size = if v then (original :: Vector3) * math.max(0.001, v) else original
					elseif inst:IsA("Model") then
						inst:ScaleTo(if v then (original :: number) * math.max(0.001, v) else original)
					end
				elseif typeof(original) == "NumberRange" then
					(inst :: any)[prop] = if v then NumberRange.new(v) else original
				else
					(inst :: any)[prop] = if v then v else original
				end
			end)
		end
		addAnim(delay, duration, nil, function(alpha)
			if mine() then
				apply(sampleSequence(seq, alpha, jitter))
			end
		end, function()
			if mine() then
				apply(nil)
				inst:SetAttribute(baseName, nil)
				inst:SetAttribute(tokenName, nil)
			end
		end)
		longest = math.max(longest, delay + duration)
	end
	return longest
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
			if light.Parent then
				light.Enabled = true
			end
		end, function(alpha)
			if pulseTokens[light] == token and light.Parent then
				light.Brightness = baseBrightness * (1 - alpha) ^ 2
			end
		end, function()
			if pulseTokens[light] == token and light.Parent then
				light.Enabled = false
				light.Brightness = baseBrightness
			end
		end)
		return
	end
	addAnim(delay, 0.016, function()
		if pulseTokens[inst] == token and alive(inst) then
			setOn(inst, true)
		end
	end, function() end)
	addAnim(delay + duration, 0.016, function()
		if pulseTokens[inst] == token and alive(inst) then
			setOn(inst, false)
		end
	end, function() end)
end

-- A stream inside a burst effect (EmitDuration): the runtime emits it at the emitter's Rate,
-- times the play's quality, for `duration` seconds after `delay`, instead of switching the
-- emitter on. Roblox thins an enabled emitter's Rate at low graphics levels; at the lowest it left
-- a fire with no flames (Studio at QualityLevel 1, 2026-10-25). Emit counts are not thinned.
-- VFX_Streaming marks the window, so tools still read it as a stream.
local function stream(e: ParticleEmitter, delay: number, duration: number, quality: number)
	local token = (pulseTokens[e] or 0) + 1
	pulseTokens[e] = token
	local owed = 0
	-- in effect time, as the clock runs it (slow motion emits fewer a second)
	local scale = playScale
	addAnim(delay, duration, function()
		if pulseTokens[e] == token and alive(e) then
			e:SetAttribute("VFX_Streaming", true)
		end
	end, function(_alpha, dt)
		if pulseTokens[e] ~= token or not alive(e) then
			return
		end
		owed += e.Rate * quality * dt * scale
		local n = math.floor(owed)
		if n > 0 then
			owed -= n
			e:Emit(n)
		end
	end, function()
		if pulseTokens[e] == token and alive(e) then
			e:SetAttribute("VFX_Streaming", nil)
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

-- A mesh shell (Builder's `shell` layer): grows from Size0 to Size1, turns by SpinDeg,
-- fades and shows one baked frame at a time (each frame is its own MeshPart with a
-- SurfaceAppearance, since TextureID alpha doesn't cut a mesh out). Tint and emissive
-- are the SurfaceAppearance properties a script may set.
local function playShell(template: BasePart, ctx: Ctx): number
	local delay = num(template, "Delay", 0)
	local duration = num(template, "Duration", 0.3)
	local size0 = vec(template, "Size0", template.Size)
	local size1 = vec(template, "Size1", size0)
	local spin = vec(template, "SpinDeg", Vector3.zero)
	local emissive = num(template, "Emissive", 3)
	local style = readStyle(template)
	local cf = ctx.origin * CFrame.new(vec(template, "Offset", Vector3.zero)) * rad(vec(template, "Tilt", Vector3.zero))
	local copy = template:Clone()
	for _, d in copy:GetDescendants() do
		if d:IsA("BaseScript") then
			d:Destroy()
		end
	end
	copy.Archivable = false
	copy.Transparency = 1
	local frames: { BasePart } = {}
	for _, c in copy:GetChildren() do
		local index = c:GetAttribute("VFX_Frame")
		if c:IsA("BasePart") and type(index) == "number" then
			frames[index] = c
		end
	end
	local shown: BasePart? = nil
	local function step(alpha: number)
		if #frames == 0 then
			return
		end
		local e = ease(alpha, style.ease)
		local frame = frames[math.min(#frames, math.floor(alpha * #frames) + 1)]
		if shown and shown ~= frame then
			shown.Transparency = 1
		end
		shown = frame
		local color = style.color0:Lerp(style.color1, e)
		frame.Size = size0:Lerp(size1, e)
		frame.CFrame = cf * CFrame.Angles(math.rad(spin.X * e), math.rad(spin.Y * e), math.rad(spin.Z * e))
		-- 0.02, not 0: at 0 a SurfaceAppearance's alpha is dithered
		frame.Transparency = math.max(0.02, fadeAt(style, alpha))
		frame.Color = color
		frame:SetAttribute("VFX_Emissive", emissive)
		local sa = frame:FindFirstChildOfClass("SurfaceAppearance")
		if sa then
			-- newer properties; guarded for engines and test harnesses without them
			pcall(function()
				sa.Color = color
				sa.EmissiveTint = color
				sa.EmissiveStrength = emissive
			end)
		end
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
		local delta = at * originOf(root):Inverse()
		for _, d in copy:GetDescendants() do
			if d:IsA("BasePart") then
				d.Anchored = true
				d.CanCollide = false
				d.CanTouch = false
				d.CanQuery = false
				if copy:IsA("BasePart") then
					d.CFrame = delta * d.CFrame
				end
			end
			if d:IsA("JointInstance") or d:IsA("WeldConstraint") or d:IsA("BaseScript") then
				d:Destroy()
			end
		end
		copy:RemoveTag(EasyVFX.Tag)
		copy.Archivable = false
		if copy:IsA("BasePart") then
			copy.Anchored = true
			copy.CanCollide = false
			copy.CanTouch = false
			copy.CanQuery = false
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
	-- a VFX_Seed attribute plays the same random every time (the studio's previews use it, so a
	-- layer alone and inside its effect turn the same way); without it, each play differs
	local seed = root:GetAttribute("VFX_Seed")
	local ctx: Ctx = {
		root = root,
		origin = originOf(root),
		quality = math.clamp(EasyVFX.Quality, 0.25, 1),
		rng = if type(seed) == "number" then Random.new(seed) else Random.new(),
		roll = 0,
		roll2 = 0,
		ignore = ignore,
	}
	ctx.roll = ctx.rng:NextNumber()
	ctx.roll2 = ctx.rng:NextNumber()
	local timeScale = root:GetAttribute("VFX_TimeScale")
	playScale = if type(timeScale) == "number" then math.clamp(timeScale, 0.05, 4) else 1

	-- Re-roll random tilts so HD slashes swing at a new angle every time.
	for _, d in root:GetDescendants() do
		if d:IsA("Attachment") then
			local tilt = d:GetAttribute("RandomTilt")
			local base = d:GetAttribute("BaseCFrame")
			if type(tilt) == "number" and typeof(base) == "CFrame" then
				local rng = ctx.rng
				d.CFrame = base
					* CFrame.Angles(
						math.rad(rng:NextNumber(-tilt, tilt)),
						math.rad(rng:NextNumber(-tilt, tilt) * 0.5),
						math.rad(rng:NextNumber(-tilt, tilt))
					)
			end
		end
	end

	local length = playSequences(root, ctx)
	for _, d in root:GetDescendants() do
		length = math.max(length, playSequences(d, ctx))
		local delay = num(d, "EmitDelay", 0)
		local duration = d:GetAttribute("EmitDuration")
		if d:IsA("ParticleEmitter") then
			liveEmitters[d] = true
			if playScale ~= 1 then
				d.TimeScale = playScale
			end
			local count = d:GetAttribute("EmitCount")
			if type(count) == "number" and count > 0 then
				local n = math.max(1, math.floor(count * ctx.quality + 0.5))
				if delay > 0 then
					addAnim(delay, 0.016, function()
						if alive(d) then
							d:Emit(n)
						end
					end, function() end)
				else
					d:Emit(n)
				end
				length = math.max(length, delay + d.Lifetime.Max)
			end
			if type(duration) == "number" and duration > 0 then
				stream(d, delay, duration, ctx.quality)
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
			if d:GetAttribute("VFX_Shell") then
				length = math.max(length, playShell(d, ctx))
			elseif d:GetAttribute("VFX_Mesh") then
				length = math.max(length, playMesh(d, ctx))
			elseif type(duration) == "number" and duration > 0 and d:GetAttribute("TransparencySequence") == nil then
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

------------------------------------------------------------------------------------
-- Animation markers: effects timed to an animation (Eclipse Animator, Moon, the
-- Roblox Animation Editor...). Two marker names are understood:
--
--   "EasyVFX"    Value = an effect name ("VFX_CrescentSlash"), optionally with a body
--                part or attachment to play it at ("VFX_CrescentSlash@RightHand"), or
--                JSON: {"effect":"VFX_GroundSlam","at":"HumanoidRootPart",
--                       "offset":[0,-3,-4],"rot":[0,0,0]}
--                (offset in studs and rot in degrees, in the space of "at").
--   "EclipseVFX" Eclipse Animator's own event-track markers. When an emit points at an
--                EasyVFX effect inside the character, the whole effect plays, including
--                shapes, shakes and impact frames that Eclipse's emitter alone skips.
--
-- Effects are looked up in ReplicatedStorage.EasyVFX_Effects first, then among all
-- EasyVFX effects in the game. The copy is played where the marker says, so one
-- template serves every character.
------------------------------------------------------------------------------------

type Marker = { effect: string, at: string?, offset: Vector3, rot: Vector3 }

local function vector(v: any): Vector3
	if type(v) == "table" and type(v[1]) == "number" and type(v[2]) == "number" and type(v[3]) == "number" then
		return Vector3.new(v[1], v[2], v[3])
	end
	return Vector3.zero
end

-- Reads a marker value. Returns nil for anything malformed (markers are data).
function EasyVFX.ParseMarker(value: string?): Marker?
	if type(value) ~= "string" or value == "" or #value > 2000 then
		return nil
	end
	local trimmed = value:match("^%s*(.-)%s*$") :: string
	if trimmed:sub(1, 1) == "{" then
		local ok, data = pcall(function()
			return HttpService:JSONDecode(trimmed)
		end)
		if not ok or type(data) ~= "table" or type(data.effect) ~= "string" or data.effect == "" then
			return nil
		end
		return {
			effect = data.effect,
			at = if type(data.at) == "string" and data.at ~= "" then data.at else nil,
			offset = vector(data.offset),
			rot = vector(data.rot),
		}
	end
	local effect, at = trimmed:match("^([^@]+)@(.+)$")
	return { effect = effect or trimmed, at = at, offset = Vector3.zero, rot = Vector3.zero }
end

local function findEffect(name: string): Instance?
	local folder = game:GetService("ReplicatedStorage"):FindFirstChild("EasyVFX_Effects")
	local inFolder = folder and folder:FindFirstChild(name, true)
	if inFolder and inFolder:HasTag(EasyVFX.Tag) then
		return inFolder
	end
	return findByName(name)
end

local function anchorOf(character: Instance, name: string?): CFrame
	local inst: Instance? = nil
	if name then
		inst = if character.Name == name then character else character:FindFirstChild(name, true)
	end
	if not inst then
		inst = character:FindFirstChild("HumanoidRootPart") or character
	end
	return originOf(inst :: Instance)
end

-- Plays the effect a marker describes, relative to `character`. Returns its length.
function EasyVFX.PlayMarker(character: Instance, value: string?): number
	local marker = EasyVFX.ParseMarker(value)
	if not marker then
		return 0
	end
	local effect = findEffect(marker.effect)
	if not effect then
		warn("[EasyVFX] Animation marker: no effect named " .. marker.effect)
		return 0
	end
	local cf = anchorOf(character, marker.at) * CFrame.new(marker.offset) * rad(marker.rot)
	return EasyVFX.Play(effect, cf)
end

-- The EasyVFX effect an Eclipse emit path points at (the path is relative to the
-- root passed to Bind), or nil when it targets a plain emitter Eclipse handles.
local function eclipseTarget(root: Instance, path: any): Instance?
	if type(path) ~= "table" or #path > 128 then
		return nil
	end
	local target: Instance? = root
	for _, step in path do
		if not target or type(step) ~= "table" or type(step.Name) ~= "string" then
			return nil
		end
		local found, index = nil, 0
		for _, child in (target :: Instance):GetChildren() do
			if child.Name == step.Name and child.ClassName == step.Class then
				index += 1
				if index == step.Index then
					found = child
					break
				end
			end
		end
		target = found
	end
	local node: Instance? = target
	while node and node ~= root.Parent do
		if (node :: Instance):HasTag(EasyVFX.Tag) then
			return node
		end
		node = node.Parent
	end
	return nil
end

-- Fires effects at an AnimationTrack's markers. Call it where the animation plays
-- (usually the client for player characters). Returns a binding with Disconnect().
function EasyVFX.BindAnimation(track: AnimationTrack, character: Instance): { Disconnect: (any) -> () }
	-- the animation also freezes with the effects on a hit-stop
	EasyVFX.TrackHitStop(track)
	local connections: { RBXScriptConnection } = {}
	table.insert(
		connections,
		track:GetMarkerReachedSignal("EasyVFX"):Connect(function(value)
			EasyVFX.PlayMarker(character, value)
		end)
	)
	table.insert(
		connections,
		track:GetMarkerReachedSignal("EclipseVFX"):Connect(function(value)
			local ok, data = pcall(function()
				return HttpService:JSONDecode(value)
			end)
			if not ok or type(data) ~= "table" or type(data.Emits) ~= "table" then
				return
			end
			local played: { [Instance]: boolean } = {}
			for _, row in data.Emits do
				local effect = if type(row) == "table" then eclipseTarget(character, row.Path) else nil
				if effect and not played[effect] then
					played[effect] = true
					EasyVFX.Play(effect)
				end
			end
		end)
	)
	return {
		Disconnect = function()
			for _, c in connections do
				c:Disconnect()
			end
			table.clear(connections)
		end,
	}
end

-- Turns the always-on layers (looping emitters, beams, lights...) on or off.
--- How many delayed emits, pulses and animations are still waiting or running: a play with a
--- quiet lead-in (a fire's tell at 0.23 s) isn't over yet. tests/timeline.luau reads it.
function EasyVFX.Pending(): number
	return #active
end

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
		if d:GetAttribute("EmitCount") ~= nil or d:GetAttribute("EmitDuration") ~= nil or d:GetAttribute("VFX_Mesh") or d:GetAttribute("VFX_Shell") then
			return true
		end
		if d:IsA("Configuration") and d:GetAttribute("Kind") ~= nil then
			return true
		end
		for name, value in d:GetAttributes() do
			if typeof(value) == "NumberSequence" and name:sub(-8) == "Sequence" then
				return true
			end
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
