@echo off
title Publicar Bot Cripto en GitHub (sdonato-afk/crypto)
color 0A

cd /d "%~dp0"

echo =================================================================
echo   [+] SUBIENDO ARCHIVOS A GITHUB: sdonato-afk/crypto
echo =================================================================
echo.

git init
git add .
git commit -m "Deploy Bot Cripto 10 Slots v1.0"
git branch -M main
git remote add origin https://github.com/sdonato-afk/crypto.git
git push -u origin main --force

echo.
echo =================================================================
echo   ¡LISTO! Todos los archivos fueron subidos a GitHub.
echo =================================================================
pause
