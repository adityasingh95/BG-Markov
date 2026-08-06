@echo off
title BG-Markov - restore practice data
cd /d "%~dp0"

echo.
echo   Restoring the practice data
echo   ---------------------------
echo.
echo   This rebuilds the pretend data BG-Markov starts with.
echo.

where py >nul 2>&1
if %errorlevel%==0 (
    py -3.12 "%~dp0run.py" restore-demo
    goto :done
)
python "%~dp0run.py" restore-demo

:done
echo.
pause
