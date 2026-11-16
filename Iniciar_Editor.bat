@echo off
setlocal
title Editor de Concertos Corais v2

set "SOURCE=%~1"
if not defined SOURCE (
  echo Arraste a pasta do concerto sobre este arquivo ou informe o caminho abaixo.
  set /p "SOURCE=Pasta do concerto: "
)
if not defined SOURCE goto :missing

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0coral_editor.py" --source "%SOURCE%"
) else (
  where python >nul 2>nul
  if errorlevel 1 goto :python_missing
  python "%~dp0coral_editor.py" --source "%SOURCE%"
)
goto :end

:missing
echo ERRO: nenhuma pasta foi informada.
goto :end

:python_missing
echo ERRO: Python 3 nao foi encontrado.
echo Instale o Python 3 e marque a opcao Add Python to PATH.

:end
echo.
pause
