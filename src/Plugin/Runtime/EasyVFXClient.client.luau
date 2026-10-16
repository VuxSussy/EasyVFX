-- Installed by the EasyVFX plugin. Plays effects on each player's device
-- (smoother and lighter on the network). You don't need to edit this.
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local EasyVFX = require(ReplicatedStorage:WaitForChild("EasyVFX"))
EasyVFX.InitClient()
