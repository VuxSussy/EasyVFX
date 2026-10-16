#!/usr/bin/env bash
# Builds the plugin and runs every check. Tools are taken from PATH unless
# ROJO / LUNE / LUAU_LSP / LUAU_DEFS are set.
set -euo pipefail
cd "$(dirname "$0")/.."

ROJO="${ROJO:-rojo}"
LUNE="${LUNE:-lune}"
LUAU_LSP="${LUAU_LSP:-luau-lsp}"
LUAU_DEFS="${LUAU_DEFS:-globalTypes.d.luau}"

echo "== build"
"$ROJO" build default.project.json -o build/EasyVFX.rbxmx

echo "== type check (strict)"
"$ROJO" sourcemap default.project.json -o sourcemap.json
# The two bootstrap scripts require ReplicatedStorage.EasyVFX, which only exists
# after the plugin installs it into a place, so that one warning is expected.
if "$LUAU_LSP" analyze --platform=roblox --definitions="$LUAU_DEFS" --sourcemap=sourcemap.json src 2>&1 \
	| grep -v "Unknown require: game/ReplicatedStorage/EasyVFX" | grep .; then
	echo "type errors found"
	exit 1
fi

echo "== builder + runtime tests"
"$LUNE" run tests/run.luau | tail -1

echo "== UI tests"
"$LUNE" run tests/ui.luau | tail -1
