@echo off
rem Quita vDS y su servicio.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\desinstalar.ps1"
