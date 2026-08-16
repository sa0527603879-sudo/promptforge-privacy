# setup-windows.ps1 — connects Claude Desktop to REAPER in one run.
#
# Does three things, each one safe to repeat:
#   1. installs uv (the launcher the MCP server runs under)
#   2. copies the bridge script into REAPER's Scripts folder
#   3. merges the "reaper" server into claude_desktop_config.json without
#      touching any other server already configured there
#
# Usage:  powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
# Portable REAPER: add  -ReaperScripts "D:\REAPER\Scripts"

[CmdletBinding()]
param(
    [string]$ReaperScripts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step($n, $text) { Write-Host "`n[$n] $text" -ForegroundColor Cyan }
function Write-Ok($text)       { Write-Host "    OK  $text" -ForegroundColor Green }
function Write-Warn2($text)    { Write-Host "    !   $text" -ForegroundColor Yellow }

Write-Host "REAPER <-> Claude setup" -ForegroundColor White

# --- 1. uv ---------------------------------------------------------------
Write-Step 1 "Installing uv"

$uvBin = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # The installer edits the persistent PATH, not this session's copy.
    $env:Path = "$uvBin;$env:Path"
}
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    throw "uv installed but uvx is still not on PATH. Close this window, open a new PowerShell, and run this script again."
}
Write-Ok (& uvx --version 2>&1 | Select-Object -First 1)

# --- 2. bridge -----------------------------------------------------------
Write-Step 2 "Installing the REAPER bridge script"

if (-not $ReaperScripts) {
    $reaperRoot = Join-Path $env:APPDATA "REAPER"
    if (-not (Test-Path $reaperRoot)) {
        throw "REAPER is not installed for this user (looked in $reaperRoot). Install REAPER from https://www.reaper.fm/download.php, launch it once so it creates its settings folder, then run this script again."
    }
    $ReaperScripts = Join-Path $reaperRoot "Scripts"
}

# --install-bridge rejects relative paths, so resolve to a full path first.
$ReaperScripts = [System.IO.Path]::GetFullPath($ReaperScripts)
New-Item -ItemType Directory -Force -Path $ReaperScripts | Out-Null

& uvx twelvetake-reaper-mcp --install-bridge "$ReaperScripts"
if ($LASTEXITCODE -ne 0) { throw "Bridge install failed (exit $LASTEXITCODE)." }

$bridge = Join-Path $ReaperScripts "reaper_mcp_bridge.lua"
if (-not (Test-Path $bridge)) { throw "Bridge script did not appear at $bridge." }
Write-Ok $bridge

# --- 3. Claude Desktop config -------------------------------------------
Write-Step 3 "Registering the server with Claude Desktop"

$configDir  = Join-Path $env:APPDATA "Claude"
$configPath = Join-Path $configDir "claude_desktop_config.json"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

$config = [ordered]@{}
if (Test-Path $configPath) {
    $raw = Get-Content $configPath -Raw -Encoding UTF8
    if ($raw.Trim()) {
        try {
            $existing = $raw | ConvertFrom-Json
        } catch {
            throw "$configPath contains invalid JSON. Fix or delete the file, then run this script again."
        }
        # Keep a copy before rewriting, so a bad merge is always recoverable.
        $backup = "$configPath.backup"
        Copy-Item $configPath $backup -Force
        Write-Ok "Backed up existing config to $backup"
        foreach ($p in $existing.PSObject.Properties) { $config[$p.Name] = $p.Value }
    }
}

$servers = [ordered]@{}
if ($config.Contains('mcpServers') -and $config['mcpServers']) {
    foreach ($p in $config['mcpServers'].PSObject.Properties) { $servers[$p.Name] = $p.Value }
}
$servers['reaper'] = [ordered]@{ command = 'uvx'; args = @('twelvetake-reaper-mcp') }
$config['mcpServers'] = $servers

# -Depth matters: the default of 2 silently flattens the args array into a type name.
$json = ($config | ConvertTo-Json -Depth 10) + "`n"
[System.IO.File]::WriteAllText($configPath, $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "$configPath  (servers: $($servers.Keys -join ', '))"

# --- next steps ----------------------------------------------------------
Write-Host "`nDone. Three things left, all by hand:" -ForegroundColor White
Write-Host "  1. Quit Claude Desktop completely - right-click its system tray icon and Quit, not just the X - then reopen it."
Write-Host "  2. In REAPER: Actions > Show action list > Load ReaScript > pick reaper_mcp_bridge.lua > Run."
Write-Host "     REAPER's console should print: REAPER MCP Bridge (File-based, Full API) started"
Write-Host "  3. Ask Claude: how many tracks are in my REAPER project?"
Write-Host "`nRe-run step 2 after every upgrade of the package - the bridge and the server must be the same version." -ForegroundColor Yellow
