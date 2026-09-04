@echo off
title Crear Acceso Directo del Sistema Cripto Trading
color 0B

cd /d "%~dp0"

echo =================================================================
echo   [+] INSTALADOR DE ACCESO DIRECTO EN ESCRITORIO (CRIPTO TRADING)
echo =================================================================
echo.
echo Creando acceso directo en el Escritorio...

powershell -ExecutionPolicy Bypass -Command "$desktop = [System.Environment]::GetFolderPath('Desktop'); $shortcutPath = Join-Path -Path $desktop -ChildPath 'Sistema Cripto Trading (Top 20).lnk'; $wshell = New-Object -ComObject WScript.Shell; $s = $wshell.CreateShortcut($shortcutPath); $s.TargetPath = '%~dp0iniciar_cripto_bot.bat'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'Sistema Cripto Trading v1.0 - Bot Binance 10 Slots (+6% TP / -2% SL)'; $s.Save(); Write-Host 'Acceso directo creado con éxito!'"

echo.
echo =================================================================
echo   ¡Listo! Se ha creado el icono 'Sistema Cripto Trading (Top 20)'
echo   en el Escritorio de esta computadora.
echo =================================================================
echo.
