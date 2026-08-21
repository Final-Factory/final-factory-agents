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
python "%CLI%" %*
