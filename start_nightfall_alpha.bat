@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "HOST=127.0.0.1"
if not defined NIGHTFALL_ALPHA_PORT set "NIGHTFALL_ALPHA_PORT=8776"
set "PORT=%NIGHTFALL_ALPHA_PORT%"
set "URL=http://%HOST%:%PORT%/"
set "PYTHONPATH=%CD%\src"

set "PY_EXE="
set "PY_ARGS="

echo Looking for a Python environment with NightFall Alpha dependencies...
call :try_python ".venv\Scripts\python.exe" ""
if not defined PY_EXE (
  where py.exe >nul 2>nul
  if not errorlevel 1 (
    call :try_python "py" "-3"
  )
)
if not defined PY_EXE (
  where python.exe >nul 2>nul
  if not errorlevel 1 (
    call :try_python "python" ""
  )
)

if not defined PY_EXE (
  echo No Python environment with the NightFall Alpha dashboard dependencies was found.
  echo.
  echo Create one in this folder, then run this file again:
  echo   py -3 -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -e .
  pause
  exit /b 1
)
echo Using Python: %PY_EXE% %PY_ARGS%

netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $html = (Invoke-WebRequest '%URL%' -UseBasicParsing -TimeoutSec 3).Content; if ($html -like '*NightFall Alpha*') { exit 0 } else { exit 2 } } catch { exit 1 }"
  if errorlevel 2 (
    echo Port %PORT% is already in use, but it is not serving NightFall Alpha.
    echo Another local dashboard is probably running there.
    echo.
    echo Choose another NightFall Alpha port like this:
    echo   set NIGHTFALL_ALPHA_PORT=8777
    echo   start_nightfall_alpha.bat
    pause
    exit /b 1
  )
  if errorlevel 1 (
    echo Port %PORT% is already in use, but the launcher could not verify the dashboard.
    echo Close the process on %PORT% or set NIGHTFALL_ALPHA_PORT to another free port.
    pause
    exit /b 1
  )
  echo NightFall Alpha already appears to be running at %URL%
  start "" "%URL%"
  pause
  exit /b 0
)

echo Starting NightFall Alpha backend...
echo Backend: %HOST%:%PORT%
echo Frontend: %URL%
echo Startup market data refresh: disabled

start "NightFall Alpha Backend" cmd /k ""%PY_EXE%" %PY_ARGS% scripts\run_dashboard.py --host %HOST% --port %PORT%"
timeout /t 3 /nobreak >nul
start "" "%URL%"

echo NightFall Alpha launched. Close the "NightFall Alpha Backend" window to stop the server.
pause
exit /b 0

:try_python
set "CANDIDATE=%~1"
set "CANDIDATE_ARGS=%~2"
if "%CANDIDATE%"=="" exit /b 0
if not exist "%CANDIDATE%" (
  if /I not "%CANDIDATE%"=="py" if /I not "%CANDIDATE%"=="python" exit /b 0
)
"%CANDIDATE%" %CANDIDATE_ARGS% -c "import fastapi, uvicorn, yaml" >nul 2>nul
if not errorlevel 1 (
  set "PY_EXE=%CANDIDATE%"
  set "PY_ARGS=%CANDIDATE_ARGS%"
)
exit /b 0
