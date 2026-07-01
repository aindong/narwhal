# Installs the seo-scan skill into your Claude Code skills directory (Windows).
#   User-wide:    ./install.ps1
#   Project-only: ./install.ps1 -Project
param([switch]$Project)

$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "skills\seo-scan"

if ($Project) {
    $dest = Join-Path (Get-Location) ".claude\skills\seo-scan"
} else {
    $dest = Join-Path $HOME ".claude\skills\seo-scan"
}

New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Copy-Item -Recurse -Force $src $dest

Write-Host "Installed seo-scan skill to $dest"
Write-Host "Optional extras: pip install -r `"$(Join-Path $dest 'requirements.txt')`""
