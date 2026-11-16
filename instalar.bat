@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Editor de Concertos - instalacao local
echo.

if not exist "ffmpeg.exe" (
  where ffmpeg >nul 2>nul
  if errorlevel 1 (
    echo ERRO: FFmpeg nao foi encontrado no PATH nem na pasta do editor.
    pause
    exit /b 1
  )
)
if not exist "ffprobe.exe" (
  where ffprobe >nul 2>nul
  if errorlevel 1 (
    echo ERRO: FFprobe nao foi encontrado no PATH nem na pasta do editor.
    pause
    exit /b 1
  )
)

set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.14 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.14"
  if not defined PY_CMD py -3.13 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.13"
  if not defined PY_CMD py -3.12 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.12"
  if not defined PY_CMD py -3.11 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.11"
  if not defined PY_CMD py -3.10 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.10"
)
if not defined PY_CMD (
  where python >nul 2>nul
  if not errorlevel 1 set "PY_CMD=python"
)
if not defined PY_CMD (
  echo ERRO: Python 3.10 a 3.14 nao foi encontrado.
  pause
  exit /b 1
)

echo Python selecionado:
%PY_CMD% --version

if not exist ".venv\Scripts\pythonw.exe" (
  echo Criando ambiente Python isolado...
  %PY_CMD% -m venv .venv
  if errorlevel 1 goto :erro
)

echo Validando o aplicativo...
".venv\Scripts\python.exe" -m py_compile coral_editor.py
if errorlevel 1 goto :erro

echo.
echo Instalacao concluida. Agora criaremos o atalho na Area de Trabalho.
call "Criar atalho do Editor.bat"
exit /b %errorlevel%

:erro
echo.
echo A instalacao falhou. Consulte as mensagens acima.
pause
exit /b 1
