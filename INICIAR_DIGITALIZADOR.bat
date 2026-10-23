@echo off
title Digitalizacion y Auditoria de Vacunacion - Jardines 3F
color 1F

echo =========================================================================
echo   MUNICIPALIDAD DE TRES DE FEBRERO
echo   Sistema de Digitalizacion y Auditoria Inteligente de Vacunacion
echo =========================================================================
echo.
echo Iniciando el servidor local y abriendo el panel en el navegador...
echo.

cd /d "%~dp0"
python main.py

pause
