@echo off
rem Diagnostico de Windows (Bluetooth, HidHide, USB/IP). Deja logs\diag-windows.txt
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0diag-windows.ps1"
