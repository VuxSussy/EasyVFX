--!strict
--[[
	EasyVFX <-> Eclipse Animator.

	The AI ("vibe") flow:
	  1. Make an animation on a rig (Eclipse Animator's MCP tools save it into the
	     rig's AnimSaves folder as a KeyframeSequence).
	  2. attach() puts EasyVFX effects inside the rig, welded to a hand, weapon or
	     the root, so they follow the body.
	  3. writeEvents() writes Eclipse Animator's own event track into that animation
	     (the "EclipseEvents" folder, format version 8) with one event per effect
	     cue. Opening the animation in Eclipse shows the cues on its event track,
	     where they can be moved, retimed or removed by hand. It also writes the
	     KeyframeMarkers Eclipse would export, so the KeyframeSequence plays in a game
	     right away, before anyone opens Eclipse.
	  4. In the game, EasyVFX.BindAnimation(track, character) plays the full effects
	     (shapes, shakes and impact frames included) at those markers.

	Cues pointing at an effect inside the rig become Eclipse "Emits" (Eclipse's
	native way to fire VFX, previewed in its editor). Cues pointing at an effect
	elsewhere (templates in ReplicatedStorage.EasyVFX_Effects) become an "EasyVFX"
	marker on the event, which Eclipse keeps and exports as a KeyframeMarker.
]]

local HttpService = game:GetService("HttpService")

local Bridge = {}

Bridge.FOLDER = "EclipseEvents"
Bridge.FORMAT = 8 -- Eclipse Animator event document version
Bridge.FPS = 60 -- Eclipse's default FPS
Bridge.EFFECTS_FOLDER = "EasyVFX"

export type Cue = {
	time: number, -- seconds into the animation
	effect: Instance, -- an EasyVFX effect root
	name: string?, -- event label shown on the track
	at: string?, -- body part / attachment (marker cues only)
	offset: Vector3?, -- studs, marker cues only
	rot: Vector3?, -- degrees, marker cues only
}

-- Eclipse's emit path: one step per ancestor, matched by name, class and index
-- among same-named siblings.
function Bridge.path(root: Instance, target: Instance): { { Name: string, Class: string, Index: number } }?
	local path = {}
	local cursor: Instance? = target
	while cursor ~= root do
		if not cursor or not cursor.Parent then
			return nil
		end
		local index = 0
		for _, child in (cursor.Parent :: Instance):GetChildren() do
			if child.Name == cursor.Name and child.ClassName == cursor.ClassName then
				index += 1
			end
			if child == cursor then
				break
			end
		end
		table.insert(path, 1, { Name = cursor.Name, Class = cursor.ClassName, Index = index })
		cursor = cursor.Parent
	end
	return path
end

local function stringValue(parent: Instance, name: string, value: string)
	local v = Instance.new("StringValue")
	v.Name = name
	v.Value = value
	v.Parent = parent
end

local function markerPayload(cue: Cue): string
	local data: { [string]: any } = { effect = cue.effect.Name }
	if cue.at then
		data.at = cue.at
	end
	if cue.offset then
		data.offset = { cue.offset.X, cue.offset.Y, cue.offset.Z }
	end
	if cue.rot then
		data.rot = { cue.rot.X, cue.rot.Y, cue.rot.Z }
	end
	return HttpService:JSONEncode(data)
end

-- Moves an effect into the rig, welded to `partName` (a BasePart in the rig;
-- default HumanoidRootPart), placed at `offset` from it. Returns the effect.
function Bridge.attach(rig: Instance, effect: BasePart, partName: string?, offset: CFrame?): BasePart
	local found = rig:FindFirstChild(partName or "HumanoidRootPart", true)
	if not (found and found:IsA("BasePart")) then
		found = rig:FindFirstChildWhichIsA("BasePart", true)
	end
	assert(found and found:IsA("BasePart"), "rig has no parts to attach to")
	local part: BasePart = found
	local folder: Instance? = rig:FindFirstChild(Bridge.EFFECTS_FOLDER)
	if not folder then
		local f = Instance.new("Folder")
		f.Name = Bridge.EFFECTS_FOLDER
		f.Parent = rig
		folder = f
	end
	for _, j in effect:GetChildren() do
		if j:IsA("WeldConstraint") or j:IsA("JointInstance") then
			j:Destroy()
		end
	end
	effect.Anchored = false
	effect.CanCollide = false
	effect.CanQuery = false
	effect.CanTouch = false
	effect.Massless = true
	effect.CFrame = part.CFrame * (offset or CFrame.identity)
	effect:SetAttribute("VFX_Trigger", "Script") -- played by the animation, not on its own
	effect.Parent = folder
	local weld = Instance.new("WeldConstraint")
	weld.Name = "EasyVFX_Weld"
	weld.Part0 = part
	weld.Part1 = effect
	weld.Parent = effect
	return effect
end

-- Writes the cues as Eclipse Animator's event track on `sequence` (replacing any
-- previous track) plus the KeyframeMarkers Eclipse exports. Returns the folder.
function Bridge.writeEvents(rig: Instance, sequence: KeyframeSequence, cues: { Cue }, fps: number?): Folder
	local rate = fps or Bridge.FPS
	local folder = Instance.new("Folder")
	folder.Name = Bridge.FOLDER
	folder:SetAttribute("Version", Bridge.FORMAT)
	folder:SetAttribute("FPS", rate)
	folder:SetAttribute("DefaultFPS", Bridge.FPS)
	folder:SetAttribute("Enabled", true)
	folder:SetAttribute("FacesEnabled", false)
	folder:SetAttribute("ProjectSubtitles", false)
	folder:SetAttribute("Revision", 1)
	folder:SetAttribute("CreatedBy", "EasyVFX")
	stringValue(folder, "FaceKeys", "{}")

	-- Eclipse keeps one event per frame; cues on the same frame share it.
	local byFrame: { [number]: { emits: { any }, markers: { any }, names: { string } } } = {}
	local frames: { number } = {}
	for _, cue in cues do
		local frame = math.max(0, math.floor(cue.time * rate + 0.5))
		local slot = byFrame[frame]
		if not slot then
			slot = { emits = {}, markers = {}, names = {} }
			byFrame[frame] = slot
			table.insert(frames, frame)
		end
		local inRig = cue.effect:IsDescendantOf(rig)
		local path = if inRig then Bridge.path(rig, cue.effect) else nil
		if path then
			table.insert(slot.emits, { Mode = "All", Path = path })
		else
			table.insert(slot.markers, { Name = "EasyVFX", Parameter = markerPayload(cue) })
		end
		table.insert(slot.names, cue.name or cue.effect.Name:gsub("^VFX_", ""))
	end
	table.sort(frames)

	for _, frame in frames do
		local slot = byFrame[frame]
		local item = Instance.new("Folder")
		item.Name = HttpService:GenerateGUID(false)
		item:SetAttribute("Frame", frame)
		item:SetAttribute("Duration", 0)
		item:SetAttribute("Speed", 1)
		local label = table.concat(slot.names, " + ")
		local markers = slot.markers
		if #markers == 0 then
			-- an event always has a name; the first marker is what Eclipse displays
			markers = { { Name = label, Parameter = "" } }
		end
		item:SetAttribute("EventName", markers[1].Name)
		item:SetAttribute("Parameter", markers[1].Parameter)
		item:SetAttribute("Enabled", true)
		stringValue(item, "Markers", HttpService:JSONEncode(markers))
		stringValue(item, "CodeBegin", "")
		stringValue(item, "CodeEnd", "")
		stringValue(item, "Emits", HttpService:JSONEncode(slot.emits))
		local sounds = Instance.new("Folder")
		sounds.Name = "Sounds"
		sounds.Parent = item
		item.Parent = folder
	end

	-- KeyframeMarkers, as Eclipse's export writes them, so the animation works in
	-- a game before it is ever opened in Eclipse. Old EasyVFX/Eclipse markers go.
	local keyAt: { [number]: Keyframe } = {}
	for _, key in sequence:GetKeyframes() do
		if key:IsA("Keyframe") then
			for _, marker in key:GetMarkers() do
				if marker.Name == "EclipseVFX" or marker.Name == "EasyVFX" then
					marker:Destroy()
				end
			end
			keyAt[math.floor(key.Time * rate + 0.5)] = key
		end
	end
	for _, frame in frames do
		local slot = byFrame[frame]
		local key = keyAt[frame]
		if not key then
			local k = Instance.new("Keyframe")
			k.Name = "Keyframe"
			k.Time = frame / rate
			k.Parent = sequence
			keyAt[frame] = k
			key = k
		end
		assert(key)
		if #slot.emits > 0 then
			local marker = Instance.new("KeyframeMarker")
			marker.Name = "EclipseVFX"
			marker.Value = HttpService:JSONEncode({ Version = 1, Emits = slot.emits })
			marker.Parent = key
		end
		for _, m in slot.markers do
			local marker = Instance.new("KeyframeMarker")
			marker.Name = m.Name
			marker.Value = m.Parameter
			marker.Parent = key
		end
	end

	local previous = sequence:FindFirstChild(Bridge.FOLDER)
	folder.Parent = sequence
	if previous and previous ~= folder then
		previous:Destroy()
	end
	if sequence:GetAttribute("EclipseEventDocumentId") == nil then
		sequence:SetAttribute("EclipseEventDocumentId", HttpService:GenerateGUID(false))
	end
	if rig:GetAttribute("EclipseEventRigId") == nil then
		rig:SetAttribute("EclipseEventRigId", HttpService:GenerateGUID(false))
	end
	return folder
end

-- Reads back an Eclipse event track (written by Eclipse or by writeEvents) as a
-- list of { frame, time, markers, emits } so a tool can inspect what's there.
function Bridge.readEvents(sequence: KeyframeSequence): { any }
	local folder = sequence:FindFirstChild(Bridge.FOLDER)
	local out = {}
	if not folder then
		return out
	end
	local fps = folder:GetAttribute("FPS")
	local rate = if type(fps) == "number" and fps > 0 then fps else Bridge.FPS
	for _, item in folder:GetChildren() do
		local frame = item:GetAttribute("Frame")
		if item:IsA("Folder") and type(frame) == "number" then
			local function json(name: string): any
				local v = item:FindFirstChild(name)
				if not (v and v:IsA("StringValue")) then
					return {}
				end
				local ok, data = pcall(function()
					return HttpService:JSONDecode(v.Value)
				end)
				return if ok and type(data) == "table" then data else {}
			end
			table.insert(out, { frame = frame, time = frame / rate, markers = json("Markers"), emits = json("Emits") })
		end
	end
	table.sort(out, function(a, b)
		return a.frame < b.frame
	end)
	return out
end

return Bridge
