@echo off
setlocal

REM Double-click to remove the WeChatAutoLogin task.
REM Also self-elevates (see install_task.bat).

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator privileges...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_task.ps1"
if errorlevel 1 (
  echo [ERROR] uninstall failed. See messages above.
)
pause