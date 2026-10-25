@echo off
rem Portable launcher for Windows (x64 and ARM64). Double-click or run:  start_hpeo.bat [doctor|detect|configure ...|start ...]
rem The Python environment is created on the LOCAL disk; code and offline wheels are read from the stick.
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PYCMD="
for %%V in (3.13 3.12 3.11 3.10) do (
  if not defined PYCMD ( py -%%V -c "import sys" >nul 2>&1 && set "PYCMD=py -%%V" )
)
if not defined PYCMD ( python -c "import sys; sys.exit(sys.version_info<(3,10))" >nul 2>&1 && set "PYCMD=python" )
if not defined PYCMD (
  echo Python 3.10+ not found. Install from https://www.python.org/downloads/ and re-run.
  exit /b 10
)

for /f %%A in ('%PYCMD% -c "import platform;print(platform.machine().lower())"') do set "ARCH=%%A"
set "VENV=%LOCALAPPDATA%\hpeo\venv-windows-%ARCH%"
for /f %%H in ('certutil -hashfile requirements-runtime.txt SHA256 ^| findstr /v ":"') do set "RH=%%H"
set "STAMP=%VENV%\.req-%RH:~0,16%"

if not exist "%STAMP%" (
  echo ^>^> Preparing environment in %VENV%
  %PYCMD% -m venv "%VENV%" || exit /b 11
  if exist "wheels\windows-%ARCH%" (
    "%VENV%\Scripts\pip" install --no-index --find-links "wheels\windows-%ARCH%" -r requirements-runtime.txt || exit /b 12
  ) else (
    "%VENV%\Scripts\pip" install -r requirements-runtime.txt || exit /b 12
  )
  type nul > "%STAMP%"
)

if "%~1"=="" ( "%VENV%\Scripts\python" -m deploy start ) else ( "%VENV%\Scripts\python" -m deploy %* )
exit /b %ERRORLEVEL%
