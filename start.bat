@echo off
setlocal EnableDelayedExpansion
REM ===================================================================
REM  AI Slop Quarantine Guard - start the full stack (Windows)
REM  FAST PATH: Setup runs once, cached in .setup-stamp
REM  Force re-check: pass --check arg or delete .setup-stamp manually
REM ===================================================================

REM ---------------------------------------------------------------
REM  Package dump location - ALL packages go here, NEVER C:\
REM ---------------------------------------------------------------
set PKG_ROOT=F:\C Drive Packages Dump
set NPM_PREFIX=%PKG_ROOT%\npm-global
set PIP_TARGET=%PKG_ROOT%\python-packages
set NODE_PATH=%NPM_PREFIX%\node_modules
set STAMP_FILE=%~dp0.setup-stamp

REM Make sure the directories exist
if not exist "%PKG_ROOT%" mkdir "%PKG_ROOT%"
if not exist "%NPM_PREFIX%" mkdir "%NPM_PREFIX%"
if not exist "%PIP_TARGET%" mkdir "%PIP_TARGET%"

REM Add pip package bin dirs to PATH so installed CLI tools are found
set PATH=%PIP_TARGET%\bin;%PIP_TARGET%;%NPM_PREFIX%\bin;%PATH%

REM Tell Python to find packages from our custom target
set PYTHONPATH=%PIP_TARGET%;%PYTHONPATH%

REM ---------------------------------------------------------------
REM  Check for --check argument (force full re-run of setup)
REM ---------------------------------------------------------------
set FORCE_CHECK=0
for %%A in (%*) do (
    if "%%A"=="--check" set FORCE_CHECK=1
)

REM ---------------------------------------------------------------
REM  Fast path: skip setup if stamp file exists
REM ---------------------------------------------------------------
if "!FORCE_CHECK!"=="0" (
    if exist "!STAMP_FILE!" (
        echo.
        echo  ==============================================================
        echo   AI Slop Quarantine Guard
        echo   Setup already done. Launching stack...
        echo   (To re-run setup: delete .setup-stamp and restart)
        echo  ==============================================================
        echo.

        REM Read PYTHON_CMD and PIP_TARGET from stamp file
        for /f "usebackq tokens=1,* delims==" %%K in ("!STAMP_FILE!") do (
            if "%%K"=="PYTHON_CMD" set PYTHON_CMD=%%L
            if "%%K"=="PIP_TARGET" set PIP_TARGET=%%L
        )

        set FIRST_RUN=0
        goto launch
    )
)

REM ---------------------------------------------------------------
REM  FIRST RUN (or --check): Full setup
REM ---------------------------------------------------------------
set FIRST_RUN=1
echo.
echo  ==============================================================
echo   AI Slop Quarantine Guard - Setup
echo   All packages install to: %PKG_ROOT%
echo  ==============================================================
echo.

if "!FORCE_CHECK!"=="1" (
    echo   [SETUP] Forced re-check ^(--check argument^)
) else (
    echo   [SETUP] First run detected - installing dependencies...
)
echo.

REM ---------------------------------------------------------------
REM  STEP 1: Check Node.js
REM ---------------------------------------------------------------
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

REM ---------------------------------------------------------------
REM  STEP 2: Check npm
REM ---------------------------------------------------------------
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

REM ---------------------------------------------------------------
REM  STEP 3: Check Python 3.9+
REM ---------------------------------------------------------------
echo   [3/5] Checking Python 3.9+...

set PYTHON_CMD=
set PYTHON_OK=0

for %%C in (py python3 python) do (
    if "!PYTHON_CMD!"=="" (
        where %%C >nul 2>&1
        if not errorlevel 1 (
            for /f "tokens=2 delims= " %%V in ('%%C --version 2^>^&1') do (
                for /f "delims=. tokens=1,2" %%A in ("%%V") do (
                    if %%A GEQ 3 (
                        if %%B GEQ 9 (
                            set PYTHON_CMD=%%C
                            set PYTHON_VER=%%V
                            set PYTHON_OK=1
                        )
                    )
                )
            )
        )
    )
)

if "!PYTHON_OK!"=="0" (
    echo.
    echo   [ERROR] Python 3.9 or higher is NOT found.
    echo.
    echo   Requires Python 3.9+. Install from: https://www.python.org/downloads/
    echo   During install, check "Add python.exe to PATH"
    echo.
    echo   Python versions found on this machine:
    py --list 2>nul || echo   (py launcher not available)
    python --version 2>nul || echo   (python not in PATH)
    echo.
    pause
    exit /b 1
)
echo         OK - Python !PYTHON_VER! (using: !PYTHON_CMD!)

REM ---------------------------------------------------------------
REM  STEP 4: Install / verify Node.js dependencies (local to web/)
REM ---------------------------------------------------------------
echo   [4/5] Checking Node.js dependencies (web\node_modules)...
if not exist "%~dp0web\node_modules\next" (
    echo         node_modules missing or incomplete - running npm install...
    echo         Packages will be installed locally inside: %~dp0web\node_modules
    echo         (This may take 2-4 minutes on first run)
    pushd "%~dp0web"
    call npm install --prefer-offline
    if errorlevel 1 (
        echo.
        echo   [ERROR] npm install failed. Check internet connection and try again.
        echo.
        popd
        pause
        exit /b 1
    )
    popd
    echo         Node dependencies installed successfully.
) else (
    echo         OK - web\node_modules found.
)

REM ---------------------------------------------------------------
REM  STEP 5: Install / verify Python dependencies
REM          --target installs to F:\C Drive Packages Dump\python-packages
REM          NEVER installs to C:\ or the system Python site-packages
REM ---------------------------------------------------------------
echo   [5/5] Checking Python dependencies...
echo         Target: %PIP_TARGET%

REM Quick check for key packages in our custom target
!PYTHON_CMD! -c "import sys; sys.path.insert(0,'%PIP_TARGET%'); import uvicorn, httpx, fastapi" >nul 2>&1
if errorlevel 1 (
    echo         Python packages missing in target dir - installing now...
    echo         (This may take 2-4 minutes on first run)

    REM Upgrade pip itself (to our target dir)
    !PYTHON_CMD! -m pip install --upgrade pip --target "%PIP_TARGET%" --quiet

    REM Try installing from pyproject.toml first
    pushd "%~dp0api"
    !PYTHON_CMD! -m pip install ".[dev]" --target "%PIP_TARGET%" --quiet 2>nul
    if errorlevel 1 (
        echo         pyproject install failed - installing packages individually...
        !PYTHON_CMD! -m pip install ^
            fastapi ^
            "uvicorn[standard]" ^
            httpx ^
            "sqlalchemy[asyncio]" ^
            aiosqlite ^
            asyncpg ^
            alembic ^
            pydantic ^
            pydantic-settings ^
            structlog ^
            arq ^
            redis ^
            "python-jose[cryptography]" ^
            PyJWT ^
            pathspec ^
            python-multipart ^
            --target "%PIP_TARGET%" --quiet
        if errorlevel 1 (
            echo.
            echo   [ERROR] Python dependency installation failed.
            echo   Check internet connection and Python version (need 3.9+).
            echo.
            popd
            pause
            exit /b 1
        )
    )
    popd
    echo         Python dependencies installed to: %PIP_TARGET%
) else (
    echo         OK - Python packages found in target dir.
)

REM ---------------------------------------------------------------
REM  Auto-copy .env example files if missing (working defaults)
REM ---------------------------------------------------------------
if not exist "%~dp0api\.env" (
    if exist "%~dp0.env.example" (
        copy "%~dp0.env.example" "%~dp0api\.env" >nul
        echo         Auto-copied .env.example -^> api\.env
    ) else (
        echo         [WARN] api\.env not found and no .env.example to copy from.
    )
)
if not exist "%~dp0web\.env.local" (
    if exist "%~dp0web\.env.example" (
        copy "%~dp0web\.env.example" "%~dp0web\.env.local" >nul
        echo         Auto-copied web\.env.example -^> web\.env.local
    ) else (
        echo         [WARN] web\.env.local not found and no web\.env.example to copy from.
    )
)

REM ---------------------------------------------------------------
REM  Wipe Next.js cache on first run only (prevents stale-build crashes)
REM ---------------------------------------------------------------
if exist "%~dp0web\.next" (
    echo         Clearing stale Next.js build cache...
    rmdir /s /q "%~dp0web\.next"
)

REM ---------------------------------------------------------------
REM  Write stamp file - skips setup on all future runs
REM ---------------------------------------------------------------
(
    echo PYTHON_CMD=!PYTHON_CMD!
    echo PIP_TARGET=%PIP_TARGET%
    echo SETUP_DATE=%date%
) > "!STAMP_FILE!"

echo.
echo   Setup complete. Launching stack...
echo   (To re-run setup: delete .setup-stamp and restart)

:launch
echo.
echo  ==============================================================
echo   Starting stack...
echo  ==============================================================
echo.

REM Rebuild PATH/PYTHONPATH with correct PIP_TARGET (stamp may have overridden it)
REM Include api dir here so child processes inherit it — avoids && in wt args
set PATH=%PIP_TARGET%\bin;%PIP_TARGET%;%NPM_PREFIX%\bin;%PATH%
set PYTHONPATH=%PIP_TARGET%;%~dp0api;%PYTHONPATH%

REM ---------------------------------------------------------------
REM  Free ports
REM ---------------------------------------------------------------
echo   Freeing ports 3000-3002 and 8000 (closing any stale servers)...
powershell -NoProfile -Command "Get-NetTCPConnection -State Listen -LocalPort 3000,3001,3002,8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} }"

REM ---------------------------------------------------------------
REM  Build env vars for child processes
REM  PYTHONPATH is inherited from this process — no inline set needed
REM ---------------------------------------------------------------
set CHILD_PYTHON=!PYTHON_CMD!

echo   Launching stack...
echo.

where wt >nul 2>&1
if errorlevel 1 goto fallback

REM One Windows Terminal window — three split panes, no separate tabs.
REM new-tab opens the first pane; split-pane -V divides left/right;
REM split-pane -H then divides the right pane top/bottom.
wt -w new new-tab --title "SQG Web" -d "%~dp0web" cmd /k "npm run dev" ; split-pane -V --title "SQG API" -d "%~dp0api" cmd /k "!CHILD_PYTHON! -m uvicorn app.main:app --host 127.0.0.1 --port 8000" ; split-pane -H --title "SQG Worker" -d "%~dp0api" cmd /k "!CHILD_PYTHON! -m app.worker"
goto open

:fallback
REM Windows Terminal not found - fall back to 3 separate windows.
start "SQG API"    /D "%~dp0api" cmd /k "!CHILD_PYTHON! -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "SQG Worker" /D "%~dp0api" cmd /k "!CHILD_PYTHON! -m app.worker"
start "SQG Web"    /D "%~dp0web" cmd /k "npm run dev"

:open
echo.
echo   Stack is starting up!
if "!FIRST_RUN!"=="1" (
    echo   - First compile takes ~20-40s - this is normal.
) else (
    echo   - Using cached build - should be ready in ~3s.
)
echo   - Dashboard: http://localhost:3000
echo   - API:       http://localhost:8000
echo   - Packages:  %PKG_ROOT%
echo.
if "!FIRST_RUN!"=="1" (
    timeout /t 18 /nobreak >nul
) else (
    timeout /t 8 /nobreak >nul
)
start "" http://localhost:3000
