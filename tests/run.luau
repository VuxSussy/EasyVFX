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
	local basicLayers = 0
	for _, layer in preset.layers do
		if not layer.hd and not layer.pack then
			basicLayers += 1
		end
	end
	check(count1 >= basicLayers, preset.id .. " layer instances " .. count1)

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

print("== HD asset pack")
do
	local assets = {}
	for _, key in {
		"slash_arc", "slash_fiber", "slash_clean", "slash_glow", "slash_core", "spark_star", "spark_streak",
		"glow_soft", "ring_wave", "flip_slash", "flip_impact", "flip_smoke", "flip_electric",
	} do
		assets[key] = "rbxassetid://" .. (1000 + #key)
	end
	check(Builder.isHD(assets), "isHD with pack")
	check(not Builder.isHD({}), "not HD without pack")
	local hdCount = 0
	for _, preset in Presets.List do
		H.warnings = {}
		local holder = roblox.Instance.new("Part")
		holder.Anchored = true
		holder.Parent = H.workspace
		local ok, root = pcall(Builder.create, Builder.defaultParams(preset.id), {
			cframe = roblox.CFrame.new(0, 3, 0),
			size = roblox.Vector3.new(4, 4, 4),
			parent = holder,
			weldTo = holder,
		}, assets)
		check(ok, preset.id .. " HD create: " .. tostring(root))
		if not ok then
			continue
		end
		check(root:GetAttribute("VFX_HD") == true, preset.id .. " marked HD")
		local usesPack, basicLeft = false, false
		for _, d in root:GetDescendants() do
			if d:IsA("ParticleEmitter") and tostring(d.Texture):find("rbxassetid://") then
				usesPack = true
			end
		end
		for i, layer in preset.layers do
			if layer.basic then
				for _, d in root:GetDescendants() do
					if d:GetAttribute("VFX_Layer") == tostring(i) then
						basicLeft = true
					end
				end
			end
		end
		check(not basicLeft, preset.id .. " basic-only layers removed in HD")
		if Builder.hasHD(preset.id) then
			check(usesPack, preset.id .. " uses pack textures")
			hdCount += 1
		end
		-- flipbook layers really are flipbooks
		for _, d in root:GetDescendants() do
			if d:IsA("ParticleEmitter") and d.Name == "FlipHD" then
				check(d.FlipbookLayout == roblox.Enum.ParticleFlipbookLayout.Grid4x4, preset.id .. " flipbook layout")
			end
		end
		-- switching back to basic removes HD layers and restores basic ones
		Builder.apply(root, Builder.readParams(root), nil)
		for _, d in root:GetDescendants() do
			if d:IsA("ParticleEmitter") then
				check(not tostring(d.Texture):find("rbxassetid://"), preset.id .. " no pack textures after removing pack")
			end
		end
		Builder.apply(root, Builder.readParams(root), assets)
		local okPlay, len = pcall(EasyVFX.PlayLocal, root)
		check(okPlay, preset.id .. " HD play: " .. tostring(len))
		waitForQuiet(400)
		for _ = 1, 60 do -- let light flashes finish before removing the effect
			task.wait()
		end
		check(#H.warnings == 0, preset.id .. " HD no warnings: " .. table.concat(H.warnings, " | "))
		holder:Destroy()
	end
	print(("  %d presets have dedicated HD layers"):format(hdCount))
	check(hdCount >= 7, "enough HD presets")
end

print("== Spiral, Projectile, Impact, Shake, property sequences")
do
	local camera = H.workspace.CurrentCamera
	if not camera then
		camera = roblox.Instance.new("Camera")
		camera.Parent = H.workspace
		H.workspace.CurrentCamera = camera
	end
	camera.CFrame = roblox.CFrame.new(0, 5, 20)

	local function shapeRoot(kind: string, attrs: { [string]: any })
		local root = roblox.Instance.new("Part")
		root.Anchored = true
		root.Transparency = 1
		root.CFrame = roblox.CFrame.new(0, 3, 0)
		root.Parent = H.workspace
		local cfg = roblox.Instance.new("Configuration")
		cfg:SetAttribute("Kind", kind)
		for k, v in attrs do
			cfg:SetAttribute(k, v)
		end
		cfg.Parent = root
		return root
	end
	local function countIn(parent, class: string): number
		local n = 0
		for _, d in parent:GetDescendants() do
			if d:IsA(class) then
				n += 1
			end
		end
		return n
	end
	local function live()
		return (H.workspace.CurrentCamera or H.workspace):FindFirstChild("EasyVFX_Live")
	end

	-- Spiral: strands * segments beams (+ cores), all sharp geometry, cleaned up
	H.warnings = {}
	local spiral = shapeRoot("Spiral", { Count = 3, Turns = 2, Height = 8, Duration = 0.6 })
	local len = EasyVFX.PlayLocal(spiral)
	check(math.abs(len - 0.6) < 1e-6, "spiral length " .. len)
	for _ = 1, 6 do
		task.wait()
	end
	local folder = live()
	check(folder and countIn(folder, "Beam") == 3 * 16 * 2, "spiral beams " .. (folder and countIn(folder, "Beam") or -1))
	local widest = 0
	if folder then
		for _, b in folder:GetDescendants() do
			if b:IsA("Beam") then
				widest = math.max(widest, b.Width0, b.Width1)
			end
		end
	end
	check(widest > 0.1, "spiral strands are visible mid-way")
	waitForQuiet(200)
	check(liveCount() == 0, "spiral cleans up")
	check(#H.warnings == 0, "spiral no warnings: " .. table.concat(H.warnings, " | "))
	spiral:Destroy()

	-- Projectile: head travels from Offset towards To along an arc
	H.warnings = {}
	local shot = shapeRoot("Projectile", { To = roblox.Vector3.new(0, 0, -30), ArcHeight = 5, Duration = 0.6, Ease = "Linear" })
	EasyVFX.PlayLocal(shot)
	local function headPos()
		local f = live()
		local best = nil
		if f then
			for _, d in f:GetDescendants() do
				if d:IsA("Part") and d.Material == roblox.Enum.Material.Neon then
					best = d.CFrame.Position
				end
			end
		end
		return best
	end
	for _ = 1, 9 do -- about half way (test frames and runtime frames are loosely synced)
		task.wait()
	end
	local mid = headPos()
	check(mid ~= nil and mid.Z < -6 and mid.Z > -24, "projectile part way along Z: " .. tostring(mid))
	check(mid ~= nil and mid.Y > 3 + 3, "projectile arcs up: " .. tostring(mid))
	waitForQuiet(200)
	check(liveCount() == 0, "projectile cleans up")
	check(#H.warnings == 0, "projectile no warnings: " .. table.concat(H.warnings, " | "))
	shot:Destroy()

	-- Impact: a ColorCorrectionEffect on the camera, gone afterwards
	H.warnings = {}
	local hit = shapeRoot("Impact", { Duration = 0.2, Style = "Mono" })
	EasyVFX.PlayLocal(hit)
	task.wait()
	task.wait()
	local cc = camera:FindFirstChild("EasyVFX_Impact")
	check(cc ~= nil and cc:IsA("ColorCorrectionEffect"), "impact frame created on camera")
	check(cc ~= nil and cc.Saturation < -0.5 and cc.Contrast > 0.5, "mono impact desaturates and punches contrast")
	for _ = 1, 12 do
		task.wait()
	end
	check(camera:FindFirstChild("EasyVFX_Impact") == nil, "impact frame removed")
	EasyVFX.PlayLocal(hit)
	EasyVFX.PlayLocal(hit)
	task.wait()
	task.wait()
	local stacked = 0
	for _, c in camera:GetChildren() do
		if c.Name == "EasyVFX_Impact" then
			stacked += 1
		end
	end
	check(stacked == 1, "impact frames do not stack: " .. stacked)
	for _ = 1, 12 do
		task.wait()
	end
	local far = shapeRoot("Impact", { Duration = 0.2, Range = 5 })
	EasyVFX.PlayLocal(far)
	task.wait()
	task.wait()
	check(camera:FindFirstChild("EasyVFX_Impact") == nil, "impact frame skipped out of range")
	check(#H.warnings == 0, "impact no warnings: " .. table.concat(H.warnings, " | "))
	hit:Destroy()
	far:Destroy()

	-- Shake: never touches the editor camera; in a running client it binds a render step
	local bound: ((number) -> ())? = nil
	roblox.implementMethod("RunService", "BindToRenderStep", function(_rs, _name, _priority, f)
		bound = f
	end)
	roblox.implementMethod("RunService", "UnbindFromRenderStep", function()
		bound = nil
	end)
	local shake = shapeRoot("Shake", { Magnitude = 2, Duration = 0.3 })
	check(EasyVFX.PlayLocal(shake) > 0 and bound == nil, "no camera shake in edit mode")
	H.setMode("client")
	EasyVFX.PlayLocal(shake)
	check(bound ~= nil, "client shake binds a render step")
	local start = camera.CFrame
	local moved = false
	for _ = 1, 4 do
		local f = bound
		if f then
			camera.CFrame = start
			f(1 / 30)
			moved = moved or (camera.CFrame.Position - start.Position).Magnitude > 1e-4
		end
	end
	check(moved, "shake moves the camera")
	for _ = 1, 20 do
		local f = bound
		if f then
			f(1 / 30)
		end
	end
	check(bound == nil, "shake unbinds when done")
	H.setMode("edit")
	shake:Destroy()

	-- <Property>Sequence attributes animate any property, then restore it.
	-- (Lune's NumberSequence.new(a, b) ignores b, so build keypoints explicitly.)
	local function ramp(a: number, b: number)
		return roblox.NumberSequence.new({ roblox.NumberSequenceKeypoint.new(0, a), roblox.NumberSequenceKeypoint.new(1, b) })
	end
	H.warnings = {}
	local holder = roblox.Instance.new("Part")
	holder.Anchored = true
	holder.Parent = H.workspace
	local glowPart = roblox.Instance.new("Part")
	glowPart.Transparency = 0.2
	glowPart.Size = roblox.Vector3.new(2, 2, 2)
	glowPart:SetAttribute("TransparencySequence", ramp(0, 1))
	glowPart:SetAttribute("ScaleSequence", ramp(1, 3))
	glowPart:SetAttribute("EmitDuration", 0.6)
	glowPart.Parent = holder
	local beamHolder = roblox.Instance.new("Attachment")
	beamHolder.Parent = holder
	local light = roblox.Instance.new("PointLight")
	light.Brightness = 1
	light:SetAttribute("BrightnessSequence", ramp(10, 0))
	light.Parent = holder
	check(EasyVFX.HasBursts(holder), "sequences count as playable layers")
	local l = EasyVFX.PlayLocal(holder)
	check(l >= 0.6, "sequence length " .. l)
	for _ = 1, 9 do
		task.wait()
	end
	check(math.abs(glowPart.Transparency - 0.5) < 0.1, "transparency half way: " .. glowPart.Transparency)
	check(glowPart.Size.X > 3 and glowPart.Size.X < 5, "scale half way: " .. glowPart.Size.X)
	check(light.Brightness > 5 and light.Brightness < 9, "light brightness follows curve: " .. light.Brightness)
	-- playing again mid-way must not take the animated value as the new original
	EasyVFX.PlayLocal(holder)
	for _ = 1, 90 do
		task.wait()
	end
	check(math.abs(glowPart.Transparency - 0.2) < 1e-6, "transparency restored: " .. glowPart.Transparency)
	check(math.abs(glowPart.Size.X - 2) < 1e-6, "size restored: " .. glowPart.Size.X)
	check(math.abs(light.Brightness - 1) < 1e-6, "brightness restored: " .. light.Brightness)
	check(#H.warnings == 0, "sequences no warnings: " .. table.concat(H.warnings, " | "))
	holder:Destroy()
end

print("== Custom effects (My Effects)")
do
	local Custom = H.require("Shared/Custom")
	-- every block, normal and dark, builds and plays cleanly
	for _, dark in { false, true } do
		local def = Custom.newDef()
		def.blocks = {}
		for _, info in Custom.Blocks do
			local b = Custom.newBlock(info.id)
			b.dark = dark
			b.delay = 0.05
			table.insert(def.blocks, b)
		end
		def = Custom.validate(def)
		check(def ~= nil and #def.blocks == #Custom.Blocks, "all blocks valid")
		Custom.registerOne(def)
		H.warnings = {}
		local holder = roblox.Instance.new("Part")
		holder.Anchored = true
		holder.Parent = H.workspace
		local ok, root = pcall(Builder.create, Builder.defaultParams(def.id), {
			cframe = roblox.CFrame.new(0, 3, 0),
			size = roblox.Vector3.new(4, 4, 4),
			parent = holder,
			weldTo = holder,
		})
		check(ok, "custom create (dark=" .. tostring(dark) .. "): " .. tostring(root))
		if ok then
			local okPlay, len = pcall(EasyVFX.PlayLocal, root)
			check(okPlay and len > 0, "custom plays: " .. tostring(len))
			waitForQuiet(400)
			for _ = 1, 30 do
				task.wait()
			end
			check(#H.warnings == 0, "custom no warnings: " .. table.concat(H.warnings, " | "))
			if dark then
				local unlit = false
				for _, d in root:GetDescendants() do
					if d:IsA("Configuration") and d:GetAttribute("Glow") == 0 and d:GetAttribute("CoreGlow") == 1 then
						unlit = true
					end
				end
				check(unlit, "dark blocks get an unlit body and a glowing core")
			end
			-- the effect carries its definition: forgetting it and reading back re-learns it
			Custom.register({})
			check(Presets.ById[def.id] == nil, "forgotten")
			local back = Builder.readParams(root)
			check(back ~= nil and Presets.ById[def.id] ~= nil, "re-registered from VFX_CustomDef")
		end
		holder:Destroy()
	end
	-- untrusted input
	check(Custom.decode("garbage") == nil, "rejects garbage")
	check(Custom.decode('{"blocks":[{"block":"nope"}]}') == nil, "rejects unknown blocks")
	local big = Custom.decode('{"id":"custom_x\'; drop","name":"' .. string.rep("a", 500) .. '","blocks":[{"block":"ring","size":1e9,"amount":-5,"delay":99,"color":"evil"}]}')
	check(big ~= nil, "clamps instead of failing")
	if big then
		local b = big.blocks[1]
		check(b.size == 4 and b.amount == 0.2 and b.delay == 3 and b.color == "p", "numbers clamped and color whitelisted")
		check(#big.name <= 40 and big.id:match("^custom_[%w_]+$") ~= nil, "name and id sanitised")
	end
	local many = { blocks = {} }
	for _ = 1, 100 do
		table.insert(many.blocks, { block = "lines" })
	end
	check(#(Custom.validate(many) :: any).blocks == Custom.MAX_BLOCKS, "block count capped")
	local def = Custom.newDef()
	local round = Custom.decode(Custom.shareCode(def))
	check(round ~= nil and round.id == def.id and #round.blocks == #def.blocks, "share code round-trip")
	Custom.register({})
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
