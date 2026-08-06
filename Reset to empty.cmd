@echo off
title BG-Markov - clear practice data
cd /d "%~dp0"

echo.
echo   Clearing the practice data
echo   --------------------------
echo.
echo   This deletes the pretend data only. You can put it back
echo   afterwards with "Restore demo data".
echo.

where py >nul 2>&1
if %errorlevel%==0 (
    py -3.12 "%~dp0run.py" reset
    goto :done
)
python "%~dp0run.py" reset

:done
echo.
pause
