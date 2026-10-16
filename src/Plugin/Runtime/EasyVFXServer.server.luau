-- Installed by the EasyVFX plugin. Wires up the no-code triggers
-- (touch, click, proximity prompt). You don't need to edit this.
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local EasyVFX = require(ReplicatedStorage:WaitForChild("EasyVFX"))
EasyVFX.InitServer()
