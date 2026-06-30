@echo off
REM ===================================================================
REM  AI Slop Quarantine Guard - start the full stack (Windows)
REM  SELF-HEALING: every run it
REM     1) frees ports 3000-3002 + 8000 (kills any stale dev servers)
REM     2) wipes the Next.js .next cache (prevents stale-build crashes)
REM     3) opens ONE Windows Terminal window split into 3 panes:
REM           left = Dashboard (:3000) | top-right = API (:8000) | bottom-right = Worker
REM  Redis = Upstash (cloud, in .env). Double-click to run. Close window to stop.
REM ===================================================================

echo.
echo   [1/3] Freeing ports 3000-3002 and 8000 (closing any stale servers)...
powershell -NoProfile -Command "Get-NetTCPConnection -State Listen -LocalPort 3000,3001,3002,8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} }"

echo   [2/3] Clearing stale Next.js build cache...
if exist "%~dp0web\.next" rmdir /s /q "%~dp0web\.next"

echo   [3/3] Launching stack...

where wt >nul 2>&1
if errorlevel 1 goto fallback

REM One Windows Terminal window, three panes (single line on purpose).
wt -w new new-tab --title "SQG Web" -d "%~dp0web" cmd /k "npm run dev" ; split-pane -V --title "SQG API" -d "%~dp0api" cmd /k "set PYTHONPATH=.&&python -m uvicorn app.main:app --host 127.0.0.1 --port 8000" ; split-pane -H --title "SQG Worker" -d "%~dp0api" cmd /k "set PYTHONPATH=.&&python -m app.worker"
goto open

:fallback
REM Windows Terminal not found - fall back to 3 separate windows.
start "SQG API"    /D "%~dp0api" cmd /k "set PYTHONPATH=.&&python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "SQG Worker" /D "%~dp0api" cmd /k "set PYTHONPATH=.&&python -m app.worker"
start "SQG Web"    /D "%~dp0web" cmd /k "npm run dev"

:open
echo.
echo   Stack starting. First compile takes ~20-40s after a cache wipe - this is normal.
timeout /t 15 /nobreak >nul
start "" http://localhost:3000
