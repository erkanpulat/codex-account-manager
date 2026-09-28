$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath ".venv/Scripts/python.exe")) {
        $created = $false
        if (Get-Command py -ErrorAction SilentlyContinue) {
            foreach ($version in @("-3.13", "-3.12", "-3.11")) {
                # An unavailable interpreter writes stderr; PS 5.1 must still try the next one.
                $probeErrorPreference = $ErrorActionPreference
                try {
                    $ErrorActionPreference = "SilentlyContinue"
                    & py $version -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,14)" 2>$null
                    $supported = $LASTEXITCODE -eq 0
                } finally {
                    $ErrorActionPreference = $probeErrorPreference
                }
                if ($supported) {
                    & py $version -m venv .venv
                    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
                    $created = $true
                    break
                }
            }
        }
        if (-not $created) {
            & python -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,14)"
            if ($LASTEXITCODE -ne 0) { throw "Install Python 3.11-3.13 before continuing." }
            & python -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
        }
    }
    $venvPython = Join-Path $projectRoot ".venv/Scripts/python.exe"
    & $venvPython -m pip install -e ".[gui]"
    if ($LASTEXITCODE -ne 0) { throw "Installation failed." }
    & $venvPython -m codex_account_manager.cli.main init
    if ($LASTEXITCODE -ne 0) { throw "Database initialization failed." }
    & $venvPython -m codex_account_manager.core.windows_shell $projectRoot
    if ($LASTEXITCODE -ne 0) { throw "Shortcut creation failed." }
    Write-Host "Ready. Open Codex Account Manager from your desktop or Start menu." -ForegroundColor Green
} finally {
    Pop-Location
}
