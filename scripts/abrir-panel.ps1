# abrir-panel.ps1 - abre DualSense Control como administrador (lo necesita para manejar el servicio).
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$IsAdmin) {
  Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`""
  exit 0
}
$App = Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) "app"
$pyw = Get-Command pythonw -ErrorAction SilentlyContinue
$exe = if ($pyw) { $pyw.Source } else { "python" }
Start-Process $exe -WorkingDirectory $App -ArgumentList "`"$(Join-Path $App 'dsgui.py')`""
