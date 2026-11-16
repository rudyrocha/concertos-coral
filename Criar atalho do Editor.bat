@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "EDITOR_APP=%~dp0"
set "EDITOR_TARGET=%~dp0Editor de Concertos.vbs"
set "EDITOR_ICON=%~dp0assets\Editor_Concertos.ico"

if not exist "%EDITOR_TARGET%" (
  echo ERRO: lancador nao encontrado:
  echo "%EDITOR_TARGET%"
  pause
  exit /b 2
)
if not exist "%EDITOR_ICON%" (
  echo ERRO: icone nao encontrado:
  echo "%EDITOR_ICON%"
  pause
  exit /b 2
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { $desktop=[Environment]::GetFolderPath('DesktopDirectory'); if (-not $desktop) { throw 'Area de Trabalho nao localizada' }; $link=Join-Path $desktop 'Editor de Concertos.lnk'; $shell=New-Object -ComObject WScript.Shell; $shortcut=$shell.CreateShortcut($link); $shortcut.TargetPath=$env:EDITOR_TARGET; $shortcut.WorkingDirectory=$env:EDITOR_APP; $shortcut.IconLocation=$env:EDITOR_ICON + ',0'; $shortcut.Description='Editor de Concertos - Coral Paineiras'; $shortcut.Save(); Write-Host ('Atalho criado ou atualizado: ' + $link) } catch { Write-Error $_; exit 1 }"

if errorlevel 1 (
  echo ERRO: nao foi possivel criar o atalho.
  pause
  exit /b 1
)

echo.
echo Atalho configurado com o logo do Clube Paineiras.
echo Se o icone anterior permanecer, atualize a Area de Trabalho com F5.
pause
exit /b 0
