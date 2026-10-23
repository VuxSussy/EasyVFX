--!strict
--[[
	Builder: turns a preset + the user's settings into real Roblox instances.

	An effect is one invisible, non-colliding Part (the "effect part") tagged "EasyVFX".
	Its settings live in VFX_* attributes, so selecting it later lets the plugin show
	the same sliders again. Layers are updated in place (matched by their VFX_Layer
	attribute) so dragging a slider doesn't restart the effect.
]]

local Presets = require(script.Parent.Presets)
local Custom = require(script.Parent.Custom)

local Builder = {}

Builder.TAG = "EasyVFX"
Builder.LAYER_ATTR = "VFX_Layer"
Builder.MAX_RATE = 400

export type Params = {
	preset: string,
	color1: Color3,
	color2: Color3,
	size: number,
	amount: number,
	speed: number,
	lifetime: number,
	glow: number,
	trigger: string, -- Always | Loop | Touch | Click | Prompt | Script
	interval: number,
	cooldown: number,
	duration: number,
	promptText: string,
	texture: string,
	rotation: number, -- extra in-plane rotation (degrees) for flat HD slashes
}

-- Asset pack: texture key -> "rbxassetid://..." (see blender/make_vfx_pack.py)
export type Assets = { [string]: string }

export type Placement = {
	cframe: CFrame,
	size: Vector3,
	parent: Instance,
	weldTo: BasePart?,
}

Builder.Triggers = { "Always", "Loop", "Touch", "Click", "Prompt", "Script" }

local ATTRS: { [string]: string } = {
	preset = "VFX_Preset",
	color1 = "VFX_Color1",
	color2 = "VFX_Color2",
	size = "VFX_Size",
	amount = "VFX_Amount",
	speed = "VFX_Speed",
	lifetime = "VFX_Lifetime",
	glow = "VFX_Glow",
	trigger = "VFX_Trigger",
	interval = "VFX_Interval",
	cooldown = "VFX_Cooldown",
	duration = "VFX_Duration",
	promptText = "VFX_PromptText",
	texture = "VFX_Texture",
	rotation = "VFX_Rotation",
}
Builder.Attributes = ATTRS

local SIZE_KEYS = {
	"Radius0", "Radius1", "Width0", "Width1", "Radius", "Width", "Distance0", "Distance1",
	"Length", "Jitter", "Size0", "Size1", "SizeMin", "SizeMax", "Force",
	"Height", "ArcHeight", "HeadSize",
}
local VECTOR_SIZE_KEYS = { "Step", "Offset", "From", "To" }
local TIME_KEYS = { "Delay", "Duration", "Stagger", "FadeIn", "FadeOut" }
local COUNTED_KINDS = { Lines = true, Debris = true, Crater = true }

------------------------------------------------------------------------------------
-- Params
------------------------------------------------------------------------------------

function Builder.defaultParams(presetId: string): Params
	local preset = Presets.ById[presetId]
	assert(preset, "Unknown preset " .. tostring(presetId))
	local d = preset.defaults
	return {
		preset = presetId,
		color1 = d.color1 or Color3.new(1, 1, 1),
		color2 = d.color2 or Color3.new(1, 1, 1),
		size = d.size or 1,
		amount = d.amount or 1,
		speed = d.speed or 1,
		lifetime = d.lifetime or 1,
		glow = d.glow or 1,
		trigger = d.trigger or (if preset.kind == "burst" then "Loop" else "Always"),
		interval = d.interval or 2,
		cooldown = d.cooldown or 1,
		duration = d.duration or 2,
		promptText = d.promptText or "Use",
		texture = "",
		rotation = d.rotation or 0,
	}
end

function Builder.isRoot(inst: Instance?): boolean
	return inst ~= nil and inst:HasTag(Builder.TAG) and type(inst:GetAttribute(ATTRS.preset)) == "string"
end

function Builder.findRoot(inst: Instance?): Instance?
	local current = inst
	while current do
		if Builder.isRoot(current) then
			return current
		end
		current = current.Parent
	end
	return nil
end

function Builder.readParams(root: Instance): Params?
	local presetId = root:GetAttribute(ATTRS.preset)
	if type(presetId) == "string" and not Presets.ById[presetId] then
		-- A custom effect made elsewhere carries its own definition: learn it.
		local def = Custom.decode(root:GetAttribute("VFX_CustomDef") :: any)
		if def and def.id == presetId then
			Custom.registerOne(def)
		end
	end
	if type(presetId) ~= "string" or not Presets.ById[presetId] then
		return nil
	end
	local params = Builder.defaultParams(presetId)
	local p = params :: any
	for key, attr in ATTRS do
		local v = root:GetAttribute(attr)
		if v ~= nil and typeof(v) == typeof(p[key]) then
			p[key] = v
		end
	end
	return params
end

function Builder.writeParams(root: Instance, params: Params)
	local p = params :: any
	for key, attr in ATTRS do
		root:SetAttribute(attr, p[key])
	end
	root:SetAttribute("VFX_PlayersOnly", if root:GetAttribute("VFX_PlayersOnly") == nil then true else root:GetAttribute("VFX_PlayersOnly"))
end

------------------------------------------------------------------------------------
-- Value helpers
------------------------------------------------------------------------------------

local function resolveColor(token: any, params: Params): Color3
	if typeof(token) == "Color3" then
		return token
	elseif token == "p" then
		return params.color1
	elseif token == "s" then
		return params.color2
	elseif token == "k" then
		return Color3.fromRGB(28, 26, 26)
	elseif token == "g" then
		return Color3.fromRGB(150, 145, 140)
	elseif token == "d" then
		return params.color1:Lerp(Color3.new(0, 0, 0), 0.65)
	elseif token == "x" then
		-- "void": near black, tinted by the second color (dark fantasy bodies)
		return params.color2:Lerp(Color3.fromRGB(6, 4, 8), 0.82)
	end
	return Color3.new(1, 1, 1)
end

local function colorSequence(spec: any, params: Params): ColorSequence
	local list = if type(spec) == "table" then spec else { spec or "p" }
	if #list <= 1 then
		return ColorSequence.new(resolveColor(list[1], params))
	end
	local points = {}
	for i, token in list do
		table.insert(points, ColorSequenceKeypoint.new((i - 1) / (#list - 1), resolveColor(token, params)))
	end
	return ColorSequence.new(points)
end

local function numberSequence(spec: any, mul: number, minValue: number?, maxValue: number?): NumberSequence
	if type(spec) == "number" then
		local v = spec * mul
		return NumberSequence.new(v)
	end
	local points = {}
	for _, kp in spec :: { { number } } do
		local v = kp[2] * mul
		if minValue then
			v = math.max(minValue, v)
		end
		if maxValue then
			v = math.min(maxValue, v)
		end
		table.insert(points, NumberSequenceKeypoint.new(kp[1], v, (kp[3] or 0) * mul))
	end
	return NumberSequence.new(points)
end

local function range(spec: any, mul: number, default: number): NumberRange
	if type(spec) == "number" then
		return NumberRange.new(spec * mul)
	elseif type(spec) == "table" then
		local a, b = spec[1] * mul, spec[2] * mul
		return NumberRange.new(math.min(a, b), math.max(a, b))
	end
	return NumberRange.new(default)
end

local function enumItem(enum: any, name: any, default: EnumItem): EnumItem
	if type(name) ~= "string" then
		return default
	end
	local ok, item = pcall(function()
		return enum[name]
	end)
	return if ok and item then item else default
end

------------------------------------------------------------------------------------
-- Instance helpers
------------------------------------------------------------------------------------

type Existing = { [string]: Instance }

local function collectExisting(root: Instance): Existing
	local existing: Existing = {}
	for _, d in root:GetDescendants() do
		local key = d:GetAttribute(Builder.LAYER_ATTR)
		if type(key) == "string" then
			if existing[key] then
				d:Destroy() -- duplicate (e.g. after a manual copy/paste)
			else
				existing[key] = d
			end
		end
	end
	return existing
end

local function getOrCreate(existing: Existing, wanted: { [string]: boolean }, key: string, className: string, parent: Instance): Instance
	wanted[key] = true
	local found: Instance? = existing[key]
	if found and found.ClassName ~= className then
		found:Destroy()
		found = nil
	end
	local inst: Instance
	if found then
		inst = found
	else
		inst = Instance.new(className)
		inst:SetAttribute(Builder.LAYER_ATTR, key)
		existing[key] = inst
	end
	if inst.Parent ~= parent then
		inst.Parent = parent
	end
	return inst
end

local function attachment(ctx: any, key: string, position: Vector3, tilt: Vector3?, randomTilt: number?): Attachment
	local a = getOrCreate(ctx.existing, ctx.wanted, key, "Attachment", ctx.root) :: Attachment
	a.Name = "VFX_Point"
	local cf = CFrame.new(position)
	if tilt then
		cf *= CFrame.Angles(math.rad(tilt.X), math.rad(tilt.Y), math.rad(tilt.Z))
	end
	a.CFrame = cf
	-- the runtime re-rolls a random tilt around BaseCFrame on every play
	a:SetAttribute("BaseCFrame", if randomTilt then cf else nil)
	a:SetAttribute("RandomTilt", randomTilt)
	return a
end

-- Turns a layer on now (Always) or makes it wait for a trigger (EmitDuration).
local function setStreaming(inst: Instance, ctx: any, onProperty: () -> (), offProperty: () -> ())
	if ctx.alwaysOn then
		onProperty()
		inst:SetAttribute("EmitDuration", nil)
	else
		offProperty()
		inst:SetAttribute("EmitDuration", ctx.params.duration)
	end
	inst:SetAttribute("EmitCount", nil)
	inst:SetAttribute("EmitDelay", nil)
end

-- Where a particle/light layer lives. Layers sharing a `group` share one attachment
-- (so all pieces of an HD slash get the same random tilt).
local function layerParent(ctx: any, key: string, layer: { [string]: any }, defaultAt: string?): Instance
	local at = layer.at or defaultAt
	if (at == nil or at == "part") and not layer.group then
		return ctx.root
	end
	local position = if typeof(at) == "Vector3" then at * ctx.params.size else Vector3.zero
	local attachKey = if layer.group then "g:" .. layer.group else key .. ":a"
	-- a shared group attachment is set up once, by the first layer that uses it
	local done = ctx.configured[attachKey]
	if done then
		ctx.wanted[attachKey] = true
		return done
	end
	local a = attachment(ctx, attachKey, position, layer.tilt, layer.randomTilt)
	ctx.configured[attachKey] = a
	return a
end

local T = Presets.Textures

-- In HD mode the soft built-in textures are swapped for the sharp Blender ones.
-- Smoke and blast puffs become the pack's 4x4 flipbooks (the second return value),
-- so every preset with smoke (Smoke, Fog, Fire, the dark fantasy ones...) is HD too.
local function hdTexture(ctx: any, layer: { [string]: any }): (string?, boolean)
	local assets = ctx.assets
	if layer.pack then
		return assets[layer.pack], false
	end
	if not ctx.hd or layer.flipbook then
		return layer.texture, false
	end
	if layer.texture == T.Star then
		return assets.spark_star or layer.texture, false
	elseif layer.texture == T.Glow and not layer.keepTexture then
		return assets.glow_soft or layer.texture, false
	elseif layer.texture == T.Square and layer.orientation == "VelocityParallel" then
		return assets.spark_streak or layer.texture, false
	elseif layer.texture == T.Smoke and assets.flip_smoke then
		return assets.flip_smoke, true
	elseif layer.texture == T.Blast and assets.flip_impact then
		return assets.flip_impact, true
	end
	return layer.texture, false
end

------------------------------------------------------------------------------------
-- Layer builders
------------------------------------------------------------------------------------

local LayerBuilders: { [string]: (ctx: any, key: string, layer: { [string]: any }) -> () } = {}

LayerBuilders.particles = function(ctx, key, layer)
	local params: Params = ctx.params
	local parent = layerParent(ctx, key, layer)
	local e = getOrCreate(ctx.existing, ctx.wanted, key, "ParticleEmitter", parent) :: ParticleEmitter
	e.Name = layer.name or (if layer.burst then "Burst" else "Stream")
	local texture, packFlipbook = hdTexture(ctx, layer)
	if params.texture ~= "" and not layer.pack then
		texture = params.texture
		packFlipbook = false
	end
	e.Texture = texture or Presets.Textures.Glow
	e.FlipbookLayout = if packFlipbook
		then Enum.ParticleFlipbookLayout.Grid4x4
		else enumItem(Enum.ParticleFlipbookLayout, layer.flipbook, Enum.ParticleFlipbookLayout.None) :: any
	e.FlipbookMode = enumItem(Enum.ParticleFlipbookMode, layer.flipMode, Enum.ParticleFlipbookMode.OneShot) :: any
	e.FlipbookStartRandom = layer.flipRandom == true
	e.Color = colorSequence(layer.color, params)
	e.Size = numberSequence(layer.size or 1, params.size, 0)
	e.Transparency = numberSequence(layer.transparency or 0, 1, 0, 1)
	e.Squash = numberSequence(layer.squash or 0, 1, -3, 3)
	e.Lifetime = range(layer.lifetime, params.lifetime, 1)
	e.Speed = range(layer.speed, params.speed * math.sqrt(params.size), 5)
	local spread = layer.spread or { 0, 0 }
	e.SpreadAngle = Vector2.new(spread[1], spread[2])
	e.Acceleration = (layer.accel or Vector3.zero) * params.speed * math.sqrt(params.size)
	e.Drag = layer.drag or 0
	local rotation = range(layer.rotation or 0, 1, 0)
	if layer.rotatable then
		rotation = NumberRange.new(rotation.Min + params.rotation, rotation.Max + params.rotation)
	end
	e.Rotation = rotation
	e.RotSpeed = range(layer.rotSpeed or 0, params.speed, 0)
	e.Orientation = enumItem(Enum.ParticleOrientation, layer.orientation, Enum.ParticleOrientation.FacingCamera) :: any
	e.EmissionDirection = enumItem(Enum.NormalId, layer.direction, Enum.NormalId.Top) :: any
	e.Shape = enumItem(Enum.ParticleEmitterShape, layer.shape, Enum.ParticleEmitterShape.Box) :: any
	e.ShapeStyle = enumItem(Enum.ParticleEmitterShapeStyle, layer.shapeStyle, Enum.ParticleEmitterShapeStyle.Volume) :: any
	e.ShapeInOut = enumItem(Enum.ParticleEmitterShapeInOut, layer.shapeInOut, Enum.ParticleEmitterShapeInOut.Outward) :: any
	e.LightEmission = math.clamp((layer.lightEmission or 1) * params.glow, 0, 1)
	e.LightInfluence = layer.lightInfluence or 0
	e.Brightness = (layer.brightness or 1) * params.glow
	e.ZOffset = layer.zOffset or 0
	e.LockedToPart = layer.locked == true
	e.WindAffectsDrag = layer.windDrag == true
	if layer.burst then
		e.Rate = 20
		e.Enabled = false
		e:SetAttribute("EmitCount", math.max(1, math.floor(layer.burst * params.amount + 0.5)))
		e:SetAttribute("EmitDelay", if layer.delay then layer.delay * params.lifetime else nil)
		e:SetAttribute("EmitDuration", nil)
	else
		e.Rate = math.min(Builder.MAX_RATE, (layer.rate or 10) * params.amount)
		setStreaming(e, ctx, function()
			e.Enabled = true
		end, function()
			e.Enabled = false
		end)
	end
end

LayerBuilders.shape = function(ctx, key, layer)
	local params: Params = ctx.params
	local cfg = getOrCreate(ctx.existing, ctx.wanted, key, "Configuration", ctx.root)
	cfg.Name = "Shape_" .. tostring(layer.kind)
	for name in cfg:GetAttributes() do
		if name ~= Builder.LAYER_ATTR then
			cfg:SetAttribute(name, nil)
		end
	end
	local attrs: { [string]: any } = table.clone(layer.attrs or {})
	local timeScale = params.lifetime / math.max(0.05, params.speed)
	for _, k in SIZE_KEYS do
		if type(attrs[k]) == "number" then
			attrs[k] *= params.size
		end
	end
	for _, k in VECTOR_SIZE_KEYS do
		if typeof(attrs[k]) == "Vector3" then
			attrs[k] *= params.size
		end
	end
	for _, k in TIME_KEYS do
		if type(attrs[k]) == "number" then
			attrs[k] *= timeScale
		end
	end
	if COUNTED_KINDS[layer.kind] and type(attrs.Count) == "number" then
		attrs.Count = math.max(1, math.floor(attrs.Count * params.amount + 0.5))
	end
	attrs.Glow = math.clamp((attrs.Glow or 1) * params.glow, 0, 1)
	if type(attrs.CoreGlow) == "number" then
		attrs.CoreGlow = math.clamp(attrs.CoreGlow * params.glow, 0, 1)
	end
	if layer.core then
		attrs.CoreColor = resolveColor(layer.core, params)
	end
	attrs.Brightness = (attrs.Brightness or 1) * params.glow
	attrs.Color0 = resolveColor(layer.color0 or "p", params)
	attrs.Color1 = resolveColor(layer.color1 or layer.color0 or "s", params)
	if params.texture ~= "" then
		attrs.Texture = params.texture
	elseif layer.beamPack and ctx.hd and ctx.assets[layer.beamPack] then
		-- HD: a Blender stroke/arc texture over the whole ribbon
		attrs.Texture = ctx.assets[layer.beamPack]
	end
	if layer.packAttrs and ctx.hd then
		for attr, key in layer.packAttrs do
			if ctx.assets[key] then
				attrs[attr] = ctx.assets[key]
			end
		end
	end
	attrs.Kind = layer.kind
	for name, value in attrs do
		cfg:SetAttribute(name, value)
	end
end

-- Beams and trails: the user's texture wins; in HD a layer may name a pack texture
-- (`packTexture`, with optional textureMode / textureLength / textureSpeed).
local function ribbonTexture(ctx: any, layer: { [string]: any }, inst: any)
	local params: Params = ctx.params
	local texture = params.texture
	local packed = params.texture == "" and layer.packTexture and ctx.hd and ctx.assets[layer.packTexture]
	if packed then
		texture = packed
	end
	inst.Texture = texture
	inst.TextureMode = if packed then enumItem(Enum.TextureMode, layer.textureMode, Enum.TextureMode.Stretch) :: any else Enum.TextureMode.Stretch
	inst.TextureLength = if packed then (layer.textureLength or 1) * params.size else 1
	if inst:IsA("Beam") then
		inst.TextureSpeed = if packed then layer.textureSpeed or 0 else 0
	end
end

LayerBuilders.light = function(ctx, key, layer)
	local params: Params = ctx.params
	local parent = layerParent(ctx, key, layer, "center")
	local light = getOrCreate(ctx.existing, ctx.wanted, key, "PointLight", parent) :: PointLight
	light.Name = "Light"
	local brightness = (layer.brightness or 1) * params.glow
	light.Brightness = brightness
	light.Range = math.min(60, (layer.range or 12) * params.size)
	light.Color = resolveColor(layer.color or "p", params)
	light.Shadows = false
	light:SetAttribute("BaseBrightness", brightness)
	if layer.flash then
		light.Enabled = false
		light:SetAttribute("EmitDuration", layer.flash * params.lifetime)
		light:SetAttribute("EmitDelay", layer.delay)
		light:SetAttribute("FlashFade", true)
	else
		light:SetAttribute("FlashFade", false)
		setStreaming(light, ctx, function()
			light.Enabled = true
		end, function()
			light.Enabled = false
		end)
	end
end

LayerBuilders.beam = function(ctx, key, layer)
	local params: Params = ctx.params
	local a0 = attachment(ctx, key .. ":a", (layer.from or Vector3.zero) * params.size)
	local a1 = attachment(ctx, key .. ":b", (layer.to or Vector3.new(0, 0, -10)) * params.size)
	local beam = getOrCreate(ctx.existing, ctx.wanted, key, "Beam", ctx.root) :: Beam
	beam.Name = "Beam"
	beam.Attachment0 = a0
	beam.Attachment1 = a1
	local width = (layer.width or 1) * params.size
	beam.Width0 = width
	beam.Width1 = width
	beam.Color = colorSequence(layer.color, params)
	beam.Transparency = numberSequence(layer.transparency or 0, 1, 0, 1)
	beam.LightEmission = math.clamp((layer.lightEmission or 1) * params.glow, 0, 1)
	beam.LightInfluence = 0
	beam.Brightness = (layer.brightness or 1) * params.glow
	beam.FaceCamera = true
	beam.Segments = 1
	ribbonTexture(ctx, layer, beam)
	setStreaming(beam, ctx, function()
		beam.Enabled = true
	end, function()
		beam.Enabled = false
	end)
end

-- A textured mesh shell (tools/meshgen, docs/plan-real-vfx.md step 2): the template
-- MeshPart the runtime clones and animates. A script can't set MeshId, so the template
-- comes from AssetService; texture frames are swapped through TextureID at play time,
-- since a mesh can't play a flipbook atlas.
LayerBuilders.shell = function(ctx, key, layer)
	local params: Params = ctx.params
	local meshId = ctx.assets[layer.mesh]
	if type(meshId) ~= "string" then
		return
	end
	local found = ctx.existing[key]
	local part: MeshPart
	if found and found:IsA("MeshPart") and found:GetAttribute("VFX_MeshAsset") == meshId then
		part = found :: MeshPart
	else
		if found then
			found:Destroy()
		end
		local ok, made = pcall(function()
			return game:GetService("AssetService"):CreateMeshPartAsync(meshId)
		end)
		if not ok or not made then
			warn("[EasyVFX] Could not load mesh " .. meshId .. ": " .. tostring(made))
			return
		end
		part = made :: MeshPart
		part:SetAttribute(Builder.LAYER_ATTR, key)
		part:SetAttribute("VFX_MeshAsset", meshId)
		ctx.existing[key] = part
	end
	ctx.wanted[key] = true
	part.Name = layer.name or "Shell"
	part.Anchored = true
	part.CanCollide = false
	part.CanTouch = false
	part.CanQuery = false
	part.CastShadow = false
	part.Transparency = 1
	part.CFrame = ctx.root.CFrame
	local frames = {}
	for _, k in layer.frames or {} do
		if ctx.assets[k] then
			table.insert(frames, ctx.assets[k])
		end
	end
	part.TextureID = frames[1] or ""
	local attrs: { [string]: any } = table.clone(layer.attrs or {})
	local timeScale = params.lifetime / math.max(0.05, params.speed)
	for _, k in { "Size0", "Size1", "Offset" } do
		if typeof(attrs[k]) == "Vector3" then
			attrs[k] *= params.size
		end
	end
	for _, k in { "Delay", "Duration" } do
		if type(attrs[k]) == "number" then
			attrs[k] *= timeScale
		end
	end
	attrs.Color0 = resolveColor(layer.color0 or "w", params)
	attrs.Color1 = resolveColor(layer.color1 or layer.color0 or "p", params)
	attrs.Frames = table.concat(frames, ",")
	attrs.VFX_Shell = true
	for name, value in attrs do
		part:SetAttribute(name, value)
	end
	if part.Parent ~= ctx.root then
		part.Parent = ctx.root
	end
end

LayerBuilders.trail = function(ctx, key, layer)
	local params: Params = ctx.params
	local size: Vector3 = ctx.root.Size
	local axis
	if size.Y >= size.X and size.Y >= size.Z then
		axis = Vector3.new(0, size.Y / 2, 0)
	elseif size.X >= size.Z then
		axis = Vector3.new(size.X / 2, 0, 0)
	else
		axis = Vector3.new(0, 0, size.Z / 2)
	end
	local a0 = attachment(ctx, key .. ":a", axis * 0.95)
	local a1 = attachment(ctx, key .. ":b", -axis * 0.95)
	local trail = getOrCreate(ctx.existing, ctx.wanted, key, "Trail", ctx.root) :: Trail
	trail.Name = "Trail"
	trail.Attachment0 = a0
	trail.Attachment1 = a1
	trail.Color = colorSequence(layer.color, params)
	trail.Transparency = numberSequence(layer.transparency or 0, 1, 0, 1)
	trail.WidthScale = numberSequence(layer.widthScale or 1, 1, 0)
	trail.Lifetime = (layer.lifetime or 0.3) * params.lifetime
	trail.LightEmission = math.clamp((layer.lightEmission or 1) * params.glow, 0, 1)
	trail.LightInfluence = 0
	trail.Brightness = (layer.brightness or 1) * params.glow
	trail.MinLength = 0.05
	trail.FaceCamera = false
	ribbonTexture(ctx, layer, trail)
	setStreaming(trail, ctx, function()
		trail.Enabled = true
	end, function()
		trail.Enabled = false
	end)
end

LayerBuilders.part = function(ctx, key, layer)
	local params: Params = ctx.params
	local root: BasePart = ctx.root
	local part = getOrCreate(ctx.existing, ctx.wanted, key, "Part", root) :: Part
	part.Name = "Glow" .. (layer.shape or "Ball")
	part.Shape = enumItem(Enum.PartType, layer.shape, Enum.PartType.Ball) :: any
	part.Material = enumItem(Enum.Material, layer.material, Enum.Material.Neon) :: any
	part.Color = resolveColor(layer.color or "p", params)
	local d = math.max(root.Size.X, root.Size.Y, root.Size.Z) * (layer.scale or 1) * params.size
	part.Size = Vector3.new(d, d, d)
	part.CFrame = root.CFrame
	part.Anchored = false
	part.Massless = true
	part.CanCollide = false
	part.CanTouch = false
	part.CanQuery = false
	part.CastShadow = false
	local weld = part:FindFirstChildOfClass("WeldConstraint") or Instance.new("WeldConstraint")
	weld.Part0 = part
	weld.Part1 = root
	weld.Parent = part
	local base = layer.transparency or 0
	part:SetAttribute("BaseTransparency", base)
	setStreaming(part, ctx, function()
		part.Transparency = base
	end, function()
		part.Transparency = 1
	end)
end

LayerBuilders.highlight = function(ctx, key, layer)
	local params: Params = ctx.params
	local h = getOrCreate(ctx.existing, ctx.wanted, key, "Highlight", ctx.root) :: Highlight
	h.Name = "Outline"
	local target = ctx.root.Parent
	h.Adornee = if target and (target:IsA("BasePart") or target:IsA("Model")) then target else nil
	h.FillColor = resolveColor(layer.fill or "p", params)
	h.OutlineColor = resolveColor(layer.outline or "s", params)
	h.FillTransparency = math.clamp((layer.fillTransparency or 0.5) / math.max(0.2, params.glow), 0, 1)
	h.OutlineTransparency = layer.outlineTransparency or 0
	h.DepthMode = Enum.HighlightDepthMode.Occluded
	setStreaming(h, ctx, function()
		h.Enabled = true
	end, function()
		h.Enabled = false
	end)
end

------------------------------------------------------------------------------------
-- Public
------------------------------------------------------------------------------------

-- Creates or updates every layer of the effect to match `params`.
-- True when the asset pack has been imported (the key HD texture is known).
function Builder.isHD(assets: Assets?): boolean
	return assets ~= nil and type(assets.slash_arc) == "string" and assets.slash_arc ~= ""
end

-- Does this preset change when the HD pack is present?
function Builder.hasHD(presetId: string): boolean
	local preset = Presets.ById[presetId]
	if not preset then
		return false
	end
	for _, layer in preset.layers do
		if layer.hd or layer.pack or layer.beamPack or layer.packTexture or layer.mesh then
			return true
		end
	end
	return false
end

function Builder.apply(root: BasePart, params: Params, assets: Assets?)
	local preset = Presets.ById[params.preset]
	assert(preset, "Unknown preset " .. tostring(params.preset))
	Builder.writeParams(root, params)
	local ctx = {
		root = root,
		params = params,
		alwaysOn = params.trigger == "Always",
		assets = assets or {},
		hd = Builder.isHD(assets),
		configured = {} :: { [string]: Attachment },
		existing = collectExisting(root),
		wanted = {} :: { [string]: boolean },
	}
	root:SetAttribute("VFX_HD", ctx.hd)
	local custom = (preset :: any).custom
	root:SetAttribute("VFX_CustomDef", if custom then Custom.encode(custom) else nil)
	for i, layer in preset.layers do
		local skip = (layer.hd and not ctx.hd) or (layer.basic and ctx.hd) or (layer.pack and not ctx.assets[layer.pack])
		if skip then
			continue
		end
		local build = LayerBuilders[layer.type]
		if build then
			build(ctx, tostring(i), layer)
		else
			warn("[EasyVFX] Unknown layer type " .. tostring(layer.type))
		end
	end
	-- Remove layers the preset no longer has (attachments last so children go first).
	local staleAttachments = {}
	for key, inst in ctx.existing do
		if not ctx.wanted[key] then
			if inst:IsA("Attachment") then
				table.insert(staleAttachments, inst)
			else
				inst:Destroy()
			end
		end
	end
	for _, inst in staleAttachments do
		inst:Destroy()
	end
end

function Builder.effectName(presetId: string): string
	local preset = Presets.ById[presetId]
	local name = if preset then preset.name.en else presetId
	return "VFX_" .. (name:gsub("[^%w]", ""))
end

-- Makes a brand new effect part.
function Builder.create(params: Params, placement: Placement, assets: Assets?): BasePart
	local root = Instance.new("Part")
	root.Name = Builder.effectName(params.preset)
	root.Size = Vector3.new(
		math.max(0.2, placement.size.X),
		math.max(0.2, placement.size.Y),
		math.max(0.2, placement.size.Z)
	)
	root.CFrame = placement.cframe
	root.Transparency = 1
	root.CanCollide = false
	root.CanTouch = false
	root.CanQuery = false
	root.CastShadow = false
	root.Massless = true
	root.TopSurface = Enum.SurfaceType.Smooth
	root.BottomSurface = Enum.SurfaceType.Smooth
	if placement.weldTo then
		root.Anchored = false
		local weld = Instance.new("WeldConstraint")
		weld.Name = "VFX_Weld"
		weld.Part0 = root
		weld.Part1 = placement.weldTo
		weld.Parent = root
	else
		root.Anchored = true
	end
	root:AddTag(Builder.TAG)
	root.Parent = placement.parent
	Builder.apply(root, params, assets)
	return root
end

return Builder
