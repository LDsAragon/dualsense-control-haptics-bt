@echo off
rem Diagnostico HID (en modo normal).
cd /d "%~dp0..\app"
python dshaptics.py diag > "%~dp0..\logs\diag.txt" 2>&1
type "%~dp0..\logs\diag.txt"
pause
