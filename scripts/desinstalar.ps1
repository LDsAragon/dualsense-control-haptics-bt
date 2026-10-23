# desinstalar.ps1 - detiene vDS, libera el joystick y quita vdsd/vdsctl y su servicio.
# USB/IP y HidHide quedan instalados (se quitan desde Configuracion > Aplicaciones).
$ErrorActionPreference = "Stop"
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$IsAdmin) {
  Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
  exit 0
}
$Root  = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Cmake = Join-Path $Root ".build\vds\build\windows"
try {
  $a = Read-Host "Detener y desinstalar vDS? (S/N)"
  if ($a -notmatch '^[sSyY]') { exit 0 }
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User")
  Write-Host "Deteniendo el servicio (al detenerse, vdsd deja de esconder el joystick)..."
  & sc.exe stop vdsd | Out-Null
  for ($i = 0; $i -lt 20; $i++) {
    if ((& sc.exe query vdsd 2>&1 | Out-String) -notmatch "RUNNING|STOP_PENDING") { break }
    Start-Sleep -Milliseconds 500
  }
  if (Test-Path $Cmake) {
    & cmake --build $Cmake --config Release --target uninstall
    if ($LASTEXITCODE -ne 0) { throw "cmake uninstall fallo (codigo $LASTEXITCODE)" }
  } else {
    & sc.exe delete vdsd | Out-Null
    Remove-Item -Recurse -Force (Join-Path $env:ProgramFiles "vDS") -ErrorAction SilentlyContinue
  }
  Remove-Item -Force (Join-Path $env:ProgramData "vDS\speaker-muted") -ErrorAction SilentlyContinue
  Write-Host "Listo. Si el joystick no aparece, apagalo y prendelo." -ForegroundColor Green
}
catch { Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red }
Read-Host "Apreta Enter para cerrar"
