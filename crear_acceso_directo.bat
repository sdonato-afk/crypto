@echo off
title Actualizar Acceso Directo a la Nube (Render)
color 0B

cd /d "%~dp0"

echo =================================================================
echo   [+] INSTALADOR DE ACCESO DIRECTO CLOUD EN ESCRITORIO
echo =================================================================
echo.
echo Vinculando icono a tu servidor 24/7 en Render...

powershell -ExecutionPolicy Bypass -Command "$desktop = [System.Environment]::GetFolderPath('Desktop'); $shortcutPath = Join-Path -Path $desktop -ChildPath 'Sistema Cripto Trading (Top 20).lnk'; $wshell = New-Object -ComObject WScript.Shell; $s = $wshell.CreateShortcut($shortcutPath); $s.TargetPath = 'https://crypto-3d7e.onrender.com/dashboard_cripto.html'; $s.Description = 'Sistema Cripto Trading 24/7 en la Nube (Render Cloud)'; $s.Save(); Write-Host 'Acceso directo a la Nube actualizado con éxito!'"

echo.
echo =================================================================
echo   ¡Listo! El icono 'Sistema Cripto Trading (Top 20)' en tu
echo   Escritorio ahora abre directamente tu servidor 24/7 en Render.
echo =================================================================
echo.
