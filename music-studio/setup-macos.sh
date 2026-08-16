#!/usr/bin/env bash
# setup-macos.sh — connects Claude Desktop to REAPER in one run.
#
# Does three things, each one safe to repeat:
#   1. installs uv (the launcher the MCP server runs under)
#   2. copies the bridge script into REAPER's Scripts folder
#   3. merges the "reaper" server into claude_desktop_config.json without
#      touching any other server already configured there
#
# Usage:  bash setup-macos.sh
# Portable REAPER: REAPER_SCRIPTS=/path/to/REAPER/Scripts bash setup-macos.sh

set -euo pipefail

step() { printf '\n\033[36m[%s] %s\033[0m\n' "$1" "$2"; }
ok()   { printf '    \033[32mOK\033[0m  %s\n' "$1"; }
die()  { printf '\n\033[31mFAILED:\033[0m %s\n' "$1" >&2; exit 1; }

APP_SUPPORT="${APP_SUPPORT:-$HOME/Library/Application Support}"

echo "REAPER <-> Claude setup"

# --- 1. uv ---------------------------------------------------------------
step 1 "Installing uv"

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uvx >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # The installer edits shell rc files, not this already-running shell.
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v uvx >/dev/null 2>&1 || die "uv installed but uvx is still not on PATH. Close this Terminal window, open a new one, and run this script again."
ok "$(uvx --version 2>&1 | head -n1)"

# --- 2. bridge -----------------------------------------------------------
step 2 "Installing the REAPER bridge script"

if [ -z "${REAPER_SCRIPTS:-}" ]; then
  reaper_root="$APP_SUPPORT/REAPER"
  [ -d "$reaper_root" ] || die "REAPER is not installed for this user (looked in $reaper_root). Install REAPER from https://www.reaper.fm/download.php, launch it once so it creates its settings folder, then run this script again."
  REAPER_SCRIPTS="$reaper_root/Scripts"
fi

# --install-bridge rejects relative paths, so make it absolute first.
mkdir -p "$REAPER_SCRIPTS"
REAPER_SCRIPTS="$(cd "$REAPER_SCRIPTS" && pwd)"

uvx twelvetake-reaper-mcp --install-bridge "$REAPER_SCRIPTS" || die "Bridge install failed."
[ -f "$REAPER_SCRIPTS/reaper_mcp_bridge.lua" ] || die "Bridge script did not appear in $REAPER_SCRIPTS."
ok "$REAPER_SCRIPTS/reaper_mcp_bridge.lua"

# --- 3. Claude Desktop config -------------------------------------------
step 3 "Registering the server with Claude Desktop"

config_dir="$APP_SUPPORT/Claude"
config_path="$config_dir/claude_desktop_config.json"
mkdir -p "$config_dir"

# Merge with python3 (ships with macOS) so any other MCP servers survive.
CONFIG_PATH="$config_path" python3 <<'PY' || die "Could not update the Claude config."
import json, os, shutil, sys

path = os.environ["CONFIG_PATH"]
config = {}

if os.path.exists(path) and os.path.getsize(path):
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    if raw.strip():
        try:
            config = json.loads(raw)
        except json.JSONDecodeError as exc:
            sys.exit(f"{path} contains invalid JSON ({exc}). Fix or delete it, then re-run.")
        # Keep a copy before rewriting, so a bad merge is always recoverable.
        shutil.copyfile(path, path + ".backup")
        print(f"    OK  Backed up existing config to {path}.backup")

servers = config.setdefault("mcpServers", {})
servers["reaper"] = {"command": "uvx", "args": ["twelvetake-reaper-mcp"]}

with open(path, "w", encoding="utf-8") as fh:
    json.dump(config, fh, indent=2, ensure_ascii=False)
    fh.write("\n")

print(f"    OK  {path}  (servers: {', '.join(servers)})")
PY

# --- next steps ----------------------------------------------------------
cat <<'EOF'

Done. Three things left, all by hand:
  1. Quit Claude Desktop completely - Cmd+Q, not just closing the window - then reopen it.
  2. In REAPER: Actions > Show action list > Load ReaScript > pick reaper_mcp_bridge.lua > Run.
     REAPER's console should print: REAPER MCP Bridge (File-based, Full API) started
  3. Ask Claude: how many tracks are in my REAPER project?

Re-run step 2 after every upgrade of the package - the bridge and the server must be the same version.
EOF
