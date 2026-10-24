--!strict
--[[
	Curves: a property's change over a particle's (or a beam's) life as a named ease,
	instead of hand-written keypoints. docs/vfx-grammar.md, "Curves and exits".

		{ from = 0, to = 1, ease = "inCubic", hold = 0.4, envelope = 0.05 }

	holds `from` until `hold` (a share of the life), then eases to `to` by the end. A layer may
	still give raw keypoints ({ { t, v, envelope? }, ... }) or a single number; Curves.keypoints
	passes those through, so every existing preset builds exactly as before.

	Eases: "linear", "in"/"out"/"inOut" with "Sine", "Quad", "Cubic", "Quart", "Expo",
	"Circ" or "Back" ("outBack" overshoots), and "steps4" ... "steps12" for the on-twos look.

	Exits: how a layer leaves, one per role (tools/evfx/grammar.json `exits`):
		flashCut      a core: holds, then gone fast in its last 40%
		snapShrink    shards: hold, then shrink to nothing
		holdFade      base, glint, dark, dust: hold most of the life, then fade
		gustDisperse  volume, ground: thin early and slowly while it keeps growing
		sinkFade      debris: solid until the last 15%, then fade
	Curves.exit(name, transparency, size) returns the layer's new transparency and size specs.
]]

local Curves = {}

local MAX_POINTS = 20 -- Roblox's NumberSequence limit
local SAMPLES = 10

local function back(t: number): number
	local s = 1.70158
	return t * t * ((s + 1) * t - s)
end

local IN: { [string]: (number) -> number } = {
	Sine = function(t)
		return 1 - math.cos(t * math.pi / 2)
	end,
	Quad = function(t)
		return t * t
	end,
	Cubic = function(t)
		return t * t * t
	end,
	Quart = function(t)
		return t * t * t * t
	end,
	Expo = function(t)
		return if t <= 0 then 0 else 2 ^ (10 * t - 10)
	end,
	Circ = function(t)
		return 1 - math.sqrt(1 - t * t)
	end,
	Back = back,
}

--- The ease function for a name, or nil when the name isn't one.
function Curves.ease(name: string?): ((number) -> number)?
	if name == nil or name == "linear" then
		return function(t)
			return t
		end
	end
	local n = (name :: string):match("^steps(%d+)$")
	if n then
		local k = math.max(1, tonumber(n) :: number)
		return function(t)
			return math.min(1, math.floor(t * k) / k)
		end
	end
	local mode, family = (name :: string):match("^(in)(%u%l+)$")
	if not mode then
		mode, family = (name :: string):match("^(out)(%u%l+)$")
	end
	if not mode then
		mode, family = (name :: string):match("^(inOut)(%u%l+)$")
	end
	local f = family and IN[family]
	if not f then
		return nil
	end
	if mode == "in" then
		return f
	elseif mode == "out" then
		return function(t)
			return 1 - f(1 - t)
		end
	end
	return function(t)
		return if t < 0.5 then f(t * 2) / 2 else 1 - f((1 - t) * 2) / 2
	end
end

--- True when a spec is a named-ease curve (not a number or a keypoint list).
function Curves.isCurve(spec: any): boolean
	return type(spec) == "table" and (spec.from ~= nil or spec.to ~= nil or spec.ease ~= nil)
end

--- A spec's value at life-share t (curves, keypoint lists and numbers alike).
function Curves.at(spec: any, t: number): number
	if type(spec) == "number" then
		return spec
	end
	if Curves.isCurve(spec) then
		local from, to = spec.from or 0, spec.to or spec.from or 0
		local hold = math.clamp(spec.hold or 0, 0, 0.99)
		if t <= hold then
			return from
		end
		local f = Curves.ease(spec.ease) :: (number) -> number
		return from + (to - from) * f((t - hold) / (1 - hold))
	end
	local list = spec :: { { number } }
	if #list == 0 then
		return 0
	end
	if t <= list[1][1] then
		return list[1][2]
	end
	for i = 2, #list do
		local a, b = list[i - 1], list[i]
		if t <= b[1] then
			local span = math.max(1e-6, b[1] - a[1])
			return a[2] + (b[2] - a[2]) * ((t - a[1]) / span)
		end
	end
	return list[#list][2]
end

--- Keypoints {{t, v, envelope}} for any spec. A curve is sampled into at most 20 points
--- (Roblox's limit): its hold, then the ease. A step ease keeps its hard steps.
function Curves.keypoints(spec: any): { { number } }
	if type(spec) == "number" then
		return { { 0, spec, 0 }, { 1, spec, 0 } }
	end
	if not Curves.isCurve(spec) then
		return spec :: { { number } }
	end
	assert(Curves.ease(spec.ease), "Curves: unknown ease " .. tostring(spec.ease))
	local env = spec.envelope or 0
	local hold = math.clamp(spec.hold or 0, 0, 0.99)
	local points = { { 0, spec.from or 0, env } }
	local steps = spec.ease and tostring(spec.ease):match("^steps(%d+)$")
	local times = {}
	if steps then
		local k = tonumber(steps) :: number
		for i = 1, k do
			local edge = hold + (1 - hold) * i / k
			table.insert(times, math.max(hold, edge - 1e-3))
			table.insert(times, math.min(1, edge))
		end
	else
		if hold > 0 then
			table.insert(times, hold)
		end
		for i = 1, SAMPLES do
			table.insert(times, hold + (1 - hold) * i / SAMPLES)
		end
	end
	for _, t in times do
		if t > points[#points][1] + 1e-4 and #points < MAX_POINTS then
			table.insert(points, { t, Curves.at(spec, t), env })
		end
	end
	if points[#points][1] < 1 then
		if #points >= MAX_POINTS then
			table.remove(points, #points)
		end
		table.insert(points, { 1, Curves.at(spec, 1), env })
	end
	return points
end

export type Exit = {
	transparency: { hold: number, ease: string },
	size: { scale: number?, hold: number?, ease: string? }?,
	life: number?,
}

Curves.EXITS = {
	flashCut = { transparency = { hold = 0.6, ease = "outQuad" } },
	snapShrink = { transparency = { hold = 0.9, ease = "linear" }, size = { scale = 0, hold = 0.3, ease = "inQuad" } },
	holdFade = { transparency = { hold = 0.5, ease = "inCubic" } },
	gustDisperse = {
		transparency = { hold = 0.3, ease = "inOutSine" },
		size = { scale = 1.35, hold = 0, ease = "outSine" },
		life = 1.5,
	},
	sinkFade = { transparency = { hold = 0.85, ease = "linear" } },
} :: { [string]: Exit }

--- A layer's transparency and size after its exit preset: transparency holds its starting
--- value, then eases to 1; size (when the preset says) eases from its start to start x scale.
--- Returns (transparency, size, lifetime multiplier).
function Curves.exit(name: string, transparency: any, size: any): (any, any, number)
	local preset = Curves.EXITS[name]
	assert(preset, "Curves: unknown exit " .. tostring(name))
	local t0 = Curves.at(transparency or 0, 0)
	local newT = { from = t0, to = 1, hold = preset.transparency.hold, ease = preset.transparency.ease }
	local newS = size
	if preset.size then
		local s0 = Curves.at(size or 1, 0)
		local peak = s0
		for _, t in { 0.25, 0.5, 0.75 } do
			peak = math.max(peak, Curves.at(size or 1, t))
		end
		local start = if (preset.size.scale or 1) < 1 then peak else s0
		newS = { from = start, to = start * (preset.size.scale or 1), hold = preset.size.hold or 0, ease = preset.size.ease or "linear" }
	end
	return newT, newS, preset.life or 1
end

return Curves
