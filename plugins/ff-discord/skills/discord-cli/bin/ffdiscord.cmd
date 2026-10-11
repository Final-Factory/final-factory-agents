@echo off
rem ffdiscord launcher for Windows shells (cmd, PowerShell). The POSIX twin beside this
rem file covers git-bash. Same resolution order: FFDISCORD_CLI, then the newest installed
rem plugin copy, then the checkout recorded by registerAgents.sh.
setlocal enabledelayedexpansion
set "SCRIPT=ffdiscord.py"
if /i "%~n0"=="ffdiscord-listener" set "SCRIPT=ffdiscord_listener.py"

set "CLI="
if defined FFDISCORD_CLI (
    for %%I in ("%FFDISCORD_CLI%") do set "CLI=%%~dpI%SCRIPT%"
) else (
    for /f "delims=" %%I in ('dir /b /s /o:n "%USERPROFILE%\.claude\plugins\cache\*\ff-discord\*\skills\discord-cli\%SCRIPT%" 2^>nul') do set "CLI=%%I"
    if not defined CLI (
        for /f "delims=" %%I in ('dir /b /s /o:n "%USERPROFILE%\.codex\plugins\cache\*\ff-discord\*\skills\discord-cli\%SCRIPT%" 2^>nul') do set "CLI=%%I"
    )
    if not defined CLI (
        if exist "%USERPROFILE%\.claude\final-factory-agents-checkout" (
            set /p CHECKOUT=<"%USERPROFILE%\.claude\final-factory-agents-checkout"
            if exist "!CHECKOUT!\plugins\ff-discord\skills\discord-cli\%SCRIPT%" set "CLI=!CHECKOUT!\plugins\ff-discord\skills\discord-cli\%SCRIPT%"
        )
    )
)

if not defined CLI (
    echo %~n0: cannot locate %SCRIPT%. 1>&2
    echo   Install the plugin on this machine:  sh registerAgents.sh --plugin ff-discord 1>&2
    echo   Or point FFDISCORD_CLI at a copy of ffdiscord.py. 1>&2
    exit /b 69
)

rem Find a Python 3 that RUNS (w912). `python` and `python3` on a stock Windows are often the
rem Microsoft Store "App Execution Alias" (...\WindowsApps\python.exe), which exists but only
rem prints "Python was not found", so each candidate must execute a one-liner and exit 0.
rem Order: %FFDISCORD_PYTHON%, python3, python, py -3, then python.org install dirs, newest last-wins.
set "PYRUN="
set "PYTEST=import sys; sys.exit(0 if sys.version_info[0]==3 else 1)"
if defined FFDISCORD_PYTHON (
    "%FFDISCORD_PYTHON%" -c "!PYTEST!" >nul 2>&1 && set "PYRUN="%FFDISCORD_PYTHON%""
    if not defined PYRUN (
        echo %~n0: FFDISCORD_PYTHON=%FFDISCORD_PYTHON% does not run a Python 3. 1>&2
        exit /b 127
    )
)
if not defined PYRUN python3 -c "!PYTEST!" >nul 2>&1 && set "PYRUN=python3"
if not defined PYRUN python -c "!PYTEST!" >nul 2>&1 && set "PYRUN=python"
if not defined PYRUN py -3 -c "!PYTEST!" >nul 2>&1 && set "PYRUN=py -3"
if not defined PYRUN (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "C:\Python3*" "%ProgramFiles%\Python3*" "!ProgramFiles(x86)!\Python3*") do (
        if exist "%%~D\python.exe" "%%~D\python.exe" -c "!PYTEST!" >nul 2>&1 && set "PYRUN="%%~D\python.exe""
    )
)
if not defined PYRUN (
    echo %~n0: no working Python 3 found. Tried: python3, python, py -3, and the python.org install dirs 1>&2
    echo   (%%LOCALAPPDATA%%\Programs\Python\Python3*, C:\Python3*, %%ProgramFiles%%\Python3*^). 1>&2
    echo   python / python3 under WindowsApps are the Microsoft Store stub: install Python 3 1>&2
    echo   (winget install Python.Python.3.13^), or set FFDISCORD_PYTHON to a full python.exe path. 1>&2
    exit /b 127
)
!PYRUN! "%CLI%" %*
