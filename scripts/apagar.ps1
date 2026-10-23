# apagar.ps1 - apaga el/los DualSense conectados por Bluetooth. Si Windows lo niega, reintenta como admin.
$App = Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) "app"
& python (Join-Path $App "dshaptics.py") apagar
if ($LASTEXITCODE -eq 5) {
  Write-Host "Hace falta permiso de administrador, reintentando..."
  Start-Process python -Verb RunAs -Wait -WorkingDirectory $App -ArgumentList "`"$(Join-Path $App 'dshaptics.py')`" apagar"
}
Start-Sleep -Seconds 2
