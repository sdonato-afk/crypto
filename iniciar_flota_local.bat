@echo off
echo ========================================================
echo INICIANDO FLOTA MAESTRA LOCAL (2 NODOS ASIMETRICOS)
echo ========================================================
echo.

echo Borrando estados fantasmas anteriores...
del estado_A.json 2>nul
del estado_B.json 2>nul
echo.

echo Levantando Nodo A (Top 1-50) en Puerto 5000...
set PORT=5000
set NO_BROWSER=1
set UNIVERSE_START=0
set UNIVERSE_END=50
set TAKE_PROFIT_PCT=9.0
set STOP_LOSS_PCT=4.0
set TRAILING_STAGE_1_LOCK=0.3
set BREAKEVEN_EXIT=0.3
set TRAILING_STAGE_2_LOCK=4.0
set TRAILING_LOCK_EXIT=3.9
set STATE_FILE_NAME=estado_A.json
start "Nodo A - Puerto 5000" cmd /c "python run_system.py"

timeout /t 2 /nobreak >nul

echo Levantando Nodo B (Top 51-100) en Puerto 5001...
set PORT=5001
set UNIVERSE_START=50
set UNIVERSE_END=100
set TAKE_PROFIT_PCT=12.0
set STOP_LOSS_PCT=7.0
set TRAILING_STAGE_1_LOCK=0.5
set BREAKEVEN_EXIT=0.5
set TRAILING_STAGE_2_LOCK=5.0
set TRAILING_LOCK_EXIT=4.8
set STATE_FILE_NAME=estado_B.json
start "Nodo B - Puerto 5001" cmd /c "python run_system.py"

echo.
echo Abriendo Dashboard Maestro...
start dashboard_maestro.html
echo Listo. Puedes monitorear la flota desde el Dashboard.
