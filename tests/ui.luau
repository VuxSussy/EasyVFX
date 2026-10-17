--[[
	UI smoke test: builds the whole panel under Lune with fake events, then clicks
	through it (tabs, every card, every trigger, sliders, overlays, language).
	Property names/types are validated by Lune's Roblox reflection database.

	Run from the project root:  lune run tests/ui.luau
]]

local roblox = require("@lune/roblox")
local process = require("@lune/process")
local task = require("@lune/task")
local H = require("./harness")
H.install()

----------------------------------------------------------------------------- fake events
local signals = {}

local function newSignal()
	local handlers = {}
	local signal = {}
	function signal:Connect(fn)
		table.insert(handlers, fn)
		return {
			Connected = true,
			Disconnect = function()
				local i = table.find(handlers, fn)
				if i then
					table.remove(handlers, i)
				end
			end,
		}
	end
	function signal:Fire(...)
		for _, fn in table.clone(handlers) do
			fn(...)
		end
	end
	function signal:Wait() end
	return signal
end

local nextId = 0
local function signalFor(inst, name)
	-- Lune hands out a new wrapper per access, so key by a stable attribute id.
	local id = inst:GetAttribute("__testSignalId")
	if not id then
		nextId += 1
		id = nextId
		inst:SetAttribute("__testSignalId", id)
	end
	signals[id] = signals[id] or {}
	local s = signals[id][name]
	if not s then
		s = newSignal()
		signals[id][name] = s
	end
	return s
end

local GUI = { "Frame", "TextLabel", "TextButton", "TextBox", "ScrollingFrame", "ImageLabel", "ScreenGui" }
local EVENTS = { "Activated", "MouseEnter", "MouseLeave", "InputBegan", "InputEnded", "InputChanged", "Focused", "FocusLost", "AncestryChanged", "MouseButton1Click" }
for _, class in GUI do
	for _, event in EVENTS do
		roblox.implementProperty(class, event, function(inst)
			return signalFor(inst, event)
		end)
	end
	roblox.implementMethod(class, "GetPropertyChangedSignal", function(inst, prop)
		return signalFor(inst, "Changed:" .. prop)
	end)
	roblox.implementProperty(class, "AbsoluteSizeUnused", function()
		return roblox.Vector2.new(320, 24)
	end)
	roblox.implementProperty(class, "AbsolutePositionUnused", function()
		return roblox.Vector2.new(10, 100)
	end)
end
for _, class in { "Part", "Configuration", "ParticleEmitter", "Attachment" } do
	roblox.implementProperty(class, "AncestryChanged", function(inst)
		return signalFor(inst, "AncestryChanged")
	end)
end
roblox.implementMethod("ScreenGui", "GetRelativeMousePosition", function()
	return roblox.Vector2.new(200, 110)
end)
roblox.implementProperty("RunService", "Heartbeat", function(inst)
	return signalFor(inst, "Heartbeat")
end)
roblox.implementMethod("TweenService", "Create", function(_ts, inst, _info, goal)
	return {
		Play = function()
			for k, v in goal do
				inst[k] = v
			end
		end,
	}
end)

local function fire(inst, name, ...)
	assert(inst ~= nil, "fire: no instance for " .. name .. " at " .. debug.traceback())
	signalFor(inst, name):Fire(...)
end

----------------------------------------------------------------------------- app
local Presets = H.require("Shared/Presets")
local Builder = H.require("Shared/Builder")
local App = H.require("UI/App")

local failures, passed = 0, 0
local function check(cond, msg)
	if cond then
		passed += 1
	else
		failures += 1
		print("  FAIL: " .. msg)
	end
end

local widget = roblox.Instance.new("ScreenGui")
widget.Name = "Widget"
widget.Enabled = true
local settingsStore = {}
local favorites = {}
local selection = { kind = "none", name = "" }
local inserted = {}
local applied = 0
local previews = 0
local packAssets = nil

local api
api = {
	widget = widget,
	getSetting = function(k)
		return settingsStore[k]
	end,
	setSetting = function(k, v)
		settingsStore[k] = v
	end,
	insert = function(presetId, params)
		local p = params or Builder.defaultParams(presetId)
		local holder = roblox.Instance.new("Part")
		holder.Parent = H.workspace
		local root = Builder.create(p, { cframe = roblox.CFrame.new(), size = roblox.Vector3.new(4, 4, 4), parent = holder, weldTo = holder })
		table.insert(inserted, root)
		return root
	end,
	apply = function(root, params, final)
		Builder.apply(root, params)
		applied += 1
	end,
	beginEdit = function() end,
	preview = function()
		previews += 1
		return 0.5
	end,
	hasBursts = function(root)
		local p = Builder.readParams(root)
		return p ~= nil and Presets.ById[p.preset].kind == "burst"
	end,
	duplicate = function() end,
	delete = function(root)
		root.Parent = nil
	end,
	rename = function(root, name)
		root.Name = name
	end,
	addBloom = function()
		return true
	end,
	selectionInfo = function()
		return selection
	end,
	loadFavorites = function()
		return table.clone(favorites)
	end,
	getAssets = function()
		return if packAssets and Builder.isHD(packAssets) then packAssets else nil
	end,
	countAssets = function()
		local n = 0
		for _ in packAssets or {} do
			n += 1
		end
		return n
	end,
	scanAssets = function()
		packAssets = { slash_arc = "rbxassetid://11", flip_slash = "rbxassetid://12", spark_star = "rbxassetid://13" }
		return 3
	end,
	assetsFromText = function(text)
		packAssets = packAssets or {}
		local n = 0
		for key, id in text:gmatch("([%w_]+)%s*=%s*(%d+)") do
			packAssets[key] = "rbxassetid://" .. id
			n += 1
		end
		return n
	end,
	disableHD = function()
		packAssets = nil
	end,
	enableHD = function()
		packAssets = table.clone(H.require("Shared/DefaultAssets"))
	end,
	applyAll = function()
		local n = 0
		for _, root in inserted do
			if root.Parent then
				Builder.apply(root, Builder.readParams(root), api.getAssets())
				n += 1
			end
		end
		return n
	end,
	saveFavorites = function(list)
		favorites = list
	end,
}

local function findAll(root, pred)
	local out = {}
	for _, d in root:GetDescendants() do
		if pred(d) then
			table.insert(out, d)
		end
	end
	return out
end

local function buttonWithText(root, text)
	for _, d in root:GetDescendants() do
		if d:IsA("TextButton") and d.Text == text then
			return d
		end
	end
	return nil
end

local function run(name, fn)
	local ok, err = pcall(fn)
	check(ok, name .. ": " .. tostring(err))
end

print("== Build panel (first run shows guide)")
local app
run("App.new", function()
	app = App.new(api)
end)
check(app ~= nil, "app created")
check(app.overlay.Visible, "onboarding overlay visible on first run")

print("== Onboarding steps")
run("onboarding", function()
	for step = 1, 3 do
		local next_ = buttonWithText(app.overlay, app:L(if step == 3 then "onboardDone" else "onboardNext"))
		check(next_ ~= nil, "next button on step " .. step)
		fire(next_, "Activated")
	end
end)
check(not app.overlay.Visible, "overlay closed after guide")
check(settingsStore.EasyVFX_Onboarded == true, "onboarding remembered")

print("== Library: categories, search, every card")
local cards = findAll(app.grid, function(d)
	return d:IsA("TextButton")
end)
check(#cards == #Presets.List, ("all %d cards shown (got %d)"):format(#Presets.List, #cards))
run("categories", function()
	for _, cat in Presets.Categories do
		local chip = buttonWithText(app.libraryPage, cat.en)
		check(chip ~= nil, "chip " .. cat.id)
		fire(chip, "Activated")
	end
	fire(buttonWithText(app.libraryPage, "All"), "Activated")
	-- "All" shows one titled section per category, in order
	local titles = {}
	for _, d in app.grid:GetDescendants() do
		if d:IsA("TextLabel") and d.Text:find(" · %d+$") then
			table.insert(titles, d.Text)
		end
	end
	check(#titles >= 7, "section titles in All view (" .. #titles .. ")")
	-- a single category shows its cards without a title
	fire(buttonWithText(app.libraryPage, "Slashes"), "Activated")
	local slashCards = findAll(app.grid, function(d)
		return d:IsA("TextButton")
	end)
	check(#slashCards == 5, "5 slash cards (got " .. #slashCards .. ")")
	fire(buttonWithText(app.libraryPage, "All"), "Activated")
	-- the style filter narrows every category to the dark fantasy look
	fire(buttonWithText(app.libraryPage, "Dark Fantasy"), "Activated")
	local darkCards = findAll(app.grid, function(d)
		return d:IsA("TextButton")
	end)
	check(#darkCards == 8, "8 dark fantasy cards (got " .. #darkCards .. ")")
	fire(buttonWithText(app.libraryPage, "All styles"), "Activated")
	check(#findAll(app.grid, function(d)
		return d:IsA("TextButton")
	end) == #Presets.List, "all styles shows everything again")
end)
run("search", function()
	local box = findAll(app.libraryPage, function(d)
		return d:IsA("TextBox")
	end)[1]
	box.Text = "strike"
	fire(box, "Changed:Text")
	local shown = findAll(app.grid, function(d)
		return d:IsA("TextButton")
	end)
	check(#shown == 1, "search 'strike' finds Lightning Strike only (got " .. #shown .. ")")
	box.Text = "zzzz"
	fire(box, "Changed:Text")
	check(app.emptyNote.Visible, "empty search note shown")
	box.Text = ""
	fire(box, "Changed:Text")
end)

print("== Insert + customize every preset")
for _, preset in Presets.List do
	run("preset " .. preset.id, function()
		local card
		for _, d in app.grid:GetDescendants() do
			if d:IsA("TextButton") and d.LayoutOrder == table.find(Presets.List, preset) then
				card = d
			end
		end
		check(card ~= nil, preset.id .. " card")
		fire(card, "MouseEnter")
		fire(card, "MouseLeave")
		fire(card, "Activated")
		local root = inserted[#inserted]
		check(root and root.Parent, preset.id .. " inserted")
		selection = { kind = "effect", name = root.Name, root = root }
		app:setSelection(selection)
		check(app.editPage.Visible, preset.id .. " switches to Customize tab")

		-- every trigger
		for _, trig in Builder.Triggers do
			local key = ({
				Always = "trigAlways",
				Loop = "trigLoop",
				Touch = "trigTouch",
				Click = "trigClick",
				Prompt = "trigPrompt",
				Script = "trigScript",
			})[trig]
			local radioTitle
			for _, d in app.editPage:GetDescendants() do
				if d:IsA("TextLabel") and d.Text == app:L(key) then
					radioTitle = d
				end
			end
			check(radioTitle ~= nil, preset.id .. " radio " .. trig)
			local radio = radioTitle and radioTitle:FindFirstAncestorOfClass("TextButton")
			fire(radio, "Activated")
			check(root:GetAttribute("VFX_Trigger") == trig, preset.id .. " trigger set to " .. trig)
		end

		-- sliders: drag begin, heartbeat move, release; then type a number
		local hits = findAll(app.editPage, function(d)
			return d:IsA("TextButton") and d.Text == "" and d:FindFirstChildOfClass("Frame") ~= nil and d.Size.Y.Offset == 22
		end)
		check(#hits >= 5, preset.id .. " has sliders (" .. #hits .. ")")
		for _, hit in hits do
			local input = { UserInputType = roblox.Enum.UserInputType.MouseButton1, Position = roblox.Vector3.new(150, 0, 0) }
			fire(hit, "InputBegan", input)
			fire(H.game:GetService("RunService"), "Heartbeat")
			fire(app.frame, "InputEnded", input)
		end
		local boxes = findAll(app.editPage, function(d)
			return d:IsA("TextBox") and d.Size.X.Offset == 56
		end)
		for _, box in boxes do
			box.Text = "1.5"
			fire(box, "FocusLost", true)
		end

		-- colors: click a swatch, type a hex, type garbage
		local swatches = findAll(app.editPage, function(d)
			return d:IsA("TextButton") and d.Size.X.Offset == 22
		end)
		check(#swatches >= 24, preset.id .. " swatches")
		local before = applied
		fire(swatches[4], "Activated")
		check(applied == before + 1, preset.id .. " swatch applies a color")
		local hexBoxes = findAll(app.editPage, function(d)
			return d:IsA("TextBox") and d.Size.X.Offset == 76
		end)
		hexBoxes[1].Text = "#12ABEF"
		fire(hexBoxes[1], "FocusLost", true)
		local c1, c2 = root:GetAttribute("VFX_Color1"), root:GetAttribute("VFX_Color2")
		check(c1:ToHex():upper() == "12ABEF" or c2:ToHex():upper() == "12ABEF", preset.id .. " hex color applied")
		hexBoxes[2].Text = "not a color"
		fire(hexBoxes[2], "FocusLost", true)
		check(app.toast.Visible, preset.id .. " invalid hex shows toast")

		-- advanced: open, texture, favorite, reset
		fire(buttonWithText(app.editPage, "+  " .. app:L("sectionAdvanced")), "Activated")
		local tex = findAll(app.editPage, function(d)
			return d:IsA("TextBox") and d.PlaceholderText == app:L("texturePlaceholder")
		end)[1]
		check(tex ~= nil, preset.id .. " texture box")
		tex.Text = "rbxassetid://123456"
		fire(tex, "FocusLost", true)
		check(root:GetAttribute("VFX_Texture") == "rbxassetid://123456", preset.id .. " texture applied")
		fire(buttonWithText(app.editPage, app:L("saveFavorite")), "Activated")
		fire(buttonWithText(app.editPage, app:L("reset")), "Activated")
		check(root:GetAttribute("VFX_Texture") == "", preset.id .. " reset clears texture")
		fire(buttonWithText(app.editPage, "−  " .. app:L("sectionAdvanced")), "Activated")

		-- header actions
		fire(buttonWithText(app.editPage, app:L("play")), "Activated")
		local nameBox = findAll(app.editPage, function(d)
			return d:IsA("TextBox") and d.Text == root.Name
		end)[1]
		nameBox.Text = "My " .. preset.id
		fire(nameBox, "FocusLost", true)
		check(root.Name == "My " .. preset.id, preset.id .. " renamed")
		local del = buttonWithText(app.editPage, app:L("delete"))
		fire(del, "Activated")
		check(del.Text == app:L("deleteConfirm"), preset.id .. " delete asks to confirm")
		fire(del, "Activated")
		check(root.Parent == nil, preset.id .. " deleted after confirm")
		selection = { kind = "none", name = "" }
		app:setSelection(selection)
		app:setTab("library")
	end)
end
check(applied > 0, "builder applied changes")
check(#favorites > 0 and #favorites <= 12, "favorites saved and capped (" .. #favorites .. ")")

print("== HD pack card")
run("hd paste", function()
	app:renderLibrary()
	fire(buttonWithText(app.libraryPage, app:L("hdPaste")), "Activated")
	local box = findAll(app.libraryPage, function(d)
		return d:IsA("TextBox") and d.MultiLine
	end)[1]
	check(box ~= nil, "paste box shown")
	box.Text = "spark_star = 555"
	fire(buttonWithText(app.libraryPage, app:L("hdSave")), "Activated")
	check(api.getAssets() == nil, "HD stays off without slash_arc")
	check(app.toastText.Text == app:L("hdMissing"), "missing-main-texture message")
end)
run("hd scan", function()
	fire(buttonWithText(app.libraryPage, app:L("hdScan")), "Activated")
	check(api.getAssets() ~= nil, "HD on after scan")
	check(buttonWithText(app.libraryPage, app:L("hdApplyAll")) ~= nil, "apply-all shown when HD on")
	local before = #inserted
	fire(app.grid:GetChildren()[2], "Activated")
	local root = inserted[#inserted]
	if root and #inserted > before then
		selection = { kind = "effect", name = root.Name, root = root }
		app:setSelection(selection)
		local hasRotation = false
		for _, d in app.editPage:GetDescendants() do
			if d:IsA("TextLabel") and d.Text == app:L("rotation") then
				hasRotation = true
			end
		end
		local p = Builder.readParams(root)
		check(not Builder.hasHD(p.preset) or hasRotation, "rotation slider for HD preset")
		selection = { kind = "none", name = "" }
		app:setSelection(selection)
		app:setTab("library")
	end
	fire(buttonWithText(app.libraryPage, app:L("hdApplyAll")), "Activated")
	fire(buttonWithText(app.libraryPage, app:L("hdDisable")), "Activated")
	check(api.getAssets() == nil, "HD off after disable")
	local enable = buttonWithText(app.libraryPage, app:L("hdEnable"))
	check(enable ~= nil, "built-in HD button when HD is off")
	fire(enable, "Activated")
	check(api.getAssets() ~= nil and api.getAssets().slash_arc ~= nil, "built-in pack turns HD back on")
	check(buttonWithText(app.libraryPage, app:L("hdDisable")) ~= nil, "card shows the on state")
end)

print("== Favorites row, help, language, theme re-render")
run("favorites", function()
	app:renderLibrary()
	local fav = buttonWithText(app.libraryPage, favorites[1].name)
	check(fav ~= nil, "favorite chip shown")
	local before = #inserted
	fire(fav, "Activated")
	check(#inserted == before + 1, "favorite inserts an effect")
	fire(buttonWithText(app.libraryPage, "×"), "Activated")
end)
run("help", function()
	fire(buttonWithText(app.frame, app:L("help")), "Activated")
	check(app.overlay.Visible, "help visible")
	fire(buttonWithText(app.overlay, app:L("bloom")), "Activated")
	fire(buttonWithText(app.overlay, app:L("close")), "Activated")
	check(not app.overlay.Visible, "help closed")
	fire(buttonWithText(app.frame, app:L("help")), "Activated")
	fire(buttonWithText(app.overlay, app:L("replayGuide")), "Activated")
	check(app.overlay.Visible and app.state.onboardStep == 1, "replay guide")
	fire(buttonWithText(app.overlay, app:L("onboardSkip")), "Activated")
end)
run("language", function()
	check(app.state.lang == "en", "English by default")
	fire(buttonWithText(app.frame, "VI"), "Activated")
	check(app.state.lang == "vi", "switched to Vietnamese")
	check(buttonWithText(app.frame, "Thư viện") ~= nil, "Vietnamese tab label")
	fire(buttonWithText(app.frame, "EN"), "Activated")
	check(app.state.lang == "en", "switched back to English")
end)
run("empty customize", function()
	app:setTab("edit")
	local b = buttonWithText(app.editPage, app:L("emptyAction"))
	check(b ~= nil, "empty state action")
	fire(b, "Activated")
	check(app.libraryPage.Visible, "empty action opens library")
end)
print("== Create tab: build, save, share, import, delete")
local Custom = H.require("Shared/Custom")
run("create", function()
	fire(buttonWithText(app.frame, app:L("tabCreate")), "Activated")
	check(app.createPage.Visible, "create tab visible")
	local function blocksTitle()
		for _, d in app.createPage:GetDescendants() do
			if d:IsA("TextLabel") and d.Text == string.format(app:L("createBlocks"), #app.state.draft.blocks):upper() then
				return d.Text
			end
		end
		return ""
	end
	check(#app.state.draft.blocks == 3, "starts with 3 blocks")
	check(blocksTitle() ~= "", "blocks section title")
	fire(buttonWithText(app.createPage, "+ Spiral"), "Activated")
	fire(buttonWithText(app.createPage, "+ Camera shake"), "Activated")
	check(#app.state.draft.blocks == 5, "added blocks: " .. #app.state.draft.blocks)
	local voids = findAll(app.createPage, function(d)
		return d:IsA("TextButton") and d.Text == app:L("colorVoid")
	end)
	fire(voids[1], "Activated")
	local voided = 0
	for _, b in app.state.draft.blocks do
		if b.color == "x" then
			voided += 1
		end
	end
	check(voided == 1, "one block color changed")
	fire(buttonWithText(app.createPage, app:L("blockRemove")), "Activated")
	check(#app.state.draft.blocks == 4, "removed a block")
	fire(buttonWithText(app.createPage, app:L("badgeLoop")), "Activated")
	check(app.state.draft.kind == "loop", "kind switched to loop")
	for _, box in findAll(app.createPage, function(d)
		return d:IsA("TextBox") and d.Text == "My Effect"
	end) do
		box.Text = "Doom Burst"
		fire(box, "FocusLost", true)
	end
	check(app.state.draft.name == "Doom Burst", "renamed: " .. app.state.draft.name)
	app.state.draft.blocks[1].dark = true

	local before = #inserted
	fire(buttonWithText(app.createPage, app:L("createSaveAdd")), "Activated")
	check(#inserted == before + 1, "save & add inserted an effect")
	local root = inserted[#inserted]
	local def = Custom.decode(root:GetAttribute("VFX_CustomDef"))
	check(def ~= nil and def.name == "Doom Burst", "effect carries its definition")
	check(type(settingsStore[Custom.SETTING]) == "string", "saved in plugin settings")
	local preset = Presets.ById[app.state.draft.id]
	check(preset ~= nil and preset.category == "custom", "registered in library")

	fire(buttonWithText(app.frame, app:L("tabLibrary")), "Activated")
	local chip = buttonWithText(app.libraryPage, "My Effects")
	check(chip ~= nil, "My Effects category chip")
	fire(chip, "Activated")
	local card = nil
	for _, d in app.libraryPage:GetDescendants() do
		if d:IsA("TextLabel") and d.Text == "Doom Burst" then
			card = d
		end
	end
	check(card ~= nil, "custom effect card in library")

	fire(buttonWithText(app.frame, app:L("tabCreate")), "Activated")
	fire(buttonWithText(app.createPage, app:L("myShare")), "Activated")
	local code = nil
	for _, d in app.createPage:GetDescendants() do
		if d:IsA("TextBox") and d.Text:sub(1, #Custom.PREFIX) == Custom.PREFIX then
			code = d.Text
		end
	end
	check(code ~= nil, "share code shown")
	local function importText(text)
		for _, d in app.createPage:GetDescendants() do
			if d:IsA("TextBox") and d.PlaceholderText:sub(1, #Custom.PREFIX) == Custom.PREFIX then
				d.Text = text
			end
		end
		fire(buttonWithText(app.createPage, app:L("importButton")), "Activated")
	end
	importText(code)
	check(#Custom.load(settingsStore[Custom.SETTING]) == 2, "imported a copy")
	importText("EVFX1:{not json")
	importText('EVFX1:{"name":"x","blocks":[{"block":"rm -rf"}]}')
	check(#Custom.load(settingsStore[Custom.SETTING]) == 2, "bad codes rejected")
	local del = buttonWithText(app.createPage, app:L("myDelete"))
	fire(del, "Activated")
	fire(del, "Activated")
	check(#Custom.load(settingsStore[Custom.SETTING]) == 1, "deleted one")
	fire(buttonWithText(app.createPage, app:L("myEdit")), "Activated")
	check(app.state.draft.name == "Doom Burst", "edit loads the definition")
	fire(buttonWithText(app.createPage, app:L("createNew")), "Activated")
	check(app.state.draft.name == "My Effect", "new draft")
end)
run("destroy", function()
	app:destroy()
end)

task.wait(0.2)
print(("\n%d passed, %d failed"):format(passed, failures))
process.exit(if failures == 0 then 0 else 1)
