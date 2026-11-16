@echo off
setlocal
title Renderizacao Final - Concertos Corais v2

set "SOURCE=%~1"
if not defined SOURCE set /p "SOURCE=Pasta do concerto: "
if not defined SOURCE goto :missing

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0coral_editor.py" --source "%SOURCE%" --render-final
) else (
  where python >nul 2>nul
  if errorlevel 1 goto :python_missing
  python "%~dp0coral_editor.py" --source "%SOURCE%" --render-final
)
goto :end

:missing
echo ERRO: nenhuma pasta foi informada.
goto :end

:python_missing
echo ERRO: Python 3 nao foi encontrado.

:end
echo.
pause
