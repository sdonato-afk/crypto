@echo off
title Sistema Cripto Trading - Bot Binance (10 Slots Paper Trading)
color 0B

cd /d "%~dp0"

echo =================================================================
echo   [+] INICIANDO BOT CRIPTO DE TRADING (10 SLOTS SIMULTANEOS)
echo   [+] MODO: PAPER TRADING EN VIVO ($1,000 USDT)
echo   [+] ESTRATEGIA: ABSORCION DE VOLUMEN + OCO SERVER-SIDE
echo =================================================================
echo.

python run_system.py

pause
