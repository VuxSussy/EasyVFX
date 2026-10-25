--[[
	Prints Presets.Kits as JSON for the studio (tools/evfx/serve.py, Layers): each kit's
	preset, its layers in order, each variant's note and layer data, and its picks. The layer
	data lets the studio show what changed in a variant since Phát last looked.

	lune run tests/kits.luau
]]

local serde = require("@lune/serde")
local H = require("./harness")
H.install()

local Presets = H.require("Shared/Presets")
H.loadKits(Presets)

local function round(n: number): number
	return math.floor(n * 1000 + 0.5) / 1000
end

-- plain JSON values: vectors as {x, y, z}, colours as #rrggbb, numbers to 3 places
local function plain(v: any): any
	local kind = typeof(v)
	if kind == "number" then
		return round(v)
	elseif kind == "Vector3" then
		return { round(v.X), round(v.Y), round(v.Z) }
	elseif kind == "Color3" then
		return "#" .. v:ToHex()
	elseif kind == "table" then
		local out = {}
		for k, x in v do
			out[k] = plain(x)
		end
		return out
	end
	return v
end

local out = {}
for name, kit in Presets.Kits do
	local layers = {}
	for _, layerName in kit.order do
		local variants = {}
		for key, variant in kit.layers[layerName] do
			variants[key] = { note = variant.note, count = #variant.layers, layers = plain(variant.layers) }
		end
		table.insert(layers, { name = layerName, variants = variants })
	end
	out[name] = { preset = kit.preset, layers = layers, picks = kit.picks }
end
print(serde.encode("json", out))
