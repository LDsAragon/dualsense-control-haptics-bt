@echo off
rem Vuelve el DualSense a joystick Bluetooth comun (Steam, otros juegos, PS5). Sobrevive al reinicio.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\modo.ps1" -Modo normal
