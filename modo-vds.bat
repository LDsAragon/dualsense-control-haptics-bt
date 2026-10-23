@echo off
rem Joystick virtual USB con haptica nativa. vDS arranca con Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\modo.ps1" -Modo vds
