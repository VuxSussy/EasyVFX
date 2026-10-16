--!nonstrict
--[[
	The EasyVFX panel.
	  Header      title, language switch, help
	  Tabs        Library (pick an effect) | Customize (tune the selected effect)
	  Status bar  what the next effect will attach to
	  Overlays    toast messages, 3-step first-run guide, help card
]]

local Presets = require(script.Parent.Parent.Shared.Presets)
local Builder = require(script.Parent.Parent.Shared.Builder)
local Strings = require(script.Parent.Parent.Shared.Strings)
local Theme = require(script.Parent.Theme)
local C = require(script.Parent.Components)

type Params = Builder.Params

export type SelectionInfo = {
	kind: string, -- "none" | "part" | "effect"
	name: string,
	root: Instance?,
}

export type Favorite = { name: string, params: Params }

export type Api = {
	widget: any,
	getSetting: (key: string) -> any,
	setSetting: (key: string, value: any) -> (),
	insert: (presetId: string, params: Params?) -> Instance?,
	apply: (root: Instance, params: Params, final: boolean) -> (),
	beginEdit: (name: string) -> (),
	preview: (root: Instance) -> number,
	hasBursts: (root: Instance) -> boolean,
	duplicate: (root: Instance) -> (),
	delete: (root: Instance) -> (),
	rename: (root: Instance, name: string) -> (),
	addBloom: () -> boolean,
	selectionInfo: () -> SelectionInfo,
	loadFavorites: () -> { Favorite },
	saveFavorites: (favorites: { Favorite }) -> (),
	getAssets: () -> Builder.Assets?,
	countAssets: () -> number,
	scanAssets: () -> number,
	assetsFromText: (text: string) -> number,
	disableHD: () -> (),
	applyAll: () -> number,
}

local App = {}
App.__index = App

export type State = {
	tab: string,
	category: string,
	search: string,
	lang: string,
	autoPreview: boolean,
	advancedOpen: boolean,
	onboardStep: number?,
	helpOpen: boolean,
	root: Instance?,
	selection: SelectionInfo,
}

local HEADER_H, TABS_H, STATUS_H = 52, 38, 30

function App.new(api: Api)
	local self = setmetatable({}, App)
	self.api = api
	local lang = api.getSetting("EasyVFX_Lang")
	self.state = {
		tab = "library",
		category = "all",
		search = "",
		lang = if lang == "vi" then "vi" else "en",
		autoPreview = api.getSetting("EasyVFX_AutoPreview") ~= false,
		advancedOpen = false,
		pasteOpen = false,
		onboardStep = if api.getSetting("EasyVFX_Onboarded") then nil else 1,
		helpOpen = false,
		root = nil,
		selection = { kind = "none", name = "" },
	} :: State
	self.previewToken = 0
	self.toastToken = 0
	self.rootConnections = {} :: { RBXScriptConnection }
	self:render()
	return self
end

function App:L(key: string): string
	local lang = (Strings :: any)[self.state.lang] or Strings.vi
	return lang[key] or Strings.en[key] or key
end

------------------------------------------------------------------------------------
-- Full render (theme or language change)
------------------------------------------------------------------------------------

function App:render()
	local t = Theme.current()
	self.t = t
	if self.frame then
		self.frame:Destroy()
	end
	local api: Api = self.api
	local frame = C.new("Frame", {
		Name = "EasyVFX",
		BackgroundColor3 = t.bg,
		BorderSizePixel = 0,
		Size = UDim2.fromScale(1, 1),
		Active = true,
		Parent = api.widget,
	})
	self.frame = frame

	-- Header
	local header = C.new("Frame", {
		BackgroundColor3 = t.bg,
		BorderSizePixel = 0,
		Size = UDim2.new(1, 0, 0, HEADER_H),
		Parent = frame,
	}, { C.padding(10, 12, 6, 12) })
	C.new("TextLabel", {
		BackgroundTransparency = 1,
		Text = self:L("appTitle"),
		TextColor3 = t.fg,
		TextSize = Theme.Text.hero,
		FontFace = Theme.Font.bold,
		TextXAlignment = Enum.TextXAlignment.Left,
		Size = UDim2.new(1, -120, 0, 20),
		Parent = header,
	})
	C.new("TextLabel", {
		BackgroundTransparency = 1,
		Text = self:L("appSubtitle"),
		TextColor3 = t.mutedFg,
		TextSize = Theme.Text.caption,
		FontFace = Theme.Font.regular,
		TextXAlignment = Enum.TextXAlignment.Left,
		Position = UDim2.new(0, 0, 0, 20),
		Size = UDim2.new(1, -120, 0, 16),
		TextTruncate = Enum.TextTruncate.AtEnd,
		Parent = header,
	})
	local actions = C.new("Frame", {
		BackgroundTransparency = 1,
		AnchorPoint = Vector2.new(1, 0),
		Position = UDim2.new(1, 0, 0, 2),
		Size = UDim2.new(0, 116, 0, 30),
		Parent = header,
	}, { C.new("UIListLayout", {
		FillDirection = Enum.FillDirection.Horizontal,
		HorizontalAlignment = Enum.HorizontalAlignment.Right,
		Padding = UDim.new(0, 6),
		SortOrder = Enum.SortOrder.LayoutOrder,
	}) })
	C.button(t, {
		text = self:L("language"),
		width = UDim.new(0, 40),
		height = 30,
		order = 1,
		onClick = function()
			self.state.lang = if self.state.lang == "vi" then "en" else "vi"
			api.setSetting("EasyVFX_Lang", self.state.lang)
			self:render()
		end,
	}).Parent = actions
	C.button(t, {
		text = self:L("help"),
		width = UDim.new(0, 70),
		height = 30,
		order = 2,
		onClick = function()
			self.state.helpOpen = true
			self:renderOverlay()
		end,
	}).Parent = actions

	-- Tabs
	local tabs = C.new("Frame", {
		BackgroundColor3 = t.bg,
		BorderSizePixel = 0,
		Position = UDim2.new(0, 0, 0, HEADER_H),
		Size = UDim2.new(1, 0, 0, TABS_H),
		Parent = frame,
	})
	C.new("Frame", {
		BackgroundColor3 = t.border,
		BorderSizePixel = 0,
		AnchorPoint = Vector2.new(0, 1),
		Position = UDim2.new(0, 0, 1, 0),
		Size = UDim2.new(1, 0, 0, 1),
		Parent = tabs,
	})
	self.tabButtons = {}
	for i, tab in { { id = "library", key = "tabLibrary" }, { id = "edit", key = "tabEdit" } } do
		local b = C.new("TextButton", {
			AutoButtonColor = false,
			BackgroundTransparency = 1,
			Text = self:L(tab.key),
			TextSize = Theme.Text.body,
			FontFace = Theme.Font.semibold,
			Position = UDim2.new((i - 1) * 0.5, 0, 0, 0),
			Size = UDim2.new(0.5, 0, 1, 0),
			Parent = tabs,
		})
		local underline = C.new("Frame", {
			BorderSizePixel = 0,
			AnchorPoint = Vector2.new(0.5, 1),
			Position = UDim2.new(0.5, 0, 1, 0),
			Size = UDim2.new(0.6, 0, 0, 2),
			Parent = b,
		})
		b.Activated:Connect(function()
			self:setTab(tab.id)
		end)
		self.tabButtons[tab.id] = { button = b, underline = underline }
	end

	-- Body: one scrolling page per tab
	local body = C.new("Frame", {
		BackgroundTransparency = 1,
		Position = UDim2.new(0, 0, 0, HEADER_H + TABS_H),
		Size = UDim2.new(1, 0, 1, -(HEADER_H + TABS_H + STATUS_H)),
		ClipsDescendants = true,
		Parent = frame,
	})
	local function page(): ScrollingFrame
		return C.new("ScrollingFrame", {
			BackgroundTransparency = 1,
			BorderSizePixel = 0,
			Size = UDim2.fromScale(1, 1),
			CanvasSize = UDim2.new(),
			AutomaticCanvasSize = Enum.AutomaticSize.Y,
			ScrollingDirection = Enum.ScrollingDirection.Y,
			ScrollBarThickness = 6,
			ScrollBarImageColor3 = t.borderStrong,
			VerticalScrollBarInset = Enum.ScrollBarInset.ScrollBar,
			Parent = body,
		})
	end
	self.libraryPage = page()
	self.editPage = page()

	-- Status bar
	local status = C.new("Frame", {
		BackgroundColor3 = t.card,
		BorderSizePixel = 0,
		AnchorPoint = Vector2.new(0, 1),
		Position = UDim2.new(0, 0, 1, 0),
		Size = UDim2.new(1, 0, 0, STATUS_H),
		Parent = frame,
	}, { C.padding(0, 12) })
	C.new("Frame", {
		BackgroundColor3 = t.border,
		BorderSizePixel = 0,
		Position = UDim2.new(0, -12, 0, 0),
		Size = UDim2.new(1, 24, 0, 1),
		Parent = status,
	})
	self.statusDot = C.new("Frame", {
		AnchorPoint = Vector2.new(0, 0.5),
		Position = UDim2.new(0, 0, 0.5, 0),
		Size = UDim2.new(0, 8, 0, 8),
		Parent = status,
	}, { C.round() })
	self.statusText = C.new("TextLabel", {
		BackgroundTransparency = 1,
		TextColor3 = t.mutedFg,
		TextSize = Theme.Text.caption,
		FontFace = Theme.Font.medium,
		TextXAlignment = Enum.TextXAlignment.Left,
		TextTruncate = Enum.TextTruncate.AtEnd,
		Position = UDim2.new(0, 16, 0, 0),
		Size = UDim2.new(1, -16, 1, 0),
		Parent = status,
	})

	-- Toast
	self.toast = C.new("Frame", {
		BackgroundColor3 = t.fg,
		AnchorPoint = Vector2.new(0.5, 1),
		Position = UDim2.new(0.5, 0, 1, -(STATUS_H + 10)),
		Size = UDim2.new(1, -24, 0, 0),
		AutomaticSize = Enum.AutomaticSize.Y,
		Visible = false,
		ZIndex = 20,
		Parent = frame,
	}, { C.corner(Theme.Radius.md), C.padding(10, 12) })
	self.toastText = C.text(t, { text = "", size = Theme.Text.label, font = Theme.Font.medium, color = t.bg })
	self.toastText.ZIndex = 21
	self.toastText.Parent = self.toast

	self.overlay = C.new("Frame", {
		BackgroundColor3 = t.overlay,
		BackgroundTransparency = 0.35,
		BorderSizePixel = 0,
		Size = UDim2.fromScale(1, 1),
		Visible = false,
		Active = true,
		ZIndex = 30,
		Parent = frame,
	})

	self:renderLibrary()
	self:renderEdit()
	self:setTab(self.state.tab)
	self:renderStatus()
	self:renderOverlay()
end

function App:setTab(id: string)
	self.state.tab = id
	local t = self.t
	for tabId, parts in self.tabButtons do
		local active = tabId == id
		parts.button.TextColor3 = if active then t.fg else t.mutedFg
		parts.underline.BackgroundColor3 = t.accent
		parts.underline.Visible = active
	end
	self.libraryPage.Visible = id == "library"
	self.editPage.Visible = id == "edit"
end

------------------------------------------------------------------------------------
-- Library tab
------------------------------------------------------------------------------------

local function matches(preset: Presets.Preset, query: string): boolean
	if query == "" then
		return true
	end
	query = query:lower()
	local hay = (preset.name.vi .. " " .. preset.name.en .. " " .. preset.desc.vi .. " " .. preset.desc.en .. " " .. preset.id):lower()
	for word in query:gmatch("%S+") do
		if not hay:find(word, 1, true) then
			return false
		end
	end
	return true
end

function App:renderLibrary()
	local t = self.t
	local api: Api = self.api
	local pageFrame: ScrollingFrame = self.libraryPage
	for _, child in pageFrame:GetChildren() do
		child:Destroy()
	end
	local content = C.stack({ Parent = pageFrame }, 12)
	C.padding(12, 12, 16, 12).Parent = content

	-- Search
	local _, searchBox = C.input(t, {
		label = self:L("searchLabel"),
		text = self.state.search,
		placeholder = self:L("searchPlaceholder"),
		order = 1,
	})
	searchBox.Parent.Parent = content
	searchBox:GetPropertyChangedSignal("Text"):Connect(function()
		self.state.search = searchBox.Text
		self:renderCards()
	end)

	-- Categories
	local chips = C.new("Frame", {
		BackgroundTransparency = 1,
		Size = UDim2.new(1, 0, 0, 0),
		AutomaticSize = Enum.AutomaticSize.Y,
		LayoutOrder = 2,
		Parent = content,
	})
	C.list(Enum.FillDirection.Horizontal, 6, true).Parent = chips
	for i, cat in Presets.Categories do
		C.chip(t, (cat :: any)[self.state.lang], self.state.category == cat.id, function()
			self.state.category = cat.id
			self:renderLibrary()
		end, i).Parent = chips
	end

	self:hdCard(content, 0)

	-- Favorites
	local favorites = api.loadFavorites()
	if #favorites > 0 then
		local favWrap = C.stack({ LayoutOrder = 3 }, 6)
		C.text(t, { text = self:L("favorites"):upper(), size = Theme.Text.caption, font = Theme.Font.bold, color = t.mutedFg, order = 1 }).Parent =
			favWrap
		local row = C.new("Frame", {
			BackgroundTransparency = 1,
			Size = UDim2.new(1, 0, 0, 0),
			AutomaticSize = Enum.AutomaticSize.Y,
			LayoutOrder = 2,
			Parent = favWrap,
		})
		C.list(Enum.FillDirection.Horizontal, 6, true).Parent = row
		for i, fav in favorites do
			local pill = C.new("Frame", {
				BackgroundColor3 = t.muted,
				Size = UDim2.new(0, 0, 0, 28),
				AutomaticSize = Enum.AutomaticSize.X,
				LayoutOrder = i,
				Parent = row,
			}, { C.round(), C.list(Enum.FillDirection.Horizontal, 0) })
			local swatch = C.new("Frame", { Size = UDim2.new(0, 28, 0, 28), BackgroundTransparency = 1, LayoutOrder = 0, Parent = pill })
			C.new("Frame", {
				AnchorPoint = Vector2.new(0.5, 0.5),
				Position = UDim2.fromScale(0.5, 0.5),
				Size = UDim2.new(0, 14, 0, 14),
				BackgroundColor3 = fav.params.color1,
				Parent = swatch,
			}, { C.round() })
			local nameButton = C.new("TextButton", {
				AutoButtonColor = false,
				BackgroundTransparency = 1,
				Text = fav.name,
				TextColor3 = t.fg,
				TextSize = Theme.Text.caption,
				FontFace = Theme.Font.semibold,
				Size = UDim2.new(0, 0, 1, 0),
				AutomaticSize = Enum.AutomaticSize.X,
				LayoutOrder = 1,
				Parent = pill,
			})
			nameButton.Activated:Connect(function()
				api.insert(fav.params.preset, fav.params)
			end)
			local remove = C.new("TextButton", {
				AutoButtonColor = false,
				BackgroundTransparency = 1,
				Text = "×",
				TextColor3 = t.mutedFg,
				TextSize = Theme.Text.body,
				FontFace = Theme.Font.bold,
				Size = UDim2.new(0, 26, 1, 0),
				LayoutOrder = 2,
				Parent = pill,
			})
			remove.Activated:Connect(function()
				table.remove(favorites, i)
				api.saveFavorites(favorites)
				self:renderLibrary()
			end)
		end
		favWrap.Parent = content
	end

	-- Cards
	local grid = C.new("Frame", {
		BackgroundTransparency = 1,
		Size = UDim2.new(1, 0, 0, 0),
		AutomaticSize = Enum.AutomaticSize.Y,
		LayoutOrder = 4,
		Parent = content,
	})
	local layout = C.new("UIGridLayout", {
		CellPadding = UDim2.new(0, 8, 0, 8),
		CellSize = UDim2.new(0.5, -4, 0, 118),
		SortOrder = Enum.SortOrder.LayoutOrder,
		Parent = grid,
	})
	local function fit()
		local _, size = C.abs(grid)
		local oneColumn = size.X > 0 and size.X < 280
		layout.CellSize = if oneColumn then UDim2.new(1, 0, 0, 110) else UDim2.new(0.5, -4, 0, 118)
	end
	grid:GetPropertyChangedSignal("AbsoluteSize"):Connect(fit)
	fit()
	self.grid = grid
	self.emptyNote = C.text(t, { text = self:L("noResults"), size = Theme.Text.label, color = t.mutedFg, order = 5 })
	self.emptyNote.Visible = false
	self.emptyNote.Parent = content
	self:renderCards()
end

-- "HD quality" card: how to import the Blender pack, scan it, or paste IDs.
function App:hdCard(parent: Instance, order: number)
	local t = self.t
	local api: Api = self.api
	local count = api.countAssets()
	local on = api.getAssets() ~= nil
	local card = C.stack({ LayoutOrder = order, BackgroundColor3 = t.card, BackgroundTransparency = 0 }, 10)
	C.corner(Theme.Radius.lg).Parent = card
	C.stroke(if on then t.accent else t.border, 1).Parent = card
	C.padding(12).Parent = card
	local head = C.new("Frame", { BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 22), LayoutOrder = 1, Parent = card })
	C.new("TextLabel", {
		BackgroundTransparency = 1,
		Text = self:L("hdTitle"),
		TextColor3 = t.fg,
		TextSize = Theme.Text.label,
		FontFace = Theme.Font.bold,
		TextXAlignment = Enum.TextXAlignment.Left,
		Size = UDim2.new(1, -56, 1, 0),
		TextTruncate = Enum.TextTruncate.AtEnd,
		Parent = head,
	})
	C.new("TextLabel", {
		BackgroundColor3 = if on then t.accent else t.muted,
		Text = if on then "HD" else "BASIC",
		TextColor3 = if on then t.onAccent else t.mutedFg,
		TextSize = Theme.Text.caption,
		FontFace = Theme.Font.bold,
		AnchorPoint = Vector2.new(1, 0.5),
		Position = UDim2.new(1, 0, 0.5, 0),
		Size = UDim2.new(0, 0, 0, 20),
		AutomaticSize = Enum.AutomaticSize.X,
		Parent = head,
	}, { C.round(), C.padding(0, 8) })
	C.text(t, {
		text = if on then self:L("hdBodyOn"):format(count) else self:L("hdBodyOff"),
		size = Theme.Text.caption,
		color = t.mutedFg,
		order = 2,
	}).Parent = card

	local row = C.new("Frame", { BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 30), LayoutOrder = 3, Parent = card })
	C.new("UIListLayout", {
		FillDirection = Enum.FillDirection.Horizontal,
		Padding = UDim.new(0, 6),
		SortOrder = Enum.SortOrder.LayoutOrder,
		Parent = row,
	})
	local function toastApplied()
		local n = api.applyAll()
		self:toastMessage(self:L("hdApplied"):format(n), "success")
		self:renderEdit()
	end
	if on then
		C.button(t, { text = self:L("hdApplyAll"), variant = "primary", width = UDim.new(0.6, -3), height = 30, order = 1, onClick = toastApplied }).Parent =
			row
		C.button(t, {
			text = self:L("hdDisable"),
			width = UDim.new(0.4, -3),
			height = 30,
			order = 2,
			onClick = function()
				api.disableHD()
				self:toastMessage(self:L("hdDisabled"), "success")
				self:renderLibrary()
			end,
		}).Parent = row
	else
		C.button(t, {
			text = self:L("hdScan"),
			variant = "primary",
			width = UDim.new(0.5, -3),
			height = 30,
			order = 1,
			onClick = function()
				local n = api.scanAssets()
				if n == 0 then
					self:toastMessage(self:L("hdScanNone"), "error")
				elseif api.getAssets() == nil then
					self:toastMessage(self:L("hdMissing"), "error")
				else
					self:toastMessage(self:L("hdScanFound"):format(n), "success")
					api.applyAll()
				end
				self:renderLibrary()
			end,
		}).Parent = row
		C.button(t, {
			text = self:L("hdPaste"),
			width = UDim.new(0.5, -3),
			height = 30,
			order = 2,
			onClick = function()
				self.state.pasteOpen = not self.state.pasteOpen
				self:renderLibrary()
			end,
		}).Parent = row
	end
	if self.state.pasteOpen and not on then
		local wrap, box = C.input(t, {
			label = self:L("hdPasteLabel"),
			text = "",
			placeholder = self:L("hdPastePlaceholder"),
			order = 4,
			mono = true,
		})
		box.MultiLine = true
		box.TextWrapped = true
		box.TextYAlignment = Enum.TextYAlignment.Top
		box.Size = UDim2.new(1, 0, 0, 110)
		C.padding(8, 10).Parent = box
		wrap.Parent = card
		C.button(t, {
			text = self:L("hdSave"),
			variant = "primary",
			order = 5,
			height = 30,
			onClick = function()
				local n = api.assetsFromText(box.Text)
				if api.getAssets() == nil then
					self:toastMessage(self:L("hdMissing"), "error")
				else
					self.state.pasteOpen = false
					self:toastMessage(self:L("hdScanFound"):format(n), "success")
					api.applyAll()
				end
				self:renderLibrary()
			end,
		}).Parent = card
	end
	card.Parent = parent
end

function App:card(preset: Presets.Preset, order: number): TextButton
	local t = self.t
	local api: Api = self.api
	local d = preset.defaults
	local b = C.new("TextButton", {
		AutoButtonColor = false,
		BackgroundColor3 = t.card,
		Text = "",
		LayoutOrder = order,
	}, { C.corner(Theme.Radius.lg) })
	local stroke = C.stroke(t.border, 1)
	stroke.Parent = b

	local strip = C.new("Frame", {
		BackgroundColor3 = Color3.new(1, 1, 1),
		Position = UDim2.new(0, 6, 0, 6),
		Size = UDim2.new(1, -12, 0, 46),
		ClipsDescendants = true,
		Parent = b,
	}, { C.corner(Theme.Radius.md) })
	C.new("UIGradient", {
		Color = ColorSequence.new({
			ColorSequenceKeypoint.new(0, (d.color1 :: Color3):Lerp(Color3.new(0, 0, 0), 0.55)),
			ColorSequenceKeypoint.new(0.55, d.color1),
			ColorSequenceKeypoint.new(1, d.color2),
		}),
		Rotation = 20,
		Parent = strip,
	})
	-- tiny glyph: a ring for one-shot effects, rising dots for looping ones
	if preset.kind == "burst" then
		local ring = C.new("Frame", {
			BackgroundTransparency = 1,
			AnchorPoint = Vector2.new(0.5, 0.5),
			Position = UDim2.new(0, 26, 0.5, 0),
			Size = UDim2.new(0, 26, 0, 26),
			Parent = strip,
		}, { C.round() })
		C.stroke(Color3.new(1, 1, 1), 2, 0.1).Parent = ring
		C.new("Frame", {
			BackgroundColor3 = Color3.new(1, 1, 1),
			AnchorPoint = Vector2.new(0.5, 0.5),
			Position = UDim2.fromScale(0.5, 0.5),
			Size = UDim2.new(0, 8, 0, 8),
			Parent = ring,
		}, { C.round() })
	else
		for i = 1, 3 do
			C.new("Frame", {
				BackgroundColor3 = Color3.new(1, 1, 1),
				BackgroundTransparency = 0.1 * i,
				AnchorPoint = Vector2.new(0.5, 0.5),
				Position = UDim2.new(0, 10 + i * 8, 0.5, 10 - i * 7),
				Size = UDim2.new(0, 10 - i * 2, 0, 10 - i * 2),
				Parent = strip,
			}, { C.round() })
		end
	end
	local badge = C.new("TextLabel", {
		BackgroundColor3 = Color3.new(0, 0, 0),
		BackgroundTransparency = 0.45,
		Text = self:L(if preset.kind == "burst" then "badgeBurst" else "badgeLoop"),
		TextColor3 = Color3.new(1, 1, 1),
		TextSize = Theme.Text.caption,
		FontFace = Theme.Font.semibold,
		AnchorPoint = Vector2.new(1, 0),
		Position = UDim2.new(1, -6, 0, 6),
		Size = UDim2.new(0, 0, 0, 20),
		AutomaticSize = Enum.AutomaticSize.X,
		Parent = strip,
	}, { C.round(), C.padding(0, 8) })
	badge.ZIndex = 2

	local name = C.new("TextLabel", {
		BackgroundTransparency = 1,
		Text = (preset.name :: any)[self.state.lang],
		TextColor3 = t.fg,
		TextSize = Theme.Text.body,
		FontFace = Theme.Font.semibold,
		TextXAlignment = Enum.TextXAlignment.Left,
		TextTruncate = Enum.TextTruncate.AtEnd,
		Position = UDim2.new(0, 10, 0, 58),
		Size = UDim2.new(1, -20, 0, 18),
		Parent = b,
	})
	C.new("TextLabel", {
		BackgroundTransparency = 1,
		Text = (preset.desc :: any)[self.state.lang],
		TextColor3 = t.mutedFg,
		TextSize = Theme.Text.caption,
		FontFace = Theme.Font.regular,
		TextXAlignment = Enum.TextXAlignment.Left,
		TextYAlignment = Enum.TextYAlignment.Top,
		TextWrapped = true,
		TextTruncate = Enum.TextTruncate.AtEnd,
		Position = UDim2.new(0, 10, 0, 78),
		Size = UDim2.new(1, -20, 1, -84),
		Parent = b,
	})
	b.MouseEnter:Connect(function()
		C.tween(stroke, { Color = t.accent })
		C.tween(b, { BackgroundColor3 = t.muted })
	end)
	b.MouseLeave:Connect(function()
		C.tween(stroke, { Color = t.border })
		C.tween(b, { BackgroundColor3 = t.card })
	end)
	b.Activated:Connect(function()
		api.insert(preset.id, nil)
	end)
	local _ = name
	return b
end

function App:renderCards()
	local grid: Frame = self.grid
	for _, child in grid:GetChildren() do
		if child:IsA("GuiObject") then
			child:Destroy()
		end
	end
	local shown = 0
	for i, preset in Presets.List do
		local p = preset :: any
		if (self.state.category == "all" or p.category == self.state.category) and matches(p, self.state.search) then
			self:card(p, i).Parent = grid
			shown += 1
		end
	end
	self.emptyNote.Visible = shown == 0
end

------------------------------------------------------------------------------------
-- Customize tab
------------------------------------------------------------------------------------

local function luaPath(inst: Instance): string
	local parts = {}
	local current: Instance? = inst
	while current and current.Parent and current ~= game do
		table.insert(parts, 1, current.Name)
		current = current.Parent
	end
	local out = "workspace"
	if parts[1] ~= "Workspace" then
		out = "game"
	else
		table.remove(parts, 1)
	end
	for _, name in parts do
		if name:match("^[%a_][%w_]*$") then
			out ..= "." .. name
		else
			out ..= '["' .. name:gsub('"', '\\"') .. '"]'
		end
	end
	return out
end

function App:renderEdit()
	local t = self.t
	local api: Api = self.api
	local pageFrame: ScrollingFrame = self.editPage
	local scroll = pageFrame.CanvasPosition
	for _, child in pageFrame:GetChildren() do
		child:Destroy()
	end
	local content = C.stack({ Parent = pageFrame }, 16)
	C.padding(12, 12, 16, 12).Parent = content

	local root = self.state.root
	local params = if root and root.Parent then Builder.readParams(root) else nil
	if not root or not params then
		local empty = C.stack({ LayoutOrder = 1 }, 8)
		C.padding(24, 8).Parent = empty
		C.text(t, { text = self:L("emptyTitle"), size = Theme.Text.title, font = Theme.Font.bold, align = Enum.TextXAlignment.Center, order = 1 }).Parent =
			empty
		C.text(t, { text = self:L("emptyBody"), size = Theme.Text.label, color = t.mutedFg, align = Enum.TextXAlignment.Center, order = 2 }).Parent =
			empty
		local holder = C.new("Frame", { BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 44), LayoutOrder = 3, Parent = empty })
		local b = C.button(t, {
			text = self:L("emptyAction"),
			variant = "primary",
			width = UDim.new(0, 160),
			onClick = function()
				self:setTab("library")
			end,
		})
		b.AnchorPoint = Vector2.new(0.5, 1)
		b.Position = UDim2.new(0.5, 0, 1, 0)
		b.Parent = holder
		empty.Parent = content
		return
	end
	assert(root)
	local p: Params = params
	local preset = Presets.ById[p.preset]
	local slider: C.SliderCtx = { widget = api.widget, root = self.frame }

	local function apply(final: boolean)
		api.apply(root, p, final)
	end
	local function edit(name: string)
		return function()
			api.beginEdit(name)
		end
	end

	-- Effect header
	local headCard = C.stack({ LayoutOrder = 1, BackgroundColor3 = t.card, BackgroundTransparency = 0 }, 10)
	C.corner(Theme.Radius.lg).Parent = headCard
	C.stroke(t.border, 1).Parent = headCard
	C.padding(12).Parent = headCard
	C.text(t, { text = (preset.name :: any)[self.state.lang], size = Theme.Text.title, font = Theme.Font.bold, order = 1 }).Parent =
		headCard
	local nameWrap = C.input(t, {
		label = self:L("nameLabel"),
		text = root.Name,
		order = 2,
		onCommit = function(text)
			if text ~= "" and text ~= root.Name then
				api.rename(root, text)
			end
		end,
	})
	nameWrap.Parent = headCard
	local row = C.new("Frame", { BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 32), LayoutOrder = 3, Parent = headCard })
	C.new("UIListLayout", {
		FillDirection = Enum.FillDirection.Horizontal,
		Padding = UDim.new(0, 6),
		SortOrder = Enum.SortOrder.LayoutOrder,
		Parent = row,
	})
	C.button(t, {
		text = self:L("play"),
		variant = "primary",
		width = UDim.new(0.44, -4),
		order = 1,
		onClick = function()
			api.preview(root)
		end,
	}).Parent = row
	C.button(t, {
		text = self:L("duplicate"),
		width = UDim.new(0.28, -4),
		order = 2,
		onClick = function()
			api.duplicate(root)
		end,
	}).Parent = row
	local armed = false
	local deleteButton: TextButton
	deleteButton = C.button(t, {
		text = self:L("delete"),
		variant = "danger",
		width = UDim.new(0.28, -4),
		order = 3,
		onClick = function()
			if armed then
				api.delete(root)
				return
			end
			armed = true
			deleteButton.Text = self:L("deleteConfirm")
			deleteButton.BackgroundColor3 = t.danger
			deleteButton.TextColor3 = t.onDanger
			task.delay(3, function()
				if armed and C.alive(deleteButton) then
					armed = false
					deleteButton.Text = self:L("delete")
					deleteButton.BackgroundColor3 = t.card
					deleteButton.TextColor3 = t.danger
				end
			end)
		end,
	})
	deleteButton.Parent = row
	C.toggle(t, self:L("autoPreview"), self.state.autoPreview, function(on)
		self.state.autoPreview = on
		api.setSetting("EasyVFX_AutoPreview", on)
		self:restartPreview()
	end, 4).Parent = headCard
	headCard.Parent = content

	-- Colors
	local colorOuter, colors = C.section(t, self:L("sectionColor"), 2)
	local function invalid()
		self:toastMessage(self:L("hexInvalid"), "error")
	end
	C.colorPicker(t, self:L("color1"), self:L("hexLabel"), p.color1, function(color)
		api.beginEdit("Color")
		p.color1 = color
		apply(true)
	end, invalid, 1).Parent = colors
	C.colorPicker(t, self:L("color2"), self:L("hexLabel"), p.color2, function(color)
		api.beginEdit("Color")
		p.color2 = color
		apply(true)
	end, invalid, 2).Parent = colors
	colorOuter.Parent = content

	-- Look
	local lookOuter, look = C.section(t, self:L("sectionLook"), 3)
	local sliders = {
		{ key = "size", label = "size", hint = "sizeHint", min = 0.2, max = 4, step = 0.05 },
		{ key = "amount", label = "amount", hint = "amountHint", min = 0.1, max = 4, step = 0.05 },
		{ key = "speed", label = "speed", hint = "speedHint", min = 0.2, max = 3, step = 0.05 },
		{ key = "lifetime", label = "lifetime", hint = "lifetimeHint", min = 0.2, max = 3, step = 0.05 },
		{ key = "glow", label = "glow", hint = "glowHint", min = 0, max = 2, step = 0.05 },
	}
	for i, s in sliders do
		C.slider(t, slider, {
			label = self:L(s.label),
			hint = self:L(s.hint),
			min = s.min,
			max = s.max,
			step = s.step,
			value = (p :: any)[s.key],
			suffix = "x",
			order = i,
			onBegin = edit(self:L(s.label)),
			onChange = function(v, final)
				(p :: any)[s.key] = v
				apply(final)
			end,
		}).Parent = look
	end
	if api.getAssets() ~= nil and Builder.hasHD(p.preset) then
		C.slider(t, slider, {
			label = self:L("rotation"),
			hint = self:L("rotationHint"),
			min = 0,
			max = 360,
			step = 5,
			value = p.rotation,
			suffix = "°",
			order = #sliders + 1,
			onBegin = edit(self:L("rotation")),
			onChange = function(v, final)
				p.rotation = v
				apply(final)
			end,
		}).Parent = look
	end
	lookOuter.Parent = content

	-- Trigger
	local trigOuter, trig = C.section(t, self:L("sectionTrigger"), 4)
	local trigText = {
		Always = { "trigAlways", "trigAlwaysHint" },
		Loop = { "trigLoop", "trigLoopHint" },
		Touch = { "trigTouch", "trigTouchHint" },
		Click = { "trigClick", "trigClickHint" },
		Prompt = { "trigPrompt", "trigPromptHint" },
		Script = { "trigScript", "trigScriptHint" },
	}
	local radios = C.stack({ LayoutOrder = 1 }, 6)
	for i, id in Builder.Triggers do
		local texts = trigText[id]
		C.radio(t, self:L(texts[1]), self:L(texts[2]), p.trigger == id, function()
			if p.trigger == id then
				return
			end
			api.beginEdit("Trigger")
			p.trigger = id
			apply(true)
			self:renderEdit()
		end, i).Parent = radios
	end
	radios.Parent = trig
	local extras = C.stack({ LayoutOrder = 2 }, 12)
	local function numberSlider(key: string, labelKey: string, min: number, max: number, step: number, order: number)
		C.slider(t, slider, {
			label = self:L(labelKey),
			min = min,
			max = max,
			step = step,
			value = (p :: any)[key],
			suffix = "s",
			order = order,
			onBegin = edit(self:L(labelKey)),
			onChange = function(v, final)
				(p :: any)[key] = v
				apply(final)
			end,
		}).Parent = extras
	end
	local hasBursts = api.hasBursts(root)
	if p.trigger == "Loop" or (p.trigger == "Always" and hasBursts) then
		numberSlider("interval", "interval", 0.2, 10, 0.1, 1)
	end
	if p.trigger == "Touch" or p.trigger == "Click" or p.trigger == "Prompt" then
		numberSlider("cooldown", "cooldown", 0, 10, 0.1, 2)
	end
	if p.trigger ~= "Always" and preset.kind == "loop" then
		numberSlider("duration", "duration", 0.1, 20, 0.1, 3)
	end
	if p.trigger == "Prompt" then
		local wrap = C.input(t, {
			label = self:L("promptText"),
			text = p.promptText,
			order = 4,
			onCommit = function(text)
				if text ~= p.promptText then
					api.beginEdit("Prompt text")
					p.promptText = text
					apply(true)
				end
			end,
		})
		wrap.Parent = extras
	end
	if p.trigger == "Script" then
		local wrap = C.input(t, {
			label = self:L("scriptSnippetLabel"),
			text = ("require(game.ReplicatedStorage.EasyVFX).Play(%s)"):format(luaPath(root)),
			mono = true,
			readOnly = true,
			order = 5,
		})
		wrap.Parent = extras
	end
	extras.Parent = trig
	trigOuter.Parent = content

	-- Advanced (collapsed by default: progressive disclosure)
	local adv = C.stack({ LayoutOrder = 5 }, 8)
	C.button(t, {
		text = (if self.state.advancedOpen then "−  " else "+  ") .. self:L("sectionAdvanced"),
		variant = "ghost",
		order = 1,
		onClick = function()
			self.state.advancedOpen = not self.state.advancedOpen
			self:renderEdit()
		end,
	}).Parent = adv
	if self.state.advancedOpen then
		local box = C.stack({ LayoutOrder = 2, BackgroundColor3 = t.card, BackgroundTransparency = 0 }, 12)
		C.corner(Theme.Radius.lg).Parent = box
		C.stroke(t.border, 1).Parent = box
		C.padding(12).Parent = box
		local texWrap = C.input(t, {
			label = self:L("textureLabel"),
			text = (p.texture:gsub("^rbxassetid://", "")),
			placeholder = self:L("texturePlaceholder"),
			hint = self:L("textureHint"),
			order = 1,
			onCommit = function(text)
				local cleaned = text:gsub("%s", "")
				local id = cleaned:match("(%d+)")
				local value = if cleaned == "" then "" elseif cleaned:match("^rbxasset") then cleaned elseif id then "rbxassetid://" .. id else nil
				if value == nil then
					self:toastMessage(self:L("texturePlaceholder"), "error")
					return
				end
				if value ~= p.texture then
					api.beginEdit("Texture")
					p.texture = value
					apply(true)
				end
			end,
		})
		texWrap.Parent = box
		C.button(t, {
			text = self:L("bloom"),
			order = 2,
			onClick = function()
				local added = api.addBloom()
				self:toastMessage(self:L(if added then "bloomDone" else "bloomExists"), "success")
			end,
		}).Parent = box
		C.text(t, { text = self:L("bloomTip"), size = Theme.Text.caption, color = t.mutedFg, order = 3 }).Parent = box
		C.button(t, {
			text = self:L("saveFavorite"),
			order = 4,
			onClick = function()
				local favorites = api.loadFavorites()
				table.insert(favorites, 1, { name = root.Name, params = table.clone(p) })
				while #favorites > 12 do
					table.remove(favorites)
				end
				api.saveFavorites(favorites)
				self:renderLibrary()
				self:toastMessage(self:L("saved"):format(root.Name), "success")
			end,
		}).Parent = box
		C.button(t, {
			text = self:L("reset"),
			variant = "danger",
			order = 5,
			onClick = function()
				api.beginEdit("Reset")
				local fresh = Builder.defaultParams(p.preset)
				api.apply(root, fresh, true)
				self:renderEdit()
				self:toastMessage(self:L("resetDone"), "success")
			end,
		}).Parent = box
		box.Parent = adv
	end
	adv.Parent = content

	task.defer(function()
		if C.alive(pageFrame) then -- the page may have been rebuilt meanwhile
			pageFrame.CanvasPosition = scroll
		end
	end)
end

------------------------------------------------------------------------------------
-- Selection, preview, status
------------------------------------------------------------------------------------

function App:watchRoot(root: Instance?)
	for _, c in self.rootConnections do
		c:Disconnect()
	end
	table.clear(self.rootConnections)
	if root then
		table.insert(
			self.rootConnections,
			root.AncestryChanged:Connect(function()
				if not root.Parent then
					self:setSelection(self.api.selectionInfo())
				end
			end)
		)
	end
end

function App:setSelection(info: SelectionInfo)
	self.state.selection = info
	local newRoot = if info.kind == "effect" then info.root else nil
	if newRoot ~= self.state.root then
		self.state.root = newRoot
		self:watchRoot(newRoot)
		self:renderEdit()
		if newRoot then
			self:setTab("edit")
		end
		self:restartPreview()
	end
	self:renderStatus()
end

function App:refresh()
	self:renderEdit()
	self:renderStatus()
end

function App:renderStatus()
	local t = self.t
	local info: SelectionInfo = self.state.selection
	if info.kind == "effect" then
		self.statusText.Text = self:L("targetEffect"):format(info.name)
		self.statusDot.BackgroundColor3 = t.accent
	elseif info.kind == "part" then
		self.statusText.Text = self:L("targetSome"):format(info.name)
		self.statusDot.BackgroundColor3 = t.accent
	else
		self.statusText.Text = self:L("targetNone")
		self.statusDot.BackgroundColor3 = t.mutedFg
	end
end

-- Replays the selected one-shot effect in a loop while it is selected.
function App:restartPreview()
	self.previewToken += 1
	local token = self.previewToken
	local root = self.state.root
	local api: Api = self.api
	if not (root and self.state.autoPreview and api.hasBursts(root)) then
		return
	end
	task.spawn(function()
		task.wait(0.15)
		while token == self.previewToken and C.alive(root) and api.widget.Enabled do
			local length = api.preview(root)
			local interval = root:GetAttribute("VFX_Interval")
			task.wait(math.max(1, length + 0.4, if type(interval) == "number" then interval else 0))
		end
	end)
end

function App:toastMessage(text: string, kind: string?)
	local t = self.t
	self.toastToken += 1
	local token = self.toastToken
	self.toast.BackgroundColor3 = if kind == "error" then t.danger else t.fg
	self.toastText.TextColor3 = if kind == "error" then t.onDanger else t.bg
	self.toastText.Text = text
	self.toast.Visible = true
	task.delay(3.2, function()
		if token == self.toastToken and C.alive(self.toast) then
			self.toast.Visible = false
		end
	end)
end

------------------------------------------------------------------------------------
-- Overlays: first-run guide and help
------------------------------------------------------------------------------------

function App:renderOverlay()
	local t = self.t
	local api: Api = self.api
	local overlay: Frame = self.overlay
	for _, child in overlay:GetChildren() do
		child:Destroy()
	end
	local step = self.state.onboardStep
	if not step and not self.state.helpOpen then
		overlay.Visible = false
		return
	end
	overlay.Visible = true
	local card = C.stack({
		AnchorPoint = Vector2.new(0.5, 0.5),
		Position = UDim2.fromScale(0.5, 0.5),
		Size = UDim2.new(1, -32, 0, 0),
		BackgroundColor3 = t.card,
		BackgroundTransparency = 0,
		ZIndex = 31,
		Parent = overlay,
	}, 12)
	C.corner(Theme.Radius.lg).Parent = card
	C.stroke(t.borderStrong, 1).Parent = card
	C.padding(16).Parent = card
	local constraint = C.new("UISizeConstraint", { MaxSize = Vector2.new(420, math.huge), Parent = card })
	local _ = constraint

	local function finishOnboarding()
		self.state.onboardStep = nil
		api.setSetting("EasyVFX_Onboarded", true)
		self:renderOverlay()
	end

	local buttons = C.new("Frame", { BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 32), LayoutOrder = 10 })
	C.new("UIListLayout", {
		FillDirection = Enum.FillDirection.Horizontal,
		HorizontalAlignment = Enum.HorizontalAlignment.Right,
		Padding = UDim.new(0, 6),
		SortOrder = Enum.SortOrder.LayoutOrder,
		Parent = buttons,
	})

	if step then
		local dots = C.new("Frame", { BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 8), LayoutOrder = 1, Parent = card })
		C.list(Enum.FillDirection.Horizontal, 6).Parent = dots
		for i = 1, 3 do
			C.new("Frame", {
				BackgroundColor3 = if i == step then t.accent else t.borderStrong,
				Size = UDim2.new(0, if i == step then 20 else 8, 0, 8),
				LayoutOrder = i,
				Parent = dots,
			}, { C.round() })
		end
		C.text(t, { text = self:L("onboard" .. step .. "Title"), size = Theme.Text.title, font = Theme.Font.bold, order = 2 }).Parent =
			card
		C.text(t, { text = self:L("onboard" .. step .. "Body"), size = Theme.Text.body, color = t.mutedFg, order = 3 }).Parent =
			card
		C.button(t, { text = self:L("onboardSkip"), variant = "ghost", width = UDim.new(0, 80), order = 1, onClick = finishOnboarding }).Parent =
			buttons
		if step > 1 then
			C.button(t, {
				text = self:L("onboardBack"),
				width = UDim.new(0, 80),
				order = 2,
				onClick = function()
					self.state.onboardStep = step - 1
					self:renderOverlay()
				end,
			}).Parent = buttons
		end
		C.button(t, {
			text = self:L(if step == 3 then "onboardDone" else "onboardNext"),
			variant = "primary",
			width = UDim.new(0, 96),
			order = 3,
			onClick = function()
				if step >= 3 then
					finishOnboarding()
					self:setTab("library")
				else
					self.state.onboardStep = step + 1
					self:renderOverlay()
				end
			end,
		}).Parent = buttons
	else
		C.text(t, { text = self:L("helpTitle"), size = Theme.Text.title, font = Theme.Font.bold, order = 1 }).Parent = card
		C.text(t, { text = self:L("helpBody"), size = Theme.Text.label, color = t.mutedFg, order = 2 }).Parent = card
		C.button(t, {
			text = self:L("bloom"),
			width = UDim.new(1, 0),
			order = 3,
			onClick = function()
				local added = api.addBloom()
				self:toastMessage(self:L(if added then "bloomDone" else "bloomExists"), "success")
			end,
		}).Parent = card
		C.button(t, {
			text = self:L("replayGuide"),
			variant = "ghost",
			width = UDim.new(0, 150),
			order = 1,
			onClick = function()
				self.state.helpOpen = false
				self.state.onboardStep = 1
				self:renderOverlay()
			end,
		}).Parent = buttons
		C.button(t, {
			text = self:L("close"),
			variant = "primary",
			width = UDim.new(0, 90),
			order = 2,
			onClick = function()
				self.state.helpOpen = false
				self:renderOverlay()
			end,
		}).Parent = buttons
	end
	buttons.Parent = card
end

function App:destroy()
	self.previewToken += 1
	self:watchRoot(nil)
	if self.frame then
		self.frame:Destroy()
	end
end

return App
