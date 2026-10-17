--!strict
--[[
	EasyVFX — no-code visual effects for Roblox Studio.

	Plugin entry point: toolbar button, dock panel, inserting effects where the user
	is looking or onto the selected object, undo/redo, and installing the small
	runtime that plays effects in game.
]]

local ChangeHistoryService = game:GetService("ChangeHistoryService")
local Lighting = game:GetService("Lighting")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Selection = game:GetService("Selection")
local ServerScriptService = game:GetService("ServerScriptService")
local StarterPlayer = game:GetService("StarterPlayer")
local Workspace = game:GetService("Workspace")

if not RunService:IsEdit() then
	return -- only in edit mode, not in Play test sessions
end

local Presets = require(script.Shared.Presets)
local Builder = require(script.Shared.Builder)
local Custom = require(script.Shared.Custom)
local Strings = require(script.Shared.Strings)
local Runtime = require(script.Runtime.EasyVFX)
local App = require(script.UI.App)

type Params = Builder.Params

local HUGE_PART = 64 -- parts bigger than this (baseplates, terrain-like floors) are treated as ground

local function setting(key: string): any
	local ok, value = pcall(function()
		return plugin:GetSetting(key)
	end)
	return if ok then value else nil
end

local function setSetting(key: string, value: any)
	pcall(function()
		plugin:SetSetting(key, value)
	end)
end

-- Authoring API for AI agents and command-bar scripts (Builder, Presets, Custom,
-- EclipseBridge, Runtime) at ServerStorage.EasyVFX_Authoring while Studio is in
-- edit mode. Archivable = false, so it is never saved with the place.
if RunService:IsEdit() then
	pcall(function()
		local ServerStorage = game:GetService("ServerStorage")
		local old = ServerStorage:FindFirstChild("EasyVFX_Authoring")
		if old then
			old:Destroy()
		end
		local folder = script.Shared:Clone()
		folder.Name = "EasyVFX_Authoring"
		folder.Archivable = false
		local runtime = script.Runtime.EasyVFX:Clone()
		runtime.Name = "Runtime"
		runtime.Parent = folder
		for _, d in folder:GetDescendants() do
			d.Archivable = false
		end
		folder.Parent = ServerStorage
	end)
end

-- Effects people made themselves ("My Effects") join the library on start.
Custom.register(Custom.load(setting(Custom.SETTING)))

local function lang(): string
	return if setting("EasyVFX_Lang") == "vi" then "vi" else "en" -- English unless the user picked Vietnamese
end

local function L(key: string): string
	local table_ = (Strings :: any)[lang()] or Strings.vi
	return table_[key] or key
end

------------------------------------------------------------------------------------
-- Toolbar + panel
------------------------------------------------------------------------------------

local toolbar = plugin:CreateToolbar("EasyVFX")
local button = toolbar:CreateButton("EasyVFXOpen", L("toolbarTip"), "", L("toolbar"))
button.ClickableWhenViewportHidden = true

local widgetInfo = DockWidgetPluginGuiInfo.new(Enum.InitialDockState.Right, false, false, 340, 640, 300, 420)
local widget: DockWidgetPluginGui
do
	local ok, result = pcall(function()
		return (plugin :: any):CreateDockWidgetPluginGuiAsync("EasyVFX_Main", widgetInfo)
	end)
	if ok and result then
		widget = result
	else
		widget = (plugin :: any):CreateDockWidgetPluginGui("EasyVFX_Main", widgetInfo)
	end
end
widget.Name = "EasyVFX"
widget.Title = "EasyVFX"
widget.ZIndexBehavior = Enum.ZIndexBehavior.Sibling

------------------------------------------------------------------------------------
-- Undo / redo
------------------------------------------------------------------------------------

local openRecording: string? = nil

local function finishEdit(commit: boolean)
	if openRecording then
		ChangeHistoryService:FinishRecording(
			openRecording,
			if commit then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel
		)
		openRecording = nil
	end
end

local function beginEdit(name: string)
	if openRecording then
		return
	end
	openRecording = ChangeHistoryService:TryBeginRecording("EasyVFX: " .. name)
end

local function record(name: string, fn: () -> any): any
	finishEdit(true)
	local id = ChangeHistoryService:TryBeginRecording("EasyVFX: " .. name)
	local ok, result = pcall(fn)
	if id then
		ChangeHistoryService:FinishRecording(
			id,
			if ok then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel
		)
	end
	if not ok then
		warn("[EasyVFX] " .. tostring(result))
		return nil
	end
	return result
end

------------------------------------------------------------------------------------
-- Runtime install (one time per place)
------------------------------------------------------------------------------------

local function ensureRuntime(): string?
	local message: string? = nil
	local template = script.Runtime
	local existing = ReplicatedStorage:FindFirstChild("EasyVFX")
	if not existing or existing:GetAttribute("EasyVFXVersion") ~= Runtime.Version then
		message = if existing then "runtimeUpdated" else "runtimeInstalled"
		if existing then
			existing:Destroy()
		end
		local module = template.EasyVFX:Clone()
		module:SetAttribute("EasyVFXVersion", Runtime.Version)
		module.Parent = ReplicatedStorage
	end
	if not ServerScriptService:FindFirstChild("EasyVFXServer") then
		local server = template.EasyVFXServer:Clone() :: Script
		server.Enabled = true
		server.Parent = ServerScriptService
		message = message or "runtimeInstalled"
	end
	local playerScripts = StarterPlayer:FindFirstChildOfClass("StarterPlayerScripts")
		or StarterPlayer:WaitForChild("StarterPlayerScripts", 5)
	if playerScripts and not playerScripts:FindFirstChild("EasyVFXClient") then
		local client = template.EasyVFXClient:Clone() :: LocalScript
		client.Enabled = true
		client.Parent = playerScripts
		message = message or "runtimeInstalled"
	end
	return message
end

------------------------------------------------------------------------------------
-- Where a new effect goes
------------------------------------------------------------------------------------

local function isHuge(part: BasePart): boolean
	return part:IsA("Terrain") or math.max(part.Size.X, part.Size.Y, part.Size.Z) > HUGE_PART
end

local function clampSize(size: Vector3): Vector3
	return Vector3.new(math.min(size.X, 24), math.min(size.Y, 24), math.min(size.Z, 24))
end

local function usableTarget(): Instance?
	local selected = Selection:Get()[1]
	if not selected then
		return nil
	end
	local root = Builder.findRoot(selected)
	if root then
		selected = root.Parent
	end
	if not selected or selected == Workspace then
		return nil
	end
	if selected:IsA("BasePart") then
		return if isHuge(selected) then nil else selected
	elseif selected:IsA("Model") or selected:IsA("Attachment") then
		return selected
	end
	return nil
end

local function cameraPlacement(preset: Presets.Preset): Builder.Placement
	local camera = Workspace.CurrentCamera
	local area = preset.area or Vector3.new(4, 4, 4)
	local camCF = if camera then camera.CFrame else CFrame.new(0, 10, 20)
	local look = camCF.LookVector
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = if camera then { camera } else {}
	local hit = Workspace:Raycast(camCF.Position, look * 400, params)
	local point = if hit then hit.Position else camCF.Position + look * 25
	local placement = preset.placement or "ground"
	local lift = if placement == "sky" then 30 elseif placement == "air" then 3.5 else area.Y / 2
	local position = point + Vector3.new(0, lift, 0)
	local flat = Vector3.new(look.X, 0, look.Z)
	if flat.Magnitude < 0.01 then
		flat = Vector3.new(0, 0, -1)
	end
	return {
		cframe = CFrame.lookAt(position, position + flat.Unit),
		size = area,
		parent = Workspace,
		weldTo = nil,
	}
end

local function placementFor(preset: Presets.Preset): Builder.Placement
	local target = usableTarget()
	local useArea = preset.category == "world" and preset.area ~= nil
	if target and target:IsA("BasePart") then
		return {
			cframe = target.CFrame,
			size = if useArea then preset.area :: Vector3 else clampSize(target.Size),
			parent = target,
			weldTo = target,
		}
	elseif target and target:IsA("Model") then
		local anchor = target.PrimaryPart or target:FindFirstChildWhichIsA("BasePart", true)
		if anchor then
			local cf, size = target:GetBoundingBox()
			return {
				cframe = cf,
				size = if useArea then preset.area :: Vector3 else clampSize(size),
				parent = target,
				weldTo = anchor,
			}
		end
	elseif target and target:IsA("Attachment") and target.Parent and target.Parent:IsA("BasePart") then
		local part = target.Parent :: BasePart
		return {
			cframe = target.WorldCFrame,
			size = preset.area or Vector3.new(4, 4, 4),
			parent = part,
			weldTo = part,
		}
	end
	return cameraPlacement(preset)
end

local function selectionInfo(): App.SelectionInfo
	local selected = Selection:Get()[1]
	if selected then
		local root = Builder.findRoot(selected)
		if root then
			return { kind = "effect", name = root.Name, root = root }
		end
	end
	local target = usableTarget()
	if target then
		return { kind = "part", name = target.Name }
	end
	return { kind = "none", name = "" }
end

------------------------------------------------------------------------------------
-- Favorites (stored in plugin settings; colors as hex)
------------------------------------------------------------------------------------

local function encodeParams(p: Params): { [string]: any }
	local out = table.clone(p) :: any
	out.color1 = p.color1:ToHex()
	out.color2 = p.color2:ToHex()
	return out
end

local function decodeParams(raw: any): Params?
	if type(raw) ~= "table" or type(raw.preset) ~= "string" or not Presets.ById[raw.preset] then
		return nil
	end
	local p = Builder.defaultParams(raw.preset)
	local dict = p :: any
	for key, value in raw do
		if key == "color1" or key == "color2" then
			if type(value) == "string" then
				local ok, color = pcall(Color3.fromHex, value)
				if ok then
					dict[key] = color
				end
			end
		elseif dict[key] ~= nil and type(value) == type(dict[key]) then
			dict[key] = value
		end
	end
	return p
end

local function loadFavorites(): { App.Favorite }
	local raw = setting("EasyVFX_Favorites")
	local out = {}
	if type(raw) == "table" then
		for _, item in raw do
			if type(item) == "table" and type(item.name) == "string" then
				local params = decodeParams(item.params)
				if params then
					table.insert(out, { name = item.name, params = params })
				end
			end
		end
	end
	return out
end

local function saveFavorites(favorites: { App.Favorite })
	local raw = {}
	for _, fav in favorites do
		table.insert(raw, { name = fav.name, params = encodeParams(fav.params) })
	end
	setSetting("EasyVFX_Favorites", raw)
end

------------------------------------------------------------------------------------
-- HD asset pack (textures rendered in Blender). Image IDs are account-wide, so they
-- are remembered in plugin settings and reused in every place.
------------------------------------------------------------------------------------

local PACK_PREFIX = "EVFX_Tex_"
local SCAN_ROOTS = { Workspace, ReplicatedStorage, game:GetService("ServerStorage") }

local function loadAssets(): Builder.Assets?
	local raw = setting("EasyVFX_Assets")
	if type(raw) ~= "table" then
		return nil
	end
	local out: Builder.Assets = {}
	for key, value in raw do
		if type(key) == "string" and type(value) == "string" and value ~= "" then
			out[key] = value
		end
	end
	return if Builder.isHD(out) then out else nil
end

local function countAssets(assets: Builder.Assets?): number
	local n = 0
	if assets then
		for _ in assets do
			n += 1
		end
	end
	return n
end

local function normalizeId(text: string): string?
	local cleaned = text:gsub("%s", "")
	if cleaned:match("^rbxasset") then
		return cleaned
	end
	local id = cleaned:match("(%d+)")
	return if id then "rbxassetid://" .. id else nil
end

-- Finds the texture an imported EVFX_Tex_* object carries (3D Importer output).
local function textureOf(inst: Instance): string?
	local candidates = {}
	if inst:IsA("MeshPart") then
		table.insert(candidates, inst.TextureID)
	end
	for _, d in inst:GetDescendants() do
		if d:IsA("SurfaceAppearance") then
			local ok, value = pcall(function()
				return (d :: any).ColorMap
			end)
			if ok then
				table.insert(candidates, value)
			end
		elseif d:IsA("Decal") or d:IsA("Texture") then
			table.insert(candidates, d.Texture)
		elseif d:IsA("MeshPart") then
			table.insert(candidates, d.TextureID)
		end
	end
	for _, value in candidates do
		if type(value) == "string" and value ~= "" then
			return value
		end
	end
	return nil
end

local function saveAssets(assets: Builder.Assets)
	setSetting("EasyVFX_Assets", assets)
end

local function scanAssets(): number
	local found: Builder.Assets = loadAssets() or {}
	local n = 0
	for _, scanRoot in SCAN_ROOTS do
		for _, inst in scanRoot:GetDescendants() do
			if inst.Name:sub(1, #PACK_PREFIX) == PACK_PREFIX then
				local key = inst.Name:sub(#PACK_PREFIX + 1)
				local texture = textureOf(inst)
				if texture and key ~= "" then
					found[key] = texture
					n += 1
				end
			end
		end
	end
	if n > 0 then
		saveAssets(found)
	end
	return n
end

local function assetsFromText(text: string): number
	local found: Builder.Assets = loadAssets() or {}
	local n = 0
	for line in text:gmatch("[^\r\n]+") do
		local key, rest = line:match("^%s*([%w_]+)%s*[=:%s]%s*(.-)%s*$")
		local id = if rest then normalizeId(rest) else nil
		if key and id then
			found[key] = id
			n += 1
		end
	end
	if n > 0 then
		saveAssets(found)
	end
	return n
end

------------------------------------------------------------------------------------
-- Actions used by the panel
------------------------------------------------------------------------------------

local app: any = nil

local queued: { root: Instance, params: Params }? = nil
local applyScheduled = false

local function applyNow(root: Instance, params: Params)
	if root.Parent and root:IsA("BasePart") then
		local ok, err = pcall(Builder.apply :: any, root, params, loadAssets())
		if not ok then
			warn("[EasyVFX] " .. tostring(err))
		end
	end
end

local function apply(root: Instance, params: Params, final: boolean)
	beginEdit("Edit effect")
	if final then
		queued = nil
		applyNow(root, params)
		finishEdit(true)
		if app and not app.state.autoPreview and Runtime.HasBursts(root) then
			Runtime.PlayLocal(root)
		end
		return
	end
	-- Live slider drags: apply at most ~20 times per second.
	queued = { root = root, params = table.clone(params) }
	if not applyScheduled then
		applyScheduled = true
		task.delay(0.05, function()
			applyScheduled = false
			local job = queued
			queued = nil
			if job then
				applyNow(job.root, job.params)
			end
		end)
	end
end

local function insert(presetId: string, params: Params?): Instance?
	local preset = Presets.ById[presetId]
	if not preset then
		return nil
	end
	local p: Params = if params then table.clone(params) else Builder.defaultParams(presetId)
	p.preset = presetId
	if not params and lang() == "vi" then
		p.promptText = "Kích hoạt"
	end
	local runtimeMessage: string? = nil
	local root = record("Add " .. preset.name.en, function()
		local placement = placementFor(preset)
		local created = Builder.create(p, placement, loadAssets())
		runtimeMessage = ensureRuntime()
		return created
	end)
	if root then
		Selection:Set({ root })
		if app then
			local text = L("added"):format((preset.name :: any)[lang()])
			if runtimeMessage then
				text ..= "\n" .. L(runtimeMessage)
			end
			app:toastMessage(text, "success")
		end
	end
	return root
end

local api: App.Api = {
	widget = widget,
	getSetting = setting,
	setSetting = setSetting,
	insert = insert,
	apply = apply,
	beginEdit = beginEdit,
	preview = function(root)
		return Runtime.PlayLocal(root)
	end,
	hasBursts = function(root)
		return Runtime.HasBursts(root)
	end,
	duplicate = function(root)
		local copy = record("Duplicate effect", function()
			local c = root:Clone()
			c.Parent = root.Parent
			if c:IsA("BasePart") and c.Anchored then
				c.CFrame += c.CFrame.RightVector * (c.Size.X + 2)
			end
			return c
		end)
		if copy then
			Selection:Set({ copy })
		end
	end,
	delete = function(root)
		record("Delete effect", function()
			root.Parent = nil
			return nil
		end)
		Selection:Set({})
		if app then
			app:toastMessage(L("deleted"), "success")
		end
	end,
	rename = function(root, name)
		record("Rename effect", function()
			root.Name = name
			return nil
		end)
	end,
	addBloom = function()
		if Lighting:FindFirstChildOfClass("BloomEffect") then
			return false
		end
		record("Add Bloom", function()
			local bloom = Instance.new("BloomEffect")
			bloom.Name = "EasyVFX_Bloom"
			bloom.Intensity = 0.9
			bloom.Size = 28
			bloom.Threshold = 0.85
			bloom.Parent = Lighting
			return nil
		end)
		return true
	end,
	selectionInfo = selectionInfo,
	loadFavorites = loadFavorites,
	saveFavorites = saveFavorites,
	getAssets = loadAssets,
	countAssets = function()
		return countAssets(loadAssets())
	end,
	scanAssets = scanAssets,
	assetsFromText = assetsFromText,
	disableHD = function()
		setSetting("EasyVFX_Assets", nil)
	end,
	applyAll = function()
		local assets = loadAssets()
		local n = 0
		record("Apply HD setting", function()
			for _, inst in game:GetService("CollectionService"):GetTagged(Builder.TAG) do
				local params = if inst:IsA("BasePart") then Builder.readParams(inst) else nil
				if params then
					Builder.apply(inst :: BasePart, params, assets)
					n += 1
				end
			end
			return nil
		end)
		return n
	end,
}

app = App.new(api)
app:setSelection(selectionInfo())

------------------------------------------------------------------------------------
-- Wiring
------------------------------------------------------------------------------------

button.Click:Connect(function()
	widget.Enabled = not widget.Enabled
end)

widget:GetPropertyChangedSignal("Enabled"):Connect(function()
	button:SetActive(widget.Enabled)
	if widget.Enabled then
		app:restartPreview()
	end
end)
button:SetActive(widget.Enabled)

Selection.SelectionChanged:Connect(function()
	app:setSelection(selectionInfo())
end)

local function afterHistory()
	finishEdit(true)
	app:setSelection(selectionInfo())
	app:refresh()
end
ChangeHistoryService.OnUndo:Connect(afterHistory)
ChangeHistoryService.OnRedo:Connect(afterHistory)

pcall(function()
	(settings().Studio :: any).ThemeChanged:Connect(function()
		app:render()
	end)
end)

-- First time: open the panel so the 3-step guide is seen.
if not setting("EasyVFX_Onboarded") then
	widget.Enabled = true
end

plugin.Unloading:Connect(function()
	finishEdit(true)
	app:destroy()
end)
