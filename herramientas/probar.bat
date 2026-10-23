@echo off
rem Prueba rapida por Bluetooth directo (en modo normal).
cd /d "%~dp0..\app"
python dshaptics.py fx heartbeat -v
python dshaptics.py fx sweep
python dshaptics.py fx pingpong --rate 3
pause
