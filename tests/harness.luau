--[[
	Tiny Roblox-like environment for running EasyVFX modules under Lune.
	Instances come from @lune/roblox (real class/property validation from the
	Roblox reflection database). Engine-only methods are mocked below.
]]

local fs = require("@lune/fs")
local luau = require("@lune/luau")
local process = require("@lune/process")
local roblox = require("@lune/roblox")

local Harness = {}

local ROOT = "src/Plugin"

Harness.warnings = {} :: { string }
Harness.emitLog = {} :: { any }
Harness.recordEmits = false
Harness.frame = 0
Harness.emitted = {} :: { [any]: number }
Harness.onFrame = nil :: ((number) -> ())?

-- Virtual time: task.wait() returns a fixed frame time so tests run fast. EVFX_FPS=60
-- records a timeline at 60 frames a second for the beat judge (tools/evfx beats).
local FRAME = 1 / (tonumber(process.env.EVFX_FPS) or 30)
Harness.FRAME = FRAME
local realTask = require("@lune/task")
local pending = {}
local parked: { thread } = {}

-- Lockstep mode (tests/timeline.luau): waiting coroutines park, and Harness.tick()
-- advances one frame and resumes them in order, so a play is the same every run.
Harness.lockstep = false
local fakeTask = {
	spawn = realTask.spawn,
	defer = realTask.defer,
	cancel = realTask.cancel,
	wait = function(_t: number?)
		if Harness.lockstep then
			table.insert(parked, coroutine.running())
			return coroutine.yield()
		end
		realTask.wait()
		Harness.frame += 1
		if Harness.onFrame then
			Harness.onFrame(Harness.frame)
		end
		local now = Harness.frame * FRAME
		local due = {}
		for i = #pending, 1, -1 do
			if pending[i].at <= now then
				table.insert(due, table.remove(pending, i))
			end
		end
		for i = #due, 1, -1 do
			realTask.spawn(due[i].f, table.unpack(due[i].args))
		end
		return FRAME
	end,
	-- virtual-time delay: fires when enough fake frames have passed
	delay = function(t: number, f, ...)
		table.insert(pending, { at = Harness.frame * FRAME + t, f = f, args = { ... } })
		if #pending == 1 and not Harness.lockstep then
			-- keep virtual time moving even when no animation is running
			realTask.spawn(function()
				while #pending > 0 do
					Harness.task.wait()
				end
			end)
		end
	end,
}
Harness.task = fakeTask

function Harness.tick()
	Harness.frame += 1
	if Harness.onFrame then
		Harness.onFrame(Harness.frame)
	end
	local now = Harness.frame * FRAME
	local due = {}
	for i = #pending, 1, -1 do
		if pending[i].at <= now then
			table.insert(due, table.remove(pending, i))
		end
	end
	for i = #due, 1, -1 do
		realTask.spawn(due[i].f, table.unpack(due[i].args))
	end
	local waiting = parked
	parked = {}
	for _, co in waiting do
		if coroutine.status(co) == "suspended" then
			realTask.spawn(co, FRAME)
		end
	end
end

-- Random datatype (not provided by Lune).
local RandomMeta = {}
RandomMeta.__index = RandomMeta
function RandomMeta:NextNumber(a: number?, b: number?)
	a = a or 0
	b = b or 1
	return a + (b - a) * math.random()
end
function RandomMeta:NextInteger(a: number, b: number)
	return math.random(a, b)
end
local Random = {
	new = function(_seed: number?)
		return setmetatable({}, RandomMeta)
	end,
}

local RaycastParams = {
	new = function()
		return { FilterType = nil, FilterDescendantsInstances = {}, IgnoreWater = false }
	end,
}

-- DataModel
local game = roblox.Instance.new("DataModel")
local workspace = game:GetService("Workspace")
Harness.game = game
Harness.workspace = workspace

local ground = roblox.Instance.new("Part")
ground.Name = "Ground"
ground.Anchored = true
ground.Size = roblox.Vector3.new(200, 1, 200)
ground.CFrame = roblox.CFrame.new(0, -0.5, 0)
ground.Color = roblox.Color3.fromRGB(90, 160, 80)
ground.Parent = workspace
Harness.ground = ground

local isRunning, isServer, isClient = false, false, false
function Harness.setMode(mode: string)
	isRunning = mode ~= "edit"
	isServer = mode == "server"
	isClient = mode == "client"
end

local function captureWarn(...)
	local parts = {}
	for i = 1, select("#", ...) do
		table.insert(parts, tostring((select(i, ...))))
	end
	table.insert(Harness.warnings, table.concat(parts, " "))
end

-- Module loader with fake `script` objects that mirror the Rojo tree.
local cache: { [string]: any } = {}

-- Index the source tree up front (fs calls can't run inside metamethods).
local known: { [string]: boolean } = {}
local function scan(dir: string, rel: string)
	for _, name in fs.readDir(dir) do
		local full = dir .. "/" .. name
		if fs.isDir(full) then
			known[rel .. name] = true
			scan(full, rel .. name .. "/")
		elseif name:match("%.luau$") then
			local base = name:gsub("%.server%.luau$", ""):gsub("%.client%.luau$", ""):gsub("%.luau$", "")
			known[rel .. base] = true
		end
	end
end
scan(ROOT, "")
local fakes: { [string]: any } = {}

local function fakeScript(path: string)
	if fakes[path] then
		return fakes[path]
	end
	local name = path:match("([^/]+)$") or path
	local parentPath = path:match("^(.*)/[^/]+$") or (if path ~= "" then "" else nil)
	local obj = { __path = path, Name = name }
	setmetatable(obj, {
		__index = function(self, key)
			if key == "Parent" then
				return if parentPath then fakeScript(parentPath) else nil
			end
			local child = if path == "" then key else path .. "/" .. key
			if known[child] then
				return fakeScript(child)
			end
			return nil
		end,
	})
	obj.FindFirstChild = function(_self, key)
		return obj[key]
	end
	fakes[path] = obj
	return obj
end

local env

local function requireFake(target)
	if type(target) ~= "table" or not target.__path then
		error("harness can only require fake scripts, got " .. tostring(target))
	end
	local path = target.__path
	if cache[path] ~= nil then
		return cache[path]
	end
	local file = ROOT .. "/" .. path .. ".luau"
	local source = fs.readFile(file)
	local chunk = luau.load(source, {
		debugName = file,
		environment = (function()
			local flat = { script = target }
			for k, v in env do
				flat[k] = v
			end
			return flat
		end)(),
	})
	local result = chunk()
	cache[path] = result
	return result
end

local virtualOs = setmetatable({
	clock = function()
		return if Harness.lockstep then Harness.frame * FRAME else os.clock()
	end,
}, { __index = os })

env = setmetatable({
	os = virtualOs,
	game = game,
	workspace = workspace,
	Instance = roblox.Instance,
	Enum = roblox.Enum,
	Vector3 = roblox.Vector3,
	Vector2 = roblox.Vector2,
	CFrame = roblox.CFrame,
	Color3 = roblox.Color3,
	ColorSequence = roblox.ColorSequence,
	ColorSequenceKeypoint = roblox.ColorSequenceKeypoint,
	NumberSequence = roblox.NumberSequence,
	NumberSequenceKeypoint = roblox.NumberSequenceKeypoint,
	NumberRange = roblox.NumberRange,
	Font = roblox.Font,
	TweenInfo = { new = function(...) return { ... } end },
	settings = function() error("no settings in tests") end,
	UDim = roblox.UDim,
	UDim2 = roblox.UDim2,
	Random = Random,
	RaycastParams = RaycastParams,
	UserSettings = function()
		error("UserSettings not available in tests")
	end,
	task = fakeTask,
	warn = captureWarn,
	require = requireFake,
	typeof = typeof,
}, { __index = _G })

function Harness.install()
	-- Animation data (Lune has the classes but not these methods)
	roblox.implementMethod("KeyframeSequence", "GetKeyframes", function(seq)
		local out = {}
		for _, c in seq:GetChildren() do
			if c:IsA("Keyframe") then
				table.insert(out, c)
			end
		end
		table.sort(out, function(a, b)
			return a.Time < b.Time
		end)
		return out
	end)
	roblox.implementMethod("Keyframe", "GetMarkers", function(key)
		local out = {}
		for _, c in key:GetChildren() do
			if c:IsA("KeyframeMarker") then
				table.insert(out, c)
			end
		end
		return out
	end)
	local serde = require("@lune/serde")
	local guidCount = 0
	roblox.implementMethod("HttpService", "JSONEncode", function(_hs, value)
		return serde.encode("json", value)
	end)
	roblox.implementMethod("HttpService", "JSONDecode", function(_hs, text)
		return serde.decode("json", text)
	end)
	roblox.implementMethod("HttpService", "GenerateGUID", function(_hs, braces)
		guidCount += 1
		local g = string.format("%08x-0000-4000-8000-%012x", math.random(0, 0x7fffffff), guidCount)
		return if braces == false then g else "{" .. g .. "}"
	end)
	roblox.implementMethod("RunService", "IsRunning", function()
		return isRunning
	end)
	roblox.implementMethod("RunService", "IsServer", function()
		return isServer
	end)
	roblox.implementMethod("RunService", "IsClient", function()
		return isClient
	end)
	-- Studio loads a mesh by ID; here the MeshPart just carries the ID it was given
	roblox.implementMethod("AssetService", "CreateMeshPartAsync", function(_as, meshId)
		local part = roblox.Instance.new("MeshPart")
		part.MeshId = meshId
		return part
	end)
	roblox.implementMethod("ParticleEmitter", "Emit", function(inst, n)
		Harness.emitted[inst] = (Harness.emitted[inst] or 0) + (n or 16)
		if Harness.recordEmits then
			-- remember where/how it emitted, for tests/snapshot.luau
			local parent = inst.Parent
			local cf, size = roblox.CFrame.new(), roblox.Vector3.new(0, 0, 0)
			if parent and parent:IsA("Attachment") then
				cf = parent.Parent.CFrame * parent.CFrame
			elseif parent and parent:IsA("BasePart") then
				cf, size = parent.CFrame, parent.Size
			end
			table.insert(Harness.emitLog, { emitter = inst, count = n or 16, frame = Harness.frame, cframe = cf, size = size })
		end
	end)
	roblox.implementMethod("Workspace", "Raycast", function(_ws, origin, _dir, _params)
		return {
			Position = roblox.Vector3.new(origin.X, 0, origin.Z),
			Material = roblox.Enum.Material.Grass,
			Instance = ground,
			Normal = roblox.Vector3.new(0, 1, 0),
		}
	end)
	roblox.implementMethod("CollectionService", "GetTagged", function(_cs, tag)
		local out = {}
		for _, d in game:GetDescendants() do
			if d:HasTag(tag) then
				table.insert(out, d)
			end
		end
		return out
	end)
	roblox.implementMethod("Players", "GetPlayers", function()
		return {}
	end)
end

function Harness.require(path: string)
	return requireFake(fakeScript(path))
end

return Harness
