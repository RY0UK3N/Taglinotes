param([switch]$ApiOnly)
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/pythonw.exe'
if (!(Test-Path -LiteralPath $runtime)) { $runtime = (Get-Command pythonw.exe -ErrorAction Stop).Source }
$healthy = $false
try { $healthy = (Invoke-RestMethod 'http://127.0.0.1:8765/health' -TimeoutSec 2).app -eq 'Taglinotes' } catch {}
if (!$healthy) {
    Start-Process -FilePath $runtime -ArgumentList ('"' + (Join-Path $PSScriptRoot 'api.py') + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
}
if (!$ApiOnly) {
    Start-Process -FilePath $runtime -ArgumentList ('"' + (Join-Path $PSScriptRoot 'taglinotes.py') + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
}
