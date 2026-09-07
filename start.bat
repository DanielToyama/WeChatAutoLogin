@echo off
setlocal EnableExtensions

REM ============================================================
REM  WeChatAutoLogin launcher (auto-start with Windows)
REM
REM  HOW TO USE
REM   Option A: keep start.bat next to wechat_autologin.py,
REM             put a SHORTCUT to this bat into the Startup folder
REM             (Win+R -> shell:startup -> Enter).
REM   Option B: set SCRIPT below to the absolute path of
REM             wechat_autologin.py, then drop start.bat into the
REM             Startup folder.
REM
REM  Runs silently via pythonw --watch (retries until login).
REM ============================================================

set "SCRIPT=%~dp0wechat_autologin.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0..\wechat_autologin.py"
if not exist "%SCRIPT%" (
  echo [ERROR] wechat_autologin.py not found. Edit the SCRIPT path in start.bat.
  exit /b 1
)

set "PYW=pythonw"
for /f "usebackq delims=" %%i in (`python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"`) do set "PYW=%%i"

start "" "%PYW%" "%SCRIPT%" --watch
exit /b 0