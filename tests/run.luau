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
		H.boundStep = f
	end)
	roblox.implementMethod("RunService", "UnbindFromRenderStep", function()
		bound = nil
		H.boundStep = nil
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

print("== Built-in HD pack")
do
	local Defaults = H.require("Shared/DefaultAssets")
	check(Builder.isHD(Defaults), "built-in pack turns HD on")
	local n = 0
	for key, id in Defaults do
		n += 1
		check(type(id) == "string" and id:match("^rbxassetid://%d+$") ~= nil, "built-in id " .. key)
	end
	check(n == 19, "19 built-in textures")
	-- smoke becomes the HD smoke flipbook
	local holder = roblox.Instance.new("Part")
	holder.Parent = H.workspace
	local root = Builder.create(Builder.defaultParams("smoke"), { cframe = roblox.CFrame.new(), size = roblox.Vector3.new(4, 4, 4), parent = holder }, Defaults)
	local smokeHD = false
	for _, d in root:GetDescendants() do
		if d:IsA("ParticleEmitter") and tostring(d.Texture) == Defaults.flip_smoke and d.FlipbookLayout == roblox.Enum.ParticleFlipbookLayout.Grid4x4 then
			smokeHD = true
		end
	end
	check(smokeHD, "smoke uses the HD smoke flipbook")
	Builder.apply(root, Builder.readParams(root), nil)
	for _, d in root:GetDescendants() do
		if d:IsA("ParticleEmitter") then
			check(d.FlipbookLayout == roblox.Enum.ParticleFlipbookLayout.None, "flipbook off again in basic")
		end
	end
	holder:Destroy()
	-- every texture the HD layers ask for exists in pack/textures; ones without a
	-- built-in ID yet (not uploaded) are skipped cleanly
	local fs = require("@lune/fs")
	local pending = {}
	for _, preset in Presets.List do
		for _, layer in preset.layers do
			local key = layer.pack or layer.beamPack
			if key then
				check(fs.isFile("pack/textures/" .. key .. ".png"), preset.id .. " texture file " .. key)
				if not Defaults[key] then
					pending[key] = true
				end
			end
		end
	end
	local holderP = roblox.Instance.new("Part")
	holderP.Parent = H.workspace
	H.warnings = {}
	local okHit, hitRoot = pcall(Builder.create, Builder.defaultParams("impact"), { cframe = roblox.CFrame.new(), size = roblox.Vector3.new(4, 4, 4), parent = holderP }, Defaults)
	check(okHit, "HD impact builds without the v3 textures: " .. tostring(hitRoot))
	local function hasSpark(r)
		for _, d in r:GetDescendants() do
			if d:IsA("ParticleEmitter") and d.Name == "HitSparkHD" then
				return true
			end
		end
		return false
	end
	check(okHit and hasSpark(hitRoot), "built-in pack gives the HD hit spark")
	-- without the v3 IDs (an older custom pack) those layers drop out, no empty emitters
	local older = table.clone(Defaults)
	for _, key in { "hit_star", "flip_hitspark", "ring_hard", "speed_lines", "stroke_wind", "arc_electric" } do
		older[key] = nil
	end
	local okOld, oldRoot = pcall(Builder.create, Builder.defaultParams("impact"), { cframe = roblox.CFrame.new(), size = roblox.Vector3.new(4, 4, 4), parent = holderP }, older)
	check(okOld and not hasSpark(oldRoot), "packs without v3 skip the v3 layers")
	holderP:Destroy()
	local list = {}
	for k in pending do
		table.insert(list, k)
	end
	table.sort(list)
	print("  awaiting upload: " .. (if #list > 0 then table.concat(list, ", ") else "none"))
end

print("== Weight: hit-stop, FOV punch, camera kick, textured strokes")
do
	local function root(kind, attrs)
		local part = roblox.Instance.new("Part")
		part.Anchored = true
		part.CFrame = roblox.CFrame.new(0, 3, 0)
		part.Parent = H.workspace
		local cfg = roblox.Instance.new("Configuration")
		cfg:SetAttribute("Kind", kind)
		for k, v in attrs do
			cfg:SetAttribute(k, v)
		end
		cfg.Parent = part
		return part
	end
	local camera = H.workspace.CurrentCamera
	-- hit-stop holds running effects
	H.warnings = {}
	local orb = root("Orb", { Size0 = 1, Size1 = 9, Duration = 0.5, Ease = "Linear" })
	EasyVFX.PlayLocal(orb)
	task.wait()
	task.wait()
	EasyVFX.HitStop(0.25)
	local live = camera:FindFirstChild("EasyVFX_Live")
	local piece = live and live:FindFirstChildWhichIsA("Part")
	local before = piece and piece.Size.X
	for _ = 1, 3 do
		task.wait()
	end
	check(piece ~= nil and math.abs(piece.Size.X - before) < 1e-6, "hit-stop freezes running effects")
	local start = os.clock()
	while os.clock() - start < 0.3 do
		task.wait()
	end
	for _ = 1, 3 do
		task.wait()
	end
	local alive, sizeNow = pcall(function()
		return piece.Size.X
	end)
	check(piece ~= nil and (not alive or sizeNow > before), "effects resume after the hit-stop")
	waitForQuiet(200)
	orb:Destroy()
	-- tracks registered for hit-stop slow down, then come back
	local adjusted = {}
	local track = { IsPlaying = true, Speed = 1 }
	function track:AdjustSpeed(v)
		table.insert(adjusted, v)
		self.Speed = v
	end
	EasyVFX.TrackHitStop(track :: any)
	EasyVFX.HitStop(0.05)
	check(adjusted[1] ~= nil and adjusted[1] < 0.1, "tracked animation slowed")
	local t0 = os.clock()
	while os.clock() - t0 < 0.1 do
		task.wait()
	end
	check(adjusted[2] == 1, "tracked animation speed restored")

	-- FOV punch + kick shake on a running client
	H.setMode("client")
	camera.FieldOfView = 70
	local hit = root("Punch", { Amount = -8, Duration = 0.2 })
	local kick = root("Shake", { Kick = true, Magnitude = 3, Duration = 0.2 })
	EasyVFX.PlayLocal(hit)
	EasyVFX.PlayLocal(kick)
	check(H.boundStep ~= nil, "punch/kick bind the camera step")
	if H.boundStep then
		H.boundStep(1 / 60)
		check(camera.FieldOfView < 66, "FOV punched in: " .. camera.FieldOfView)
		for _ = 1, 30 do
			if H.boundStep then
				H.boundStep(1 / 30)
			end
		end
	end
	check(math.abs(camera.FieldOfView - 70) < 1e-3, "FOV restored: " .. camera.FieldOfView)
	check(H.boundStep == nil, "camera step unbound after the punch")
	H.setMode("edit")
	hit:Destroy()
	kick:Destroy()

	-- with a Texture, a stroke is one beam carrying the whole texture
	H.warnings = {}
	local streak = root("Streak", { To = roblox.Vector3.new(0, 0, -20), Texture = "rbxassetid://1", Duration = 0.3 })
	EasyVFX.PlayLocal(streak)
	task.wait()
	task.wait()
	task.wait()
	local enabled, textured = 0, 0
	for _, d in camera.EasyVFX_Live:GetDescendants() do
		if d:IsA("Beam") and d.Enabled then
			enabled += 1
			if tostring(d.Texture) == "rbxassetid://1" then
				textured += 1
			end
		end
	end
	check(enabled == 1 and textured == 1, "textured streak = one beam (" .. enabled .. "/" .. textured .. ")")
	waitForQuiet(200)
	check(#H.warnings == 0, "weight tools no warnings: " .. table.concat(H.warnings, " | "))
	streak:Destroy()
print("== Animation markers (EasyVFX + Eclipse Animator)")
do
	-- markers parse in both forms and reject junk
	local m = EasyVFX.ParseMarker("VFX_CrescentSlash@RightHand")
	check(m ~= nil and m.effect == "VFX_CrescentSlash" and m.at == "RightHand", "shorthand marker")
	local j = EasyVFX.ParseMarker('{"effect":"VFX_GroundSlam","at":"HumanoidRootPart","offset":[0,-3,-4],"rot":[0,90,0]}')
	check(j ~= nil and j.effect == "VFX_GroundSlam" and j.offset == roblox.Vector3.new(0, -3, -4), "JSON marker")
	check(EasyVFX.ParseMarker("") == nil and EasyVFX.ParseMarker("{bad json") == nil and EasyVFX.ParseMarker('{"at":"x"}') == nil, "junk rejected")

	-- a character with a hand, and an effect template in ReplicatedStorage.EasyVFX_Effects
	local character = roblox.Instance.new("Model")
	character.Name = "Hero"
	local hrp = roblox.Instance.new("Part")
	hrp.Name = "HumanoidRootPart"
	hrp.Anchored = true
	hrp.CFrame = roblox.CFrame.new(30, 3, 0)
	hrp.Parent = character
	local hand = roblox.Instance.new("Part")
	hand.Name = "RightHand"
	hand.Anchored = true
	hand.CFrame = roblox.CFrame.new(32, 4, -1)
	hand.Parent = character
	character.Parent = H.workspace
	local folder = roblox.Instance.new("Folder")
	folder.Name = "EasyVFX_Effects"
	folder.Parent = H.game:GetService("ReplicatedStorage")
	local holder = roblox.Instance.new("Part")
	holder.Parent = folder
	local template = Builder.create(Builder.defaultParams("slash"), {
		cframe = roblox.CFrame.new(0, -50, 0),
		size = roblox.Vector3.new(4, 4, 4),
		parent = holder,
	})
	template:SetAttribute("VFX_Trigger", "Script")

	-- a fake AnimationTrack with marker signals
	local signals = {}
	local function signal()
		local s = { handlers = {} }
		function s:Connect(fn)
			table.insert(self.handlers, fn)
			local conn = { Connected = true }
			function conn.Disconnect()
				conn.Connected = false
				local i = table.find(s.handlers, fn)
				if i then
					table.remove(s.handlers, i)
				end
			end
			return conn
		end
		function s:Fire(...)
			for _, fn in table.clone(self.handlers) do
				fn(...)
			end
		end
		return s
	end
	local track = {}
	function track:GetMarkerReachedSignal(name)
		signals[name] = signals[name] or signal()
		return signals[name]
	end

	H.warnings = {}
	local binding = EasyVFX.BindAnimation(track :: any, character)
	signals.EasyVFX:Fire(template.Name .. "@RightHand")
	task.wait()
	task.wait()
	local live = (H.workspace.CurrentCamera or H.workspace):FindFirstChild("EasyVFX_Live")
	local copy = nil
	if live then
		for _, c in live:GetChildren() do
			if c.Name == template.Name then
				copy = c
			end
		end
	end
	check(copy ~= nil, "marker played a copy of the template")
	check(copy ~= nil and (copy.CFrame.Position - hand.CFrame.Position).Magnitude < 0.01, "copy placed at the hand")
	waitForQuiet(400)
	for _ = 1, 40 do
		task.wait()
	end

	-- Eclipse Animator event-track marker pointing at an effect inside the character
	local weapon = roblox.Instance.new("Part")
	weapon.Name = "Sword"
	weapon.Anchored = true
	weapon.CFrame = roblox.CFrame.new(31, 4, -2)
	weapon.Parent = character
	local onSword = Builder.create(Builder.defaultParams("impact"), {
		cframe = weapon.CFrame,
		size = roblox.Vector3.new(2, 2, 2),
		parent = weapon,
	})
	onSword:SetAttribute("VFX_Trigger", "Script")
	local emitted = false
	H.emitted = {}
	local payload = H.game:GetService("HttpService"):JSONEncode({
		Version = 1,
		Emits = { { Mode = "All", Path = { { Name = "Sword", Class = "Part", Index = 1 }, { Name = onSword.Name, Class = "Part", Index = 1 } } } },
	})
	signals.EclipseVFX:Fire(payload)
	task.wait()
	for _, n in H.emitted do
		if n > 0 then
			emitted = true
		end
	end
	check(emitted, "EclipseVFX marker played the EasyVFX effect")
	signals.EclipseVFX:Fire('{"Version":1,"Emits":[{"Path":"nope"}]}')
	signals.EclipseVFX:Fire("not json")
	signals.EasyVFX:Fire("VFX_DoesNotExist")
	check(#H.warnings == 1 and H.warnings[1]:find("VFX_DoesNotExist") ~= nil, "unknown effect warns once: " .. table.concat(H.warnings, " | "))

	binding.Disconnect()
	check(#signals.EasyVFX.handlers == 0 and #signals.EclipseVFX.handlers == 0, "binding disconnects")
	waitForQuiet(400)
	for _ = 1, 40 do
		task.wait()
	end
	character:Destroy()
	folder:Destroy()
end

print("== Eclipse Animator bridge (event track format)")
do
	local Bridge = H.require("Shared/EclipseBridge")
	local HttpService = H.game:GetService("HttpService")
	local rig = roblox.Instance.new("Model")
	rig.Name = "Rig"
	local hrp = roblox.Instance.new("Part")
	hrp.Name = "HumanoidRootPart"
	hrp.Anchored = true
	hrp.CFrame = roblox.CFrame.new(-30, 3, 0)
	hrp.Parent = rig
	local hand = roblox.Instance.new("Part")
	hand.Name = "RightHand"
	hand.CFrame = roblox.CFrame.new(-28, 4, -1)
	hand.Parent = rig
	rig.Parent = H.workspace
	local saves = roblox.Instance.new("Folder")
	saves.Name = "AnimSaves"
	saves.Parent = rig
	local seq = roblox.Instance.new("KeyframeSequence")
	seq.Name = "Slash Combo"
	seq.Parent = saves
	for _, t in { 0, 0.25, 0.5 } do
		local k = roblox.Instance.new("Keyframe")
		k.Time = t
		k.Parent = seq
	end

	-- one effect attached to the hand (Eclipse emit), one template elsewhere (marker)
	local holder = roblox.Instance.new("Part")
	holder.Parent = H.workspace
	local slash = Builder.create(Builder.defaultParams("slash"), { cframe = roblox.CFrame.new(), size = roblox.Vector3.new(4, 4, 4), parent = holder })
	Bridge.attach(rig, slash, "RightHand", roblox.CFrame.new(0, 0, -2))
	check(slash.Parent and slash.Parent.Name == "EasyVFX" and slash.Parent.Parent == rig, "effect moved into the rig")
	check(slash:FindFirstChild("EasyVFX_Weld") ~= nil and slash:GetAttribute("VFX_Trigger") == "Script", "welded and script-triggered")
	local folder = roblox.Instance.new("Folder")
	folder.Name = "EasyVFX_Effects"
	folder.Parent = H.game:GetService("ReplicatedStorage")
	local slamHolder = roblox.Instance.new("Part")
	slamHolder.Parent = folder
	local slam = Builder.create(Builder.defaultParams("ground_slam"), { cframe = roblox.CFrame.new(0, -60, 0), size = roblox.Vector3.new(4, 4, 4), parent = slamHolder })
	slam:SetAttribute("VFX_Trigger", "Script")

	local doc = Bridge.writeEvents(rig, seq, {
		{ time = 0.25, effect = slash, name = "Swing" },
		{ time = 0.5, effect = slam, at = "HumanoidRootPart", offset = roblox.Vector3.new(0, -3, -4) },
		{ time = 0.5, effect = slash },
	})
	check(doc.Name == "EclipseEvents" and doc.Parent == seq and doc:GetAttribute("Version") == 8, "Eclipse event document")
	check(doc:GetAttribute("FPS") == 60 and seq:GetAttribute("EclipseEventDocumentId") ~= nil and rig:GetAttribute("EclipseEventRigId") ~= nil, "document ids and FPS")
	local events = Bridge.readEvents(seq)
	check(#events == 2 and events[1].frame == 15 and events[2].frame == 30, "two events at frames 15 and 30")
	local e1 = events[1]
	check(#e1.emits == 1 and e1.emits[1].Mode == "All", "attached effect is an Eclipse emit")
	-- the emit path resolves to the effect, the way Eclipse resolves it
	local cursor = rig
	for _, step in e1.emits[1].Path do
		local count, found = 0, nil
		for _, child in cursor:GetChildren() do
			if child.Name == step.Name and child.ClassName == step.Class then
				count += 1
				if count == step.Index then
					found = child
					break
				end
			end
		end
		cursor = found
		if not cursor then
			break
		end
	end
	check(cursor == slash, "emit path resolves to the effect")
	local e2 = events[2]
	check(#e2.emits == 1 and #e2.markers == 1 and e2.markers[1].Name == "EasyVFX", "same-frame cues share one event")
	local payload = EasyVFX.ParseMarker(e2.markers[1].Parameter)
	check(payload ~= nil and payload.effect == slam.Name and payload.at == "HumanoidRootPart", "marker payload")
	for _, item in doc:GetChildren() do
		if not item:IsA("Folder") then
			continue
		end
		check(item:FindFirstChild("Markers") and item:FindFirstChild("Emits") and item:FindFirstChild("CodeBegin") and item:FindFirstChild("Sounds"), "event has Eclipse's fields")
	end

	-- KeyframeMarkers for the game, like Eclipse's export
	local markers = {}
	for _, key in seq:GetKeyframes() do
		for _, m in key:GetMarkers() do
			table.insert(markers, { name = m.Name, value = m.Value, time = key.Time })
		end
	end
	local names = {}
	for _, m in markers do
		names[m.name .. "@" .. m.time] = true
	end
	check(names["EclipseVFX@0.25"] and names["EclipseVFX@0.5"] and names["EasyVFX@0.5"], "keyframe markers written")
	-- rewriting replaces, never duplicates
	Bridge.writeEvents(rig, seq, { { time = 0.25, effect = slash } })
	local count = 0
	for _, key in seq:GetKeyframes() do
		count += #key:GetMarkers()
	end
	check(count == 1 and #Bridge.readEvents(seq) == 1, "rewrite replaces old markers and events")

	-- and the markers play the full effects through BindAnimation
	H.warnings = {}
	H.emitted = {}
	local signals = {}
	local track = {}
	function track:GetMarkerReachedSignal(name)
		signals[name] = signals[name] or { handlers = {}, Connect = function(sig, fn)
			table.insert(sig.handlers, fn)
			return { Disconnect = function() end }
		end }
		return signals[name]
	end
	EasyVFX.BindAnimation(track :: any, rig)
	for _, key in seq:GetKeyframes() do
		for _, m in key:GetMarkers() do
			for _, fn in signals[m.Name].handlers do
				fn(m.Value)
			end
		end
	end
	task.wait()
	local liveFolder = (H.workspace.CurrentCamera or H.workspace):FindFirstChild("EasyVFX_Live")
	check((liveFolder and #liveFolder:GetChildren() > 0) or next(H.emitted) ~= nil, "Eclipse emit played the attached EasyVFX effect")
	waitForQuiet(400)
	for _ = 1, 40 do
		task.wait()
	end
	check(#H.warnings == 0, "bridge no warnings: " .. table.concat(H.warnings, " | "))
	rig:Destroy()
	folder:Destroy()
	holder:Destroy()
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
