@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv Python was not found.
    pause
    exit /b 1
)
echo Running all three brands. Woolworths uses sequential stores and 10-second navigation spacing.
".venv\Scripts\python.exe" -u run_pipelines.py
set "daily_exit=%ERRORLEVEL%"
echo.
if "%daily_exit%"=="0" (
    echo SUCCESS: collection, upload and cloud batch processing confirmed. See manifest for details.
) else (
    echo NOT COMPLETE: review the errors above and data\production_*\manifest.json.
    echo Exit code 2 means uploaded data is safe but cloud processing is not confirmed.
)
pause
exit /b %daily_exit%
