@echo off
rem Diagnostico: vDS nuevo vs anterior (deja logs\prueba-ab.log)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0prueba-ab.ps1"
