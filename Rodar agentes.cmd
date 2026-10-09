@echo off
rem Acorda os agentes do segundo-cerebro ate sobrar so decisao do Arthur (usa o Claude Code desta maquina).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
cerebro rodar --max-turnos 15
echo.
echo Veja o que espera por voce em "Caixa do Arthur" no Obsidian.
pause
