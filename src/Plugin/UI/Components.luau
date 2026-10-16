--!strict
--[[
	Small UI kit for the plugin. Every builder takes the theme tokens `t` first.
	Kept deliberately plain: clear labels, visible hover/focus states, 150 ms
	transitions, no icon-only buttons.
]]

local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local Theme = require(script.Parent.Theme)

type Tokens = Theme.Tokens

local C = {}

local FAST = TweenInfo.new(Theme.Motion.fast, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)

function C.new(className: string, props: { [string]: any }?, children: { any }?): any
	local inst = Instance.new(className) :: any
	local parent = nil
	if props then
		for key, value in props do
			if key == "Parent" then
				parent = value
			else
				inst[key] = value
			end
		end
	end
	if children then
		for _, child in children do
			child.Parent = inst
		end
	end
	if parent then
		inst.Parent = parent
	end
	return inst
end

-- True while the object is still in a tree (safe to call on destroyed objects).
function C.alive(inst: Instance?): boolean
	if not inst then
		return false
	end
	local ok, parent = pcall(function()
		return inst.Parent
	end)
	return ok and parent ~= nil
end

-- AbsolutePosition / AbsoluteSize, or zeros before the object is laid out.
function C.abs(gui: GuiObject): (Vector2, Vector2)
	local ok, pos, size = pcall(function()
		return gui.AbsolutePosition, gui.AbsoluteSize
	end)
	if ok then
		return pos, size
	end
	return Vector2.zero, Vector2.zero
end

function C.tween(inst: Instance, goal: { [string]: any })
	TweenService:Create(inst, FAST, goal):Play()
end

function C.corner(radius: number): any
	return C.new("UICorner", { CornerRadius = UDim.new(0, radius) })
end

function C.round(): any
	return C.new("UICorner", { CornerRadius = UDim.new(1, 0) })
end

function C.stroke(color: Color3, thickness: number?, transparency: number?): any
	return C.new("UIStroke", {
		Color = color,
		Thickness = thickness or 1,
		Transparency = transparency or 0,
		ApplyStrokeMode = Enum.ApplyStrokeMode.Border,
	})
end

function C.padding(top: number, right: number?, bottom: number?, left: number?): any
	return C.new("UIPadding", {
		PaddingTop = UDim.new(0, top),
		PaddingRight = UDim.new(0, right or top),
		PaddingBottom = UDim.new(0, bottom or top),
		PaddingLeft = UDim.new(0, left or right or top),
	})
end

function C.list(direction: Enum.FillDirection?, padding: number?, wraps: boolean?): any
	return C.new("UIListLayout", {
		FillDirection = direction or Enum.FillDirection.Vertical,
		Padding = UDim.new(0, padding or 0),
		SortOrder = Enum.SortOrder.LayoutOrder,
		Wraps = wraps == true,
	})
end

-- Plain frame that grows with its content.
function C.stack(props: { [string]: any }?, gap: number?): Frame
	local f = C.new("Frame", {
		BackgroundTransparency = 1,
		Size = UDim2.new(1, 0, 0, 0),
		AutomaticSize = Enum.AutomaticSize.Y,
	})
	if props then
		for k, v in props do
			f[k] = v
		end
	end
	C.list(Enum.FillDirection.Vertical, gap or 0).Parent = f
	return f
end

type TextProps = {
	text: string,
	size: number?,
	font: Font?,
	color: Color3?,
	wrap: boolean?,
	align: Enum.TextXAlignment?,
	order: number?,
	height: number?,
	rich: boolean?,
}

function C.text(t: Tokens, p: TextProps): TextLabel
	local size = p.size or Theme.Text.body
	local label = C.new("TextLabel", {
		BackgroundTransparency = 1,
		Text = p.text,
		TextSize = size,
		FontFace = p.font or Theme.Font.regular,
		TextColor3 = p.color or t.fg,
		TextXAlignment = p.align or Enum.TextXAlignment.Left,
		TextYAlignment = Enum.TextYAlignment.Top,
		TextWrapped = p.wrap ~= false,
		RichText = p.rich == true,
		LayoutOrder = p.order or 0,
		Size = UDim2.new(1, 0, 0, p.height or 0),
		AutomaticSize = if p.height then Enum.AutomaticSize.None else Enum.AutomaticSize.Y,
		LineHeight = 1.15,
	})
	return label
end

export type ButtonProps = {
	text: string,
	variant: string?, -- primary | secondary | ghost | danger
	height: number?,
	width: UDim?,
	order: number?,
	onClick: (() -> ())?,
}

local function variantColors(t: Tokens, variant: string): (Color3, Color3, Color3, Color3?)
	if variant == "primary" then
		return t.accent, t.accentHover, t.onAccent, nil
	elseif variant == "danger" then
		return t.card, t.muted, t.danger, t.danger
	elseif variant == "ghost" then
		return t.bg, t.muted, t.fg, nil
	end
	return t.muted, t.hover, t.fg, t.border
end

function C.button(t: Tokens, p: ButtonProps): TextButton
	local variant = p.variant or "secondary"
	local bg, bgHover, fg, border = variantColors(t, variant)
	local b = C.new("TextButton", {
		AutoButtonColor = false,
		BackgroundColor3 = bg,
		BackgroundTransparency = if variant == "ghost" then 1 else 0,
		Text = p.text,
		TextColor3 = fg,
		TextSize = Theme.Text.label,
		FontFace = if variant == "primary" then Theme.Font.bold else Theme.Font.semibold,
		Size = UDim2.new(p.width or UDim.new(1, 0), UDim.new(0, p.height or 32)),
		LayoutOrder = p.order or 0,
		TextTruncate = Enum.TextTruncate.AtEnd,
	}, { C.corner(Theme.Radius.md), C.padding(0, 10) })
	if border then
		C.stroke(border, 1).Parent = b
	end
	b.MouseEnter:Connect(function()
		C.tween(b, { BackgroundColor3 = bgHover, BackgroundTransparency = 0 })
	end)
	b.MouseLeave:Connect(function()
		C.tween(b, { BackgroundColor3 = bg, BackgroundTransparency = if variant == "ghost" then 1 else 0 })
	end)
	if p.onClick then
		local onClick = p.onClick
		b.Activated:Connect(function()
			onClick()
		end)
	end
	return b
end

-- Pill-shaped toggle chip (categories).
function C.chip(t: Tokens, text: string, selected: boolean, onClick: () -> (), order: number?): TextButton
	local b = C.new("TextButton", {
		AutoButtonColor = false,
		BackgroundColor3 = if selected then t.fg else t.muted,
		Text = text,
		TextColor3 = if selected then t.bg else t.fg,
		TextSize = Theme.Text.caption,
		FontFace = Theme.Font.semibold,
		Size = UDim2.new(0, 0, 0, 28),
		AutomaticSize = Enum.AutomaticSize.X,
		LayoutOrder = order or 0,
	}, { C.round(), C.padding(0, 12) })
	if not selected then
		b.MouseEnter:Connect(function()
			C.tween(b, { BackgroundColor3 = t.hover })
		end)
		b.MouseLeave:Connect(function()
			C.tween(b, { BackgroundColor3 = t.muted })
		end)
	end
	b.Activated:Connect(onClick)
	return b
end

export type InputProps = {
	label: string?,
	text: string,
	placeholder: string?,
	hint: string?,
	mono: boolean?,
	order: number?,
	readOnly: boolean?,
	onCommit: ((text: string) -> ())?,
}

function C.input(t: Tokens, p: InputProps): (Frame, TextBox)
	local wrap = C.stack({ LayoutOrder = p.order or 0 }, 4)
	if p.label then
		C.text(t, { text = p.label, size = Theme.Text.caption, font = Theme.Font.semibold, color = t.mutedFg, order = 1 }).Parent =
			wrap
	end
	local box = C.new("TextBox", {
		BackgroundColor3 = t.card,
		Text = p.text,
		PlaceholderText = p.placeholder or "",
		PlaceholderColor3 = t.mutedFg,
		TextColor3 = t.fg,
		TextSize = Theme.Text.label,
		FontFace = if p.mono then Theme.Font.mono else Theme.Font.regular,
		TextXAlignment = Enum.TextXAlignment.Left,
		ClearTextOnFocus = false,
		TextEditable = not p.readOnly,
		TextTruncate = Enum.TextTruncate.AtEnd,
		Size = UDim2.new(1, 0, 0, 32),
		LayoutOrder = 2,
	}, { C.corner(Theme.Radius.md), C.padding(0, 10) })
	local stroke = C.stroke(t.borderStrong, 1)
	stroke.Parent = box
	box.Focused:Connect(function()
		stroke.Color = t.accent
		stroke.Thickness = 2
	end)
	box.FocusLost:Connect(function()
		stroke.Color = t.borderStrong
		stroke.Thickness = 1
		if p.onCommit and not p.readOnly then
			p.onCommit(box.Text)
		end
	end)
	box.Parent = wrap
	if p.hint then
		C.text(t, { text = p.hint, size = Theme.Text.caption, color = t.mutedFg, order = 3 }).Parent = wrap
	end
	return wrap, box
end

export type SliderProps = {
	label: string,
	hint: string?,
	min: number,
	max: number,
	step: number,
	value: number,
	order: number?,
	suffix: string?,
	onChange: (value: number, final: boolean) -> (),
	onBegin: (() -> ())?,
}

export type SliderCtx = {
	widget: any, -- DockWidgetPluginGui (for mouse position)
	root: GuiObject, -- full-size frame that receives mouse moves
}

local function roundTo(v: number, step: number): number
	return math.floor(v / step + 0.5) * step
end

local function format(v: number, step: number): string
	if step >= 1 then
		return tostring(math.floor(v + 0.5))
	elseif step >= 0.1 then
		return string.format("%.1f", v)
	end
	return string.format("%.2f", v)
end

function C.slider(t: Tokens, ctx: SliderCtx, p: SliderProps): Frame
	local value = math.clamp(p.value, p.min, p.max)
	local frame = C.stack({ LayoutOrder = p.order or 0 }, 2)

	local top = C.new("Frame", { BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 24), LayoutOrder = 1, Parent = frame })
	C.new("TextLabel", {
		BackgroundTransparency = 1,
		Text = p.label,
		TextSize = Theme.Text.label,
		FontFace = Theme.Font.semibold,
		TextColor3 = t.fg,
		TextXAlignment = Enum.TextXAlignment.Left,
		Size = UDim2.new(1, -64, 1, 0),
		TextTruncate = Enum.TextTruncate.AtEnd,
		Parent = top,
	})
	local box = C.new("TextBox", {
		BackgroundColor3 = t.card,
		Text = format(value, p.step) .. (p.suffix or ""),
		TextColor3 = t.fg,
		TextSize = Theme.Text.caption,
		FontFace = Theme.Font.mono,
		ClearTextOnFocus = false,
		AnchorPoint = Vector2.new(1, 0.5),
		Position = UDim2.new(1, 0, 0.5, 0),
		Size = UDim2.new(0, 56, 0, 22),
		Parent = top,
	}, { C.corner(Theme.Radius.sm) })
	local boxStroke = C.stroke(t.border, 1)
	boxStroke.Parent = box

	if p.hint then
		C.text(t, { text = p.hint, size = Theme.Text.caption, color = t.mutedFg, order = 2 }).Parent = frame
	end

	local hit = C.new("TextButton", {
		AutoButtonColor = false,
		BackgroundTransparency = 1,
		Text = "",
		Size = UDim2.new(1, 0, 0, 22),
		LayoutOrder = 3,
		Parent = frame,
	})
	local track = C.new("Frame", {
		BackgroundColor3 = t.muted,
		BorderSizePixel = 0,
		AnchorPoint = Vector2.new(0, 0.5),
		Position = UDim2.new(0, 7, 0.5, 0),
		Size = UDim2.new(1, -14, 0, 4),
		Parent = hit,
	}, { C.round() })
	local fill = C.new("Frame", {
		BackgroundColor3 = t.accent,
		BorderSizePixel = 0,
		Size = UDim2.new(0, 0, 1, 0),
		Parent = track,
	}, { C.round() })
	local knob = C.new("Frame", {
		BackgroundColor3 = t.fg,
		AnchorPoint = Vector2.new(0.5, 0.5),
		Position = UDim2.new(0, 0, 0.5, 0),
		Size = UDim2.new(0, 14, 0, 14),
		ZIndex = 2,
		Parent = track,
	}, { C.round() })
	local knobStroke = C.stroke(t.accent, 2)
	knobStroke.Parent = knob

	local function render()
		local f = (value - p.min) / (p.max - p.min)
		fill.Size = UDim2.new(f, 0, 1, 0)
		knob.Position = UDim2.new(f, 0, 0.5, 0)
		box.Text = format(value, p.step) .. (p.suffix or "")
	end
	render()

	local function setValue(v: number, final: boolean)
		local newValue = math.clamp(roundTo(v, p.step), p.min, p.max)
		local changed = newValue ~= value
		value = newValue
		render()
		if changed or final then
			p.onChange(value, final)
		end
	end

	local dragging = false
	local connections: { RBXScriptConnection } = {}
	local function fromX(x: number)
		local pos, size = C.abs(track)
		local f = math.clamp((x - pos.X) / math.max(1, size.X), 0, 1)
		setValue(p.min + f * (p.max - p.min), false)
	end
	local function stop()
		if not dragging then
			return
		end
		dragging = false
		knob.Size = UDim2.new(0, 14, 0, 14)
		for _, c in connections do
			c:Disconnect()
		end
		table.clear(connections)
		setValue(value, true)
	end
	hit.InputBegan:Connect(function(input)
		if input.UserInputType ~= Enum.UserInputType.MouseButton1 then
			return
		end
		dragging = true
		knob.Size = UDim2.new(0, 16, 0, 16)
		if p.onBegin then
			p.onBegin()
		end
		fromX(input.Position.X)
		table.insert(
			connections,
			RunService.Heartbeat:Connect(function()
				if dragging then
					fromX(ctx.widget:GetRelativeMousePosition().X)
				end
			end)
		)
		table.insert(
			connections,
			ctx.root.InputEnded:Connect(function(ended)
				if ended.UserInputType == Enum.UserInputType.MouseButton1 then
					stop()
				end
			end)
		)
	end)
	hit.InputEnded:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseButton1 then
			stop()
		end
	end)
	hit.MouseEnter:Connect(function()
		C.tween(knob, { Size = UDim2.new(0, 16, 0, 16) })
	end)
	hit.MouseLeave:Connect(function()
		if not dragging then
			C.tween(knob, { Size = UDim2.new(0, 14, 0, 14) })
		end
	end)

	box.Focused:Connect(function()
		boxStroke.Color = t.accent
	end)
	box.FocusLost:Connect(function()
		boxStroke.Color = t.border
		local n = tonumber((box.Text:gsub("[^%d%.%-]", "")))
		if n then
			if p.onBegin then
				p.onBegin()
			end
			setValue(n, true)
		else
			render()
		end
	end)
	return frame
end

function C.toggle(t: Tokens, label: string, value: boolean, onChange: (boolean) -> (), order: number?): TextButton
	local row = C.new("TextButton", {
		AutoButtonColor = false,
		BackgroundTransparency = 1,
		Text = "",
		Size = UDim2.new(1, 0, 0, 28),
		LayoutOrder = order or 0,
	})
	C.new("TextLabel", {
		BackgroundTransparency = 1,
		Text = label,
		TextColor3 = t.fg,
		TextSize = Theme.Text.label,
		FontFace = Theme.Font.medium,
		TextXAlignment = Enum.TextXAlignment.Left,
		Size = UDim2.new(1, -48, 1, 0),
		TextTruncate = Enum.TextTruncate.AtEnd,
		Parent = row,
	})
	local track = C.new("Frame", {
		AnchorPoint = Vector2.new(1, 0.5),
		Position = UDim2.new(1, 0, 0.5, 0),
		Size = UDim2.new(0, 36, 0, 20),
		Parent = row,
	}, { C.round() })
	local dot = C.new("Frame", {
		AnchorPoint = Vector2.new(0, 0.5),
		Size = UDim2.new(0, 16, 0, 16),
		BackgroundColor3 = Color3.new(1, 1, 1),
		Parent = track,
	}, { C.round() })
	local on = value
	local function render(animate: boolean)
		local goalTrack = { BackgroundColor3 = if on then t.accent else t.borderStrong }
		local goalDot = { Position = if on then UDim2.new(1, -18, 0.5, 0) else UDim2.new(0, 2, 0.5, 0) }
		if animate then
			C.tween(track, goalTrack)
			C.tween(dot, goalDot)
		else
			track.BackgroundColor3 = goalTrack.BackgroundColor3
			dot.Position = goalDot.Position
		end
	end
	render(false)
	row.Activated:Connect(function()
		on = not on
		render(true)
		onChange(on)
	end)
	return row
end

-- Row of color swatches + hex box.
function C.colorPicker(t: Tokens, label: string, hexLabel: string, value: Color3, onPick: (Color3) -> (), onInvalid: () -> (), order: number?): Frame
	local frame = C.stack({ LayoutOrder = order or 0 }, 6)
	local head = C.new("Frame", { BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 22), LayoutOrder = 1, Parent = frame })
	C.new("TextLabel", {
		BackgroundTransparency = 1,
		Text = label,
		TextColor3 = t.fg,
		TextSize = Theme.Text.label,
		FontFace = Theme.Font.semibold,
		TextXAlignment = Enum.TextXAlignment.Left,
		Size = UDim2.new(1, -110, 1, 0),
		Parent = head,
	})
	local preview = C.new("Frame", {
		BackgroundColor3 = value,
		AnchorPoint = Vector2.new(1, 0.5),
		Position = UDim2.new(1, -84, 0.5, 0),
		Size = UDim2.new(0, 18, 0, 18),
		Parent = head,
	}, { C.corner(Theme.Radius.sm), C.stroke(t.borderStrong, 1) })
	local hexBox = C.new("TextBox", {
		BackgroundColor3 = t.card,
		Text = "#" .. value:ToHex():upper(),
		PlaceholderText = hexLabel,
		TextColor3 = t.fg,
		TextSize = Theme.Text.caption,
		FontFace = Theme.Font.mono,
		ClearTextOnFocus = false,
		AnchorPoint = Vector2.new(1, 0.5),
		Position = UDim2.new(1, 0, 0.5, 0),
		Size = UDim2.new(0, 76, 0, 22),
		Parent = head,
	}, { C.corner(Theme.Radius.sm) })
	local hexStroke = C.stroke(t.border, 1)
	hexStroke.Parent = hexBox

	local grid = C.new("Frame", {
		BackgroundTransparency = 1,
		Size = UDim2.new(1, 0, 0, 0),
		AutomaticSize = Enum.AutomaticSize.Y,
		LayoutOrder = 2,
		Parent = frame,
	})
	C.list(Enum.FillDirection.Horizontal, 6, true).Parent = grid
	local strokes: { [Color3]: UIStroke } = {}
	local current = value

	local function mark()
		for color, s in strokes do
			local selected = color:ToHex() == current:ToHex()
			s.Color = if selected then t.ring else t.border
			s.Thickness = if selected then 2 else 1
		end
		preview.BackgroundColor3 = current
		hexBox.Text = "#" .. current:ToHex():upper()
	end

	local function pick(color: Color3)
		current = color
		mark()
		onPick(color)
	end

	for i, color in Theme.Swatches do
		local sw = C.new("TextButton", {
			AutoButtonColor = false,
			BackgroundColor3 = color,
			Text = "",
			Size = UDim2.new(0, 22, 0, 22),
			LayoutOrder = i,
			Parent = grid,
		}, { C.round() })
		local s = C.stroke(t.border, 1)
		s.Parent = sw
		strokes[color] = s
		sw.MouseEnter:Connect(function()
			C.tween(sw, { Size = UDim2.new(0, 24, 0, 24) })
		end)
		sw.MouseLeave:Connect(function()
			C.tween(sw, { Size = UDim2.new(0, 22, 0, 22) })
		end)
		sw.Activated:Connect(function()
			pick(color)
		end)
	end
	mark()

	hexBox.Focused:Connect(function()
		hexStroke.Color = t.accent
	end)
	hexBox.FocusLost:Connect(function()
		hexStroke.Color = t.border
		local text = hexBox.Text:gsub("%s", "")
		local r, g, b = text:match("^(%d+),(%d+),(%d+)$")
		if r and g and b then
			pick(Color3.fromRGB(math.clamp(tonumber(r) or 0, 0, 255), math.clamp(tonumber(g) or 0, 0, 255), math.clamp(tonumber(b) or 0, 0, 255)))
			return
		end
		local hex = text:gsub("^#", "")
		if #hex == 6 and hex:match("^%x+$") then
			pick(Color3.fromHex(hex))
		else
			mark()
			onInvalid()
		end
	end)
	return frame
end

-- Selectable option with a title and a one-line explanation.
function C.radio(t: Tokens, title: string, hint: string, selected: boolean, onClick: () -> (), order: number?): TextButton
	local b = C.new("TextButton", {
		AutoButtonColor = false,
		BackgroundColor3 = if selected then t.muted else t.card,
		Text = "",
		Size = UDim2.new(1, 0, 0, 0),
		AutomaticSize = Enum.AutomaticSize.Y,
		LayoutOrder = order or 0,
	}, { C.corner(Theme.Radius.md), C.padding(8, 10) })
	C.stroke(if selected then t.accent else t.border, if selected then 2 else 1).Parent = b
	local dot = C.new("Frame", {
		BackgroundTransparency = 1,
		Position = UDim2.new(0, 0, 0, 2),
		Size = UDim2.new(0, 16, 0, 16),
		Parent = b,
	}, { C.round(), C.stroke(if selected then t.accent else t.borderStrong, 2) })
	if selected then
		C.new("Frame", {
			BackgroundColor3 = t.accent,
			AnchorPoint = Vector2.new(0.5, 0.5),
			Position = UDim2.new(0.5, 0, 0.5, 0),
			Size = UDim2.new(0, 8, 0, 8),
			Parent = dot,
		}, { C.round() })
	end
	local textCol = C.stack({ Position = UDim2.new(0, 26, 0, 0), Size = UDim2.new(1, -26, 0, 0), Parent = b }, 2)
	C.text(t, { text = title, size = Theme.Text.label, font = Theme.Font.semibold, order = 1 }).Parent = textCol
	C.text(t, { text = hint, size = Theme.Text.caption, color = t.mutedFg, order = 2 }).Parent = textCol
	if not selected then
		b.MouseEnter:Connect(function()
			C.tween(b, { BackgroundColor3 = t.muted })
		end)
		b.MouseLeave:Connect(function()
			C.tween(b, { BackgroundColor3 = t.card })
		end)
	end
	b.Activated:Connect(onClick)
	return b
end

-- Titled group. Returns the outer frame and the content frame to fill.
function C.section(t: Tokens, title: string, order: number?): (Frame, Frame)
	local outer = C.stack({ LayoutOrder = order or 0 }, 8)
	C.text(t, { text = title:upper(), size = Theme.Text.caption, font = Theme.Font.bold, color = t.mutedFg, order = 1 }).Parent =
		outer
	local content = C.stack({ LayoutOrder = 2, BackgroundColor3 = t.card, BackgroundTransparency = 0 }, 12)
	C.corner(Theme.Radius.lg).Parent = content
	C.stroke(t.border, 1).Parent = content
	C.padding(12).Parent = content
	content.Parent = outer
	return outer, content
end

return C
