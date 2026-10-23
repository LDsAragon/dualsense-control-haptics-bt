# modo.ps1 - cambia entre los dos modos del joystick (y el cambio sobrevive a reiniciar).
#   -Modo normal : DualSense Bluetooth comun. Detiene vDS, le saca el arranque automatico,
#                  se asegura de que HidHide no lo esconda y apaga los gatillos adaptativos.
#   -Modo vds    : joystick virtual USB (haptica nativa en juegos). vDS arranca con Windows.
param(
  [ValidateSet("normal", "vds")][string]$Modo = "normal",
  [switch]$SinPausa,
  [switch]$SinRestablecer      # el panel / .exe restablece los gatillos por su cuenta
)
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$IsAdmin) {
  $fwd = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Modo $Modo"
  if ($SinPausa) { $fwd += " -SinPausa" }
  if ($SinRestablecer) { $fwd += " -SinRestablecer" }
  Start-Process powershell.exe -Verb RunAs -ArgumentList $fwd
  exit 0
}
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Py   = Join-Path $Root "app\dshaptics.py"
$Cli  = Join-Path $env:ProgramFiles "Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe"
$code = 0

function Wait-Service($pattern, $seconds = 10) {
  for ($i = 0; $i -lt $seconds * 2; $i++) {
    if ((& sc.exe query vdsd 2>&1 | Out-String) -match $pattern) { return $true }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

try {
  if ($Modo -eq "normal") {
    Write-Host "Pasando a modo normal..."
    & sc.exe stop vdsd | Out-Null
    if (!(Wait-Service "STOPPED|1060")) { throw "vdsd no se detuvo" }
    & sc.exe config vdsd start= demand | Out-Null
    # vdsd libera el joystick al detenerse; por las dudas, sacar de HidHide cualquier DualSense que quede
    if (Test-Path $Cli) {
      foreach ($line in (& $Cli --dev-list 2>$null)) {
        $path = "$line".Trim().Trim('"')
        if ($path -match '054C') { & $Cli --dev-unhide $path | Out-Null; Write-Host "  HidHide: liberado $path" }
      }
    }
    if (!$SinRestablecer -and (Test-Path $Py)) {
      Start-Sleep -Seconds 2
      $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
      & python $Py restablecer 2>&1 | ForEach-Object { Write-Host "  $_" }
      $ErrorActionPreference = $old
    }
    Write-Host "Modo normal: el DualSense es un joystick Bluetooth comun. vDS ya no arranca con Windows." -ForegroundColor Green
  } else {
    Write-Host "Pasando a modo vDS..."
    & sc.exe config vdsd start= auto | Out-Null
    & sc.exe start vdsd | Out-Null
    if (!(Wait-Service "RUNNING")) { throw "vdsd no arranco. Mira $env:ProgramData\vDS\vdsd.log" }
    Write-Host "Modo vDS: joystick virtual USB, y vDS arranca con Windows." -ForegroundColor Green
  }
}
catch {
  Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
  $code = 1
}
if (!$SinPausa) { Start-Sleep -Seconds 3 }
exit $code
