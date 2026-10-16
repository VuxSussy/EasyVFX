--[[
	EasyVFX tests. Run from the project root:  lune run tests/run.luau
]]

local roblox = require("@lune/roblox")
local process = require("@lune/process")
local H = require("./harness")
local task = require("@lune/task")
H.install()

local Presets = H.require("Shared/Presets")
local Builder = H.require("Shared/Builder")
local EasyVFX = H.require("Runtime/EasyVFX")
local Strings = H.require("Shared/Strings")

local failures = 0
local passed = 0

local function check(cond: any, message: string)
	if cond then
		passed += 1
	else
		failures += 1
		print("  FAIL: " .. message)
	end
end

local function layerCount(root): number
	local n = 0
	for _, d in root:GetDescendants() do
		if d:GetAttribute("VFX_Layer") ~= nil then
			n += 1
		end
	end
	return n
end

local function liveCount(): number
	local parent = H.workspace.CurrentCamera or H.workspace
	local folder = parent:FindFirstChild("EasyVFX_Live")
	return if folder then #folder:GetChildren() else 0
end

local function waitForQuiet(maxFrames: number): (number, number)
	local peak = 0
	for frame = 1, maxFrames do
		task.wait()
		peak = math.max(peak, liveCount())
		if frame > 5 and liveCount() == 0 then
			return frame, peak
		end
	end
	return maxFrames, peak
end

print("== Presets data")
local ids = {}
for _, p in Presets.List do
	check(ids[p.id] == nil, "duplicate preset id " .. p.id)
	ids[p.id] = true
	check(type(p.name.vi) == "string" and type(p.name.en) == "string", p.id .. " has names")
	check(type(p.desc.vi) == "string" and type(p.desc.en) == "string", p.id .. " has descriptions")
	check(p.kind == "loop" or p.kind == "burst", p.id .. " kind")
	local catOk = false
	for _, c in Presets.Categories do
		if c.id == p.category then
			catOk = true
		end
	end
	check(catOk, p.id .. " category " .. tostring(p.category))
	check(#p.layers > 0, p.id .. " has layers")
end
print(("  %d presets"):format(#Presets.List))

print("== Strings")
for key, value in Strings.vi do
	check(Strings.en[key] ~= nil, "missing en string " .. key)
end
for key, value in Strings.en do
	check(Strings.vi[key] ~= nil, "missing vi string " .. key)
end

print("== Build, update, play every preset")
H.setMode("edit")
for _, preset in Presets.List do
	H.warnings = {}
	local target = roblox.Instance.new("Part")
	target.Name = "Target_" .. preset.id
	target.Anchored = true
	target.Size = roblox.Vector3.new(4, 6, 4)
	target.CFrame = roblox.CFrame.new(0, 3, 0)
	target.Parent = H.workspace

	local params = Builder.defaultParams(preset.id)
	local ok, root = pcall(Builder.create, params, {
		cframe = target.CFrame,
		size = preset.area or target.Size,
		parent = target,
		weldTo = target,
	})
	check(ok, preset.id .. " create: " .. tostring(root))
	if not ok then
		continue
	end
	check(root:HasTag("EasyVFX"), preset.id .. " tagged")
	check(Builder.isRoot(root), preset.id .. " isRoot")
	check(Builder.findRoot(root:GetDescendants()[1] or root) == root, preset.id .. " findRoot from child")
	local count1 = layerCount(root)
	check(count1 >= #preset.layers, preset.id .. " layer instances " .. count1)

	-- read back
	local back = Builder.readParams(root)
	check(back ~= nil and back.preset == preset.id, preset.id .. " readParams")
	check(back and back.color1 == params.color1, preset.id .. " color round-trip")

	-- update in place with extreme settings, no duplicates
	local extreme = table.clone(params)
	extreme.size, extreme.amount, extreme.speed, extreme.lifetime, extreme.glow = 3, 4, 0.25, 3, 2
	extreme.trigger = "Touch"
	local ok2, err2 = pcall(Builder.apply, root, extreme)
	check(ok2, preset.id .. " apply extreme: " .. tostring(err2))
	check(layerCount(root) == count1, preset.id .. " no duplicate layers after update")
	for _, d in root:GetDescendants() do
		if d:IsA("ParticleEmitter") then
			check(d.Rate <= Builder.MAX_RATE, preset.id .. " rate capped")
			check(d.LightEmission >= 0 and d.LightEmission <= 1, preset.id .. " light emission range")
			if d:GetAttribute("EmitCount") == nil then
				check(d.Enabled == false and d:GetAttribute("EmitDuration") ~= nil, preset.id .. " stream waits for trigger")
			end
		end
	end

	-- back to defaults; always-on streams enabled again
	local ok3, err3 = pcall(Builder.apply, root, params)
	check(ok3, preset.id .. " apply default: " .. tostring(err3))
	if params.trigger == "Always" then
		for _, d in root:GetDescendants() do
			if d:IsA("ParticleEmitter") and d:GetAttribute("EmitCount") == nil then
				check(d.Enabled == true, preset.id .. " always-on emitter enabled")
			end
		end
	end

	-- serialisable as a model file (what Studio saves)
	local okSer, errSer = pcall(roblox.serializeModel, { root }, true)
	check(okSer, preset.id .. " serializes: " .. tostring(errSer))

	-- play it locally, like the Studio preview / a client
	H.emitted = {}
	local okPlay, length = pcall(EasyVFX.PlayLocal, root)
	check(okPlay, preset.id .. " play: " .. tostring(length))
	local frames, peak = waitForQuiet(400)
	local emittedTotal = 0
	for _, n in H.emitted do
		emittedTotal += n
	end
	if preset.kind == "burst" then
		check(okPlay and length > 0, preset.id .. " burst has a length")
		check(emittedTotal > 0 or peak > 0, preset.id .. " burst produced something")
	end
	check(liveCount() == 0, preset.id .. " cleans up (" .. liveCount() .. " left)")
	check(#H.warnings == 0, preset.id .. " no runtime warnings: " .. table.concat(H.warnings, " | "))
	print(("  %-14s layers=%2d len=%.2fs pieces=%3d emitted=%4d frames=%d"):format(
		preset.id, count1, okPlay and length or -1, peak, emittedTotal, frames))

	-- play a copy at another position
	local okAt, errAt = pcall(EasyVFX.PlayLocal, root, roblox.CFrame.new(50, 5, 50))
	check(okAt, preset.id .. " PlayAt: " .. tostring(errAt))
	waitForQuiet(400)
	task.wait(0.5)

	-- change to a different preset in place
	local other = Builder.defaultParams(Presets.List[1].id)
	local ok4, err4 = pcall(Builder.apply, root, other)
	check(ok4, preset.id .. " switch preset: " .. tostring(err4))
	target:Destroy()
end

print("== Server mode forwards to clients")
H.setMode("server")
do
	local p = roblox.Instance.new("Part")
	p.Parent = H.workspace
	local root = Builder.create(Builder.defaultParams("impact"), {
		cframe = roblox.CFrame.new(),
		size = roblox.Vector3.new(4, 4, 4),
		parent = p,
	})
	H.emitted = {}
	local length = EasyVFX.Play(root)
	check(length == 0 and next(H.emitted) == nil, "server does not render effects itself")
end
H.setMode("edit")

print(("\n%d passed, %d failed"):format(passed, failures))
process.exit(if failures == 0 then 0 else 1)
