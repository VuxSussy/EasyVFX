--!nonstrict
--[[
	Ready-made effects. Every preset is plain data that Builder turns into instances.

	Layer types
	  particles  ParticleEmitter. `burst = n` makes it a one-shot (EmitCount), otherwise
	             it streams with `rate`. `at` = "part" (whole effect volume),
	             "center", or a Vector3 offset in studs.
	  shape      Crisp procedural piece played by the runtime (Ring, Slash, Lines, Bolt,
	             Orb, Debris, Crater, Jet). `attrs` are written as attributes.
	  light      PointLight. `flash = seconds` makes it a quick fading flash.
	  beam       Static Beam between two offsets (lasers).
	  trail      Trail along the longest side of the effect part (weapon swings).
	  part       Static visible part (shield bubble, energy core).
	  highlight  Outline glow on the object the effect is attached to.

	Colors: "p" = main color, "s" = second color, "w" = white, "k" = soot black,
	"d" = dark version of main color, or any Color3.
	Sizes / times / counts are multiplied by the Size, Speed, Lifetime and Amount
	sliders in the plugin.
]]

local Presets = {}

Presets.Textures = {
	Glow = "rbxasset://textures/particles/explosion01_implosion_main.dds",
	Ring = "rbxasset://textures/particles/explosion01_shockwave_main.dds",
	Smoke = "rbxasset://textures/particles/smoke_main.dds",
	Star = "rbxasset://textures/particles/sparkles_main.dds",
	Fire = "rbxasset://textures/particles/fire_main.dds",
	Blast = "rbxasset://textures/particles/explosion01_core_main.dds",
	Bubble = "rbxasset://textures/particles/forcefield_vortex_main.dds",
	Square = "rbxasset://textures/particles/SquareParticle.png",
}

local T = Presets.Textures

export type Layer = { [string]: any }
export type Preset = {
	id: string,
	category: string,
	name: { vi: string, en: string },
	desc: { vi: string, en: string },
	kind: string, -- "loop" | "burst"
	style: string?, -- "dark" for the dark fantasy look, nil otherwise
	placement: string?, -- "ground" | "sky" | "air"
	area: Vector3?,
	defaults: { [string]: any },
	layers: { Layer },
}

-- Grouped by what the effect is for, so the library stays easy to scan. The look
-- (dark fantasy...) is a separate filter: Presets.Styles.
Presets.Categories = {
	{ id = "all", vi = "Tất cả", en = "All" },
	{ id = "slash", vi = "Chém", en = "Slashes" },
	{ id = "impact", vi = "Va chạm & nổ", en = "Impacts & Explosions" },
	{ id = "projectile", vi = "Đạn, tia & lướt", en = "Projectiles, Beams & Dashes" },
	{ id = "aura", vi = "Hào quang & buff", en = "Auras & Buffs" },
	{ id = "circle", vi = "Vòng phép & cổng", en = "Circles & Portals" },
	{ id = "elements", vi = "Nguyên tố", en = "Elements" },
	{ id = "world", vi = "Môi trường", en = "Environment" },
	{ id = "custom", vi = "Của tôi", en = "My Effects" },
}

Presets.Styles = {
	{ id = "all", vi = "Mọi phong cách", en = "All styles" },
	{ id = "dark", vi = "Hắc ám", en = "Dark Fantasy" },
}


local function rgb(r: number, g: number, b: number): Color3
	return Color3.fromRGB(r, g, b)
end

-- Reusable sharp spark streaks (crisp square texture stretched along velocity).
local function sparks(count: number, speed: number, at: any?): Layer
	return {
		type = "particles",
		at = at or "center",
		texture = T.Square,
		burst = count,
		color = { "w", "p" },
		size = { { 0, 0.22 }, { 1, 0 } },
		squash = { { 0, -2.5 }, { 1, -2.5 } },
		orientation = "VelocityParallel",
		lifetime = { 0.35, 0.7 },
		speed = { speed * 0.6, speed },
		spread = { 180, 180 },
		drag = 5,
		accel = Vector3.new(0, -25, 0),
		lightEmission = 1,
		brightness = 2,
	}
end

-- HD (asset pack) layers ------------------------------------------------------
-- Layers marked `hd` only appear when the Blender pack is available (built in by
-- default); `basic` layers only without it.

-- Slashes stay the sharp Slash shape (hot edge, eroding tail) in HD too; the pack
-- adds star twinkles thrown off the blade (plus the hit spark / weight below).
local function twinkles(count: number, speed: number, at: any?, delay: number?, color: { any }?): Layer
	return {
		type = "particles",
		name = "Twinkles",
		hd = true,
		pack = "spark_star",
		at = at or "center",
		delay = delay,
		burst = count,
		direction = "Front",
		speed = { speed * 0.5, speed },
		drag = 5,
		spread = { 80, 80 },
		size = { { 0, 0 }, { 0.15, 0.8 }, { 1, 0 } },
		lifetime = { 0.35, 0.8 },
		rotation = { 0, 360 },
		color = color or { "w", "p" },
		lightEmission = 1,
		brightness = 2,
	}
end

-- Marks a layer as "only without the HD pack".
local function basic(layer: Layer): Layer
	layer.basic = true
	return layer
end

local function hdRing(at: any, size1: number, life: number, tilt: Vector3?, delay: number?): Layer
	return {
		type = "particles",
		name = "RingHD",
		hd = true,
		pack = "ring_wave",
		at = at,
		tilt = tilt,
		delay = delay,
		burst = 1,
		orientation = "VelocityPerpendicular",
		direction = "Top",
		speed = { 0.01, 0.01 },
		size = { { 0, size1 * 0.08 }, { 1, size1 } },
		transparency = { { 0, 0 }, { 0.6, 0.25 }, { 1, 1 } },
		lifetime = { life, life },
		rotation = { 0, 360 },
		color = { "w", "p", "s" },
		lightEmission = 1,
		brightness = 2,
	}
end

local function hdFlip(pack: string, at: any, count: number, size: { any }, life: { number }, extra: { [string]: any }?): Layer
	local layer: Layer = {
		type = "particles",
		name = "FlipHD",
		hd = true,
		pack = pack,
		at = at,
		flipbook = "Grid4x4",
		flipMode = "OneShot",
		burst = count,
		size = size,
		lifetime = life,
		rotation = { 0, 360 },
		color = { "w", "p" },
		lightEmission = 1,
		brightness = 2,
	}
	if extra then
		for k, v in extra do
			layer[k] = v
		end
	end
	return layer
end

local function hdDust(count: number): Layer
	return hdFlip("flip_smoke", Vector3.new(0, -1.6, 0), count, { { 0, 2.5 }, { 1, 6 } }, { 0.9, 1.4 }, {
		color = { "g" },
		lightEmission = 0,
		lightInfluence = 1,
		brightness = 1,
		speed = { 8, 14 },
		spread = { 90, 90 },
		drag = 4,
		transparency = { { 0, 0.15 }, { 1, 0.6 } },
	})
end

local function dust(count: number, at: any?): Layer
	return {
		type = "particles",
		at = at or Vector3.new(0, -1.5, 0),
		texture = T.Smoke,
		burst = count,
		color = { "g" },
		size = { { 0, 2 }, { 1, 5 } },
		transparency = { { 0, 0.4 }, { 1, 1 } },
		lifetime = { 1, 1.8 },
		speed = { 10, 18 },
		spread = { 90, 90 },
		direction = "Top",
		drag = 5,
		rotation = { 0, 360 },
		rotSpeed = { -40, 40 },
		lightEmission = 0,
		lightInfluence = 1,
	}
end


-- Dark fantasy helpers ---------------------------------------------------------
-- Dark bodies are unlit (lightEmission 0, lightInfluence 1) so black and blood red
-- really cover the scene; a thin additive core or ember keeps them readable.

local function darkSmoke(count: number, at: any?, extra: { [string]: any }?): Layer
	local layer: Layer = {
		type = "particles",
		at = at or "center",
		texture = T.Smoke,
		burst = count,
		color = { "x", "k" },
		size = { { 0, 2 }, { 1, 6 } },
		transparency = { { 0, 0.15 }, { 0.6, 0.35 }, { 1, 1 } },
		lifetime = { 1.2, 2 },
		speed = { 3, 7 },
		spread = { 180, 180 },
		drag = 3,
		accel = Vector3.new(0, 2, 0),
		rotation = { 0, 360 },
		rotSpeed = { -40, 40 },
		lightEmission = 0,
		lightInfluence = 1,
		zOffset = -0.5,
	}
	if extra then
		for k, v in extra do
			layer[k] = v
		end
	end
	return layer
end

local function embers(rate: number, at: any?, color: { any }?): Layer
	return {
		type = "particles",
		at = at or "part",
		texture = T.Square,
		rate = rate,
		color = color or { "w", "p", "s" },
		size = { { 0, 0.14 }, { 0.7, 0.1 }, { 1, 0 } },
		squash = { { 0, -1.2 }, { 1, -1.2 } },
		orientation = "VelocityParallel",
		lifetime = { 1.5, 3 },
		speed = { 1, 3 },
		spread = { 40, 40 },
		accel = Vector3.new(0, 2.5, 0),
		drag = 1,
		lightEmission = 1,
		brightness = 2,
	}
end


-- Impact kit -------------------------------------------------------------------
-- What makes a hit feel heavy (see docs/impact.md): a hard white hit spark held for
-- a couple of frames, a crisp ring that is gone before the main effect, a short
-- hit-stop, a camera kick and a small FOV punch. The HD layers use the v3 Blender
-- textures and simply drop out when they are not available.

local function hitSpark(at: any, size: number, delay: number?): { Layer }
	return {
		{
			type = "particles",
			name = "HitStarHD",
			hd = true,
			pack = "hit_star",
			at = at,
			delay = delay,
			burst = 1,
			size = { { 0, size * 0.8 }, { 0.3, size }, { 1, size * 1.1 } },
			transparency = { { 0, 0 }, { 0.5, 0 }, { 1, 1 } },
			lifetime = { 0.09, 0.09 }, -- a 2-3 frame hold
			rotation = { 0, 360 },
			color = { "w" },
			lightEmission = 1,
			brightness = 4,
			zOffset = 3,
		},
		{
			type = "particles",
			name = "HitSparkHD",
			hd = true,
			pack = "flip_hitspark",
			at = at,
			delay = (delay or 0) + 0.03,
			flipbook = "Grid4x4",
			flipMode = "OneShot",
			burst = 1,
			size = { { 0, size * 1.1 }, { 1, size * 1.6 } },
			lifetime = { 0.32, 0.32 },
			rotation = { 0, 360 },
			color = { "w", "p", "s" },
			lightEmission = 1,
			brightness = 3,
			zOffset = 2.5,
		},
	}
end

local function hardRing(at: any, size: number, life: number, tilt: Vector3?, delay: number?): Layer
	return {
		type = "particles",
		name = "RingHardHD",
		hd = true,
		pack = "ring_hard",
		at = at,
		tilt = tilt,
		delay = delay,
		burst = 1,
		orientation = "VelocityPerpendicular",
		direction = "Top",
		speed = { 0.01, 0.01 },
		size = { { 0, size * 0.15 }, { 0.35, size * 0.85 }, { 1, size } },
		transparency = { { 0, 0 }, { 0.4, 0.1 }, { 1, 1 } },
		lifetime = { life, life },
		color = { "w", "p" },
		lightEmission = 1,
		brightness = 3,
	}
end

-- hit-stop + FOV punch + camera kick, scaled by how heavy the hit is (0..1)
local function weight(heavy: number, at: Vector3?, delay: number?): { Layer }
	return {
		{ type = "shape", kind = "HitStop", attrs = { Delay = delay or 0, Duration = 0.04 + 0.05 * heavy } },
		{ type = "shape", kind = "Punch", attrs = { Offset = at, Delay = delay or 0, Amount = -(2 + 6 * heavy), Duration = 0.18 + 0.15 * heavy } },
		{ type = "shape", kind = "Shake", attrs = { Offset = at, Delay = delay or 0, Kick = true, Magnitude = 1 + 2 * heavy, Duration = 0.2 + 0.25 * heavy, Roughness = 26 } },
	}
end

-- Hero set (docs/plan-real-vfx.md, step 3) --------------------------------------
-- Library v4 layers (tools/texgen, pack/generated) in Zenless Zone Zero's grammar: a
-- 2-frame white core, a burst that peaks by frame 4, a short sparse tail. Emitters are
-- named by role and grouped by beat (reference H). They sit beside the originals, which
-- stay as they are, and `needs` hides them in the plugin until v4 has uploaded IDs.
local function v4(pack: string, beat: string, at: any, fields: { [string]: any }): Layer
	local layer: Layer = {
		type = "particles",
		hd = true,
		pack = pack,
		group = beat,
		at = at,
		burst = 1,
		speed = { 0, 0 },
		rotation = { 0, 360 },
		color = { "w" },
		lightEmission = 1,
		lightInfluence = 0,
		brightness = 2,
	}
	for k, v in fields do
		layer[k] = v
	end
	return layer
end

-- the flash beat: a 2-frame core, a cross flare and god rays over a dark halo
local function heroFlash(at: any, size: number, delay: number?): { Layer }
	return {
		v4("shape_core_flash", "Hit", at, {
			name = "Core",
			delay = delay,
			size = { { 0, size * 0.85 }, { 1, size * 0.5 } },
			transparency = { { 0, 0 }, { 0.6, 0 }, { 1, 1 } },
			lifetime = { 0.067, 0.067 },
			brightness = 4,
			zOffset = 3,
		}),
		v4("shape_cross_flare", "Hit", at, {
			name = "Flare",
			delay = delay,
			size = { { 0, size * 1.3 }, { 1, size * 1.6 } },
			transparency = { { 0, 0 }, { 0.5, 0.1 }, { 1, 1 } },
			lifetime = { 0.067, 0.067 },
			rotation = { -8, 8 },
			brightness = 3,
			zOffset = 2.5,
		}),
		v4("shape_godray_fan", "Hit", at, {
			name = "Rays",
			delay = delay,
			size = { { 0, size * 0.8 }, { 1, size * 1.4 } },
			transparency = { { 0, 0 }, { 1, 1 } },
			lifetime = { 0.067, 0.067 },
			color = { "w", "p" },
			zOffset = 2,
		}),
		v4("art_dark_halo", "Hit", at, {
			name = "Halo",
			delay = delay,
			size = { { 0, size * 0.9 }, { 1, size * 1.4 } },
			transparency = { { 0, 0.15 }, { 1, 1 } },
			lifetime = { 0.15, 0.15 },
			color = { "k" },
			lightEmission = 0,
			brightness = 1,
			zOffset = -2,
		}),
	}
end

-- shards that explode and stop (high drag), with a per-keypoint size envelope
local function heroShards(at: any, count: number, speed: number, fields: { [string]: any }?): Layer
	local layer = v4("shape_aniso_shard", "Burst", at, {
		name = "Shards",
		burst = count,
		orientation = "VelocityParallel",
		speed = { speed * 0.55, speed },
		spread = { 180, 180 },
		drag = 9,
		size = { { 0, 1.1, 0.35 }, { 0.6, 0.7, 0.2 }, { 1, 0 } },
		squash = { { 0, -0.6 }, { 1, -0.2 } },
		lifetime = { 0.22, 0.38 },
		color = { "w", "p" },
		zOffset = 1,
	})
	if fields then
		for k, v in fields do
			layer[k] = v
		end
	end
	return layer
end

-- a crescent shell carrying every other frame of the slash ribbon (8 of 16): each frame
-- is a baked MeshPart, so fewer frames keep the template light
local RIBBON = {}
for k = 0, 15, 2 do
	table.insert(RIBBON, string.format("seq_slash_ribbon_%02d", k))
end

local function heroShell(mesh: string, fields: { [string]: any }): Layer
	local layer: Layer = { type = "shell", hd = true, mesh = mesh, frames = RIBBON }
	for k, v in fields do
		layer[k] = v
	end
	return layer
end

-- the tail: a few slow embers
local function heroEmbers(at: any, count: number, delay: number?): Layer
	return v4("sheet_embers", "Tail", at, {
		name = "Embers",
		delay = delay,
		burst = count,
		flipbook = "Grid4x4",
		flipMode = "Loop",
		flipRandom = true,
		speed = { 3, 8 },
		spread = { 180, 180 },
		drag = 2.5,
		accel = Vector3.new(0, 3, 0),
		size = { { 0, 0.45, 0.15 }, { 1, 0 } },
		lifetime = { 0.35, 0.5 },
		color = { "w", "p" },
	})
end

-- Layer kits: a layer's variants, picked one at a time in the studio (`evfx serve`, Layers),
-- then combined. A kit's preset is built from its `picks`; tests/timeline.luau can also play
-- one variant alone ("kit__<kit>__<layer>__<variant>") or swapped into the preset
-- ("...__in"), which is what the studio renders. Picks come from Phát, never from the studio.
export type KitVariant = { note: string, layers: { Layer } }
export type Kit = { preset: string, order: { string }, layers: { [string]: { [string]: KitVariant } }, picks: { [string]: string } }

local FLOOR = -1.85
local function floorAt(x: number?, z: number?): Vector3
	return Vector3.new(x or 0, FLOOR, z or 0)
end
local lying = { orientation = "VelocityPerpendicular", direction = "Top", speed = { 0.01, 0.01 } }
local function with(base: { [string]: any }, fields: { [string]: any }): { [string]: any }
	local out = table.clone(base)
	for k, v in fields do
		out[k] = v
	end
	return out
end

-- The fire library (Phát's fire pit, 2026-10-24 to 25, is the first effect built from it): builders
-- for a fire made of particles, timed by a FireBeats table. A game keeps its own tuned fire, the
-- numbers and picks, in its own repo and loads it with Presets.register.
--
-- FireBeats, in seconds: `tell` the anticipation, `strike` the impact, `flash` the flash, `burst`
-- the explosion and `burn` when the fire burns steady; `out` is when it starts dying, `burnFor`
-- how long the layers that outlast the flames (smoke, embers, ground glow) run from `burn`, and
-- `held` how much longer than 15 loop frames it burns. fireBeats builds one: `hold` (seconds)
-- holds the burn longer, in whole 16-frame cycles of an 18 fps flame loop, so it still dies on the
-- loop's frame 15 (0 gives the 15 frames, 0.83 s)
export type FireBeats = {
	tell: number,
	strike: number,
	flash: number,
	burst: number,
	burn: number,
	out: number,
	burnFor: number,
	held: number,
}
local FLAME_FPS = 18
local function fireBeats(o): FireBeats
	local out = o.burn + (math.floor((o.hold or 0) * FLAME_FPS / 16) * 16 + 15) / FLAME_FPS
	return {
		tell = o.tell,
		strike = o.strike,
		flash = o.flash,
		burst = o.burst,
		burn = o.burn,
		out = out,
		burnFor = out - o.burn + 0.967,
		held = out - (o.burn + 15 / FLAME_FPS),
	}
end

-- FireLoop's pool fire, built from hook-flame particles: `o.spots` are where on the seat the
-- flames come from, each streaming `o.rate` a second while the fire burns; a small glowing core,
-- dark hook shapes rising from `o.smokeAt` studs up as smoke, and now and then a tall lick that
-- peels off the top (`o.licks` a second). `o.rise` is the flames'
-- upward pull (studs/s², 5 when left out); `o.inward` pulls each spot's flames toward the middle
-- as they rise (per stud out from it), so a wide seat narrows into a cone. `o.stagger` lets each
-- spot catch up to that many seconds late, with its own rate and speed, so the seat never lights
-- as one ring rising in step (Phát, 2026-10-25: it broke the organic feel)
local function hash(i: number, salt: number): number
	return (math.sin(i * 12.9898 + salt * 78.233) * 43758.5453) % 1
end

local function fireLoop(b: FireBeats, o): { Layer }
	local HOOK = "shape_mold_fire_hook"
	local out = {}
	local stagger = o.stagger or 0
	-- `o.start` lets the fire catch before BURN (from the blast, Phát, 2026-10-25); its licks and
	-- smoke still wait until it has grown, just before BURN
	local start = o.start or b.burn
	local grown = math.max(start, b.burn - 0.3)
	for i, spot in o.spots do
		local late = stagger * hash(i, 1)
		local pace = 1 + stagger * (hash(i, 3) - 0.5)
		table.insert(out, v4(HOOK, "Sustain", floorAt(spot[1], spot[2]) + Vector3.new(0, 0.3, 0), { name = "ContinuousFlame", delay = start + late,
			burst = false, rate = o.rate * (1 + 1.5 * stagger * (hash(i, 2) - 0.5)), streamFor = b.out - start - late,
			orientation = "FacingCameraWorldUp", direction = "Top", speed = { o.speed[1] * pace, o.speed[2] * pace },
			spread = { 8, 8 }, drag = 1,
			accel = Vector3.new(-spot[1] * (o.inward or 0), o.rise or 5, -spot[2] * (o.inward or 0)),
			size = o.size, transparency = { { 0, 0.4 }, { 0.12, 0 }, { 0.75, 0.1 }, { 1, 1 } },
			lifetime = o.life, rotation = { -12, 12 },
			color = { Color3.fromRGB(255, 190, 110), Color3.fromRGB(255, 105, 40), Color3.fromRGB(190, 35, 28) },
			lightEmission = 0.1, brightness = 1.1, zOffset = if i == 1 then 1.2 else 1 }))
	end
	if o.licks then
		table.insert(out, v4(HOOK, "Sustain", floorAt() + Vector3.new(0, 0.8, 0), { name = "IntermittentFlame", delay = grown + 0.1,
			burst = false, rate = o.licks, streamFor = b.out - grown, orientation = "FacingCameraWorldUp",
			direction = "Top", speed = { o.speed[2], o.speed[2] + 2 }, spread = { 6, 6 }, accel = Vector3.new(0, o.rise or 5, 0),
			size = { { 0, 2 }, { 0.25, 3.6 }, { 1, 1 } }, transparency = { { 0, 0.3 }, { 0.1, 0 }, { 0.7, 0.15 }, { 1, 1 } },
			lifetime = { 0.6, 0.8 }, rotation = { -12, 12 },
			color = { Color3.fromRGB(255, 190, 110), Color3.fromRGB(255, 100, 40), Color3.fromRGB(185, 33, 28) },
			lightEmission = 0.1, brightness = 1.1, zOffset = 1.1 }))
	end
	table.insert(out, v4(HOOK, "Sustain", floorAt() + Vector3.new(0, 0.2, 0), { name = "FlameCore", delay = start,
		burst = false, rate = 10, streamFor = b.out - start, orientation = "FacingCameraWorldUp",
		direction = "Top", speed = { 1, 2 }, spread = { 12, 12 }, accel = Vector3.new(0, 2, 0),
		size = { { 0, 1.4 }, { 0.4, 1.9 }, { 1, 0.6 } }, transparency = { { 0, 0.5 }, { 0.15, 0.1 }, { 1, 1 } },
		lifetime = { 0.3, 0.45 }, rotation = { -12, 12 }, color = { Color3.fromRGB(255, 215, 150), Color3.fromRGB(255, 135, 55) },
		lightEmission = 0.3, brightness = 1.15, zOffset = 1.4 }))
	local smoke = o.smokeSize or 2.4
	table.insert(out, v4(HOOK, "Sustain", floorAt() + Vector3.new(0, o.smokeAt, 0), { name = "BuoyantPlume", delay = grown + 0.1,
		burst = false, rate = o.smokeRate, streamFor = b.out - grown, orientation = "FacingCameraWorldUp",
		direction = "Top", speed = { 3, 4.5 }, spread = { 18, 18 }, accel = Vector3.new(0, 2, 0),
		size = { { 0, 1.2 }, { 0.4, smoke * 0.85 }, { 1, smoke } }, transparency = { { 0, 1 }, { 0.12, 0 }, { 0.7, 0.25 }, { 1, 1 } },
		lifetime = { 0.7, 1 }, rotation = { -20, 20 }, color = { Color3.fromRGB(60, 40, 36), Color3.fromRGB(26, 22, 22) },
		lightEmission = 0, brightness = 1, zOffset = 0.5 }))
	return out
end


-- A flame jet as one Beam (Phát, 2026-10-24: "one single texture, but on a beam"): the texture
-- is his two-peak sketch (beam/flame_spire), base on the spot. It flashes in, then narrows as it
-- stretches out over its 2 frames (f8-9).
local JET_TINT = Color3.fromRGB(255, 250, 150)

local function fireSpike(azimuth: number, fromVertical: number, delay: number, length: number): Layer
	return {
		type = "shape",
		kind = "Jet",
		hd = true,
		name = "JetFlame",
		packAttrs = { Texture = "beam_flame_spire" },
		attrs = {
			Delay = delay,
			Duration = 0.08,
			Offset = floorAt() + Vector3.new(0, 0.2, 0),
			Tilt = Vector3.new(0, -azimuth, -fromVertical),
			Length0 = length * 0.6,
			Length1 = length,
			-- thinner across than the texture's square, as the reference's jets are
			Width0 = length * 0.24,
			Width1 = length * 0.06,
			Flash = 1.6,
			FlashFor = 0.35,
			FadeStart = 0.6,
			Ease = "Out",
			-- additive, so where the two jets cross (and over the burst) the light adds up and they
			-- merge into one hot source instead of one lying over the other; the brightness stays
			-- low enough that each jet's two tones still read
			Glow = 1,
			Brightness = 0.7,
			Transparency = 0.1,
			-- the V changes as one each play: tipped up to 15 degrees either way in its own plane,
			-- and mirrored half the time, never turned edge-on (Phát: they merged when it did)
			Sway = 30,
			Mirror = 1,
		},
		-- tinted so the cream core, with the bloom added, lands on the reference's pale yellow
		-- (about 253, 255, 190 at its hottest), not white
		color0 = JET_TINT,
	}
end


-- A transparency that breathes over `life` seconds: a slow, uneven swell about every 0.8 s
-- (never twice the same), `deep` at a swell and `shallow` between, then a fade out over the
-- last `fade` of its life. For heat that stays and pulses (Phát, 2026-10-25)
local function breathe(life: number, deep: number, shallow: number, fade: number): { { number } }
	local out = { { 0, shallow } }
	local steps = math.min(16, math.floor(life * (1 - fade) / 0.4))
	for k = 1, steps do
		local t = k / (steps + 1) * (1 - fade)
		table.insert(out, { t, if k % 2 == 0 then deep + (k % 3) * 0.03 else shallow })
	end
	table.insert(out, { 1 - fade, shallow })
	table.insert(out, { 1, 1 })
	return out
end

-- the breathing tints come on with the tell, before the blast (the reference's f7: the air and
-- the floor are already red-pink): `breathe`, faded in over its first 0.12 s
local function breatheIn(life: number, deep: number, shallow: number, fade: number): { { number } }
	local out = breathe(life, deep, shallow, fade)
	out[1] = { 0, 1 }
	table.insert(out, 2, { math.min(0.12 / life, out[2][1] * 0.5), shallow })
	return out
end

-- AirGlow: the burst's red puff, and (`deep`, `shallow` given) a faint pink that stays in the air
-- behind the fire from the tell until it burns out, breathing between those transparencies, in `tint` (pink when
-- left out)
local function airGlow(b: FireBeats, deep: number?, shallow: number?, tint: Color3?): { Layer }
	local out = {
		-- from the tell (the reference's f7: the air is already red before the blast), swelling
		-- through the blast and gone by f27
		v4("shape_soft_glow", "Explosion", floorAt() + Vector3.new(0, 2.2, 0), { name = "AirGlowBurst", delay = b.tell,
			orientation = "FacingCamera", size = { { 0, 9 }, { 0.2, 11 }, { 1, 17 } },
			transparency = { { 0, 0.5 }, { 0.15, 0.35 }, { 0.4, 0.55 }, { 1, 1 } }, lifetime = { 0.7, 0.7 }, rotation = { 0, 0 },
			color = { Color3.fromRGB(205, 30, 45) }, lightEmission = 1, brightness = 1, zOffset = -2 }),
	}
	if deep and shallow then
		local start = b.tell - 0.017
		local life = b.burn + b.burnFor - start
		table.insert(out, v4("shape_soft_glow", "Sustain", floorAt() + Vector3.new(0, 2.4, 0), { name = "AirGlowLoop", delay = start,
			orientation = "FacingCamera", size = 13, transparency = breatheIn(life, deep, shallow, 0.15),
			lifetime = { life, life }, rotation = { 0, 0 },
			color = { tint or Color3.fromRGB(200, 45, 85) }, lightEmission = 1, brightness = 1, zOffset = -2 }))
	end
	return out
end

-- The ignite (the reference's f7, Phát, 2026-10-25): a heap of flames on the spot, a tall one in
-- the middle and five shorter ones round it, each placed apart so the heap reads as flames, not
-- one white blob; painted, cream at the foot burning to orange, and buried by the jets a frame on
local function flameKernels(b: FireBeats): { Layer }
	local out = {}
	for k = 0, 5 do
		local a = math.rad(k * 72 + 40 * hash(k, 31))
		local r = if k == 0 then 0 else 0.7 + 0.4 * hash(k, 32)
		local tall = if k == 0 then 1.25 else 0.8 + 0.25 * hash(k, 33)
		table.insert(out, v4("shape_mold_fire_hook", "Anticipation", floorAt(math.cos(a) * r, math.sin(a) * r) + Vector3.new(0, 0.5, 0), {
			name = "FlameKernel", delay = b.tell, burst = 1, orientation = "FacingCameraWorldUp", direction = "Top",
			speed = { 0.5, 1.5 }, spread = { 20, 20 }, drag = 4,
			size = { { 0, 2.4 * tall }, { 0.5, 3 * tall }, { 1, 2.8 * tall } }, transparency = { { 0, 0 }, { 0.7, 0 }, { 1, 1 } },
			lifetime = { 0.05, 0.07 }, rotation = { -12, 12 },
			color = { Color3.fromRGB(255, 220, 150), Color3.fromRGB(255, 150, 70), Color3.fromRGB(215, 60, 35) },
			lightEmission = 0.3, brightness = 1.5, zOffset = 1 }))
	end
	return out
end

-- GroundGlow: a glow `size` studs across lying on the floor from the anticipation to the
-- fire's end, breathing between `deep` and `shallow` transparency, in `color`
local function groundGlow(b: FireBeats, size: number, deep: number, shallow: number, color: Color3): Layer
	local start = b.tell - 0.017
	local life = b.burn + b.burnFor - start
	return v4("shape_soft_glow", "Sustain", floorAt() + Vector3.new(0, 0.017, 0), with(lying, { name = "BounceLight", delay = start,
		size = size, transparency = breatheIn(life, deep, shallow, 0.15), lifetime = { life, life }, rotation = { 0, 0 },
		color = { color }, lightEmission = 1, brightness = 1 }))
end

-- The fireball (Phát, 2026-10-25: a Molotov), built from hook flames, all upright (the texture's
-- axis stays vertical), painted rather than glowing so they keep their colour where they overlap,
-- cream at birth burning to red. `scale` sizes every flame (1 as tuned):
--   FireballCore   the fire packs into one dense white-hot ball on the spot under the spikes
--                  (`core` flames; the reference's f8-10)
--   FireballHeart  a dense heart of flames (`heart` a second, for `heartFor` seconds) keeps the
--                  middle full through the blast; `heartRise` scales how fast it rises
--   VortexRing     the blast as one toroidal flow (Phát, 2026-10-25): fire leaves the core going
--                  down and outward, skims out along the floor, slows, and rises a little at the rim
--                  as it curls over; thrown once, over `pour` seconds, and gone. `torus` is how far
--                  it spreads (studs), `lift` the hot air's pull up on it, `curl` how hard its far
--                  end is drawn back in as it rises
-- `life` scales every flame's life (1 as tuned); `edge` is how see-through the ring's flames start,
-- so they melt away instead of showing as single flames; `dim` scales every flame's brightness;
-- `spin` (degrees) turns each flame its own way at birth, up to that far, and slowly after. The
-- crown, surge, roll, licks and swirl tail it was built from before are in git history
local function fireball(b: FireBeats, o): { Layer }
	local HOOK = "shape_mold_fire_hook"
	local k_ = o.scale or 1
	local function grow(a, b, c)
		return { { 0, a * k_ }, { 0.3, b * k_ }, { 1, c * k_ } }
	end
	local t0 = b.flash - 0.017
	local hot = { Color3.fromRGB(255, 175, 90), Color3.fromRGB(245, 95, 38), Color3.fromRGB(185, 33, 28) }
	local lf = o.life or 1
	local function lives(a, b)
		return { a * lf, b * lf }
	end
	local ringStart = o.edge * 0.6
	local out = {}
	table.insert(out, v4(HOOK, "Explosion", floorAt() + Vector3.new(0, 0.5, 0), { name = "FireballCore", delay = b.strike - 0.017,
		-- a ball, not a flame: each turned its own way, nudged off the spot and held by drag
		burst = o.core, orientation = "FacingCameraWorldUp", direction = "Top", speed = { 1, 3 }, spread = { 180, 180 },
		drag = 12, size = grow(1.6, 2.6, 2.6), transparency = { { 0, 0 }, { 0.8, 0 }, { 1, 0.6 } },
		lifetime = { b.flash - b.strike + 0.05, b.flash - b.strike + 0.1 }, rotation = { 0, 360 }, color = { Color3.fromRGB(255, 225, 160), Color3.fromRGB(255, 175, 90) },
		lightEmission = 0.3, brightness = 1.3, zOffset = 1.3 }))
	table.insert(out, v4(HOOK, "Explosion", floorAt() + Vector3.new(0, 0.4, 0), { name = "FireballHeart", delay = t0,
		burst = false, rate = o.heart, streamFor = o.heartFor, orientation = "FacingCameraWorldUp", direction = "Top",
		speed = { 0.5, 2.2 * o.heartRise }, spread = { 40, 40 }, drag = 2, accel = Vector3.new(0, 3 * o.heartRise, 0),
		size = grow(1.3, 2.2, 0.6), transparency = { { 0, 0.1 }, { 0.6, 0.15 }, { 1, 1 } },
		lifetime = lives(0.35, 0.5), rotation = { 0, 0 }, color = hot, lightEmission = 0.15, brightness = 1.15, zOffset = 1.25 }))
	local m = 22
	local spinT = 15
	for k = 0, m - 1 do
		local az = spinT + (k + hash(k, 21) - 0.5) * 360 / m
		local a = math.rad(az)
		local cx, cz = math.cos(a), math.sin(a)
		-- a little below level, out of the core, slowed by drag to about `torus` studs, lifted by the
		-- hot air so the far end curls up, and drawn back in a touch as it curls
		local reachSpeed = o.torus * 2.8
		table.insert(out, v4(HOOK, "Explosion", floorAt(cx * 0.2, cz * 0.2) + Vector3.new(0, 0.6, 0), { name = "VortexRing",
			delay = t0, tilt = Vector3.new(0, -az, -(100 + 8 * hash(k, 22))), burst = false, rate = 4 / o.pour, streamFor = o.pour,
			orientation = "FacingCameraWorldUp", direction = "Top",
			speed = { reachSpeed * 0.8, reachSpeed * 1.15 }, spread = { 14, 14 }, drag = 4.5,
			accel = Vector3.new(-cx * o.curl, o.lift, -cz * o.curl),
			size = grow(1.8, 3.2, 0.8), transparency = { { 0, ringStart }, { 0.5, ringStart + 0.05 }, { 1, 1 } }, lifetime = lives(0.45, 0.65),
			rotation = { 0, 0 }, color = hot, lightEmission = 0.15, brightness = 1.1, zOffset = 1.15 }))
	end
	for _, layer in out do
		layer.brightness = (layer.brightness or 1) * (o.dim or 1)
		if o.spin then
			layer.rotation = { -o.spin, o.spin }
			layer.rotSpeed = { -30, 30 }
		end
	end
	return out
end

-- Kits. A kit's preset is built from its picks; this repo keeps only the demo, a small campfire
-- from the fire library's builders. Tuned kits live in their games' repos (Presets.register)
local CAMP = fireBeats({ tell = 0, strike = 0, flash = 0, burst = 0, burn = 0.2, hold = 1 })

Presets.Kits = {
	campfire = {
		preset = "campfire_demo",
		order = { "FireLoop", "EmberLoop", "GroundGlow", "PointLight" },
		layers = {
			FireLoop = {
				A = { note = "a pool fire of hook flames on a small seat, narrowing into a cone, smoke off the tips", layers = fireLoop(CAMP, {
					spots = { { 0, 0 }, { 0.5, 0.3 }, { -0.5, -0.3 }, { 0.3, -0.5 } }, rate = 5, speed = { 2, 3.5 }, life = { 0.6, 0.8 },
					stagger = 0.2, size = { { 0, 1.4 }, { 0.3, 2.6 }, { 1, 0.5 } }, rise = 2, inward = 1, smokeAt = 3, smokeRate = 3, licks = 1,
				}) },
			},
			EmberLoop = {
				A = { note = "small sparks rising off the fire", layers = {
					v4("shape_soft_glow", "Sustain", floorAt() + Vector3.new(0, 1, 0), { name = "LoftedFirebrands", delay = CAMP.burn,
						burst = false, rate = 4, streamFor = CAMP.out - CAMP.burn, direction = "Top", speed = { 3, 6 }, spread = { 40, 40 },
						drag = 1.6, accel = Vector3.new(1.5, 2.2, 0.5), size = { { 0, 0.25, 0.08 }, { 1, 0 } },
						transparency = { { 0, 0 }, { 0.7, 0.1 }, { 1, 1 } }, lifetime = { 0.9, 1.4 }, rotation = { 0, 0 },
						color = { Color3.fromRGB(255, 120, 60) }, lightEmission = 1, brightness = 2.5, zOffset = 2 }),
				} },
			},
			GroundGlow = {
				A = { note = "a warm glow lying on the floor round the fire, breathing", layers = { groundGlow(CAMP, 6, 0.5, 0.65, Color3.fromRGB(240, 100, 50)) } },
			},
			PointLight = {
				A = { note = "the fire's light", layers = {
					{ type = "light", brightness = 2.5, range = 8, color = Color3.fromRGB(240, 110, 50), delay = CAMP.burn, flash = CAMP.out - CAMP.burn + 0.5 },
				} },
			},
		},
		picks = { FireLoop = "A", EmberLoop = "A", GroundGlow = "A", PointLight = "A" },
	},
} :: { [string]: Kit }

--- A kit's layers with `picks` (a layer -> variant map) over its own; a layer with no pick
--- uses its first variant, and a layer picked "-" is left out. `only` keeps one layer.
function Presets.kitLayers(kit: Kit, picks: { [string]: string }?, only: string?): { Layer }
	local out = {}
	for _, name in kit.order do
		local off = ((picks and picks[name]) or kit.picks[name]) == "-"
		if (only == nil or only == name) and not off then
			local variants = kit.layers[name]
			local pick = (picks and picks[name]) or kit.picks[name]
			local chosen = pick and variants[pick]
			if not chosen then
				local keys = {}
				for k in variants do
					table.insert(keys, k)
				end
				table.sort(keys)
				chosen = variants[keys[1]]
			end
			for _, layer in chosen.layers do
				table.insert(out, layer)
			end
		end
	end
	return out
end

-- extra layers per preset (appended after the list below)
local IMPACT_KIT: { [string]: { Layer } } = {}

Presets.List = ({
	------------------------------------------------------------------ Combat
	{
		id = "fireball",
		category = "projectile",
		name = { vi = "Cầu lửa", en = "Fireball" },
		desc = { vi = "Quả cầu bay theo đường cong rồi nổ", en = "Arcing shot that bursts on impact" },
		kind = "burst",
		defaults = { color1 = rgb(255, 150, 40), color2 = rgb(230, 40, 20), trigger = "Loop", interval = 2 },
		layers = {
			{
				type = "shape",
				kind = "Projectile",
				attrs = { To = Vector3.new(0, 0, -28), ArcHeight = 3, Duration = 0.55, HeadSize = 1.6, Width = 1.1, TrailLength = 0.3, Ease = "Linear", Brightness = 2 },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Orb",
				attrs = { Offset = Vector3.new(0, 0, -28), Delay = 0.55, Size0 = 1, Size1 = 7, Duration = 0.22, Transparency = 0.1, FadeStart = 0 },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "shape",
				kind = "Ring",
				attrs = { Offset = Vector3.new(0, 0, -28), Delay = 0.55, Tilt = Vector3.new(90, 0, 0), Radius0 = 0.5, Radius1 = 9, Width0 = 1.2, Width1 = 0.05, Duration = 0.4 },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Offset = Vector3.new(0, 0, -28), Delay = 0.55, Count = 12, Distance0 = 0.5, Distance1 = 9, Length = 4, Width = 0.3, Duration = 0.35 },
				color0 = "w",
				color1 = "p",
			},
			sparks(18, 35, Vector3.new(0, 0, -28)),
			{ type = "shape", kind = "Impact", attrs = { Offset = Vector3.new(0, 0, -28), Delay = 0.55, Duration = 0.08, Style = "Flash", Strength = 0.7 } },
			{ type = "shape", kind = "Shake", attrs = { Offset = Vector3.new(0, 0, -28), Delay = 0.55, Magnitude = 1, Duration = 0.4 } },
		},
	},
	{
		id = "impact_frame",
		category = "impact",
		name = { vi = "Khung hình va chạm", en = "Impact Frame" },
		desc = { vi = "Chớp màn hình kiểu anime + rung camera", en = "Anime screen flash + camera shake" },
		kind = "burst",
		defaults = { color1 = rgb(255, 255, 255), color2 = rgb(255, 60, 60), trigger = "Loop", interval = 2 },
		layers = {
			{ type = "shape", kind = "Impact", attrs = { Duration = 0.1, Style = "Invert" } },
			{ type = "shape", kind = "Impact", attrs = { Delay = 0.1, Duration = 0.12, Style = "Mono", Strength = 0.8 } },
			{ type = "shape", kind = "Shake", attrs = { Magnitude = 2, Duration = 0.5, Roughness = 18 } },
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 22, Distance0 = 0.5, Distance1 = 16, Length = 9, Width = 0.35, Duration = 0.3, Brightness = 2 },
				color0 = "w",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Ring",
				attrs = { Count = 2, Stagger = 0.05, Radius0 = 0.5, Radius1 = 12, Width0 = 1.6, Width1 = 0.05, Duration = 0.35, Tilt = Vector3.new(90, 0, 0) },
				color0 = "w",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Orb",
				attrs = { Size0 = 0.5, Size1 = 5, Duration = 0.15, Transparency = 0, FadeStart = 0 },
				color0 = "w",
				color1 = "s",
			},
			sparks(24, 55),
		},
	},
	{
		id = "slash",
		category = "slash",
		name = { vi = "Chém lưỡi liềm", en = "Crescent Slash" },
		desc = { vi = "Vệt chém sắc nét kiểu anime", en = "Crisp anime sword slash" },
		kind = "burst",
		placement = "air",
		defaults = { color1 = rgb(255, 214, 64), color2 = rgb(255, 120, 20), trigger = "Loop", interval = 1.5 },
		layers = {
			{
				type = "shape",
				kind = "Slash",
				attrs = { Radius = 5, Arc = 170, Width = 2, Sweep = 60, Duration = 0.4, Brightness = 2, TailFade = 0.8 },
				color0 = "p",
				color1 = "s",
			},
			twinkles(14, 28, Vector3.new(0, 0, -4.5), 0.04),
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 8, Mode = "Ring", Distance0 = 3, Distance1 = 9, Length = 3, Width = 0.18, Duration = 0.3, Delay = 0.05 },
				color0 = "p",
				color1 = "s",
			},
			sparks(14, 35),
			{ type = "light", brightness = 3, range = 14, color = "p", flash = 0.25 },
		},
	},
	{
		id = "multi_slash",
		category = "slash",
		name = { vi = "Liên hoàn trảm", en = "Slash Flurry" },
		desc = { vi = "Nhiều nhát chém xoay ngẫu nhiên", en = "Many slashes at random angles" },
		kind = "burst",
		placement = "air",
		defaults = { color1 = rgb(170, 90, 255), color2 = rgb(90, 200, 255), trigger = "Loop", interval = 2 },
		layers = {
			{
				type = "shape",
				kind = "Slash",
				attrs = { Count = 5, Stagger = 0.07, RandomTilt = 70, Radius = 4.5, Arc = 150, Width = 1.6, Sweep = 40, Duration = 0.35, Brightness = 2 },
				color0 = "p",
				color1 = "s",
			},
			twinkles(8, 22, "center", 0.04),
			twinkles(8, 22, "center", 0.18),
			{
				type = "shape",
				kind = "Orb",
				basic = true,
				attrs = { Size0 = 0.6, Size1 = 3, Duration = 0.15, Transparency = 0.45, FadeStart = 0 },
				color0 = "w",
				color1 = "p",
			},
			sparks(24, 40),
			{ type = "light", brightness = 3, range = 16, color = "p", flash = 0.5 },
		},
	},
	{
		id = "impact",
		category = "impact",
		name = { vi = "Va chạm", en = "Hit Impact" },
		desc = { vi = "Chớp sáng + tia + sóng khi đánh trúng", en = "Flash, needles and ring on hit" },
		kind = "burst",
		placement = "air",
		defaults = { color1 = rgb(255, 235, 120), color2 = rgb(255, 140, 40), trigger = "Loop", interval = 1.2 },
		layers = {
			{
				type = "shape",
				kind = "Orb",
				attrs = { Size0 = 0.5, Size1 = 3.5, Duration = 0.15, Transparency = 0.2, FadeStart = 0 },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 14, Mode = "Sphere", Distance0 = 0.5, Distance1 = 8, Length = 4, Width = 0.35, Duration = 0.3 },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "shape",
				kind = "Ring",
				basic = true,
				attrs = { Radius0 = 0.5, Radius1 = 6, Width0 = 0.8, Width1 = 0.05, Duration = 0.35, Tilt = Vector3.new(90, 0, 0) },
				color0 = "p",
				color1 = "s",
			},
			hdFlip("flip_impact", "center", 1, { { 0, 6 }, { 1, 9 } }, { 0.4, 0.4 }, { zOffset = 1, color = { "p", "s" }, brightness = 1.2 }),
			hdRing("center", 13, 0.35, Vector3.new(90, 0, 0)),
			sparks(16, 30),
			{ type = "light", brightness = 4, range = 14, color = "p", flash = 0.2 },
		},
	},
	{
		id = "ground_slam",
		category = "impact",
		name = { vi = "Đập đất", en = "Ground Slam" },
		desc = { vi = "Hố nứt, đá văng, sóng xung kích", en = "Crater, flying rocks, shockwave" },
		kind = "burst",
		placement = "ground",
		defaults = { color1 = rgb(255, 200, 60), color2 = rgb(255, 90, 20), trigger = "Loop", interval = 3.5 },
		layers = {
			{ type = "shape", kind = "Crater", attrs = { Count = 14, Radius = 7, SizeMin = 1.4, SizeMax = 2.6, Duration = 3, Ground = true } },
			{ type = "shape", kind = "Debris", attrs = { Count = 14, Force = 40, SizeMin = 0.4, SizeMax = 1.1, Duration = 2.2, Ground = true } },
			{
				type = "shape",
				kind = "Ring",
				attrs = { Count = 3, Stagger = 0.08, Radius0 = 1, Radius1 = 14, Width0 = 1.4, Width1 = 0.05, Duration = 0.5, Ground = true },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 16, Mode = "Up", Cone = 35, Distance0 = 0, Distance1 = 10, Length = 6, Width = 0.3, Duration = 0.45, Ground = true },
				color0 = "p",
				color1 = "s",
			},
			basic(dust(14)),
			hdDust(12),
			hdRing(Vector3.new(0, -1.8, 0), 30, 0.55),
			hdFlip("flip_impact", Vector3.new(0, -1, 0), 1, { { 0, 7 }, { 1, 11 } }, { 0.35, 0.35 }, { color = { "p", "s" }, brightness = 1.2 }),
			{ type = "shape", kind = "Shake", attrs = { Magnitude = 1.6, Duration = 0.7, Roughness = 10 } },
			{ type = "light", brightness = 5, range = 22, color = "p", flash = 0.35 },
		},
	},
	{
		id = "energy_blast",
		category = "projectile",
		name = { vi = "Pháo năng lượng", en = "Energy Blast" },
		desc = { vi = "Đường hầm vòng sáng bắn về phía trước", en = "Tunnel of rings firing forward" },
		kind = "burst",
		placement = "air",
		defaults = { color1 = rgb(255, 235, 40), color2 = rgb(80, 200, 255), trigger = "Loop", interval = 2 },
		layers = {
			{
				type = "shape",
				kind = "Ring",
				attrs = {
					Count = 7,
					Stagger = 0.04,
					Step = Vector3.new(0, 0, -4),
					Tilt = Vector3.new(90, 0, 0),
					Radius0 = 0.5,
					Radius1 = 4,
					Width0 = 0.6,
					Width1 = 0.05,
					Duration = 0.5,
					Brightness = 2,
				},
				color0 = "p",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 20, Mode = "Forward", Cone = 12, Distance0 = 1, Distance1 = 30, Length = 9, Width = 0.3, Duration = 0.45 },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Orb",
				attrs = { Shape = "Cylinder", Length = 22, Size0 = 2.5, Size1 = 0.3, Tilt = Vector3.new(0, 90, 0), Offset = Vector3.new(0, 0, -11), Duration = 0.45, Transparency = 0.15, FadeStart = 0.3 },
				color0 = "w",
				color1 = "s",
			},
			sparks(18, 45),
			hdFlip("flip_electric", "center", 2, { { 0, 4 }, { 1, 7 } }, { 0.3, 0.4 }, { color = { "w", "s" }, brightness = 3 }),
			{ type = "light", brightness = 4, range = 20, color = "s", flash = 0.4 },
		},
	},
	{
		id = "explosion",
		category = "impact",
		name = { vi = "Vụ nổ", en = "Explosion" },
		desc = { vi = "Cầu lửa, khói, tia lửa, đá vụn", en = "Fireball, smoke, sparks, rubble" },
		kind = "burst",
		placement = "ground",
		defaults = { color1 = rgb(255, 160, 40), color2 = rgb(210, 40, 10), trigger = "Loop", interval = 3 },
		layers = {
			{
				type = "shape",
				kind = "Orb",
				attrs = { Size0 = 1, Size1 = 9, Duration = 0.25, Transparency = 0.15, FadeStart = 0 },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "particles",
				at = "center",
				texture = T.Blast,
				burst = 14,
				color = { "w", "p", "s" },
				size = { { 0, 3 }, { 1, 8 } },
				transparency = { { 0, 0 }, { 0.6, 0.3 }, { 1, 1 } },
				lifetime = { 0.5, 0.9 },
				speed = { 8, 16 },
				spread = { 180, 180 },
				drag = 6,
				rotation = { 0, 360 },
				rotSpeed = { -90, 90 },
				lightEmission = 0.8,
			},
			{
				type = "particles",
				at = "center",
				texture = T.Smoke,
				burst = 10,
				delay = 0.1,
				basic = true,
				color = { "k" },
				size = { { 0, 4 }, { 1, 10 } },
				transparency = { { 0, 0.3 }, { 1, 1 } },
				lifetime = { 1.5, 2.5 },
				speed = { 4, 9 },
				spread = { 180, 180 },
				drag = 3,
				accel = Vector3.new(0, 3, 0),
				rotation = { 0, 360 },
				rotSpeed = { -30, 30 },
				lightEmission = 0,
				lightInfluence = 1,
			},
			{
				type = "shape",
				kind = "Ring",
				attrs = { Radius0 = 1, Radius1 = 18, Width0 = 1.6, Width1 = 0.05, Duration = 0.55, Ground = true },
				color0 = "p",
				color1 = "s",
			},
			{ type = "shape", kind = "Debris", attrs = { Count = 10, Force = 45, Duration = 2, Ground = true } },
			hdFlip("flip_impact", "center", 1, { { 0, 9 }, { 1, 15 } }, { 0.45, 0.45 }, { zOffset = 2, color = { "p", "s" }, brightness = 1.2 }),
			hdFlip("flip_smoke", "center", 9, { { 0, 5 }, { 1, 12 } }, { 1.6, 2.4 }, {
				delay = 0.1,
				color = { "k" },
				lightEmission = 0,
				lightInfluence = 1,
				brightness = 1,
				speed = { 5, 10 },
				spread = { 180, 180 },
				drag = 3,
				accel = Vector3.new(0, 3, 0),
				transparency = { { 0, 0.1 }, { 1, 0.5 } },
			}),
			hdRing(Vector3.new(0, -1.8, 0), 36, 0.55),
			sparks(30, 50),
			{ type = "shape", kind = "Shake", attrs = { Magnitude = 1.4, Duration = 0.6 } },
			{ type = "light", brightness = 8, range = 30, color = "p", flash = 0.5 },
		},
	},
	{
		id = "lightning",
		category = "projectile",
		name = { vi = "Sét đánh", en = "Lightning Strike" },
		desc = { vi = "Tia sét zig-zag từ trời xuống", en = "Zig-zag bolt from the sky" },
		kind = "burst",
		placement = "ground",
		defaults = { color1 = rgb(130, 190, 255), color2 = rgb(200, 120, 255), trigger = "Loop", interval = 2.5 },
		layers = {
			{
				type = "shape",
				kind = "Bolt",
				attrs = { Count = 2, Stagger = 0.06, From = Vector3.new(0, 40, 0), To = Vector3.new(0, -2, 0), Segments = 10, Jitter = 3, Width = 0.7, Duration = 0.4, Brightness = 3 },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Ring",
				attrs = { Radius0 = 0.5, Radius1 = 9, Width0 = 1, Width1 = 0.05, Duration = 0.4, Ground = true },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 10, Mode = "Up", Cone = 60, Distance0 = 0, Distance1 = 6, Length = 3, Width = 0.25, Duration = 0.3, Ground = true },
				color0 = "w",
				color1 = "p",
			},
			sparks(20, 30, Vector3.new(0, -1.8, 0)),
			hdFlip("flip_electric", Vector3.new(0, -1.2, 0), 2, { { 0, 6 }, { 1, 9 } }, { 0.35, 0.45 }, { color = { "w", "p", "s" }, brightness = 3 }),
			hdFlip("flip_impact", Vector3.new(0, -1.2, 0), 1, { { 0, 5 }, { 1, 8 } }, { 0.3, 0.3 }),
			{ type = "shape", kind = "Shake", attrs = { Magnitude = 0.8, Duration = 0.35, Roughness = 22 } },
			{ type = "light", brightness = 10, range = 40, color = "p", flash = 0.35 },
		},
	},
	{
		id = "shockwave",
		category = "impact",
		name = { vi = "Sóng xung kích", en = "Shockwave" },
		desc = { vi = "Nhiều vòng sóng lan trên mặt đất", en = "Rings racing across the ground" },
		kind = "burst",
		placement = "ground",
		defaults = { color1 = rgb(255, 255, 255), color2 = rgb(120, 200, 255), trigger = "Loop", interval = 2 },
		layers = {
			{
				type = "shape",
				kind = "Ring",
				attrs = { Count = 3, Stagger = 0.1, Radius0 = 1, Radius1 = 16, Width0 = 1.2, Width1 = 0.05, Duration = 0.7, Ground = true },
				color0 = "p",
				color1 = "s",
			},
			basic(dust(18)),
			hdDust(16),
			hdRing(Vector3.new(0, -1.8, 0), 34, 0.7),
			hdRing(Vector3.new(0, -1.8, 0), 24, 0.6, nil, 0.12),
		},
	},
	{
		id = "sword_trail",
		category = "slash",
		name = { vi = "Vệt vũ khí", en = "Weapon Trail" },
		desc = { vi = "Gắn vào kiếm: để lại vệt khi vung", en = "Put on a sword: streak when swung" },
		kind = "loop",
		placement = "air",
		area = Vector3.new(0.5, 4, 0.5),
		defaults = { color1 = rgb(120, 210, 255), color2 = rgb(60, 80, 255), trigger = "Always" },
		layers = {
			{
				type = "trail",
				color = { "w", "p", "s" },
				transparency = { { 0, 0.1 }, { 1, 1 } },
				lifetime = 0.25,
				widthScale = { { 0, 1 }, { 1, 0.2 } },
				lightEmission = 1,
				brightness = 2,
				-- HD: fibrous slash streaks instead of a flat band
				packTexture = "slash_fiber",
			},
			{
				-- a thin white-hot edge along the tip of the swing
				type = "trail",
				color = { "w", "w", "p" },
				transparency = { { 0, 0 }, { 0.5, 0.4 }, { 1, 1 } },
				lifetime = 0.12,
				widthScale = { { 0, 1 }, { 1, 0.4 } },
				lightEmission = 1,
				brightness = 3,
				hd = true,
				packTexture = "slash_core",
			},
			{
				-- glints along the blade so a still weapon still reads as enchanted
				type = "particles",
				name = "Glint",
				hd = true,
				pack = "spark_star",
				at = "part",
				rate = 3,
				size = { { 0, 0 }, { 0.3, 0.7 }, { 1, 0 } },
				lifetime = { 0.3, 0.5 },
				speed = { 0, 0 },
				rotation = { 0, 360 },
				color = { "w", "p" },
				lightEmission = 1,
				brightness = 2,
			},
		},
	},

	------------------------------------------------------------------ Magic
	{
		id = "magic_circle",
		category = "circle",
		name = { vi = "Vòng phép", en = "Magic Circle" },
		desc = { vi = "Vòng sáng xoay + hạt bay lên", en = "Spinning rings with rising motes" },
		kind = "loop",
		placement = "ground",
		defaults = { color1 = rgb(170, 90, 255), color2 = rgb(80, 220, 255), trigger = "Always", interval = 1.6 },
		layers = {
			{
				type = "shape",
				kind = "Ring",
				attrs = { Radius0 = 5, Radius1 = 5.4, Width0 = 0.35, Width1 = 0.35, Spin = 90, Duration = 1.6, Transparency = 0.1, FadeStart = 0.6, Ease = "Linear", Ground = true },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Ring",
				attrs = { Radius0 = 3.4, Radius1 = 3.2, Width0 = 0.2, Width1 = 0.2, Spin = -120, Duration = 1.6, Transparency = 0.2, FadeStart = 0.6, Ease = "Linear", Ground = true },
				color0 = "s",
				color1 = "p",
			},
			{
				type = "particles",
				at = "part",
				texture = T.Glow,
				rate = 14,
				color = { "w", "p", "s" },
				size = { { 0, 0 }, { 0.2, 0.5 }, { 1, 0 } },
				lifetime = { 1.2, 2 },
				speed = { 0.2, 0.6 },
				accel = Vector3.new(0, 5, 0),
				lightEmission = 1,
			},
			{ type = "light", brightness = 1.5, range = 12, color = "p" },
		},
	},
	{
		id = "heal",
		category = "aura",
		name = { vi = "Hồi máu", en = "Heal" },
		desc = { vi = "Vòng xanh + tia sáng bay lên", en = "Green ring and rising light" },
		kind = "burst",
		placement = "ground",
		defaults = { color1 = rgb(80, 255, 140), color2 = rgb(210, 255, 120), trigger = "Loop", interval = 2 },
		layers = {
			{
				type = "shape",
				kind = "Ring",
				attrs = { Count = 2, Stagger = 0.15, Radius0 = 1, Radius1 = 5, Width0 = 0.6, Width1 = 0.05, Duration = 0.7, Ground = true },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 12, Mode = "Up", Cone = 8, Distance0 = 0, Distance1 = 9, Length = 3, Width = 0.25, Duration = 0.8, Stagger = 0.3, Ground = true },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "particles",
				at = "part",
				texture = T.Star,
				burst = 24,
				color = { "w", "p" },
				size = { { 0, 0.7 }, { 1, 0 } },
				lifetime = { 0.8, 1.4 },
				speed = { 0.2, 0.5 },
				accel = Vector3.new(0, 10, 0),
				drag = 1,
				rotation = { 0, 360 },
				lightEmission = 1,
			},
			{ type = "light", brightness = 3, range = 12, color = "p", flash = 0.6 },
		},
	},
	{
		id = "level_up",
		category = "aura",
		name = { vi = "Lên cấp", en = "Level Up" },
		desc = { vi = "Cột sáng + vòng bay lên + sao", en = "Light pillar, rising rings, stars" },
		kind = "burst",
		placement = "ground",
		defaults = { color1 = rgb(255, 220, 80), color2 = rgb(255, 255, 255), trigger = "Loop", interval = 3 },
		layers = {
			{
				type = "shape",
				kind = "Orb",
				attrs = { Shape = "Cylinder", Length = 26, Size0 = 3, Size1 = 0.1, Tilt = Vector3.new(0, 0, 90), Offset = Vector3.new(0, 11, 0), Duration = 0.9, Transparency = 0.35, FadeStart = 0.2, Ease = "Out" },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Ring",
				attrs = { Count = 4, Stagger = 0.12, Step = Vector3.new(0, 2, 0), Radius0 = 3, Radius1 = 1.5, Width0 = 0.4, Width1 = 0.1, Duration = 0.8, Ground = true },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "particles",
				at = "part",
				texture = T.Star,
				burst = 30,
				color = { "w", "p" },
				size = { { 0, 0.8 }, { 1, 0 } },
				lifetime = { 1, 1.6 },
				speed = { 0.5, 1 },
				accel = Vector3.new(0, 12, 0),
				rotation = { 0, 360 },
				rotSpeed = { -90, 90 },
				lightEmission = 1,
			},
			{ type = "light", brightness = 4, range = 18, color = "p", flash = 1 },
		},
	},
	{
		id = "power_aura",
		category = "aura",
		name = { vi = "Hào quang sức mạnh", en = "Power Aura" },
		desc = { vi = "Tia năng lượng liên tục bốc lên", en = "Energy streaks rising nonstop" },
		kind = "loop",
		placement = "ground",
		area = Vector3.new(4, 5, 4),
		defaults = { color1 = rgb(80, 200, 255), color2 = rgb(255, 255, 255), trigger = "Always", interval = 0.35 },
		layers = {
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 5, Mode = "Up", Cone = 6, Distance0 = 0, Distance1 = 7, Length = 4, Width = 0.35, Duration = 0.5, Stagger = 0.2, Ground = true },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "particles",
				at = "part",
				texture = T.Glow,
				rate = 25,
				color = { "w", "p" },
				size = { { 0, 0.6 }, { 1, 0 } },
				lifetime = { 0.5, 0.9 },
				speed = { 0.1, 0.3 },
				accel = Vector3.new(0, 14, 0),
				lightEmission = 1,
			},
			{ type = "light", brightness = 2, range = 12, color = "p" },
		},
	},
	{
		id = "portal",
		category = "circle",
		name = { vi = "Cổng dịch chuyển", en = "Portal" },
		desc = { vi = "Hạt xoáy hút vào tâm", en = "Particles swirling inward" },
		kind = "loop",
		placement = "ground",
		area = Vector3.new(7, 7, 7),
		defaults = { color1 = rgb(140, 80, 255), color2 = rgb(60, 220, 255), trigger = "Always", interval = 1 },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Glow,
				rate = 60,
				color = { "s", "p", "w" },
				size = { { 0, 0.6 }, { 1, 0 } },
				transparency = { { 0, 1 }, { 0.3, 0 }, { 1, 0 } },
				lifetime = { 0.8, 1.2 },
				speed = { 2.5, 3.5 },
				shape = "Sphere",
				shapeStyle = "Surface",
				shapeInOut = "Inward",
				lightEmission = 1,
			},
			{
				type = "shape",
				kind = "Ring",
				attrs = { Tilt = Vector3.new(90, 0, 0), Radius0 = 3.4, Radius1 = 0.2, Width0 = 0.3, Width1 = 0.05, Duration = 1, Transparency = 0.1, Ease = "In" },
				color0 = "p",
				color1 = "w",
			},
			{
				type = "particles",
				at = "center",
				texture = T.Glow,
				rate = 4,
				locked = true,
				color = { "p" },
				size = { { 0, 6 }, { 1, 6 } },
				transparency = { { 0, 1 }, { 0.5, 0.5 }, { 1, 1 } },
				lifetime = { 1, 1 },
				speed = { 0, 0 },
				lightEmission = 1,
			},
			{ type = "light", brightness = 2, range = 16, color = "p" },
		},
	},
	{
		id = "shield",
		category = "aura",
		name = { vi = "Khiên năng lượng", en = "Energy Shield" },
		desc = { vi = "Bong bóng bảo vệ lung linh", en = "Shimmering protective bubble" },
		kind = "loop",
		placement = "ground",
		area = Vector3.new(6, 6, 6),
		defaults = { color1 = rgb(90, 180, 255), color2 = rgb(255, 255, 255), trigger = "Always" },
		layers = {
			{ type = "part", shape = "Ball", material = "ForceField", color = "p", transparency = 0, scale = 1.3 },
			{
				type = "particles",
				at = "part",
				texture = T.Star,
				rate = 12,
				color = { "w", "p" },
				size = { { 0, 0 }, { 0.3, 0.5 }, { 1, 0 } },
				lifetime = { 0.6, 1 },
				speed = { 0, 0 },
				shape = "Sphere",
				shapeStyle = "Surface",
				rotation = { 0, 360 },
				lightEmission = 1,
			},
		},
	},
	{
		id = "energy_orb",
		category = "aura",
		name = { vi = "Quả cầu năng lượng", en = "Energy Orb" },
		desc = { vi = "Lõi neon phát sáng + tia điện", en = "Neon core with crackling sparks" },
		kind = "loop",
		placement = "air",
		area = Vector3.new(2, 2, 2),
		defaults = { color1 = rgb(80, 200, 255), color2 = rgb(255, 255, 255), trigger = "Always", interval = 0.4 },
		layers = {
			{ type = "part", shape = "Ball", material = "Neon", color = "p", transparency = 0.1, scale = 0.8 },
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 4, Mode = "Sphere", Distance0 = 0.8, Distance1 = 3, Length = 1.5, Width = 0.15, Duration = 0.25, Stagger = 0.3 },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "particles",
				at = "center",
				texture = T.Glow,
				rate = 8,
				locked = true,
				color = { "p" },
				size = { { 0, 5 }, { 1, 5 } },
				transparency = { { 0, 1 }, { 0.5, 0.6 }, { 1, 1 } },
				lifetime = { 0.6, 0.8 },
				speed = { 0, 0 },
				lightEmission = 1,
			},
			{ type = "light", brightness = 2, range = 12, color = "p" },
		},
	},
	{
		id = "sparkles",
		category = "aura",
		name = { vi = "Lấp lánh", en = "Sparkles" },
		desc = { vi = "Sao lấp lánh quanh vật thể", en = "Twinkling stars around an object" },
		kind = "loop",
		defaults = { color1 = rgb(255, 230, 120), color2 = rgb(255, 255, 255), trigger = "Always" },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Star,
				rate = 15,
				color = { "s", "p" },
				size = { { 0, 0 }, { 0.3, 0.6 }, { 1, 0 } },
				lifetime = { 0.8, 1.5 },
				speed = { 0.5, 1.5 },
				spread = { 180, 180 },
				rotation = { 0, 360 },
				rotSpeed = { -90, 90 },
				lightEmission = 1,
			},
		},
	},

	------------------------------------------------------------------ Elements
	{
		id = "fire",
		category = "elements",
		name = { vi = "Lửa", en = "Fire" },
		desc = { vi = "Ngọn lửa, tàn lửa, khói", en = "Flames, embers and smoke" },
		kind = "loop",
		defaults = { color1 = rgb(255, 140, 40), color2 = rgb(200, 40, 20), trigger = "Always", duration = 3 },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Glow,
				rate = 40,
				color = { "w", "p", "s" },
				size = { { 0, 1.6 }, { 0.5, 1.2 }, { 1, 0 } },
				transparency = { { 0, 0.4 }, { 0.2, 0.1 }, { 1, 1 } },
				lifetime = { 0.6, 1 },
				speed = { 3, 5 },
				spread = { 10, 10 },
				accel = Vector3.new(0, 4, 0),
				drag = 1,
				rotation = { 0, 360 },
				rotSpeed = { -60, 60 },
				lightEmission = 1,
			},
			{
				type = "particles",
				at = "part",
				texture = T.Fire,
				rate = 18,
				color = { "p", "s" },
				size = { { 0, 2 }, { 1, 0.5 } },
				transparency = { { 0, 0.3 }, { 1, 1 } },
				lifetime = { 0.5, 0.9 },
				speed = { 4, 6 },
				rotation = { 0, 360 },
				rotSpeed = { -90, 90 },
				lightEmission = 1,
			},
			{
				type = "particles",
				at = "part",
				texture = T.Square,
				rate = 8,
				color = { "w", "p" },
				size = { { 0, 0.15 }, { 1, 0 } },
				squash = { { 0, -1.5 }, { 1, -1.5 } },
				orientation = "VelocityParallel",
				lifetime = { 1, 2 },
				speed = { 6, 9 },
				spread = { 25, 25 },
				accel = Vector3.new(0, 2, 0),
				drag = 2,
				lightEmission = 1,
			},
			{
				type = "particles",
				at = "part",
				texture = T.Smoke,
				rate = 6,
				color = { "k" },
				size = { { 0, 1.5 }, { 1, 4 } },
				transparency = { { 0, 1 }, { 0.2, 0.7 }, { 1, 1 } },
				lifetime = { 2, 3 },
				speed = { 4, 6 },
				rotSpeed = { -30, 30 },
				lightEmission = 0,
				lightInfluence = 1,
				zOffset = -0.5,
			},
			{ type = "light", brightness = 2, range = 12, color = "p" },
		},
	},
	{
		id = "smoke",
		category = "elements",
		name = { vi = "Khói", en = "Smoke" },
		desc = { vi = "Cột khói bốc lên chậm", en = "Slowly rising smoke column" },
		kind = "loop",
		defaults = { color1 = rgb(170, 170, 175), color2 = rgb(90, 90, 95), trigger = "Always", duration = 4 },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Smoke,
				rate = 10,
				color = { "p", "s" },
				size = { { 0, 2 }, { 1, 6 } },
				transparency = { { 0, 1 }, { 0.15, 0.5 }, { 1, 1 } },
				lifetime = { 3, 5 },
				speed = { 2, 4 },
				spread = { 15, 15 },
				accel = Vector3.new(0, 1, 0),
				rotation = { 0, 360 },
				rotSpeed = { -20, 20 },
				lightEmission = 0,
				lightInfluence = 1,
			},
		},
	},
	{
		id = "frost",
		category = "elements",
		name = { vi = "Băng giá", en = "Frost" },
		desc = { vi = "Tinh thể băng rơi + hơi lạnh", en = "Falling ice glints and cold mist" },
		kind = "loop",
		defaults = { color1 = rgb(170, 230, 255), color2 = rgb(255, 255, 255), trigger = "Always" },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Star,
				rate = 14,
				color = { "s", "p" },
				size = { { 0, 0 }, { 0.3, 0.45 }, { 1, 0 } },
				lifetime = { 1.5, 2.5 },
				speed = { 0.2, 0.5 },
				accel = Vector3.new(0, -1.5, 0),
				rotation = { 0, 360 },
				rotSpeed = { -60, 60 },
				lightEmission = 0.6,
			},
			{
				type = "particles",
				at = "part",
				texture = T.Smoke,
				rate = 5,
				color = { "p" },
				size = { { 0, 2 }, { 1, 4 } },
				transparency = { { 0, 1 }, { 0.3, 0.8 }, { 1, 1 } },
				lifetime = { 2, 3 },
				speed = { 0.5, 1 },
				accel = Vector3.new(0, -1, 0),
				rotSpeed = { -10, 10 },
				lightEmission = 0.2,
				lightInfluence = 0.5,
			},
		},
	},
	{
		id = "fountain",
		category = "elements",
		name = { vi = "Đài phun nước", en = "Fountain" },
		desc = { vi = "Tia nước phun lên rồi rơi", en = "Water jet that arcs and falls" },
		kind = "loop",
		placement = "ground",
		area = Vector3.new(2, 2, 2),
		defaults = { color1 = rgb(110, 190, 255), color2 = rgb(255, 255, 255), trigger = "Always" },
		layers = {
			{
				type = "particles",
				at = "center",
				texture = T.Glow,
				rate = 120,
				color = { "s", "p" },
				size = { { 0, 0.35 }, { 1, 0.15 } },
				transparency = { { 0, 0.2 }, { 1, 0.6 } },
				lifetime = { 1.5, 2 },
				speed = { 22, 26 },
				spread = { 8, 8 },
				accel = Vector3.new(0, -30, 0),
				lightEmission = 0.3,
				lightInfluence = 0.8,
			},
		},
	},

	------------------------------------------------------------------ World
	{
		id = "rain",
		category = "world",
		name = { vi = "Mưa", en = "Rain" },
		desc = { vi = "Mưa rơi trên một vùng rộng", en = "Rain over a wide area" },
		kind = "loop",
		placement = "sky",
		area = Vector3.new(60, 1, 60),
		defaults = { color1 = rgb(170, 190, 220), color2 = rgb(255, 255, 255), trigger = "Always" },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Square,
				rate = 300,
				color = { "p" },
				size = { { 0, 0.12 }, { 1, 0.12 } },
				squash = { { 0, 3 }, { 1, 3 } },
				orientation = "FacingCameraWorldUp",
				transparency = { { 0, 0.4 }, { 1, 0.4 } },
				lifetime = { 0.9, 1.1 },
				speed = { 50, 60 },
				direction = "Bottom",
				accel = Vector3.new(0, -20, 0),
				lightEmission = 0.2,
				lightInfluence = 1,
				noSpread = true,
			},
		},
	},
	{
		id = "snow",
		category = "world",
		name = { vi = "Tuyết", en = "Snow" },
		desc = { vi = "Tuyết rơi nhẹ nhàng", en = "Gently falling snow" },
		kind = "loop",
		placement = "sky",
		area = Vector3.new(60, 1, 60),
		defaults = { color1 = rgb(255, 255, 255), color2 = rgb(200, 220, 255), trigger = "Always" },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Glow,
				rate = 120,
				color = { "p", "s" },
				size = { { 0, 0.35 }, { 1, 0.35 } },
				transparency = { { 0, 1 }, { 0.1, 0.1 }, { 0.9, 0.1 }, { 1, 1 } },
				lifetime = { 8, 10 },
				speed = { 3, 5 },
				direction = "Bottom",
				spread = { 10, 10 },
				windDrag = true,
				drag = 0.5,
				lightEmission = 0.3,
				lightInfluence = 0.5,
			},
		},
	},
	{
		id = "fireflies",
		category = "world",
		name = { vi = "Đom đóm", en = "Fireflies" },
		desc = { vi = "Đốm sáng bay lơ lửng", en = "Floating glowing dots" },
		kind = "loop",
		placement = "ground",
		area = Vector3.new(20, 6, 20),
		defaults = { color1 = rgb(210, 255, 90), color2 = rgb(255, 220, 80), trigger = "Always" },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Glow,
				rate = 6,
				color = { "p", "s" },
				size = { { 0, 0 }, { 0.2, 0.35 }, { 0.8, 0.35 }, { 1, 0 } },
				transparency = { { 0, 0 }, { 0.5, 0.6 }, { 1, 0 } },
				lifetime = { 4, 7 },
				speed = { 0.5, 1 },
				spread = { 180, 180 },
				lightEmission = 1,
			},
		},
	},
	{
		id = "fog",
		category = "world",
		name = { vi = "Sương mù", en = "Ground Fog" },
		desc = { vi = "Sương mỏng sát mặt đất", en = "Thin mist hugging the ground" },
		kind = "loop",
		placement = "ground",
		area = Vector3.new(40, 2, 40),
		defaults = { color1 = rgb(220, 225, 235), color2 = rgb(200, 205, 220), trigger = "Always" },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Smoke,
				rate = 4,
				color = { "p", "s" },
				size = { { 0, 8 }, { 1, 14 } },
				transparency = { { 0, 1 }, { 0.3, 0.85 }, { 0.7, 0.85 }, { 1, 1 } },
				lifetime = { 8, 12 },
				speed = { 0.5, 1 },
				spread = { 180, 180 },
				rotSpeed = { -5, 5 },
				lightEmission = 0,
				lightInfluence = 1,
			},
		},
	},
	{
		id = "confetti",
		category = "world",
		name = { vi = "Pháo giấy", en = "Confetti" },
		desc = { vi = "Giấy màu tung lên ăn mừng", en = "Colorful celebration burst" },
		kind = "burst",
		placement = "ground",
		defaults = { color1 = rgb(255, 80, 120), color2 = rgb(80, 180, 255), trigger = "Loop", interval = 3 },
		layers = (function()
			local layers = {}
			for i, c in { "p", "s", rgb(255, 220, 60), rgb(90, 230, 120) } do
				table.insert(layers, {
					type = "particles",
					at = "center",
					texture = T.Square,
					burst = 15,
					color = { c },
					size = { { 0, 0.35 }, { 1, 0.35 } },
					squash = { { 0, -0.6 }, { 0.25, 0.6 }, { 0.5, -0.6 }, { 0.75, 0.6 }, { 1, -0.6 } },
					lifetime = { 3, 4 },
					speed = { 25, 40 },
					spread = { 35, 35 },
					direction = "Top",
					accel = Vector3.new(0, -25, 0),
					drag = 2,
					rotation = { 0, 360 },
					rotSpeed = { -360, 360 },
					lightEmission = 0,
					lightInfluence = 1,
					delay = (i - 1) * 0.02,
				})
			end
			return layers
		end)(),
	},
	{
		id = "bubbles",
		category = "world",
		name = { vi = "Bong bóng", en = "Bubbles" },
		desc = { vi = "Bong bóng nổi lên", en = "Rising bubbles" },
		kind = "loop",
		defaults = { color1 = rgb(180, 230, 255), color2 = rgb(255, 255, 255), trigger = "Always" },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Bubble,
				rate = 6,
				color = { "p", "s" },
				size = { { 0, 0.4 }, { 1, 1 } },
				transparency = { { 0, 1 }, { 0.1, 0.2 }, { 0.9, 0.3 }, { 1, 1 } },
				lifetime = { 3, 5 },
				speed = { 1, 2 },
				direction = "Top",
				spread = { 20, 20 },
				accel = Vector3.new(0, 1, 0),
				rotSpeed = { -30, 30 },
				lightEmission = 0.3,
			},
		},
	},

	------------------------------------------------------------------ Light
	{
		id = "laser",
		category = "projectile",
		name = { vi = "Tia laser", en = "Laser Beam" },
		desc = { vi = "Tia sáng bắn thẳng phía trước", en = "Straight beam shooting forward" },
		kind = "loop",
		placement = "air",
		area = Vector3.new(1, 1, 1),
		defaults = { color1 = rgb(255, 40, 70), color2 = rgb(255, 160, 160), trigger = "Always", duration = 1 },
		layers = {
			{ type = "beam", from = Vector3.zero, to = Vector3.new(0, 0, -30), width = 0.35, color = { "w" }, lightEmission = 1, brightness = 3 },
			{ type = "beam", from = Vector3.zero, to = Vector3.new(0, 0, -30), width = 1.4, color = { "p", "s" }, transparency = { { 0, 0.3 }, { 1, 0.5 } }, lightEmission = 1, brightness = 2, basic = true },
			-- HD: a soft-edged body with energy pulses running down it
			{
				type = "beam",
				hd = true,
				from = Vector3.zero,
				to = Vector3.new(0, 0, -30),
				width = 2.4,
				color = { "p", "s" },
				lightEmission = 1,
				brightness = 3,
				packTexture = "slash_core",
				textureMode = "Wrap",
				textureLength = 7,
				textureSpeed = 2.5,
			},
			{
				type = "beam",
				hd = true,
				from = Vector3.zero,
				to = Vector3.new(0, 0, -30),
				width = 1.2,
				color = { "w", "p" },
				lightEmission = 1,
				brightness = 2,
				packTexture = "slash_core",
				textureMode = "Wrap",
				textureLength = 30,
			},
			-- muzzle flare and the burning hit point
			{
				type = "particles",
				name = "MuzzleHD",
				hd = true,
				pack = "hit_star",
				at = Vector3.zero,
				rate = 14,
				size = { { 0, 1.6 }, { 1, 2.2 } },
				transparency = { { 0, 0 }, { 1, 1 } },
				lifetime = { 0.08, 0.12 },
				speed = { 0, 0 },
				rotation = { 0, 360 },
				color = { "w", "p" },
				lightEmission = 1,
				brightness = 3,
			},
			{
				type = "particles",
				name = "HitPointHD",
				hd = true,
				pack = "flip_hitspark",
				at = Vector3.new(0, 0, -30),
				flipbook = "Grid4x4",
				flipMode = "OneShot",
				rate = 10,
				size = { { 0, 2.5 }, { 1, 4 } },
				lifetime = { 0.25, 0.3 },
				speed = { 0, 0 },
				rotation = { 0, 360 },
				color = { "w", "p" },
				lightEmission = 1,
				brightness = 3,
			},
			{
				type = "particles",
				at = Vector3.new(0, 0, -30),
				texture = T.Square,
				rate = 30,
				color = { "w", "p" },
				size = { { 0, 0.2 }, { 1, 0 } },
				squash = { { 0, -2 }, { 1, -2 } },
				orientation = "VelocityParallel",
				lifetime = { 0.2, 0.4 },
				speed = { 15, 25 },
				spread = { 180, 180 },
				drag = 4,
				lightEmission = 1,
			},
			{ type = "light", at = Vector3.new(0, 0, -30), brightness = 3, range = 10, color = "p" },
		},
	},
	{
		id = "glow",
		category = "aura",
		name = { vi = "Quầng sáng", en = "Soft Glow" },
		desc = { vi = "Vầng sáng dịu + đèn", en = "Soft halo with a light" },
		kind = "loop",
		defaults = { color1 = rgb(255, 220, 150), color2 = rgb(255, 255, 255), trigger = "Always" },
		layers = {
			{
				type = "particles",
				at = "center",
				texture = T.Glow,
				rate = 3,
				locked = true,
				color = { "p" },
				size = { { 0, 8 }, { 1, 8 } },
				transparency = { { 0, 1 }, { 0.5, 0.6 }, { 1, 1 } },
				lifetime = { 2, 2 },
				speed = { 0, 0 },
				lightEmission = 1,
			},
			{ type = "light", brightness = 1.5, range = 14, color = "p" },
		},
	},
	{
		id = "outline",
		category = "aura",
		name = { vi = "Viền phát sáng", en = "Glowing Outline" },
		desc = { vi = "Tô viền vật thể (Highlight)", en = "Outline the object (Highlight)" },
		kind = "loop",
		defaults = { color1 = rgb(255, 200, 60), color2 = rgb(255, 255, 255), trigger = "Always" },
		layers = {
			{ type = "highlight", fill = "p", outline = "s", fillTransparency = 0.6, outlineTransparency = 0 },
		},
	},
	{
		id = "tornado",
		category = "elements",
		name = { vi = "Lốc xoáy", en = "Tornado" },
		desc = { vi = "Các dải gió xoắn ốc bay lên", en = "Twisting wind strands spiraling up" },
		kind = "burst",
		placement = "ground",
		defaults = { color1 = rgb(200, 240, 255), color2 = rgb(120, 200, 255), trigger = "Loop", interval = 0.35 },
		layers = {
			{
				type = "shape",
				kind = "Spiral",
				attrs = { Count = 3, Turns = 2.5, Height = 14, Radius0 = 1, Radius1 = 5, Width = 0.7, Duration = 1, Spin = 300, Ground = true, Transparency = 0.15 },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "shape",
				kind = "Ring",
				attrs = { Radius0 = 1, Radius1 = 6, Width0 = 0.5, Width1 = 0.05, Duration = 0.6, Spin = 180, Ground = true, Transparency = 0.4 },
				color0 = "p",
				color1 = "s",
			},
			basic(dust(3)),
		},
	},
	{
		id = "charge_up",
		category = "aura",
		name = { vi = "Tụ lực", en = "Charge Up" },
		desc = { vi = "Năng lượng xoáy và hút vào tâm", en = "Energy spiraling and pulling inward" },
		kind = "burst",
		defaults = { color1 = rgb(90, 200, 255), color2 = rgb(170, 90, 255), trigger = "Loop", interval = 1.2 },
		layers = {
			{
				type = "shape",
				kind = "Spiral",
				attrs = { Offset = Vector3.new(0, -3, 0), Count = 4, Turns = 1.5, Height = 3, Radius0 = 4, Radius1 = 0.3, Width = 0.35, Duration = 0.9, Spin = -240, Ease = "InOut" },
				color0 = "p",
				color1 = "w",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 14, Distance0 = 9, Distance1 = 0.4, Length = 3, Width = 0.2, Duration = 0.5, Stagger = 0.5, Ease = "In" },
				color0 = "p",
				color1 = "w",
			},
			{
				type = "shape",
				kind = "Orb",
				attrs = { Size0 = 0.3, Size1 = 2.2, Duration = 1.1, Transparency = 0.1, FadeStart = 0.8, Ease = "In" },
				color0 = "s",
				color1 = "w",
			},
			{ type = "light", brightness = 3, range = 14, color = "p", flash = 1.1 },
		},
	},
	------------------------------------------------------------------ Dark fantasy
	{
		id = "shadow_slash",
		category = "slash",
		style = "dark",
		name = { vi = "Chém bóng tối", en = "Shadow Slash" },
		desc = { vi = "Vệt chém đen, viền tím, khói tan", en = "Black slash, violet edge, fading smoke" },
		kind = "burst",
		defaults = { color1 = rgb(170, 90, 255), color2 = rgb(60, 10, 90), trigger = "Loop", interval = 1.6 },
		layers = {
			{
				type = "shape",
				kind = "Slash",
				attrs = { Radius = 6, Arc = 170, Width = 2.6, Sweep = 60, Duration = 0.5, Glow = 0, CoreGlow = 1, Brightness = 3, TailFade = 0.9 },
				color0 = "x",
				color1 = "k",
				core = "p",
			},
			{
				type = "shape",
				kind = "Slash",
				attrs = { Delay = 0.05, Radius = 6.4, Arc = 150, Width = 0.5, Sweep = 60, Duration = 0.45, Brightness = 3, Core = false },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Delay = 0.08, Count = 10, Mode = "Ring", Distance0 = 1, Distance1 = 8, Length = 3, Width = 0.25, Duration = 0.35, Brightness = 2 },
				color0 = "p",
				color1 = "s",
			},
			darkSmoke(8, "center", { delay = 0.1, speed = { 2, 5 } }),
			twinkles(12, 26, Vector3.new(0, 0, -5), 0.06, { "p", "s" }),
		},
	},
	{
		id = "soul_flame",
		category = "elements",
		style = "dark",
		name = { vi = "Lửa linh hồn", en = "Soul Flame" },
		desc = { vi = "Lửa ma xanh lục, khói đen, tàn bay", en = "Ghostly green fire, black smoke, embers" },
		kind = "loop",
		defaults = { color1 = rgb(90, 255, 200), color2 = rgb(20, 120, 110), trigger = "Always", duration = 3 },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Fire,
				rate = 22,
				color = { "w", "p", "s" },
				size = { { 0, 1.8 }, { 0.6, 1.2 }, { 1, 0 } },
				transparency = { { 0, 0.3 }, { 0.3, 0.05 }, { 1, 1 } },
				lifetime = { 0.6, 1.1 },
				speed = { 3, 5 },
				spread = { 8, 8 },
				accel = Vector3.new(0, 3, 0),
				rotation = { 0, 360 },
				rotSpeed = { -90, 90 },
				lightEmission = 1,
			},
			{
				type = "particles",
				at = "part",
				texture = T.Smoke,
				rate = 8,
				color = { "x", "k" },
				size = { { 0, 1.5 }, { 1, 4.5 } },
				transparency = { { 0, 1 }, { 0.25, 0.45 }, { 1, 1 } },
				lifetime = { 2, 3 },
				speed = { 4, 6 },
				rotSpeed = { -30, 30 },
				lightEmission = 0,
				lightInfluence = 1,
				zOffset = -0.5,
			},
			embers(10, "part", { "w", "p" }),
			{ type = "light", brightness = 2.5, range = 14, color = "p" },
		},
	},
	{
		id = "blood_burst",
		category = "impact",
		style = "dark",
		name = { vi = "Huyết bạo", en = "Blood Burst" },
		desc = { vi = "Vụ nổ máu đỏ thẫm, giọt văng, vòng đỏ", en = "Crimson burst, flying drops, red ring" },
		kind = "burst",
		placement = "ground",
		defaults = { color1 = rgb(200, 10, 30), color2 = rgb(70, 0, 10), trigger = "Loop", interval = 2.5 },
		layers = {
			{
				type = "shape",
				kind = "Orb",
				attrs = { Size0 = 0.8, Size1 = 6, Duration = 0.22, Material = "SmoothPlastic", Transparency = 0.05, FadeStart = 0.2, Glow = 0 },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 18, Distance0 = 0.5, Distance1 = 11, Length = 4, Width = 0.4, Duration = 0.4, Glow = 0, CoreGlow = 1, Brightness = 2 },
				color0 = "s",
				color1 = "p",
				core = "p",
			},
			{
				type = "particles",
				at = "center",
				texture = T.Square,
				burst = 40,
				color = { "p", "s" },
				size = { { 0, 0.35 }, { 1, 0.1 } },
				squash = { { 0, -1.8 }, { 1, -1.8 } },
				orientation = "VelocityParallel",
				lifetime = { 0.6, 1.1 },
				speed = { 18, 32 },
				spread = { 180, 180 },
				accel = Vector3.new(0, -60, 0),
				drag = 1.5,
				lightEmission = 0,
				lightInfluence = 1,
			},
			{
				type = "shape",
				kind = "Ring",
				attrs = { Radius0 = 0.5, Radius1 = 10, Width0 = 1.4, Width1 = 0.05, Duration = 0.45, Ground = true, Glow = 0, CoreGlow = 1 },
				color0 = "s",
				color1 = "k",
				core = "p",
			},
			{ type = "shape", kind = "Impact", attrs = { Duration = 0.1, Style = "Flash", Strength = 0.6 } },
			{ type = "shape", kind = "Shake", attrs = { Magnitude = 1, Duration = 0.35 } },
		},
	},
	{
		id = "void_rift",
		category = "circle",
		style = "dark",
		name = { vi = "Khe nứt hư vô", en = "Void Rift" },
		desc = { vi = "Lỗ đen viền tím hút mọi thứ vào trong", en = "Black hole with a violet rim that pulls everything in" },
		kind = "burst",
		area = Vector3.new(6, 9, 6),
		defaults = { color1 = rgb(150, 60, 255), color2 = rgb(30, 0, 60), trigger = "Loop", interval = 0.8 },
		layers = {
			{
				type = "shape",
				kind = "Orb",
				-- a flat black disc facing forward (Ball parts are always round)
				attrs = { Shape = "Cylinder", Length = 0.15, Tilt = Vector3.new(0, 90, 0), Size0 = 5.6, Size1 = 6, Duration = 0.9, Transparency = 0, FadeStart = 0.85, Ease = "Linear" },
				color0 = "x",
				color1 = "x",
			},
			{
				type = "shape",
				kind = "Ring",
				attrs = { Tilt = Vector3.new(90, 0, 0), Radius0 = 3, Radius1 = 3.15, Width0 = 0.45, Width1 = 0.35, Duration = 0.9, Spin = 120, Transparency = 0.05, FadeStart = 0.85, Ease = "Linear", Brightness = 2 },
				color0 = "p",
				color1 = "w",
			},
			{
				type = "shape",
				kind = "Spiral",
				attrs = { Offset = Vector3.new(0, -4, 0), Count = 3, Turns = 2, Height = 8, Radius0 = 3.5, Radius1 = 0.4, Width = 0.3, Duration = 0.9, Spin = -300, Brightness = 2 },
				color0 = "p",
				color1 = "w",
			},
			{
				type = "particles",
				at = "part",
				texture = T.Glow,
				rate = 40,
				color = { "s", "p", "w" },
				size = { { 0, 0.5 }, { 1, 0 } },
				transparency = { { 0, 1 }, { 0.3, 0 }, { 1, 0 } },
				lifetime = { 0.7, 1 },
				speed = { 3, 4 },
				shape = "Sphere",
				shapeStyle = "Surface",
				shapeInOut = "Inward",
				lightEmission = 1,
			},
			{
				type = "shape",
				kind = "Bolt",
				attrs = { From = Vector3.new(0, 4, 0), To = Vector3.new(0, -4, 0), Segments = 8, Jitter = 1.2, Width = 0.18, Duration = 0.25, Delay = 0.3, Brightness = 3 },
				color0 = "p",
				color1 = "w",
			},
			{ type = "light", brightness = 3, range = 16, color = "p" },
		},
	},
	{
		id = "cursed_sigil",
		category = "circle",
		style = "dark",
		name = { vi = "Ấn chú nguyền", en = "Cursed Sigil" },
		desc = { vi = "Vòng ấn đỏ xoay, khói đen bốc lên", en = "Spinning red sigil, black smoke rising" },
		kind = "burst",
		placement = "ground",
		area = Vector3.new(10, 1, 10),
		defaults = { color1 = rgb(255, 40, 40), color2 = rgb(90, 0, 0), trigger = "Loop", interval = 1.2 },
		layers = {
			{
				type = "shape",
				kind = "Ring",
				attrs = { Radius0 = 5, Radius1 = 5, Width0 = 0.35, Width1 = 0.35, Duration = 1.3, Spin = 90, Ground = true, Transparency = 0.05, FadeStart = 0.7, Ease = "Linear" },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Ring",
				attrs = { Radius0 = 3.4, Radius1 = 3.4, Width0 = 0.2, Width1 = 0.2, Duration = 1.3, Spin = -140, Ground = true, Transparency = 0.1, FadeStart = 0.7, Ease = "Linear" },
				color0 = "p",
				color1 = "p",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Count = 8, Mode = "Ring", Distance0 = 3.4, Distance1 = 5, Length = 1.4, Width = 0.25, Duration = 1.2, Ground = true, Ease = "Linear", Transparency = 0.1, FadeStart = 0.7 },
				color0 = "p",
				color1 = "s",
			},
			darkSmoke(4, Vector3.new(0, -0.3, 0), { speed = { 1, 3 }, spread = { 20, 20 }, direction = "Top", accel = Vector3.new(0, 4, 0), lifetime = { 1.5, 2.5 } }),
			embers(6, "part", { "p", "s" }),
			{ type = "light", brightness = 2, range = 14, color = "p" },
		},
	},
	{
		id = "necrotic_aura",
		category = "aura",
		style = "dark",
		name = { vi = "Hào quang tử khí", en = "Necrotic Aura" },
		desc = { vi = "Khí đen xanh bao quanh nhân vật", en = "Green-black miasma around a character" },
		kind = "loop",
		area = Vector3.new(4, 6, 4),
		defaults = { color1 = rgb(120, 255, 90), color2 = rgb(20, 60, 20), trigger = "Always", duration = 3 },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Smoke,
				rate = 14,
				color = { "x", "d", "k" },
				size = { { 0, 1 }, { 1, 3 } },
				transparency = { { 0, 1 }, { 0.3, 0.35 }, { 1, 1 } },
				lifetime = { 1.2, 2 },
				speed = { 1, 2 },
				accel = Vector3.new(0, 3, 0),
				rotation = { 0, 360 },
				rotSpeed = { -40, 40 },
				lightEmission = 0,
				lightInfluence = 1,
			},
			{
				type = "particles",
				at = "part",
				texture = T.Glow,
				rate = 10,
				color = { "p", "s" },
				size = { { 0, 0.5 }, { 1, 0 } },
				transparency = { { 0, 0.2 }, { 1, 1 } },
				lifetime = { 0.8, 1.4 },
				speed = { 1, 3 },
				accel = Vector3.new(0, 4, 0),
				lightEmission = 1,
			},
			embers(6, "part", { "w", "p" }),
			{ type = "light", brightness = 1.5, range = 10, color = "p" },
		},
	},
	{
		id = "soul_release",
		category = "impact",
		style = "dark",
		name = { vi = "Giải phóng linh hồn", en = "Soul Release" },
		desc = { vi = "Nổ đen co lại rồi bung linh hồn sáng", en = "Black implosion, then bright souls burst out" },
		kind = "burst",
		defaults = { color1 = rgb(140, 230, 255), color2 = rgb(40, 20, 80), trigger = "Loop", interval = 2.4 },
		layers = {
			{
				type = "shape",
				kind = "Orb",
				attrs = { Size0 = 7, Size1 = 0.4, Duration = 0.35, Transparency = 0, FadeStart = 0.8, Ease = "In" },
				color0 = "x",
				color1 = "k",
			},
			{ type = "shape", kind = "Impact", attrs = { Delay = 0.35, Duration = 0.08, Style = "Invert" } },
			{
				type = "shape",
				kind = "Lines",
				attrs = { Delay = 0.35, Count = 20, Distance0 = 0.3, Distance1 = 12, Length = 5, Width = 0.3, Duration = 0.4, Brightness = 3 },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "particles",
				at = "center",
				texture = T.Glow,
				burst = 12,
				delay = 0.4,
				color = { "w", "p" },
				size = { { 0, 1 }, { 1, 0 } },
				transparency = { { 0, 0 }, { 1, 1 } },
				lifetime = { 1.4, 2.2 },
				speed = { 4, 8 },
				spread = { 60, 60 },
				direction = "Top",
				accel = Vector3.new(0, 6, 0),
				drag = 1,
				lightEmission = 1,
			},
			{ type = "shape", kind = "Shake", attrs = { Delay = 0.35, Magnitude = 1.2, Duration = 0.4 } },
			{ type = "light", brightness = 6, range = 22, color = "p", flash = 0.6 },
		},
	},
	{
		id = "ash_embers",
		category = "world",
		style = "dark",
		name = { vi = "Tro và tàn lửa", en = "Ash & Embers" },
		desc = { vi = "Tro xám rơi, tàn lửa bay lơ lửng", en = "Falling grey ash and drifting embers" },
		kind = "loop",
		placement = "sky",
		area = Vector3.new(40, 1, 40),
		defaults = { color1 = rgb(255, 120, 40), color2 = rgb(255, 60, 20), trigger = "Always", duration = 3 },
		layers = {
			{
				type = "particles",
				at = "part",
				texture = T.Glow,
				rate = 30,
				color = { "g" },
				size = { { 0, 0.25 }, { 1, 0.2 } },
				transparency = { { 0, 1 }, { 0.15, 0.2 }, { 0.85, 0.3 }, { 1, 1 } },
				lifetime = { 6, 9 },
				speed = { 1, 2 },
				direction = "Bottom",
				spread = { 30, 30 },
				accel = Vector3.new(0.6, -0.6, 0),
				rotSpeed = { -60, 60 },
				lightEmission = 0,
				lightInfluence = 1,
			},
			{
				type = "particles",
				at = "part",
				texture = T.Square,
				rate = 12,
				color = { "w", "p", "s" },
				size = { { 0, 0.12 }, { 1, 0 } },
				transparency = { { 0, 1 }, { 0.1, 0 }, { 1, 1 } },
				lifetime = { 4, 7 },
				speed = { 0.5, 1.5 },
				direction = "Bottom",
				spread = { 60, 60 },
				accel = Vector3.new(0.8, -0.3, 0),
				drag = 0.5,
				lightEmission = 1,
				brightness = 2,
			},
		},
	},
	------------------------------------------------------------------ From the reference clips
	{
		id = "lightning_slash",
		category = "slash",
		name = { vi = "Chém sét", en = "Lightning Slash" },
		desc = { vi = "Vệt chém xanh điện, tia điện chạy dọc lưỡi", en = "Electric blue slash with arcs running along it" },
		kind = "burst",
		defaults = { color1 = rgb(110, 180, 255), color2 = rgb(40, 50, 255), trigger = "Loop", interval = 1.4 },
		layers = {
			{
				type = "shape",
				kind = "Slash",
				attrs = { Radius = 5.5, Arc = 170, Width = 2.2, Sweep = 70, Duration = 0.4, Brightness = 3, TailFade = 0.85 },
				color0 = "p",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Crackle",
				attrs = { Delay = 0.03, Count = 9, Radius = 5.6, Arc = 160, Length = 1.8, Jitter = 0.45, Width = 0.14, Duration = 0.45, Brightness = 3 },
				color0 = "w",
				color1 = "p",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Delay = 0.05, Count = 10, Mode = "Ring", Distance0 = 4, Distance1 = 10, Length = 2.5, Width = 0.18, Duration = 0.3, Brightness = 2 },
				color0 = "w",
				color1 = "p",
			},
			sparks(26, 45),
			twinkles(12, 30, Vector3.new(0, 0, -5), 0.04),
			hdFlip("flip_electric", Vector3.new(0, 0, -5), 2, { { 0, 4 }, { 1, 6 } }, { 0.3, 0.4 }, { delay = 0.04, color = { "w", "p" }, brightness = 3 }),
			{ type = "shape", kind = "Impact", attrs = { Delay = 0.04, Duration = 0.06, Style = "Flash", Strength = 0.45 } },
			{ type = "light", brightness = 6, range = 20, color = "p", flash = 0.35 },
		},
	},
	{
		id = "flash_step",
		category = "projectile",
		name = { vi = "Bước chớp", en = "Flash Step" },
		desc = { vi = "Lướt nhanh: vệt trắng, bóng mờ đen, tia ở điểm dừng", en = "Instant dash: white streak, dark afterimage, burst at the end" },
		kind = "burst",
		defaults = { color1 = rgb(230, 245, 255), color2 = rgb(90, 140, 255), trigger = "Loop", interval = 1.6 },
		layers = {
			{
				type = "shape",
				kind = "Streak",
				attrs = { To = Vector3.new(0, 0, -24), Width = 0.7, Smear = 3, Duration = 0.45, Brightness = 3 },
				color0 = "w",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Lines",
				attrs = { Offset = Vector3.new(0, 0, -24), Delay = 0.06, Count = 12, Distance0 = 0.5, Distance1 = 7, Length = 3, Width = 0.2, Duration = 0.3, Brightness = 2 },
				color0 = "w",
				color1 = "s",
			},
			{
				type = "shape",
				kind = "Crackle",
				attrs = { Offset = Vector3.new(0, 0, -24), Delay = 0.05, Count = 5, Radius = 1.5, Arc = 360, Length = 1.4, Jitter = 0.5, Width = 0.1, Duration = 0.3, Brightness = 3 },
				color0 = "s",
				color1 = "w",
			},
			sparks(16, 30, Vector3.new(0, 0, -24)),
			{ type = "shape", kind = "Shake", attrs = { Delay = 0.05, Magnitude = 0.5, Duration = 0.25, Roughness = 22 } },
		},
	},
	{
		id = "wind_vortex",
		category = "circle",
		name = { vi = "Lốc gió", en = "Wind Vortex" },
		desc = { vi = "Đĩa gió xoáy, mảnh vụn bay, sao lấp lánh", en = "Spinning wind disc, flying debris, sparkles" },
		kind = "burst",
		area = Vector3.new(8, 4, 8),
		defaults = { color1 = rgb(235, 255, 245), color2 = rgb(70, 255, 130), trigger = "Loop", interval = 0.75 },
		layers = {
			{
				type = "shape",
				kind = "Whirl",
				attrs = { Count = 8, Strands = 3, Radius0 = 2, Radius1 = 7, Width = 0.42, ArcMin = 110, ArcMax = 240, Spin = 460, Grow = 0.25, Duration = 1.1, Tilt = Vector3.new(12, 0, -8), Transparency = 0.1, Brightness = 1.2, Ease = "Out" },
				color0 = "p",
				color1 = "s",
			},
			{
				-- a second, wider and fainter layer gives the vortex depth
				type = "shape",
				kind = "Whirl",
				attrs = { Delay = 0.05, Count = 5, Strands = 2, Radius0 = 4, Radius1 = 9, Width = 0.3, ArcMin = 90, ArcMax = 180, Spin = 320, Grow = 0.3, Duration = 1, Tilt = Vector3.new(12, 0, -8), Transparency = 0.5, Brightness = 1, Core = false },
				color0 = "w",
				color1 = "s",
			},
			{
				-- leaves / grit caught in the wind: thin slivers flung outward and up
				type = "particles",
				at = "part",
				texture = T.Square,
				burst = 22,
				color = { "w", "p" },
				size = { { 0, 0.18 }, { 1, 0 } },
				squash = { { 0, -1.8 }, { 1, -1.8 } },
				orientation = "VelocityParallel",
				lifetime = { 0.6, 1.1 },
				speed = { 10, 20 },
				spread = { 180, 25 },
				direction = "Top",
				drag = 3,
				accel = Vector3.new(0, 4, 0),
				lightEmission = 1,
				brightness = 2,
			},
			{
				type = "particles",
				at = "part",
				texture = T.Star,
				burst = 14,
				color = { "w", "s" },
				size = { { 0, 0 }, { 0.2, 0.9 }, { 1, 0 } },
				lifetime = { 0.5, 1 },
				speed = { 3, 8 },
				spread = { 180, 180 },
				drag = 3,
				rotation = { 0, 360 },
				lightEmission = 1,
				brightness = 2,
			},
			{
				type = "particles",
				at = "center",
				texture = T.Glow,
				burst = 1,
				color = { "p" },
				size = { { 0, 2 }, { 0.3, 4.5 }, { 1, 5 } },
				transparency = { { 0, 0.7 }, { 1, 1 } },
				lifetime = { 0.7, 0.7 },
				speed = { 0, 0 },
				lightEmission = 1,
			},
			hdRing(Vector3.new(0, -1.8, 0), 13, 0.6),
			hdFlip("flip_smoke", Vector3.new(0, -1.6, 0), 8, { { 0, 2 }, { 1, 5 } }, { 0.7, 1.1 }, {
				color = { "w" },
				transparency = { { 0, 0.55 }, { 1, 1 } },
				speed = { 12, 18 },
				spread = { 180, 5 },
				direction = "Top",
				drag = 4,
			}),
		},
	},
	-- Hero set: the v4 rebuilds, beside the originals above
	{
		id = "impact_v4",
		needs = "shape_core_flash",
		category = "impact",
		name = { vi = "Va chạm (v4)", en = "Hit Impact (v4)" },
		desc = { vi = "Bản dựng lại theo ngữ pháp ZZZ, thư viện v4", en = "Rebuilt in the ZZZ grammar on library v4" },
		kind = "burst",
		placement = "air",
		defaults = { color1 = rgb(255, 235, 120), color2 = rgb(255, 140, 40), trigger = "Loop", interval = 1.2 },
		layers = {
			-- Hit: 2 frames
			heroFlash("center", 7),
			-- Burst: peaks by frame 4
			v4("flip_burst_dissolve", "Burst", "center", {
				name = "Base",
				delay = 0.02,
				flipbook = "Grid4x4",
				size = { { 0, 7 }, { 1, 12 } },
				lifetime = { 0.3, 0.3 },
				color = { "p", "s" },
				brightness = 1.2,
				zOffset = 1,
			}),
			v4("flip_shock_ring", "Burst", "center", {
				name = "Ring",
				delay = 0.02,
				tilt = Vector3.new(90, 0, 0),
				flipbook = "Grid4x4",
				orientation = "VelocityPerpendicular",
				direction = "Top",
				speed = { 0.01, 0.01 },
				size = { { 0, 5 }, { 1, 20 } },
				lifetime = { 0.32, 0.32 },
				color = { "p", "s" },
			}),
			heroShards("center", 12, 75, { delay = 0.02 }),
			heroShards("center", 6, 50, {
				name = "LineBurst",
				delay = 0.02,
				direction = "Right",
				speed = { -50, 50 },
				spread = { 12, 12 },
				shape = "Box",
				shapeInOut = "InAndOut",
			}),
			v4("shape_ink_stroke", "Burst", "center", {
				name = "Ink",
				delay = 0.05,
				size = { { 0, 8 }, { 1, 9 } },
				transparency = { { 0, 0 }, { 0.6, 0.1 }, { 1, 1 } },
				lifetime = { 0.13, 0.13 },
				rotation = { -35, -20 },
				color = { "k" },
				lightEmission = 0,
				brightness = 1,
				zOffset = 1.5,
			}),
			-- Tail: sparse and calm
			heroEmbers("center", 8, 0.08),
			{ type = "light", brightness = 4, range = 14, color = "p", flash = 0.12 },
		},
	},
	{
		id = "ground_slam_v4",
		needs = "shape_core_flash",
		category = "impact",
		name = { vi = "Đập đất (v4)", en = "Ground Slam (v4)" },
		desc = { vi = "Bản dựng lại theo ngữ pháp ZZZ, thư viện v4", en = "Rebuilt in the ZZZ grammar on library v4" },
		kind = "burst",
		placement = "ground",
		defaults = { color1 = rgb(255, 200, 60), color2 = rgb(255, 90, 20), trigger = "Loop", interval = 3.5 },
		-- Beat sheet tools/evfx/sheets/ground_slam_v4.json (Phát, 2026-10-24): it fires at the press,
		-- so a Tell carries Cleave's 0.5 s wind-up and the hit lands at 0.5 s; every layer leaves
		-- its own way (docs/vfx-grammar.md, exits). The smoke and the blast are CC0 flipbooks (pack/cc0)
		-- whose frames are steady enough to play (the manifest's steadiness).
		layers = {
			-- Tell (0-0.5 s): a gold ring tightening on the ground, a glint and rising motes
			v4("cc0_kp_circle_03", "Tell", Vector3.new(0, -1.85, 0), {
				name = "TellRing",
				orientation = "VelocityPerpendicular",
				direction = "Top",
				speed = { 0.01, 0.01 },
				size = { { 0, 16 }, { 1, 7 } },
				transparency = { { 0, 1 }, { 0.35, 0.35 }, { 0.85, 0.2 }, { 1, 1 } },
				lifetime = { 0.5, 0.5 },
				color = { "p" },
				brightness = 1.5,
			}),
			v4("cc0_kp_star_06", "Tell", Vector3.new(0, 0.6, 0), {
				name = "TellGlint",
				delay = 0.22,
				size = { { 0, 0.5 }, { 0.7, 3.2 }, { 1, 1.4 } },
				transparency = { { 0, 0.4 }, { 0.7, 0 }, { 1, 1 } },
				lifetime = { 0.28, 0.28 },
				rotation = { -10, 10 },
				color = { "w", "p" },
				brightness = 3,
			}),
			v4("sheet_embers", "Tell", Vector3.new(0, -1.2, 0), {
				name = "TellMotes",
				delay = 0.05,
				burst = 14,
				flipbook = "Grid4x4",
				flipMode = "Loop",
				flipRandom = true,
				speed = { 2, 6 },
				spread = { 180, 180 },
				drag = 3,
				accel = Vector3.new(0, 5, 0),
				size = { { 0, 0.05 }, { 0.5, 0.4, 0.1 }, { 1, 0 } },
				transparency = { { 0, 0 }, { 0.6, 0 }, { 1, 1 } },
				lifetime = { 0.3, 0.45 },
				color = { "w", "p" },
			}),
			-- Hit (0.5 s): 2 frames at the ground
			heroFlash(Vector3.new(0, -1.2, 0), 7.6, 0.5),
			-- Slam (0.5-0.9 s): the ground answers
			v4("art_floor_streaks", "Slam", Vector3.new(0, -1.9, 0), {
				name = "Floor",
				delay = 0.5,
				orientation = "VelocityPerpendicular",
				direction = "Top",
				speed = { 0.01, 0.01 },
				size = { { 0, 15 }, { 0.12, 19 }, { 1, 21 } },
				transparency = { { 0, 0.1 }, { 0.4, 0.35 }, { 1, 1 } },
				lifetime = { 0.9, 0.9 },
				color = { "p", "s" },
				brightness = 0.8,
			}),
			-- a cone shell thrown up from the ground (tools/meshgen)
			{
				type = "shell",
				hd = true,
				name = "Cone",
				group = "Slam",
				mesh = "mesh_cone",
				frames = { "strip_wind_stroke" },
				attrs = {
					Delay = 0.52,
					Size0 = Vector3.new(5, 2, 5),
					Size1 = Vector3.new(13, 5, 13),
					Duration = 0.22,
					SpinDeg = Vector3.new(0, 70, 0),
					Offset = Vector3.new(0, -0.4, 0),
					Transparency = 0.35,
					FadeStart = 0.35,
				},
				color0 = "p",
				color1 = "s",
			},
			-- a hand-drawn explosion (CodeManu, CC0): its frames change shape on purpose
			v4("cc0_cm_explosion", "Slam", Vector3.new(0, -0.2, 0), {
				name = "Blast",
				delay = 0.5,
				flipbook = "Grid4x4",
				size = { { 0, 6.5 }, { 1, 10 } },
				transparency = { { 0, 0 }, { 0.65, 0.05 }, { 1, 1 } },
				lifetime = { 0.45, 0.45 },
				rotation = { -15, 15 },
				color = { "w" },
				lightEmission = 0.6,
				brightness = 1.3,
				zOffset = 0.5,
			}),
			v4("flip_shock_ring", "Slam", Vector3.new(0, -1.8, 0), {
				name = "Ring",
				delay = 0.52,
				flipbook = "Grid4x4",
				orientation = "VelocityPerpendicular",
				direction = "Top",
				speed = { 0.01, 0.01 },
				size = { { 0, 8 }, { 1, 36 } },
				transparency = { { 0, 0 }, { 0.4, 0 }, { 1, 1 } },
				lifetime = { 0.7, 0.7 },
				color = { "p", "s" },
			}),
			v4("sheet_rock_chunks", "Slam", Vector3.new(0, -1.5, 0), {
				name = "Rocks",
				delay = 0.5,
				burst = 12,
				flipbook = "Grid4x4",
				flipMode = "Loop",
				flipRandom = true,
				direction = "Top",
				speed = { 22, 32 },
				spread = { 40, 40 },
				accel = Vector3.new(0, -80, 0),
				size = { { 0, 1.0, 0.3 }, { 0.75, 1.0 }, { 1, 0.3 } },
				transparency = { { 0, 0 }, { 0.75, 0 }, { 1, 1 } },
				lifetime = { 0.5, 0.8 },
				rotSpeed = { -400, 400 },
				color = { "d" },
				lightEmission = 0,
				lightInfluence = 1,
				brightness = 1,
				zOffset = 0.5,
			}),
			heroShards(Vector3.new(0, -1.3, 0), 10, 80, { delay = 0.5, direction = "Top", spread = { 35, 35 } }),
			-- Settle (0.55-1.8 s): smoke disperses slowly, the dust ring fades, embers linger
			v4("flip_dust_ring", "Settle", Vector3.new(0, -1.85, 0), {
				name = "DustRing",
				delay = 0.53,
				flipbook = "Grid4x4",
				orientation = "VelocityPerpendicular",
				direction = "Top",
				speed = { 0.01, 0.01 },
				size = { { 0, 8 }, { 0.4, 21 }, { 1, 26 } },
				transparency = { { 0, 0.35 }, { 0.35, 0.4 }, { 1, 1 } },
				lifetime = { 1.0, 1.0 },
				color = { "g" },
				lightEmission = 0,
				lightInfluence = 1,
				brightness = 1,
			}),
			-- smoke that disperses: a steady CC0 smoke flipbook (Iche), many thin puffs that
			-- burst out, slow under drag, keep spreading and thin away over 1.4-2.2 s
			v4("cc0_fb_wispy_smoke_01", "Settle", Vector3.new(0, -1.3, 0), {
				name = "Volume",
				delay = 0.53,
				burst = 8,
				flipbook = "Grid8x8",
				direction = "Top",
				speed = { 6, 14 },
				spread = { 80, 80 },
				drag = 4,
				accel = Vector3.new(0, 1.2, 0),
				size = { { 0, 2.4, 0.5 }, { 0.35, 5 }, { 1, 7.4 } },
				transparency = { { 0, 0.5 }, { 0.2, 0.42 }, { 0.6, 0.65 }, { 1, 1 } },
				lifetime = { 1.4, 2.2 },
				rotation = { 0, 360 },
				rotSpeed = { -15, 15 },
				color = { "g" },
				lightEmission = 0,
				lightInfluence = 1,
				brightness = 1,
				zOffset = -1,
			}),
			v4("sheet_embers", "Settle", Vector3.new(0, -1, 0), {
				name = "Embers",
				delay = 0.6,
				burst = 10,
				flipbook = "Grid4x4",
				flipMode = "Loop",
				flipRandom = true,
				speed = { 3, 8 },
				spread = { 180, 180 },
				drag = 2.5,
				accel = Vector3.new(0, 2, 0),
				size = { { 0, 0.45, 0.15 }, { 0.6, 0.35 }, { 1, 0.15 } },
				transparency = { { 0, 0 }, { 0.35, 0 }, { 1, 1 } },
				lifetime = { 0.6, 1.3 },
				color = { "w", "p" },
				zOffset = 1.5,
			}),
			{ type = "shape", kind = "Shake", attrs = { Delay = 0.5, Magnitude = 1.6, Duration = 0.45, Roughness = 10 } },
			{ type = "light", brightness = 3, range = 18, color = "p", flash = 0.1, delay = 0.5 },
		},
	},
	{
		id = "campfire_demo",
		needs = "shape_mold_fire_hook",
		-- a demo of the kits and the fire library: out of the plugin's library
		study = true,
		category = "impact",
		name = { vi = "Lửa trại (bộ lớp mẫu)", en = "Campfire (demo kit)" },
		desc = { vi = "Bộ lớp mẫu dựng từ thư viện lửa", en = "A demo layer kit built from the fire library" },
		kind = "burst",
		placement = "ground",
		defaults = { color1 = rgb(255, 130, 50), color2 = rgb(205, 50, 25), trigger = "Loop", interval = 3.5 },
		layers = Presets.kitLayers(Presets.Kits.campfire),
	},
	{
		id = "slash_v4",
		needs = "shape_core_flash",
		category = "slash",
		name = { vi = "Chém lưỡi liềm (v4)", en = "Crescent Slash (v4)" },
		desc = { vi = "Bản dựng lại theo ngữ pháp ZZZ, thư viện v4", en = "Rebuilt in the ZZZ grammar on library v4" },
		kind = "burst",
		placement = "air",
		defaults = { color1 = rgb(255, 214, 64), color2 = rgb(255, 120, 20), trigger = "Loop", interval = 1.5 },
		layers = {
			-- MainSlash: crescent shells (tools/meshgen) carrying the ribbon that erodes from its tail
			heroShell("mesh_crescent_wide", {
				name = "Slash",
				attrs = {
					Size0 = Vector3.new(8, 1.2, 8),
					Size1 = Vector3.new(9.5, 1.4, 9.5),
					Duration = 0.3,
					SpinDeg = Vector3.new(0, -50, 0),
					Tilt = Vector3.new(0, 0, -18),
					Offset = Vector3.new(0, 0.6, -1.5),
					FadeStart = 0.6,
				},
				color0 = "w",
				color1 = "p",
			}),
			heroShell("mesh_crescent_thin", {
				name = "SlashEcho",
				attrs = {
					Delay = 0.03,
					Size0 = Vector3.new(9.5, 0.8, 9.5),
					Size1 = Vector3.new(11, 1, 11),
					Duration = 0.32,
					SpinDeg = Vector3.new(0, -65, 0),
					Tilt = Vector3.new(0, 0, -24),
					Offset = Vector3.new(0, 0.9, -1.5),
					Transparency = 0.45,
					FadeStart = 0.3,
				},
				color0 = "p",
				color1 = "s",
			}),
			v4("art_brush_strokes", "MainSlash", "center", {
				name = "Ink",
				delay = 0.02,
				flipbook = "Grid2x2",
				flipMode = "Loop",
				flipRandom = true,
				size = { { 0, 6.5 }, { 1, 7 } },
				transparency = { { 0, 0.1 }, { 0.5, 0.2 }, { 1, 1 } },
				lifetime = { 0.14, 0.14 },
				rotation = { -20, -10 },
				color = { "k" },
				lightEmission = 0,
				brightness = 1,
				zOffset = 1.5,
			}),
			-- Hit: where the blade lands
			heroFlash(Vector3.new(0, 0, -4.5), 4, 0.06),
			heroShards(Vector3.new(0, 0, -4.5), 8, 45, { delay = 0.06, group = "Hit" }),
			heroShards(Vector3.new(0, 0, -4.5), 6, 50, {
				name = "LineBurst",
				delay = 0.06,
				group = "Hit",
				direction = "Right",
				speed = { -50, 50 },
				spread = { 12, 12 },
				shape = "Box",
				shapeInOut = "InAndOut",
			}),
			heroEmbers(Vector3.new(0, 0, -4.5), 6, 0.1),
			{ type = "light", brightness = 3, range = 14, color = "p", flash = 0.15 },
		},
	},
	-- Bloom Strike (study only): Lotus's layering (docs/refs/lotus-layers.md) on generated art. Every
	-- beat stacks ground, back volume, main shape, line work and dust; the two flashes are
	-- 2 frames; one palette per beat.
	{
		id = "bloom_strike",
		-- a study of Lotus's layering (docs/refs/lotus-layers.md), for learning only: never
		-- listed in the plugin, never exported to SE370, its art never uploaded
		study = true,
		needs = "shape_core_flash",
		category = "impact",
		name = { vi = "Liên hoa trảm (nghiên cứu)", en = "Bloom Strike (study)" },
		desc = { vi = "Chém, chớp sao, quả cầu, ấn hoa, rồi hoa sen nở", en = "Slash, star flare, sphere, flower sigil, then a lotus blooms" },
		kind = "burst",
		placement = "air",
		defaults = { color1 = rgb(255, 105, 215), color2 = rgb(150, 95, 255), trigger = "Loop", interval = 5 },
		layers = {
			-- Wrap (f0-14): violet smoke behind, two crescent shells, streaks through, dust
			v4("flip_smoke_puff", "Wrap", "center", {
				name = "SlashSmoke",
				flipbook = "Grid4x4",
				burst = 2,
				speed = { 2, 4 },
				spread = { 60, 60 },
				size = { { 0, 4, 0.5 }, { 1, 7 } },
				transparency = { { 0, 0.35 }, { 1, 1 } },
				lifetime = { 0.45, 0.55 },
				color = { "s" },
				lightEmission = 0.4,
				brightness = 1,
				zOffset = -2,
			}),
			heroShell("mesh_crescent_wide", {
				name = "Crescent",
				group = "Wrap",
				attrs = { Size0 = Vector3.new(7, 1.1, 7), Size1 = Vector3.new(8, 1.2, 8), Duration = 0.24, SpinDeg = Vector3.new(0, -70, 0), Tilt = Vector3.new(0, 0, -15), FadeStart = 0.5 },
				color0 = "w",
				color1 = "p",
			}),
			heroShell("mesh_crescent_thin", {
				name = "CrescentEcho",
				group = "Wrap",
				attrs = { Delay = 0.03, Size0 = Vector3.new(8.5, 0.8, 8.5), Size1 = Vector3.new(9.5, 0.9, 9.5), Duration = 0.26, SpinDeg = Vector3.new(0, -85, 0), Tilt = Vector3.new(0, 0, -25), Transparency = 0.3, FadeStart = 0.4 },
				color0 = "p",
				color1 = "s",
			}),
			heroShards("center", 8, 60, {
				name = "MotionStreaks",
				group = "Wrap",
				direction = "Right",
				speed = { -60, 60 },
				spread = { 6, 6 },
				lifetime = { 0.15, 0.22 },
				color = { "w", "s" },
			}),
			(function()
				local dust = heroEmbers("center", 10, 0.05)
				dust.group = "Wrap"
				return dust
			end)(),
			-- Flare (f26-28, 2 frames): dark halo behind, violet bloom, 8-point star, then a 4-point cross
			v4("art_dark_halo", "Flare", "center", {
				name = "DarkHalo",
				delay = 0.43,
				size = { { 0, 7 }, { 1, 8 } },
				transparency = { { 0, 0 }, { 0.6, 0.2 }, { 1, 1 } },
				lifetime = { 0.12, 0.12 },
				color = { "k" },
				lightEmission = 0,
				brightness = 1,
				zOffset = -3,
			}),
			v4("shape_core_flash", "Flare", "center", {
				name = "Bloom",
				delay = 0.43,
				size = { { 0, 9 }, { 1, 6 } },
				transparency = { { 0, 0.3 }, { 1, 1 } },
				lifetime = { 0.1, 0.1 },
				color = { "s" },
				brightness = 1.5,
				zOffset = -1,
			}),
			v4("shape_star8", "Flare", "center", {
				name = "Star8",
				delay = 0.43,
				size = { { 0, 8.5 }, { 1, 9 } },
				transparency = { { 0, 0 }, { 0.7, 0 }, { 1, 1 } },
				lifetime = { 0.034, 0.034 },
				rotation = { 0, 0 },
				color = { "w" },
				brightness = 4,
				zOffset = 3,
			}),
			v4("shape_cross_flare", "Flare", "center", {
				name = "Cross4",
				delay = 0.467,
				size = { { 0, 6 }, { 1, 3 } },
				transparency = { { 0, 0 }, { 1, 1 } },
				lifetime = { 0.05, 0.05 },
				rotation = { 0, 0 },
				color = { "w", "s" },
				brightness = 3,
				zOffset = 3,
			}),
			-- Sphere (f30-52): spark ball, tendrils, a sphere shell pink-white to blue, rim wisps
			v4("shape_core_flash", "Sphere", "center", {
				name = "SparkBall",
				delay = 0.5,
				size = { { 0, 2 }, { 1, 0.6 } },
				lifetime = { 0.1, 0.1 },
				color = { "w", "p" },
				brightness = 3,
				zOffset = 2,
			}),
			heroShards("center", 6, 30, { name = "Tendrils", group = "Sphere", delay = 0.5, lifetime = { 0.12, 0.2 }, color = { "p", "s" } }),
			{
				type = "shell",
				hd = true,
				name = "Sphere",
				group = "Sphere",
				mesh = "mesh_sphere",
				frames = { "strip_energy_streak" },
				attrs = { Delay = 0.5, Size0 = Vector3.new(2.5, 2.5, 2.5), Size1 = Vector3.new(5.5, 5.5, 5.5), Duration = 0.38, SpinDeg = Vector3.new(0, 140, 30), FadeStart = 0.55 },
				color0 = "w",
				color1 = rgb(110, 150, 255),
			},
			v4("art_brush_strokes", "Sphere", "center", {
				name = "RimWisps",
				delay = 0.65,
				burst = 4,
				flipbook = "Grid2x2",
				flipMode = "Loop",
				flipRandom = true,
				speed = { 1, 3 },
				spread = { 180, 180 },
				size = { { 0, 4 }, { 1, 5.5 } },
				transparency = { { 0, 0.2 }, { 1, 1 } },
				lifetime = { 0.3, 0.4 },
				color = { rgb(140, 175, 255) },
				brightness = 1.6,
			}),
			-- Sigil (f50-96): bokeh behind, flower sigil turning, orbit rings, twinkles
			v4("shape_bokeh", "Sigil", "center", {
				name = "Bokeh",
				delay = 0.85,
				burst = 7,
				speed = { 2, 5 },
				spread = { 180, 180 },
				drag = 3,
				size = { { 0, 1.2, 0.4 }, { 1, 1.6 } },
				transparency = { { 0, 0.5 }, { 1, 1 } },
				lifetime = { 0.7, 0.9 },
				color = { "s" },
				brightness = 1,
				zOffset = -2,
			}),
			v4("art_flower_sigil", "Sigil", "center", {
				name = "FlowerSigil",
				delay = 0.83,
				size = { { 0, 3 }, { 0.25, 4.8 }, { 1, 5.2 } },
				transparency = { { 0, 0.1 }, { 0.5, 0.25 }, { 1, 1 } },
				lifetime = { 0.55, 0.55 },
				rotation = { 0, 0 },
				rotSpeed = { 40, 40 },
				color = { "w", rgb(120, 160, 255), "s" },
				brightness = 1.3,
			}),
			v4("shape_hollow_ring", "Sigil", "center", {
				name = "OrbitRings",
				delay = 0.88,
				burst = 7,
				speed = { 6, 10 },
				spread = { 180, 180 },
				drag = 5,
				size = { { 0, 0.5, 0.15 }, { 1, 0.7 } },
				transparency = { { 0, 0 }, { 0.7, 0.2 }, { 1, 1 } },
				lifetime = { 0.6, 0.8 },
				color = { "p" },
				brightness = 2,
			}),
			twinkles(6, 12, "center", 0.9, { "w", "p" }),
			-- Seed (f78-90, on the ground): gold brush ring, gold core, gold sparks
			v4("art_brush_ring", "Seed", Vector3.new(0, -1.85, 0), {
				name = "RingStroke",
				delay = 1.3,
				orientation = "VelocityPerpendicular",
				direction = "Top",
				speed = { 0.01, 0.01 },
				size = { { 0, 3.5 }, { 1, 2 } },
				transparency = { { 0, 0 }, { 1, 0.6 } },
				lifetime = { 0.22, 0.22 },
				rotSpeed = { 420, 420 },
				color = { rgb(255, 205, 95) },
				brightness = 2,
			}),
			v4("shape_core_flash", "Seed", Vector3.new(0, -1.7, 0), {
				name = "Seed",
				delay = 1.3,
				size = { { 0, 1.2 }, { 1, 0.7 } },
				lifetime = { 0.2, 0.2 },
				color = { rgb(255, 215, 120) },
				brightness = 3,
			}),
			-- Dome (f90-92, 2 frames): a white hemisphere on the ground
			{
				type = "shell",
				hd = true,
				name = "Dome",
				group = "Dome",
				mesh = "mesh_dome",
				frames = { "strip_dome_glow" },
				attrs = { Delay = 1.5, Offset = Vector3.new(0, -1.9, 0), Size0 = Vector3.new(6, 3, 6), Size1 = Vector3.new(6.6, 3.3, 6.6), Duration = 0.034, Transparency = 0.02, FadeStart = 0.7, Emissive = 5 },
				color0 = "w",
				color1 = "w",
			},
			-- Bloom (f92-162): gold ground ring, rainbow fringe, pillar, lotus, base sparks, petals, gold dust
			v4("art_sigil_ornate", "Bloom", Vector3.new(0, -1.88, 0), {
				name = "GroundRing",
				delay = 1.5,
				orientation = "VelocityPerpendicular",
				direction = "Top",
				speed = { 0.01, 0.01 },
				size = { { 0, 4.5 }, { 0.1, 5.5 }, { 1, 5.5 } },
				transparency = { { 0, 0.1 }, { 0.5, 0.35 }, { 1, 1 } },
				lifetime = { 1.1, 1.1 },
				rotSpeed = { 10, 10 },
				color = { rgb(255, 210, 110) },
				brightness = 1.2,
			}),
			v4("art_fringe_ring", "Bloom", Vector3.new(0, -0.6, 0), {
				name = "FringeArc",
				group = "Fringe",
				delay = 1.53,
				size = { { 0, 6.5 }, { 1, 7.5 } },
				transparency = { { 0, 0.1 }, { 1, 1 } },
				lifetime = { 0.32, 0.32 },
				rotation = { 0, 0 },
				color = { "w" },
				brightness = 1.4,
			}),
			{
				type = "shell",
				hd = true,
				name = "Pillar",
				group = "Bloom",
				mesh = "mesh_cylinder",
				frames = { "strip_pillar_streaks" },
				attrs = { Delay = 1.52, Offset = Vector3.new(0, 3.1, 0), Size0 = Vector3.new(1.6, 10, 1.6), Size1 = Vector3.new(2.2, 10, 2.2), Duration = 1.1, SpinDeg = Vector3.new(0, 60, 0), Transparency = 0.15, FadeStart = 0.55, Emissive = 2.5 },
				color0 = "p",
				color1 = "p",
			},
			{
				type = "shell",
				hd = true,
				name = "Lotus",
				group = "Bloom",
				mesh = "mesh_lotus",
				frames = { "art_petal_single" },
				attrs = { Delay = 1.53, Offset = Vector3.new(0, -0.6, 0), Size0 = Vector3.new(3, 0.8, 3), Size1 = Vector3.new(5.5, 3.6, 5.5), Duration = 1.15, SpinDeg = Vector3.new(0, 25, 0), Transparency = 0.05, FadeStart = 0.65, Ease = "Out", Emissive = 2.2 },
				color0 = "p",
				color1 = "p",
			},
			heroShards(Vector3.new(0, -1.7, 0), 10, 30, {
				name = "BaseSparks",
				group = "Bloom",
				delay = 1.52,
				direction = "Top",
				spread = { 85, 85 },
				lifetime = { 0.2, 0.3 },
			}),
			v4("art_petals_cel", "Bloom", Vector3.new(0, -0.5, 0), {
				name = "Petals",
				group = "BloomAir",
				delay = 1.7,
				burst = 14,
				flipbook = "Grid2x2",
				flipMode = "Loop",
				flipRandom = true,
				speed = { 2, 5 },
				spread = { 180, 50 },
				drag = 1.2,
				accel = Vector3.new(0, -1.2, 0),
				size = { { 0, 0.5, 0.15 }, { 1, 0.4 } },
				transparency = { { 0, 0 }, { 0.8, 0.2 }, { 1, 1 } },
				lifetime = { 1.6, 2.3 },
				rotSpeed = { -90, 90 },
				color = { "p" },
				lightEmission = 0.3,
				brightness = 1.2,
			}),
			v4("sheet_embers", "Bloom", Vector3.new(0, -1.5, 0), {
				name = "GoldDust",
				delay = 1.6,
				burst = 24,
				flipbook = "Grid4x4",
				flipMode = "Loop",
				flipRandom = true,
				speed = { 1, 3 },
				spread = { 180, 60 },
				drag = 1.5,
				accel = Vector3.new(0, 0.6, 0),
				size = { { 0, 0.3, 0.1 }, { 1, 0 } },
				lifetime = { 1.5, 2.4 },
				color = { rgb(255, 215, 120) },
			}),
			-- Tail (f160-240): gold swirl on the ground, dark grass; petals and dust keep drifting
			v4("art_brush_ring", "Tail", Vector3.new(0, -1.87, 0), {
				name = "GroundSwirl",
				delay = 2.0,
				orientation = "VelocityPerpendicular",
				direction = "Top",
				speed = { 0.01, 0.01 },
				size = { { 0, 6 }, { 1, 7.5 } },
				transparency = { { 0, 0.1 }, { 0.5, 0.35 }, { 1, 1 } },
				lifetime = { 1.8, 1.8 },
				rotSpeed = { 25, 25 },
				color = { rgb(255, 205, 95) },
				brightness = 1.3,
			}),
			v4("sheet_grass", "Tail", Vector3.new(0, -1.9, 0), {
				name = "Grass",
				delay = 1.6,
				burst = 12,
				shape = "Cylinder",
				flipbook = "Grid4x4",
				flipMode = "Loop",
				flipRandom = true,
				orientation = "FacingCameraWorldUp",
				speed = { 0.01, 0.01 },
				size = { { 0, 0 }, { 0.12, 1.1, 0.3 }, { 0.85, 1.1 }, { 1, 0 } },
				lifetime = { 2.0, 2.4 },
				rotation = { 0, 0 },
				color = { rgb(28, 52, 34) },
				lightEmission = 0,
				lightInfluence = 0,
				brightness = 1,
				zOffset = -1,
			}),
			{ type = "light", brightness = 3, range = 16, color = "p", flash = 0.15 },
		},
	},
} :: any) :: { Preset }

-- Helpers like hdSlash() return several layers; flatten them into the list.
for _, preset in Presets.List do
	local flat = {}
	for _, layer in preset.layers do
		if layer.type == nil and #layer > 0 then
			for _, inner in layer do
				table.insert(flat, inner)
			end
		else
			table.insert(flat, layer)
		end
	end
	preset.layers = flat
end


-- Weight and sharpness on the hits (layers appended per preset; HD parts need the pack)
local function kit(id: string, ...: { Layer })
	local all = {}
	for _, group in { ... } do
		for _, layer in group do
			table.insert(all, layer)
		end
	end
	IMPACT_KIT[id] = all
end
local FRONT = Vector3.new(0, 0, -28)
kit("impact", hitSpark("center", 9), { hardRing("center", 14, 0.22, Vector3.new(90, 0, 0)) }, weight(0.6))
kit("ground_slam", hitSpark(Vector3.new(0, -1.5, 0), 12), { hardRing(Vector3.new(0, -1.8, 0), 34, 0.3) }, weight(1))
kit("explosion", hitSpark("center", 14), { hardRing(Vector3.new(0, -1.8, 0), 40, 0.32) }, weight(0.9))
kit("slash", hitSpark(Vector3.new(0, 0, -4.5), 6, 0.05), weight(0.3, nil, 0.05))
kit("multi_slash", hitSpark(Vector3.new(-1, 0.6, -1), 3.5, 0.04), hitSpark(Vector3.new(1, -0.5, -1), 3.5, 0.18), hitSpark("center", 5, 0.32), weight(0.45, nil, 0.32))
kit("shadow_slash", hitSpark(Vector3.new(0, 0, -5.5), 7, 0.06), weight(0.5, nil, 0.06))
kit("lightning_slash", hitSpark(Vector3.new(0, 0, -5), 8, 0.04), weight(0.5, nil, 0.04))
kit("flash_step", hitSpark(FRONT + Vector3.new(0, 0, 4), 7, 0.06), weight(0.4, Vector3.new(0, 0, -24), 0.06))
kit("fireball", hitSpark(FRONT, 10, 0.55), { hardRing(FRONT, 18, 0.25, Vector3.new(90, 0, 0), 0.55) }, weight(0.6, FRONT, 0.55))
kit("impact_frame", hitSpark("center", 12), weight(1))
kit("blood_burst", hitSpark("center", 9), weight(0.7))
kit("soul_release", hitSpark("center", 10, 0.35), weight(0.8, nil, 0.35))
kit("shockwave", { hardRing(Vector3.new(0, -1.8, 0), 30, 0.28) })
kit("energy_blast", hitSpark("center", 8))
kit("impact_v4", weight(0.6))
kit("ground_slam_v4", weight(1, nil, 0.5))
kit("slash_v4", weight(0.3, nil, 0.06))
-- no hit-stop on Bloom Strike: it pauses the shells' clock but not the particles' emit
-- delays, which would pull its beats apart; the punch and shake carry the weight
kit("bloom_strike", {
	{ type = "shape", kind = "Punch", attrs = { Delay = 0.43, Amount = -6, Duration = 0.25 } },
	{ type = "shape", kind = "Shake", attrs = { Delay = 0.43, Kick = true, Magnitude = 2, Duration = 0.35, Roughness = 26 } },
	{ type = "shape", kind = "Shake", attrs = { Delay = 1.5, Magnitude = 0.6, Duration = 0.25 } },
})

-- HD strokes for the reference-clip effects
local BEAM_PACK = { Streak = "stroke_wind", Crackle = "arc_electric" }

for _, preset in Presets.List do
	for _, layer in preset.layers do
		if layer.type == "shape" and BEAM_PACK[layer.kind] and layer.beamPack == nil then
			layer.beamPack = BEAM_PACK[layer.kind]
		end
		if layer.type == "shape" and layer.kind == "Impact" then
			layer.packAttrs = { SpeedLines = "speed_lines" }
		end
	end
	local extra = IMPACT_KIT[preset.id]
	if extra then
		for _, layer in extra do
			table.insert(preset.layers, layer)
		end
	end
end

Presets.ById = {} :: { [string]: Preset }
for _, preset in Presets.List do
	Presets.ById[preset.id] = preset :: any
end

-- The builders a kit kept outside this repo is made from
Presets.Library = {
	v4 = v4,
	rgb = rgb,
	floorAt = floorAt,
	lying = lying,
	with = with,
	hash = hash,
	breathe = breathe,
	breatheIn = breatheIn,
	fireBeats = fireBeats,
	fireLoop = fireLoop,
	fireSpike = fireSpike,
	fireball = fireball,
	airGlow = airGlow,
	groundGlow = groundGlow,
	flameKernels = flameKernels,
	kitLayers = Presets.kitLayers,
}

--- Kits and presets from outside the plugin: a game keeps its own tuned effects in its own repo,
--- each a module returning `function(lib) return { kits = {...}, presets = {...} } end`, built
--- from Presets.Library. The plugin loads them from ServerStorage.EasyVFX_Kits, the evfx tools from
--- the `kits` folder of each directory in EVFX_KITS. A preset whose id is taken replaces the old one.
function Presets.register(pack: { kits: { [string]: Kit }?, presets: { Preset }? })
	local kits: { [string]: Kit } = pack.kits or {}
	local presets: { Preset } = pack.presets or {}
	for name, kit in kits do
		Presets.Kits[name] = kit
	end
	for _, preset in presets do
		local old = Presets.ById[preset.id]
		if old then
			local at = table.find(Presets.List, old)
			if at then
				Presets.List[at] = preset
			end
		else
			table.insert(Presets.List, preset)
		end
		Presets.ById[preset.id] = preset
	end
end

return Presets
