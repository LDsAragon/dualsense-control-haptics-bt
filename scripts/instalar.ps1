# instalar.ps1 - instala TODO, de cero, y se puede volver a correr cuando quieras.
#
#   1. Dependencias de Python del panel
#   2. Herramientas de compilacion (Git, CMake, Visual C++ Build Tools + vcpkg)
#   3. vDS: clon limpio en el commit fijado + nuestras modificaciones (vds-mods\*.patch)
#   4. Compilar vDS
#   5. Drivers: USB/IP (usbip-win2) y HidHide
#   6. Instalar vDS (reemplaza lo que haya) y arrancar el servicio
#   7. Conectar el DualSense como joystick virtual
#
# -SoloVds  : solo los pasos 3, 4 y 6 (regenerar y reinstalar vDS).
# -Binarios : instalar vDS ya compilado (lo usa DualSenseControl.exe): saltea 1-4.
#             -Paquete es la carpeta con los scripts de instalacion de vDS (install_service.ps1, etc.)
# -Logs     : carpeta de registros (default: logs\ junto al proyecto)
# Registro: logs\instalar.log

param([switch]$SoloVds, [string]$Binarios = "", [string]$Paquete = "", [string]$Logs = "")

$ErrorActionPreference = "Stop"

# Elevarse solo (asi el .bat no tiene que lidiar con comillas ni espacios)
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$IsAdmin) {
  $fwd = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
  if ($SoloVds) { $fwd += " -SoloVds" }
  if ($Binarios) { $fwd += " -Binarios `"$Binarios`" -Paquete `"$Paquete`"" }
  if ($Logs) { $fwd += " -Logs `"$Logs`"" }
  Start-Process powershell.exe -Verb RunAs -ArgumentList $fwd
  exit 0
}

$Root    = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$FromBin = [bool]$Binarios
if (!$Logs) { $Logs = Join-Path $Root "logs" }
$BuildDir= if ($FromBin) { Join-Path $env:TEMP "DualSenseControl" } else { Join-Path $Root ".build" }
$Src     = Join-Path $BuildDir "vds"
$Cmake   = Join-Path $Src "build\windows"
$Mods    = Join-Path $Root "vds-mods"
$App     = Join-Path $Root "app"
$VdsDir  = Join-Path $env:ProgramFiles "vDS"
$Ctl     = Join-Path $VdsDir "vdsctl.exe"
$Repo    = "https://github.com/hurryman2212/vds.git"
New-Item -ItemType Directory -Force -Path $Logs, $BuildDir | Out-Null
$Log = Join-Path $Logs "instalar.log"
"" | Set-Content -LiteralPath $Log -Encoding UTF8

function Say($msg, $color = "Cyan") {
  $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
  Write-Host $line -ForegroundColor $color
  Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
}
function Run($exe, [string[]]$argv) {
  Add-Content -LiteralPath $Log -Value ("> " + $exe + " " + ($argv -join " ")) -Encoding UTF8
  $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  $out = & $exe @argv 2>&1 | ForEach-Object { "$_" }
  $code = $LASTEXITCODE
  $ErrorActionPreference = $old
  foreach ($l in $out) { Write-Host $l; Add-Content -LiteralPath $Log -Value $l -Encoding UTF8 }
  $script:LastOut = ($out -join "`n")
  return $code
}
function Must($code, $what) { if ($code -ne 0) { throw "$what fallo (codigo $code)" } }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User")
}
$script:Paso = 0
$script:Pasos = if ($FromBin) { 3 } elseif ($SoloVds) { 4 } else { 7 }
function Step($title) {
  $script:Paso++
  Say "== $($script:Paso)/$($script:Pasos) $title =="
}
function Finish($code) { Write-Host ""; Read-Host "Apreta Enter para cerrar"; exit $code }

function Winget-Ensure($id, [string[]]$extra = @()) {
  $list = (winget list --exact --id $id --accept-source-agreements 2>&1 | Out-String)
  if ($list.Contains($id)) { Say "  ${id}: ya esta"; return }
  Say "  Instalando ${id}..."
  $code = Run "winget" (@("install", "--exact", "--id", $id, "--source", "winget",
                          "--accept-package-agreements", "--accept-source-agreements") + $extra)
  if ($code -ne 0 -and $code -ne -1978335189) { throw "winget no pudo instalar $id (codigo $code)" }
}
function Find-VS {
  $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
  if (!(Test-Path $vswhere)) { return $null }
  $p = & $vswhere -latest -products "*" `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 Microsoft.VisualStudio.Component.Vcpkg `
        -property installationPath
  if ($p) { return $p.Trim() } else { return $null }
}
function Wait-Service($state, $seconds = 10) {
  for ($i = 0; $i -lt $seconds * 2; $i++) {
    if ((& sc.exe query vdsd 2>&1 | Out-String) -match $state) { return $true }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

try {
  if (![Environment]::Is64BitOperatingSystem) { throw "Hace falta Windows de 64 bits." }
  Refresh-Path

  if (!$SoloVds) {
    Write-Host ""
    Write-Host "Esto instala todo lo necesario. Cosas a saber:" -ForegroundColor Yellow
    if (!$FromBin) { Write-Host "  - La primera vez descarga Visual C++ Build Tools (varios GB) y tarda." }
    Write-Host "  - Instalar USB/IP reinicia los hubs USB: tus dispositivos USB se cortan unos segundos."
    Write-Host "  - Si Windows pide reiniciar, reinicia y volve a correr la instalacion: sigue sola."
    Write-Host ""
    $a = Read-Host "Seguimos? (S/N)"
    if ($a -notmatch '^[sSyY]') { Say "Cancelado."; Finish 0 }
  }
  if (!$SoloVds -and !$FromBin) {
    # ---- 1. Python ------------------------------------------------------
    Step "Python"
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (!$py) { throw "No encontre Python. Instalalo desde python.org (tilda 'Add Python to PATH')." }
    Must (Run "python" @("-m", "pip", "install", "-q", "-r", (Join-Path $App "requirements.txt"))) "pip install"

    # ---- 2. Herramientas ------------------------------------------------
    Step "Herramientas de compilacion"
    if (!(Get-Command winget -ErrorAction SilentlyContinue)) {
      throw "No encontre winget. Instala 'App Installer' desde Microsoft Store."
    }
    Winget-Ensure "Git.Git"
    Winget-Ensure "Kitware.CMake"
    Winget-Ensure "Microsoft.VCRedist.2015+.x64"
    if (!(Find-VS)) {
      $components = @("--add", "Microsoft.VisualStudio.Workload.VCTools",
                      "--add", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                      "--add", "Microsoft.VisualStudio.Component.Vcpkg", "--includeRecommended")
      $existing = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" `
                    -latest -products "*" -property installationPath 2>$null
      if ($existing) {
        Say "  Agregando componentes a Visual Studio ($($existing.Trim()))..."
        $setup = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\setup.exe"
        $code = Run $setup (@("modify", "--installPath", $existing.Trim(), "--passive", "--norestart") + $components)
        if ($code -ne 0 -and $code -ne 3010) { throw "El instalador de Visual Studio fallo (codigo $code)" }
      } else {
        Say "  Instalando Visual C++ Build Tools 2022 (tarda bastante)..."
        Winget-Ensure "Microsoft.VisualStudio.2022.BuildTools" @("--override", ("--passive --wait --norestart " + ($components -join " ")))
      }
    }
    Refresh-Path
  }
  if (!$FromBin) {
  $vs = Find-VS
  if (!$vs) { throw "Falta Visual C++ Build Tools con vcpkg. Corre instalar.bat completo." }
  Say "Visual Studio: $vs"

  # ---- 3. Fuente de vDS limpia + modificaciones ---------------------------
  Step "vDS: fuente limpia + modificaciones"
  $commit = (Get-Content -LiteralPath (Join-Path $Mods "VDS_COMMIT") -TotalCount 1).Trim()
  if (Test-Path (Join-Path $Src ".git")) {
    Must (Run "git" @("-C", $Src, "fetch", "-q", "origin")) "git fetch"
  } else {
    Must (Run "git" @("-c", "core.autocrlf=false", "clone", "-q", $Repo, $Src)) "git clone"
  }
  Must (Run "git" @("-C", $Src, "config", "core.autocrlf", "false")) "git config"
  # volver exactamente al commit fijado, sin restos de compilaciones o parches anteriores
  Must (Run "git" @("-C", $Src, "-c", "advice.detachedHead=false", "checkout", "-q", "--force", $commit)) "git checkout"
  Must (Run "git" @("-C", $Src, "reset", "-q", "--hard", $commit)) "git reset"
  Must (Run "git" @("-C", $Src, "clean", "-q", "-fd", "-e", "build/")) "git clean"
  $patches = @(Get-ChildItem -LiteralPath $Mods -Filter "*.patch" | Sort-Object Name)
  foreach ($p in $patches) {
    if ((Run "git" @("-C", $Src, "apply", "--check", $p.FullName)) -ne 0) {
      throw "La modificacion $($p.Name) no aplica sobre vDS $commit."
    }
    Must (Run "git" @("-C", $Src, "apply", $p.FullName)) "git apply $($p.Name)"
    Say "  Aplicada: $($p.Name)"
  }
  Say "  vDS $($commit.Substring(0, 7)) + $($patches.Count) modificacion(es)"

  # ---- 4. Compilar ----------------------------------------------------------
  Step "Compilar vDS"
  $toolchain = Join-Path $vs "VC\vcpkg\scripts\buildsystems\vcpkg.cmake"
  Must (Run "cmake" @("-S", $Src, "-B", $Cmake, "-DINSTALL_SERVICE=YES", "-DCMAKE_TOOLCHAIN_FILE=$toolchain")) "cmake configure"
  Must (Run "cmake" @("--build", $Cmake, "--config", "Release", "--parallel")) "Compilacion"
  }

  # ---- 5. Drivers -----------------------------------------------------------
  if (!$SoloVds) {
    Step "USB/IP y HidHide"
    $deps = if ($FromBin) { Join-Path $Paquete "install_dependencies.ps1" } else { Join-Path $Src "packaging\windows\install_dependencies.ps1" }
    $dl   = Join-Path $BuildDir "descargas"
    $dlog = Join-Path $Logs "instalar-drivers.log"
    foreach ($mode in "Download", "Install") {
      & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $deps -Mode $mode -DownloadDir $dl -LogPath $dlog
      $code = $LASTEXITCODE
      if ($mode -eq "Install" -and $code -eq 3010) {
        Say "Windows necesita REINICIAR para terminar con los drivers." "Yellow"
        Say "Reinicia y volve a correr la instalacion: sigue desde aca." "Yellow"
        Finish 0
      }
      if ($code -ne 0) { throw "Drivers ($mode) fallo con codigo $code. Mira $dlog" }
    }
    Say "  USB/IP y HidHide listos."
  }

  # ---- 6. Instalar vDS (reemplaza) -------------------------------------------
  Step "Instalar vDS y arrancar el servicio"
  if ($FromBin) {
    # lo mismo que hace 'cmake --install' de vDS en Windows
    Must (Run "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Paquete "stop_service.ps1"), "-ServiceName", "vdsd")) "detener vdsd"
    New-Item -ItemType Directory -Force -Path $VdsDir | Out-Null
    foreach ($f in "vdsd.exe", "vdsctl.exe", "opus.dll") {
      Copy-Item -LiteralPath (Join-Path $Binarios $f) -Destination (Join-Path $VdsDir $f) -Force
      Say "  copiado: $f"
    }
    Must (Run "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Paquete "install_service.ps1"), "-BinaryPath", (Join-Path $VdsDir "vdsd.exe"))) "registrar el servicio"
  } else {
    Must (Run "cmake" @("--install", $Cmake, "--config", "Release")) "cmake --install"
  }
  & sc.exe start vdsd | Out-Null
  if (!(Wait-Service "RUNNING")) { throw "El servicio vdsd no arranco. Mira $env:ProgramData\vDS\vdsd.log" }
  $exe = [System.Text.Encoding]::GetEncoding(28591).GetString([System.IO.File]::ReadAllBytes((Join-Path $VdsDir "vdsd.exe")))
  if (!$exe.Contains("speaker-muted")) { throw "El vdsd.exe instalado no trae las modificaciones." }
  Say "  vdsd en marcha, con nuestras modificaciones."

  # ---- 7. Joystick ------------------------------------------------------------
  Step "Conectar el DualSense"
  Start-Sleep -Seconds 1
  $null = Run $Ctl @("list-targets")
  $targets = @($script:LastOut -split "`n" | Where-Object { $_ -match '^\s*\{' } | ForEach-Object { $_ | ConvertFrom-Json })
  $registered = @($targets | Where-Object { $_.registered })
  if ($registered.Count -gt 0) {
    Say "  Ya registrado: $(($registered | ForEach-Object { $_.address }) -join ', ')"
  } else {
    $online = @($targets | Where-Object { $_.online })
    if ($online.Count -eq 0) {
      Say "No hay un DualSense encendido y emparejado. Prendelo (por Bluetooth) y conectalo desde el panel." "Yellow"
      Finish 0
    }
    $pick = $online[0]
    if ($online.Count -gt 1) {
      for ($i = 0; $i -lt $online.Count; $i++) { Write-Host "  $i) $($online[$i].address) $($online[$i].name)" }
      $pick = $online[[int](Read-Host "Cual conecto? (numero)")]
    }
    # Sin --ports: en Windows vDS ec53159 rechaza cualquier --ports (ver docs\BITACORA.md)
    $null = Run $Ctl @("attach", $pick.address, "--profile", "ds5")
    if ($script:LastOut -notmatch '"OK":true') { throw "vdsctl attach fallo: $($script:LastOut)" }
  }
  $connected = $false
  for ($i = 0; $i -lt 20 -and !$connected; $i++) {
    Start-Sleep -Seconds 1
    $null = Run $Ctl @("list")
    $connected = $script:LastOut -match '"connected":true'
  }
  if (!$connected) { Say "Registrado, pero todavia no conecto. Revisalo en el panel." "Yellow"; Finish 1 }

  Say ("LISTO. " + $(if ($FromBin) { "Ya podes usar DualSense Control." } else { "Abri el panel con abrir-panel.bat." })) "Green"
  Finish 0
}
catch {
  Say ("ERROR: " + $_.Exception.Message) "Red"
  Say "Detalle en $Log (el boton 'Reportar problema' del panel lo junta todo)." "Red"
  Finish 1
}
