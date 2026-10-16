--!strict
--[[
	Design tokens. Palette from the UI UX Pro Max design system
	("Developer Tool / IDE": slate surfaces + green action color), dense spacing,
	minimal Swiss style. A light variant follows Studio's light theme.
]]

export type Tokens = {
	isDark: boolean,
	bg: Color3,
	card: Color3,
	muted: Color3,
	hover: Color3,
	fg: Color3,
	mutedFg: Color3,
	border: Color3,
	borderStrong: Color3,
	accent: Color3,
	accentHover: Color3,
	onAccent: Color3,
	danger: Color3,
	onDanger: Color3,
	ring: Color3,
	overlay: Color3,
}

local function hex(s: string): Color3
	return Color3.fromHex(s)
end

local Theme = {}

Theme.Dark = {
	isDark = true,
	bg = hex("#0F172A"),
	card = hex("#1B2336"),
	muted = hex("#272F42"),
	hover = hex("#303A50"),
	fg = hex("#F8FAFC"),
	mutedFg = hex("#94A3B8"),
	border = hex("#334155"),
	borderStrong = hex("#475569"),
	accent = hex("#22C55E"),
	accentHover = hex("#4ADE80"),
	onAccent = hex("#0F172A"),
	danger = hex("#EF4444"),
	onDanger = hex("#FFFFFF"),
	ring = hex("#FFFFFF"),
	overlay = hex("#020617"),
} :: Tokens

Theme.Light = {
	isDark = false,
	bg = hex("#F8FAFC"),
	card = hex("#FFFFFF"),
	muted = hex("#F1F5F9"),
	hover = hex("#E2E8F0"),
	fg = hex("#0F172A"),
	mutedFg = hex("#475569"),
	border = hex("#E2E8F0"),
	borderStrong = hex("#CBD5E1"),
	accent = hex("#15803D"),
	accentHover = hex("#166534"),
	onAccent = hex("#FFFFFF"),
	danger = hex("#DC2626"),
	onDanger = hex("#FFFFFF"),
	ring = hex("#0F172A"),
	overlay = hex("#0F172A"),
} :: Tokens

Theme.Space = { xs = 4, sm = 8, md = 12, lg = 16, xl = 24 }
Theme.Radius = { sm = 4, md = 6, lg = 8, pill = 999 }
Theme.Text = { caption = 12, body = 14, label = 13, title = 16, hero = 18 }
Theme.Motion = { fast = 0.12, base = 0.18 }

local FAMILY = "rbxasset://fonts/families/BuilderSans.json"
Theme.Font = {
	regular = Font.new(FAMILY, Enum.FontWeight.Regular),
	medium = Font.new(FAMILY, Enum.FontWeight.Medium),
	semibold = Font.new(FAMILY, Enum.FontWeight.SemiBold),
	bold = Font.new(FAMILY, Enum.FontWeight.Bold),
	mono = Font.new("rbxasset://fonts/families/RobotoMono.json", Enum.FontWeight.Regular),
}

-- Colors offered as one-click swatches.
Theme.Swatches = {
	hex("#FFFFFF"),
	hex("#FFD640"),
	hex("#FF8C28"),
	hex("#FF3B3B"),
	hex("#FF5FA2"),
	hex("#A45CFF"),
	hex("#3D8BFF"),
	hex("#3CE0FF"),
	hex("#50FF8C"),
	hex("#C8FF50"),
	hex("#9AA3B2"),
	hex("#1A1A1A"),
}

function Theme.current(): Tokens
	local ok, name = pcall(function()
		return (settings().Studio :: any).Theme.Name
	end)
	if ok and name == "Light" then
		return Theme.Light
	end
	return Theme.Dark
end

return Theme
