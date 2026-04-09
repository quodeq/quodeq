# Build Quodeq.exe for Windows
# Usage: .\packaging\windows\build-exe.ps1
# Prerequisites: Python 3.12+, Node.js, uv

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path "$ScriptDir\..\..").Path
$BuildDir = "$RepoRoot\dist\dashboard-build"
$DistDir = "$RepoRoot\dist"

# Extract version
$Version = python3 -c "import re; print(re.search(r'version = \`"(.+?)\`"', open('$RepoRoot\pyproject.toml').read()).group(1))"
Write-Host "Building Quodeq v$Version..."

# Clean build dir
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

# Step 1: Build web UI (always fresh)
$StaticDir = "$RepoRoot\src\quodeq\static"
if (Test-Path $StaticDir) { Remove-Item -Recurse -Force $StaticDir }
Write-Host "==> Building web UI..."
Push-Location "$RepoRoot\src\quodeq\ui"
npm ci
npm run build
Pop-Location

if (-not (Test-Path "$StaticDir\index.html")) {
    Write-Error "ERROR: UI build failed — no index.html"
    exit 1
}

# Step 2: Bundle with PyInstaller
Write-Host "==> Building exe..."
$env:QUODEQ_REPO_ROOT = $RepoRoot
$env:QUODEQ_VERSION = $Version
uv run --with pyinstaller --with pywebview --with flask --with jsonschema pyinstaller `
    "$ScriptDir\quodeq_dashboard.spec" `
    --distpath "$BuildDir\dist" `
    --workpath "$BuildDir\work"

$ExeDir = "$BuildDir\dist\Quodeq"
if (-not (Test-Path "$ExeDir\Quodeq.exe")) {
    Write-Error "ERROR: Quodeq.exe was not created."
    exit 1
}

Write-Host "  Created $ExeDir\Quodeq.exe"

# Step 3: Copy to dist
$ZipPath = "$DistDir\Quodeq-$Version-Windows.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath }
Compress-Archive -Path "$ExeDir\*" -DestinationPath $ZipPath

$Size = (Get-Item $ZipPath).Length / 1MB
Write-Host ""
Write-Host "==> Done: $ZipPath ($([math]::Round($Size, 1)) MB)"
