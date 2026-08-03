@echo off
REM ===================================================================
REM  Worker with a restart loop.
REM
REM  An unsupervised worker that crashes takes every future scan with it: new
REM  scans sit at "queued" forever, and because the dashboard's numbers come only
REM  from COMPLETED scans, the last finished scan keeps rendering as the current
REM  result. Restarting keeps the queue draining; the API's reconciler still fails
REM  any scan the crash interrupted, so nothing is reported as fresh that isn't.
REM
REM  Run from api/ (or double-click). Ctrl+C twice to stop for real.
REM ===================================================================

cd /d "%~dp0"
set PYTHONPATH=.

:loop
echo.
echo [worker] starting at %TIME%
python -m app.worker
echo [worker] exited with code %errorlevel% - restarting in 3s (Ctrl+C to stop)
timeout /t 3 /nobreak >nul
goto loop
