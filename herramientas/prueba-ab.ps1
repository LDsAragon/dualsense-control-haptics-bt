# prueba-ab.ps1 - diagnostico: compara el vDS nuevo (con modificaciones) con el anterior.
#   A) sin vDS: bateria y si el joystick se mantiene conectado por Bluetooth
#   B1) vDS nuevo durante 25 s
#   B2) vDS anterior durante 25 s (queda funcionando al terminar)
# Deja marcas de tiempo en logs\prueba-ab.log; Claude las cruza con vdsd.log.
$ErrorActionPreference = "Stop"
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$IsAdmin) {
  Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
  exit 0
}
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Log  = Join-Path $Logs "prueba-ab.log"
"" | Set-Content -LiteralPath $Log -Encoding UTF8
$Py   = Join-Path $Root "app\dshaptics.py"
$Inst = Join-Path $env:ProgramFiles "vDS\vdsd.exe"
$New  = Join-Path $Root ".build\vds\build\windows\Release\vdsd.exe"
$Old  = Join-Path $Root "_anterior\vds\build\windows\Release\vdsd.exe"

function Mark($msg) {
  $line = (Get-Date -Format "yyyy-MM-dd'T'HH:mm:ss.fff") + " " + $msg
  Write-Host $line -ForegroundColor Cyan
  Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
}
function Py([string[]]$argv) {
  $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  $out = & python $Py @argv 2>&1 | ForEach-Object { "$_" }
  $ErrorActionPreference = $old
  foreach ($l in $out) { Write-Host "   $l"; Add-Content -LiteralPath $Log -Value "   $l" -Encoding UTF8 }
}
function Stop-Vdsd {
  & sc.exe stop vdsd | Out-Null
  for ($i = 0; $i -lt 30; $i++) {
    if ((& sc.exe query vdsd 2>&1 | Out-String) -match "STOPPED") { return }
    Start-Sleep -Milliseconds 500
  }
  throw "vdsd no se detuvo"
}
function Run-Phase($name, $exe, $seconds) {
  if (!(Test-Path $exe)) { Mark "$name SALTEADA: no existe $exe"; return }
  Stop-Vdsd
  Copy-Item -LiteralPath $exe -Destination $Inst -Force
  Mark ("$name INICIO exe=" + (Get-Item $Inst).Length + " bytes")
  & sc.exe start vdsd | Out-Null
  for ($t = $seconds; $t -gt 0; $t -= 5) { Write-Host "   ... $t s" ; Start-Sleep -Seconds 5 }
  Mark "$name FIN"
}

try {
  Write-Host ""
  Write-Host "Prueba A/B (unos 90 segundos)." -ForegroundColor Yellow
  Write-Host "Prende el joystick, dejalo quieto y NO abras el panel ni juegos."
  Write-Host "Si se apaga durante la prueba, volve a prenderlo con el boton PS."
  Write-Host ""
  Read-Host "Apreta Enter cuando el joystick este prendido"

  Copy-Item -LiteralPath $Inst -Destination "$Inst.antes-de-prueba" -Force
  Stop-Vdsd
  Mark "A INICIO sin vDS"
  Start-Sleep -Seconds 3
  Py @("bateria")
  for ($i = 1; $i -le 3; $i++) { Start-Sleep -Seconds 4; Mark "A chequeo $i"; Py @("list") }
  Mark "A FIN"

  Run-Phase "B1 vDS-NUEVO" $New 25
  Run-Phase "B2 vDS-ANTERIOR" $Old 25
  Mark "TERMINADO (queda corriendo el vDS anterior)"
  Write-Host ""
  Write-Host "Listo. Avisale a Claude para que lea los resultados." -ForegroundColor Green
}
catch {
  Mark ("ERROR: " + $_.Exception.Message)
}
Read-Host "Apreta Enter para cerrar"
