@echo off
title BG-Markov
cd /d "%~dp0"

echo.
echo   BG-Markov
echo   ---------
echo.

rem Windows installs Python under whichever name was last registered, so `python` is
rem often some other version. The `py` launcher is how a SPECIFIC one is reached.
where py >nul 2>&1
if %errorlevel%==0 (
    py -3.12 "%~dp0run.py" start
    if not errorlevel 1 goto :eof
)

rem No py launcher, or no 3.12 registered with it. Hand over to whatever python exists so
rem run.py can report the problem in its own words -- it is much better at that than a
rem batch file, which cannot tell "not installed" from "installed but wrong version".
where python >nul 2>&1
if %errorlevel%==0 (
    python "%~dp0run.py" start
    goto :eof
)

echo.
echo   BG-Markov needs Python, and this computer does not have it.
echo.
echo   What to do:  install Python 3.12 from
echo                https://www.python.org/downloads/
echo                then start BG-Markov again.
echo.
pause
