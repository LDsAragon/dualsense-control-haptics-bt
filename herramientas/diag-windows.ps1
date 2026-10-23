# diag-windows.ps1 - junta lo que Windows sabe del joystick, Bluetooth, HidHide y USB/IP.
# Resultado: logs\diag-windows.txt (para que Claude lo lea). No cambia nada.
param([string]$Out = "")
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$IsAdmin) {
  $fwd = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
  if ($Out) { $fwd += " -Out `"$Out`"" }
  Start-Process powershell.exe -Verb RunAs -ArgumentList $fwd
  exit 0
}
if (!$Out) {
  $Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
  $Logs = Join-Path $Root "logs"
  New-Item -ItemType Directory -Force -Path $Logs | Out-Null
  $Out  = Join-Path $Logs "diag-windows.txt"
}
$since = (Get-Date).AddHours(-3)

function Section($title, [scriptblock]$body) {
  "`r`n===== $title =====" | Out-File -FilePath $Out -Append -Encoding utf8
  try { & $body 2>&1 | Out-String -Width 400 | Out-File -FilePath $Out -Append -Encoding utf8 }
  catch { "ERROR: $($_.Exception.Message)" | Out-File -FilePath $Out -Append -Encoding utf8 }
}

"diag-windows $(Get-Date -Format s)  $([Environment]::OSVersion.VersionString)" | Out-File -FilePath $Out -Encoding utf8
Write-Host "Juntando informacion (unos segundos)..."

Section "Programas que suelen tomar joysticks" {
  Get-Process | Where-Object { $_.ProcessName -match 'steam|ds4|dsx|dualsense|rewasd|padforge|x360|joy|parsec|vigem|hidhide|gamebar|xbox|epic|ea|ubisoft|battle|discord|playstation|remoteplay|chiaki|moonlight|sunshine' } |
    Select-Object ProcessName, Id, StartTime, Path | Sort-Object StartTime | Format-Table -AutoSize
}
Section "Servicio vdsd" { & sc.exe query vdsd; & sc.exe qc vdsd }
Section "Dispositivos DualSense / Wireless Controller / USB-IP" {
  Get-PnpDevice -PresentOnly:$false | Where-Object { $_.FriendlyName -match 'DualSense|Wireless Controller|USB/IP|usbip|UDE|HidHide' -or $_.InstanceId -match '054C|0CE6|00001124' } |
    Select-Object Status, Class, FriendlyName, InstanceId | Format-Table -AutoSize
}
Section "Radios Bluetooth" {
  Get-PnpDevice -Class Bluetooth | Select-Object Status, FriendlyName, InstanceId | Format-Table -AutoSize
}
Section "HidHide" {
  $cli = Join-Path $env:ProgramFiles "Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe"
  if (Test-Path $cli) {
    "cloak:";  & $cli --cloak-state
    "apps:";   & $cli --app-list
    "devs:";   & $cli --dev-list
  } else { "No encontre $cli" }
}
Section "USB/IP: puertos importados" {
  $u = Join-Path $env:ProgramFiles "USBip\usbip.exe"
  if (Test-Path $u) { & $u port } else { "No encontre $u" }
}
Section "Eventos de Bluetooth / dispositivos (ultimas 3 h)" {
  Get-WinEvent -FilterHashtable @{ LogName = 'System'; StartTime = $since } -ErrorAction SilentlyContinue |
    Where-Object { $_.ProviderName -match 'BTH|Bluetooth|Kernel-PnP|HidHide|usbip|Ude|USB|HID|Power' } |
    Select-Object -First 300 TimeCreated, ProviderName, Id, LevelDisplayName,
      @{ n = 'Mensaje'; e = { ($_.Message -replace '\s+', ' ').Substring(0, [Math]::Min(300, ($_.Message -replace '\s+', ' ').Length)) } } |
    Format-Table -AutoSize -Wrap
}
Section "Kernel-PnP Configuration (ultimas 3 h, solo DualSense/BT/USBIP)" {
  Get-WinEvent -FilterHashtable @{ LogName = 'Microsoft-Windows-Kernel-PnP/Configuration'; StartTime = $since } -ErrorAction SilentlyContinue |
    Where-Object { $_.Message -match '054C|0CE6|00001124|DualSense|usbip|USBIP|BTHENUM' } |
    Select-Object -First 200 TimeCreated, Id,
      @{ n = 'Mensaje'; e = { ($_.Message -replace '\s+', ' ').Substring(0, [Math]::Min(300, ($_.Message -replace '\s+', ' ').Length)) } } |
    Format-Table -AutoSize -Wrap
}
Section "Programas instalados o actualizados hoy" {
  Get-WinEvent -FilterHashtable @{ LogName = 'Application'; ProviderName = 'MsiInstaller'; StartTime = (Get-Date).Date } -ErrorAction SilentlyContinue |
    Select-Object -First 50 TimeCreated, Id, @{ n = 'Mensaje'; e = { ($_.Message -replace '\s+', ' ').Substring(0, [Math]::Min(200, ($_.Message -replace '\s+', ' ').Length)) } } |
    Format-Table -AutoSize -Wrap
  Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
    ForEach-Object { Get-ItemProperty $_.PSPath } |
    Where-Object { $_.InstallDate -eq (Get-Date -Format yyyyMMdd) } |
    Select-Object DisplayName, DisplayVersion, InstallDate | Format-Table -AutoSize
}
Write-Host "Listo: $Out" -ForegroundColor Green
if (!$env:DSC_SIN_PAUSA) { Start-Sleep -Seconds 3 }
