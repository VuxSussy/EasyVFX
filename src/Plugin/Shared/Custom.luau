--!strict
--[[
	"My Effects": effects people build themselves from blocks, with no code.

	A custom effect is a small, plain definition:
		{ id, name, kind = "burst" | "loop", color1 = "#RRGGBB", color2 = "#RRGGBB",
		  blocks = { { block = "slash", color = "p", delay = 0, size = 1, amount = 1, dark = false }, ... } }

	toPreset() turns it into a normal preset (same layer data as Presets.luau), and
	register() adds it to Presets.List / Presets.ById under the "custom" category, so
	the library, the Customize tab, triggers, favorites and the runtime all work with
	it unchanged. Definitions are saved in the plugin settings and inside every effect
	made from them (VFX_CustomDef), so an effect stays editable in any place.

	Share codes are "EVFX1:" + JSON. They come from other people, so decode()
	accepts only known blocks and clamps every number.
]]

local HttpService = game:GetService("HttpService")

local Presets = require(script.Parent.Presets)

local Custom = {}

Custom.SETTING = "EasyVFX_Custom"
Custom.PREFIX = "EVFX1:"
Custom.MAX_BLOCKS = 24
Custom.MAX_EFFECTS = 40

export type Block = { block: string, color: string, delay: number, size: number, amount: number, dark: boolean }
export type Def = { id: string, name: string, kind: string, color1: string, color2: string, blocks: { Block } }

local T = Presets.Textures
local COLORS = { p = true, s = true, w = true, x = true }

------------------------------------------------------------------------------------
-- Blocks: each returns layers in the same format as Presets.luau
------------------------------------------------------------------------------------

type Mod = { color: string, delay: number, size: number, amount: number, dark: boolean }
type Maker = (m: Mod) -> { any }

local function shape(kind: string, attrs: { [string]: any }, m: Mod, second: string?): { any }
	local a = table.clone(attrs)
	a.Delay = (a.Delay or 0) + m.delay
	for _, k in { "Radius", "Radius0", "Radius1", "Width", "Width0", "Width1", "Length", "Distance1", "Size0", "Size1", "Height", "HeadSize", "ArcHeight", "SizeMin", "SizeMax", "Force" } do
		if type(a[k]) == "number" then
			a[k] *= m.size
		end
	end
	for _, k in { "Offset", "To", "From" } do
		if typeof(a[k]) == "Vector3" then
			a[k] *= m.size
		end
	end
	if type(a.Count) == "number" then
		a.Count = math.max(1, math.floor(a.Count * m.amount + 0.5))
	end
	local layer: { [string]: any } = { type = "shape", kind = kind, attrs = a, color0 = m.color, color1 = second or "s" }
	if m.dark then
		a.Glow = 0
		a.CoreGlow = 1
		layer.color0 = "x"
		layer.color1 = "k"
		layer.core = if m.color == "x" then "p" else m.color
	end
	return { layer }
end

local function particles(base: { [string]: any }, m: Mod): { any }
	local layer = table.clone(base)
	layer.delay = (layer.delay or 0) + m.delay
	if layer.burst then
		layer.burst = math.max(1, math.floor(layer.burst * m.amount + 0.5))
	end
	if layer.rate then
		layer.rate = math.max(1, math.floor(layer.rate * m.amount + 0.5))
	end
	local size = {}
	for i, kp in layer.size do
		size[i] = { kp[1], kp[2] * m.size }
	end
	layer.size = size
	if layer.speed then
		layer.speed = { layer.speed[1] * m.size, layer.speed[2] * m.size }
	end
	if m.dark then
		layer.color = { "x", "k" }
		layer.lightEmission = 0
		layer.lightInfluence = 1
	elseif m.color ~= "p" then
		layer.color = { "w", m.color }
	end
	return { layer }
end

Custom.Blocks = {
	{ id = "slash", vi = "Vệt chém", en = "Slash", make = function(m: Mod)
		return shape("Slash", { Radius = 5, Arc = 160, Width = 1.6, Sweep = 50, Duration = 0.45 }, m)
	end },
	{ id = "ring", vi = "Vòng sóng", en = "Shockwave ring", make = function(m: Mod)
		return shape("Ring", { Radius0 = 0.5, Radius1 = 9, Width0 = 1.2, Width1 = 0.05, Duration = 0.45 }, m)
	end },
	{ id = "lines", vi = "Tia bắn ra", en = "Burst lines", make = function(m: Mod)
		return shape("Lines", { Count = 12, Distance0 = 0.5, Distance1 = 9, Length = 4, Width = 0.3, Duration = 0.35 }, m)
	end },
	{ id = "spiral", vi = "Xoắn ốc", en = "Spiral", make = function(m: Mod)
		return shape("Spiral", { Offset = Vector3.new(0, -2, 0), Count = 3, Turns = 2, Height = 6, Radius0 = 1, Radius1 = 3, Width = 0.4, Duration = 0.8 }, m)
	end },
	{ id = "orb", vi = "Quả cầu sáng", en = "Flash orb", make = function(m: Mod)
		return shape("Orb", { Size0 = 0.5, Size1 = 5, Duration = 0.25, Transparency = 0.1, FadeStart = 0 }, m, "w")
	end },
	{ id = "bolt", vi = "Tia sét", en = "Lightning", make = function(m: Mod)
		return shape("Bolt", { From = Vector3.new(0, 20, 0), To = Vector3.new(0, -2, 0), Segments = 10, Jitter = 2, Width = 0.5, Duration = 0.35, Count = 1 }, m, "w")
	end },
	{ id = "projectile", vi = "Đạn bay", en = "Projectile", make = function(m: Mod)
		return shape("Projectile", { To = Vector3.new(0, 0, -24), ArcHeight = 3, Duration = 0.5, HeadSize = 1.4, Width = 1, Ease = "Linear" }, m)
	end },
	{ id = "crater", vi = "Hố đá", en = "Crater rocks", make = function(m: Mod)
		return shape("Crater", { Count = 12, Radius = 6, SizeMin = 1.2, SizeMax = 2.2, Duration = 2.5 }, m)
	end },
	{ id = "debris", vi = "Đá văng", en = "Flying rocks", make = function(m: Mod)
		return shape("Debris", { Count = 10, Force = 35, Duration = 2 }, m)
	end },
	{ id = "sparks", vi = "Tia lửa", en = "Sparks", make = function(m: Mod)
		return particles({
			type = "particles", at = "center", texture = T.Square, burst = 20, color = { "w", "p" },
			size = { { 0, 0.22 }, { 1, 0 } }, squash = { { 0, -2.5 }, { 1, -2.5 } }, orientation = "VelocityParallel",
			lifetime = { 0.35, 0.7 }, speed = { 25, 40 }, spread = { 180, 180 }, drag = 5,
			accel = Vector3.new(0, -25, 0), lightEmission = 1, brightness = 2,
		}, m)
	end },
	{ id = "smoke", vi = "Khói", en = "Smoke burst", make = function(m: Mod)
		local layers = particles({
			type = "particles", at = "center", texture = T.Smoke, burst = 8, color = { "g" },
			size = { { 0, 2 }, { 1, 6 } }, transparency = { { 0, 0.3 }, { 1, 1 } }, lifetime = { 1.2, 2 },
			speed = { 3, 7 }, spread = { 180, 180 }, drag = 3, accel = Vector3.new(0, 2, 0),
			rotation = { 0, 360 }, rotSpeed = { -40, 40 }, lightEmission = 0, lightInfluence = 1, zOffset = -0.5,
		}, m)
		if not m.dark and m.color ~= "w" then
			layers[1].color = { "g" }
		end
		return layers
	end },
	{ id = "embers", vi = "Tàn lửa bay", en = "Rising embers", make = function(m: Mod)
		return particles({
			type = "particles", at = "part", texture = T.Square, rate = 10, color = { "w", "p" },
			size = { { 0, 0.14 }, { 1, 0 } }, squash = { { 0, -1.2 }, { 1, -1.2 } }, orientation = "VelocityParallel",
			lifetime = { 1.5, 3 }, speed = { 1, 3 }, spread = { 40, 40 }, accel = Vector3.new(0, 2.5, 0),
			drag = 1, lightEmission = 1, brightness = 2,
		}, m)
	end },
	{ id = "aura", vi = "Hào quang", en = "Glow aura", make = function(m: Mod)
		return particles({
			type = "particles", at = "part", texture = T.Glow, rate = 16, color = { "w", "p" },
			size = { { 0, 0.8 }, { 1, 0 } }, transparency = { { 0, 0.2 }, { 1, 1 } }, lifetime = { 0.8, 1.4 },
			speed = { 1, 3 }, accel = Vector3.new(0, 4, 0), lightEmission = 1,
		}, m)
	end },
	{ id = "light", vi = "Ánh sáng", en = "Light flash", make = function(m: Mod)
		return { { type = "light", brightness = 5 * m.amount, range = 18 * m.size, color = if m.color == "x" then "p" else m.color, flash = 0.4 } }
	end },
	{ id = "shake", vi = "Rung camera", en = "Camera shake", make = function(m: Mod)
		return { { type = "shape", kind = "Shake", attrs = { Delay = m.delay, Magnitude = 1 * m.amount, Duration = 0.4 * m.size } } }
	end },
	{ id = "impact", vi = "Khung va chạm", en = "Impact frame", make = function(m: Mod)
		return { { type = "shape", kind = "Impact", attrs = { Delay = m.delay, Duration = 0.1, Style = if m.dark then "Invert" else "Flash", Strength = math.clamp(m.amount, 0, 2) } } }
	end },
}

Custom.BlockById = {} :: { [string]: any }
for _, b in Custom.Blocks do
	Custom.BlockById[b.id] = b
end

------------------------------------------------------------------------------------
-- Colors as "#RRGGBB" (plain JSON)
------------------------------------------------------------------------------------

function Custom.hex(c: Color3): string
	return string.format("#%02X%02X%02X", math.floor(c.R * 255 + 0.5), math.floor(c.G * 255 + 0.5), math.floor(c.B * 255 + 0.5))
end

function Custom.color(hex: string?, fallback: Color3): Color3
	if type(hex) ~= "string" then
		return fallback
	end
	local r, g, b = hex:match("^#?(%x%x)(%x%x)(%x%x)$")
	if not r then
		return fallback
	end
	return Color3.fromRGB(tonumber(r, 16) :: number, tonumber(g, 16) :: number, tonumber(b, 16) :: number)
end

------------------------------------------------------------------------------------
-- Definitions
------------------------------------------------------------------------------------

function Custom.newId(): string
	return "custom_" .. HttpService:GenerateGUID(false):gsub("-", ""):sub(1, 12):lower()
end

function Custom.newBlock(blockId: string): Block
	return { block = blockId, color = "p", delay = 0, size = 1, amount = 1, dark = false }
end

function Custom.newDef(): Def
	return {
		id = Custom.newId(),
		name = "My Effect",
		kind = "burst",
		color1 = "#8C5AFF",
		color2 = "#2A0A4A",
		blocks = { Custom.newBlock("ring"), Custom.newBlock("lines"), Custom.newBlock("orb") },
	}
end

local function clampNum(v: any, lo: number, hi: number, default: number): number
	if type(v) ~= "number" or v ~= v then
		return default
	end
	return math.clamp(v, lo, hi)
end

-- Cleans a definition that came from settings, an effect or a share code.
function Custom.validate(raw: any): Def?
	if type(raw) ~= "table" or type(raw.blocks) ~= "table" then
		return nil
	end
	local id = if type(raw.id) == "string" and raw.id:match("^custom_[%w_]+$") and #raw.id <= 40 then raw.id else Custom.newId()
	local name = if type(raw.name) == "string" then raw.name:gsub("[%c]", ""):sub(1, 40) else "My Effect"
	if name == "" then
		name = "My Effect"
	end
	local blocks: { Block } = {}
	for _, b in raw.blocks do
		if #blocks >= Custom.MAX_BLOCKS then
			break
		end
		if type(b) == "table" and type(b.block) == "string" and Custom.BlockById[b.block] then
			table.insert(blocks, {
				block = b.block,
				color = if type(b.color) == "string" and COLORS[b.color] then b.color else "p",
				delay = clampNum(b.delay, 0, 3, 0),
				size = clampNum(b.size, 0.25, 4, 1),
				amount = clampNum(b.amount, 0.2, 3, 1),
				dark = b.dark == true,
			})
		end
	end
	if #blocks == 0 then
		return nil
	end
	return {
		id = id,
		name = name,
		kind = if raw.kind == "loop" then "loop" else "burst",
		color1 = Custom.hex(Custom.color(raw.color1, Color3.fromRGB(140, 90, 255))),
		color2 = Custom.hex(Custom.color(raw.color2, Color3.fromRGB(42, 10, 74))),
		blocks = blocks,
	}
end

function Custom.encode(def: Def): string
	return HttpService:JSONEncode(def)
end

function Custom.decode(text: string?): Def?
	if type(text) ~= "string" or #text > 20000 then
		return nil
	end
	local json = text:match("^%s*" .. Custom.PREFIX:gsub("%p", "%%%0") .. "(.-)%s*$") or text
	local ok, raw = pcall(function()
		return HttpService:JSONDecode(json)
	end)
	return if ok then Custom.validate(raw) else nil
end

function Custom.shareCode(def: Def): string
	return Custom.PREFIX .. Custom.encode(def)
end

------------------------------------------------------------------------------------
-- Definition -> preset, and the library
------------------------------------------------------------------------------------

function Custom.toPreset(def: Def): Presets.Preset
	local layers = {}
	for _, b in def.blocks do
		local block = Custom.BlockById[b.block]
		for _, layer in block.make(b :: any) do
			table.insert(layers, layer)
		end
	end
	local preset = {
		id = def.id,
		category = "custom",
		name = { vi = def.name, en = def.name },
		desc = { vi = #def.blocks .. " khối tự tạo", en = #def.blocks .. " custom blocks" },
		kind = def.kind,
		defaults = {
			color1 = Custom.color(def.color1, Color3.fromRGB(140, 90, 255)),
			color2 = Custom.color(def.color2, Color3.fromRGB(42, 10, 74)),
			trigger = if def.kind == "loop" then "Always" else "Loop",
			interval = 2,
			duration = 3,
		},
		layers = layers,
		custom = def,
	}
	return preset :: any
end

local function remove(id: string)
	for i = #Presets.List, 1, -1 do
		if Presets.List[i].id == id then
			table.remove(Presets.List, i)
		end
	end
	Presets.ById[id] = nil
end

-- Adds (or replaces) one custom effect in the library.
function Custom.registerOne(def: Def): Presets.Preset
	remove(def.id)
	local preset = Custom.toPreset(def)
	table.insert(Presets.List, preset)
	Presets.ById[def.id] = preset
	return preset
end

-- Replaces every custom effect in the library with `defs`.
function Custom.register(defs: { Def })
	for i = #Presets.List, 1, -1 do
		if Presets.List[i].category == "custom" then
			Presets.ById[Presets.List[i].id] = nil
			table.remove(Presets.List, i)
		end
	end
	for _, def in defs do
		Custom.registerOne(def)
	end
end

-- Saved definitions: a JSON string in the plugin settings.
function Custom.load(raw: any): { Def }
	local defs: { Def } = {}
	if type(raw) ~= "string" then
		return defs
	end
	local ok, list = pcall(function()
		return HttpService:JSONDecode(raw)
	end)
	if ok and type(list) == "table" then
		for _, item in list do
			local def = Custom.validate(item)
			if def and #defs < Custom.MAX_EFFECTS then
				table.insert(defs, def)
			end
		end
	end
	return defs
end

function Custom.save(defs: { Def }): string
	return HttpService:JSONEncode(defs)
end

return Custom
