@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Требуется Python 3.10 или новее. Установите Python и повторите запуск.
  pause
  exit /b 1
)
if exist "%LOCALAPPDATA%\KonturCopilot\access\ssh-key-1794553696842" (
  python -X utf8 vm_tunnel.py
  if errorlevel 1 pause
  exit /b
)
if not exist .env copy .env.example .env >nul
python -X utf8 server.py --open
pause
