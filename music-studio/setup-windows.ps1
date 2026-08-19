# setup-windows.ps1 — connects Claude Desktop to REAPER in one run.
#
# Five steps, all safe to repeat:
#   1. installs uv (the launcher the MCP server runs under)
#   2. copies the bridge script into REAPER's Scripts folder
#   3. hooks the bridge into REAPER's __startup.lua so it loads by itself
#      on every launch — otherwise it has to be run by hand each time
#   4. merges the "reaper" server into claude_desktop_config.json without
#      touching any other server already configured there
#   5. restarts Claude Desktop so it picks the new config up
#
# Usage:  powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
# Portable REAPER: add  -ReaperScripts "D:\REAPER\Scripts"

[CmdletBinding()]
param(
    [string]$ReaperScripts,
    [switch]$SkipClaudeRestart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step($n, $text) { Write-Host "`n[$n/5] $text" -ForegroundColor Cyan }
function Write-Ok($text)       { Write-Host "    OK  $text" -ForegroundColor Green }
function Write-Skip($text)     { Write-Host "    --  $text" -ForegroundColor DarkGray }

$marker = 'twelvetake-reaper-mcp autostart'

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

# --- 3. autostart --------------------------------------------------------
Write-Step 3 "Making the bridge load itself on every REAPER launch"

$startup = Join-Path $ReaperScripts "__startup.lua"
$alreadyHooked = (Test-Path $startup) -and ((Get-Content $startup -Raw) -match [regex]::Escape($marker))

if ($alreadyHooked) {
    Write-Skip "__startup.lua already hooked up"
} else {
    $block = @'
-- >>> twelvetake-reaper-mcp autostart >>>
-- Loads the MCP bridge when REAPER starts, so it does not have to be run
-- by hand from the action list every session. Delete this block to opt out.
local bridge = reaper.GetResourcePath() .. "/Scripts/reaper_mcp_bridge.lua"
if reaper.file_exists(bridge) then dofile(bridge) end
-- <<< twelvetake-reaper-mcp autostart <<<
'@ + "`n"
    # Someone else's __startup.lua may already be here; append, never overwrite.
    if (Test-Path $startup) {
        Copy-Item $startup "$startup.backup" -Force
        Write-Ok "Backed up existing __startup.lua to __startup.lua.backup"
        $block = "`n" + $block
        Add-Content -Path $startup -Value $block -Encoding UTF8
    } else {
        [System.IO.File]::WriteAllText($startup, $block, (New-Object System.Text.UTF8Encoding($false)))
    }
    Write-Ok $startup
}

# --- 4. Claude Desktop config -------------------------------------------
Write-Step 4 "Registering the server with Claude Desktop"

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

# --- 5. restart Claude Desktop ------------------------------------------
Write-Step 5 "Restarting Claude Desktop"

if ($SkipClaudeRestart) {
    Write-Skip "skipped (-SkipClaudeRestart)"
} else {
    $running = Get-Process -Name "claude" -ErrorAction SilentlyContinue
    if ($running) {
        # CloseMainWindow first so the app can shut down on its own terms;
        # closing the window alone is exactly what leaves it alive in the tray.
        $running | ForEach-Object { $_.CloseMainWindow() | Out-Null }
        Start-Sleep -Seconds 2
        Get-Process -Name "claude" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }

    # Claude Desktop is a Squirrel app, so the exe sits behind a versioned
    # folder. The Start Menu shortcut is the stable way in.
    $candidates = @(
        (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Claude.lnk"),
        (Join-Path $env:LOCALAPPDATA "AnthropicClaude\claude.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Claude\Claude.exe")
    )
    $launched = $false
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            Start-Process $c
            Write-Ok "Claude Desktop restarted"
            $launched = $true
            break
        }
    }
    if (-not $launched) { Write-Skip "Could not find Claude Desktop to relaunch - open it from the Start Menu" }
}

# --- next steps ----------------------------------------------------------
Write-Host "`nDone. Everything that could be automated has been." -ForegroundColor White
Write-Host "`nAll that is left: open REAPER. The bridge now loads itself, and the console"
Write-Host "should print: REAPER MCP Bridge (File-based, Full API) started"
Write-Host "`nThen ask Claude: how many tracks are in my REAPER project?"
Write-Host "`nAfter upgrading the package, run this script again - the bridge and the" -ForegroundColor Yellow
Write-Host "server have to stay on the same version." -ForegroundColor Yellow
