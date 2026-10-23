@echo off
rem Regenera vDS desde cero con nuestras modificaciones y lo reinstala.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\instalar.ps1" -SoloVds
