@echo off
cd /d "%~dp0..\app"
title DualSense - haptica por Bluetooth
rem Usa Bluetooth directo: hace falta el modo normal (modo-normal.bat en la raiz).

rem Si arrastras un archivo de audio sobre este .bat, lo reproduce directo
if not "%~1"=="" (
    python dshaptics.py file "%~1" --lowpass 300 --normalize -v
    pause
    exit /b
)

:menu
cls
echo ============================================
echo    DualSense - haptica por Bluetooth
echo    (en modo normal)
echo ============================================
echo.
echo  EFECTOS
echo   1. Latido
echo   2. Tono continuo
echo   3. Pulsos rapidos
echo   4. Barrido grave a agudo
echo   5. Rumble de motor (en loop)
echo   6. Ping-pong izquierda / derecha
echo   7. Solo motor izquierdo
echo   8. Solo motor derecho
echo.
echo  AUDIO DE LA PC (Ctrl+C para volver)
echo   9. Parlantes EDIFIER  - solo graves
echo  10. Parlantes EDIFIER  - completo
echo  11. Auriculares PRO X2 - solo graves
echo.
echo  OTROS
echo  12. Reproducir un archivo de audio
echo  13. Listar joysticks y salidas de audio
echo   0. Salir
echo.
set "op="
set /p op="Elegi una opcion: "

if "%op%"=="1"  python dshaptics.py fx heartbeat --duration 6 -v
if "%op%"=="2"  python dshaptics.py fx tone --freq 150 --duration 3 -v
if "%op%"=="3"  python dshaptics.py fx pulse --rate 8 --duty 0.3 --duration 4 -v
if "%op%"=="4"  python dshaptics.py fx sweep --duration 6 -v
if "%op%"=="5"  python dshaptics.py fx rumble --loop -v
if "%op%"=="6"  python dshaptics.py fx pingpong --rate 3 --duration 6 -v
if "%op%"=="7"  python dshaptics.py fx tone --side left --duration 3 -v
if "%op%"=="8"  python dshaptics.py fx tone --side right --duration 3 -v
if "%op%"=="9"  python dshaptics.py loopback --device EDIFIER --lowpass 150 -v
if "%op%"=="10" python dshaptics.py loopback --device EDIFIER -v
if "%op%"=="11" python dshaptics.py loopback --device "PRO X2" --lowpass 150 -v
if "%op%"=="12" goto archivo
if "%op%"=="13" python dshaptics.py list
if "%op%"=="0"  exit /b

echo.
pause
goto menu

:archivo
echo.
set "f="
set /p f="Arrastra el archivo a esta ventana y apreta Enter: "
if "%f%"=="" goto menu
python dshaptics.py file %f% --lowpass 300 --normalize -v
echo.
pause
goto menu
