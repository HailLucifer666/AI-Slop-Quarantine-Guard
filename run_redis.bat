@echo off
setlocal
REM Redis server pane (in-memory, dev queue). Kept in the foreground so the
REM pane stays open and shows the server log.
if "%REDIS_EXE%"=="" (
    echo [ERROR] REDIS_EXE is not set. Run start.bat once to set up Redis.
    pause
    exit /b 1
)
if not exist "%TEMP%\sqg-redis" mkdir "%TEMP%\sqg-redis"
echo Starting Redis (in-memory, port 6379)...
"%REDIS_EXE%" --port 6379 --save "" --appendonly no --dir "%TEMP%\sqg-redis"
echo [ERROR] Redis server stopped.
pause
