-- Installed by the EasyVFX plugin. Wires up the no-code triggers
-- (touch, click, proximity prompt). You don't need to edit this.
-- The copy kept inside the plugin is only a template. Studio can still run it in
-- every DataModel (edit, server, client) despite Enabled = false, which would start
-- the runtime twice, so it does nothing there.
if script:FindFirstAncestorWhichIsA("Plugin") then
	return
end
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local EasyVFX = require(ReplicatedStorage:WaitForChild("EasyVFX"))
EasyVFX.InitServer()
