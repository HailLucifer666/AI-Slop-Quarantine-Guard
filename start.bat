@echo off
setlocal EnableDelayedExpansion
pushd "%~dp0"
title SQG Launcher

REM ===================================================================
REM  AI Slop Quarantine Guard - start the full stack (Windows)
REM  Opens ONE Windows Terminal window with panes (Web / API / Worker /
REM  Redis) via wt.exe; falls back to separate windows if wt is missing.
REM  Setup is cached in .setup-stamp  (re-run: start.bat --check)
REM ===================================================================

set PKG_ROOT=F:\C Drive Packages Dump
set NPM_PREFIX=%PKG_ROOT%\npm-global
set PIP_TARGET=%PKG_ROOT%\python-packages
set NODE_PATH=%NPM_PREFIX%\node_modules
set STAMP_FILE=%~dp0.setup-stamp

if not exist "%PKG_ROOT%" mkdir "%PKG_ROOT%"
if not exist "%NPM_PREFIX%" mkdir "%NPM_PREFIX%"
if not exist "%PIP_TARGET%" mkdir "%PIP_TARGET%"

set PATH=%PIP_TARGET%\bin;%PIP_TARGET%;%NPM_PREFIX%\bin;%PATH%
set PYTHONPATH=%PIP_TARGET%;%PYTHONPATH%

set FORCE_CHECK=0
for %%A in (%*) do (
    if "%%A"=="--check" set FORCE_CHECK=1
)

if "%FORCE_CHECK%"=="1" goto full_setup
if not exist "%STAMP_FILE%" goto full_setup

echo.
echo  ==============================================================
echo   AI Slop Quarantine Guard
echo   Setup already done. Launching stack...
echo   (To re-run setup: start.bat --check)
echo  ==============================================================
echo.

set PYTHON_CMD=
set REDIS_EXE=
for /f "usebackq tokens=1,* delims==" %%K in ("%STAMP_FILE%") do (
    if "%%K"=="PYTHON_CMD" set PYTHON_CMD=%%L
    if "%%K"=="PIP_TARGET" set PIP_TARGET=%%L
    if "%%K"=="REDIS_EXE" set REDIS_EXE=%%L
)

if exist "!PYTHON_CMD!" (
    "!PYTHON_CMD!" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 goto launch
)
echo   [WARN] Cached Python invalid or older than 3.10. Re-running setup...

:full_setup
echo.
echo  ==============================================================
echo   AI Slop Quarantine Guard - Setup
echo   All packages install to: %PKG_ROOT%
echo  ==============================================================
echo.

if "%FORCE_CHECK%"=="1" (
    echo   [SETUP] Forced re-check (--check argument)
) else (
    echo   [SETUP] Setup running - checking dependencies...
)
echo.

echo   [1/5] Checking Node.js...
where node >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [ERROR] Node.js is NOT installed or not in PATH.
    echo   Please install Node.js v18+ from: https://nodejs.org
    echo.
    pause
    exit /b 1
)
for /f "delims=v. tokens=1" %%V in ('node --version 2^>nul') do set NODEMAJ=%%V
if !NODEMAJ! LSS 18 (
    echo.
    echo   [ERROR] Node.js version is too old. Found:
    node --version
    echo   Required: v18 or higher. Download from: https://nodejs.org
    echo.
    pause
    exit /b 1
)
echo         OK - Node.js
node --version

echo.
echo   [2/5] Checking npm...
where npm >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [ERROR] npm is NOT installed or not in PATH.
    echo   npm comes bundled with Node.js. Reinstall from: https://nodejs.org
    echo.
    pause
    exit /b 1
)
echo         OK - npm
npm --version

echo.
echo   [3/5] Checking Python 3.10+...

set PYTHON_CMD=
set PYTHON_EXE=
set PYTHON_OK=0

for %%C in ("py -3.14" "py -3.13" "py -3.12" "py -3.11" "py -3" "python" "python3") do (
    if "!PYTHON_OK!"=="0" (
        %%~C -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
        if not errorlevel 1 (
            set PYTHON_OK=1
            for /f "delims=" %%I in ('%%~C -c "import sys; print(sys.executable)"') do set PYTHON_EXE=%%I
            for /f "delims=" %%I in ('%%~C -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"') do set PYTHON_VER=%%I
        )
    )
)

if "!PYTHON_OK!"=="0" (
    echo.
    echo   [ERROR] Python 3.10 or higher is required.
    echo   Found:
    py --version 2>nul || python --version 2>nul || echo (no python found)
    echo.
    echo   Please install Python 3.10+ from: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

if "!PYTHON_EXE!"=="" (
    echo.
    echo   [ERROR] Could not resolve the Python executable path.
    echo.
    pause
    exit /b 1
)
set PYTHON_CMD=!PYTHON_EXE!
echo         OK - Python !PYTHON_VER!
echo         Using: !PYTHON_EXE!

echo.
echo   [4/5] Checking Node.js dependencies (web\node_modules)...
if not exist "%~dp0web\node_modules\next" (
    echo         node_modules missing - running npm install...
    echo         (This may take 2-4 minutes)
    pushd "%~dp0web"
    call npm install --prefer-offline
    if errorlevel 1 (
        echo.
        echo   [ERROR] npm install failed. Check internet connection.
        echo.
        popd
        pause
        exit /b 1
    )
    if not exist "%~dp0web\node_modules\next\dist\bin\next" (
        echo.
        echo   [ERROR] npm install finished but Next.js binary is missing.
        echo   Delete web\node_modules and run start.bat again.
        echo.
        popd
        pause
        exit /b 1
    )
    popd
    echo         Node dependencies installed.
) else (
    echo         OK - web\node_modules found.
)

echo.
echo   [5/5] Checking Python dependencies...
echo         Target: %PIP_TARGET%

"!PYTHON_CMD!" -c "import sys; sys.path.insert(0,r'%PIP_TARGET%'); import uvicorn, httpx, fastapi, pydantic, pydantic_core" >nul 2>&1
if errorlevel 1 (
    echo         Python packages missing - installing now...
    echo         (This may take 2-4 minutes)
    "!PYTHON_CMD!" -m pip install --no-user --upgrade pip --target "%PIP_TARGET%" --quiet
    pushd "%~dp0api"
    "!PYTHON_CMD!" -m pip install --no-user ".[dev]" --target "%PIP_TARGET%" --quiet 2>nul
    if errorlevel 1 (
        echo         pyproject install failed - installing packages individually...
        "!PYTHON_CMD!" -m pip install --no-user fastapi "uvicorn[standard]" httpx "sqlalchemy[asyncio]" aiosqlite asyncpg alembic pydantic pydantic-settings structlog arq redis "python-jose[cryptography]" PyJWT pathspec python-multipart --target "%PIP_TARGET%" --quiet
        if errorlevel 1 (
            echo.
            echo   [ERROR] Python dependency installation failed.
            echo   Check internet connection and Python version (need 3.10+).
            echo.
            popd
            pause
            exit /b 1
        )
    )
    popd
    echo         Python dependencies installed to: %PIP_TARGET%
) else (
    echo         OK - Python packages found.
)

if not exist "%~dp0api\.env" (
    if exist "%~dp0.env.example" (
        copy "%~dp0.env.example" "%~dp0api\.env" >nul
        echo         Auto-copied .env.example -^> api\.env
    )
)
if not exist "%~dp0web\.env.local" (
    if exist "%~dp0web\.env.example" (
        copy "%~dp0web\.env.example" "%~dp0web\.env.local" >nul
        echo         Auto-copied web\.env.example -^> web\.env.local
    )
)

if exist "%~dp0web\.next" (
    echo         Clearing stale Next.js build cache...
    rmdir /s /q "%~dp0web\.next"
)

echo.
echo   [6/6] Checking Redis for Windows...
set REDIS_EXE=
if exist "%PKG_ROOT%\redis\redis-server.exe" (
    set REDIS_EXE=%PKG_ROOT%\redis\redis-server.exe
    echo         OK - Redis already present.
) else (
    echo         Bootstraping Redis (one-time download ~3 MB)...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\get-redis.ps1" -InstallDir "%PKG_ROOT%\redis"
    if errorlevel 1 (
        echo.
        echo   [WARN] Redis download failed - continuing without Redis.
        echo   API will report redis:false; the worker will keep retrying.
        echo   (Re-run start.bat --check to try again.)
    ) else (
        if exist "%PKG_ROOT%\redis\redis-path.txt" (
            for /f "usebackq delims=" %%R in ("%PKG_ROOT%\redis\redis-path.txt") do set REDIS_EXE=%%R
        )
        if "!REDIS_EXE!"=="" set REDIS_EXE=%PKG_ROOT%\redis\redis-server.exe
        echo         OK - Redis ready: !REDIS_EXE!
    )
)

echo.
echo   Writing setup stamp...
(
    echo PYTHON_CMD=!PYTHON_EXE!
    echo PIP_TARGET=%PIP_TARGET%
    if not "!REDIS_EXE!"=="" echo REDIS_EXE=!REDIS_EXE!
    echo SETUP_DATE=%date%
) > "!STAMP_FILE!"

echo.
echo   Setup complete.

:launch
echo.
echo  ==============================================================
echo   Starting stack...
echo  ==============================================================
echo.

set PATH=%PIP_TARGET%\bin;%PIP_TARGET%;%NPM_PREFIX%\bin;%PATH%
set PYTHONPATH=%PIP_TARGET%;%~dp0api;%PYTHONPATH%

if "!PYTHON_CMD!"=="" (
    echo   [ERROR] Python 3.10+ not found. Cannot start API server.
    echo   Install Python from: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

set CHILD_PYTHON=!PYTHON_CMD!
set SQG_PIP_TARGET=%PIP_TARGET%
echo   Using Python: "!CHILD_PYTHON!"
if not "!REDIS_EXE!"=="" echo   Using Redis: "!REDIS_EXE!"
echo.

echo   Freeing ports 3000-3002 and 8000 (closing stale servers)...
powershell -NoProfile -Command "Get-NetTCPConnection -State Listen -LocalPort 3000,3001,3002,8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} }"

REM One window, wt.exe panes: Web fills the left column; API / Worker / Redis
REM stack in the right column. No && inside wt args (that historical misparse is
REM what produced stray tabs). %VAR% is expanded by CMD before wt sees the line.
where wt >nul 2>&1
if errorlevel 1 goto launch_legacy

echo   Opening one Windows Terminal window with panes (Web / API / Worker / Redis)...
REM Note: -d "%~dp0." — bare %~dp0 ends in a backslash and the escaped quote
REM swallows the closing quote, mangling the pane's command (web/api panes end
REM with a letter, so they never hit it).
if "!REDIS_EXE!"=="" (
    wt -w new new-tab --title "SQG Web" -d "%~dp0web" cmd /k "%~dp0run_web.bat" ; split-pane -V --title "SQG API" -d "%~dp0api" cmd /k "%~dp0run_api.bat" ; split-pane -H --title "SQG Worker" -d "%~dp0api" cmd /k "%~dp0run_worker.bat"
) else (
    wt -w new new-tab --title "SQG Web" -d "%~dp0web" cmd /k "%~dp0run_web.bat" ; split-pane -V --title "SQG API" -d "%~dp0api" cmd /k "%~dp0run_api.bat" ; split-pane -H --title "SQG Worker" -d "%~dp0api" cmd /k "%~dp0run_worker.bat" ; split-pane -H --title "SQG Redis" -d "%~dp0." cmd /k "%~dp0run_redis.bat"
)
if not errorlevel 1 goto launch_wait
echo   [WARN] wt.exe failed - falling back to separate windows.

:launch_legacy
echo   Opening separate terminal windows (Web, API, Worker, Redis)...
set "PORT=3000"
start "SQG Web (Next.js - Port 3000)" cmd /k "%~dp0run_web.bat"
start "SQG API (FastAPI - Port 8000)" cmd /k "%~dp0run_api.bat"
start "SQG Worker (Scanner)" cmd /k "%~dp0run_worker.bat"
if not "!REDIS_EXE!"=="" start "SQG Redis" cmd /k "%~dp0run_redis.bat"

:launch_wait
echo.
echo   Waiting for http://localhost:3000 to come up...
echo   (First build can take 20-60 seconds - please wait)
powershell -NoProfile -Command "for($i=0;$i -lt 150;$i++){try{$r=Invoke-WebRequest -Uri 'http://localhost:3000' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -ge 200){exit 0}}catch{}; Start-Sleep -Milliseconds 500}; exit 1"

if errorlevel 1 (
    echo.
    echo   [WARN] The dashboard did not respond in time.
    echo   Look at the "SQG Web" window for the error.
    echo   You can also open http://localhost:3000 manually.
) else (
    echo   Dashboard is up - opening browser.
    start "" http://localhost:3000
)

echo.
echo  ==============================================================
echo   AI Slop Quarantine Guard is RUNNING!
echo  ==============================================================
echo.
echo   - Dashboard: http://localhost:3000
echo   - API:       http://localhost:8000
echo   - Worker:    Active
echo.
echo   Keep this window open while using the application.
echo   Press any key to STOP all services...
pause >nul

echo.
echo   Stopping services and freeing ports...
powershell -NoProfile -Command "Get-NetTCPConnection -State Listen -LocalPort 3000,3001,3002,8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} }"
REM Stop only the Redis started by this launcher (command-line marker), never any
REM other redis-server instance on the machine.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*sqg-redis*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo   Done.
popd
exit /b 0
