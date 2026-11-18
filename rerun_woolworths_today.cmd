@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv Python was not found.
    pause
    exit /b 1
)
echo One-off Woolworths reset and recollection for 2026-10-28 only.
".venv\Scripts\python.exe" -u rerun_woolworths_today.py
set "ww_exit=%ERRORLEVEL%"
echo.
if "%ww_exit%"=="0" (
    echo SUCCESS: Woolworths recollected, ingested and checked.
) else (
    echo NOT COMPLETE: see the errors and data\ww_reset_*\reset_report.json.
    echo Do not repeatedly restart after Access Denied.
)
pause
exit /b %ww_exit%
