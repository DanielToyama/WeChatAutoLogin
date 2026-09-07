@echo off
setlocal

REM Double-click to register the WeChatAutoLogin "at logon" scheduled task
REM (earlier and more reliable than the Startup folder).
REM
REM Note: creating a scheduled task requires administrator privileges on
REM some systems (Group Policy / hardening). This script self-elevates:
REM if not already admin it re-launches itself with a UAC prompt.

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator privileges...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_task.ps1"
if errorlevel 1 (
  echo [ERROR] install failed. See messages above.
) else (
  echo.
  echo Verify with:  schtasks /Query /TN WeChatAutoLogin /V /FO LIST
)
pause