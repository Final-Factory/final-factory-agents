@echo off
rem record_clip launcher for Windows shells (cmd, PowerShell); the POSIX twin beside this file
rem covers git-bash. Same resolution: RECORD_CLIP_PY, the newest installed plugin copy, then the
rem checkout recorded by registerAgents.sh. Runs the script with uv (installs its dependencies).
setlocal enabledelayedexpansion
set "SCRIPT=record_clip.py"
set "PY="
if defined RECORD_CLIP_PY (
    set "PY=%RECORD_CLIP_PY%"
) else (
    for /f "delims=" %%I in ('dir /b /s /o:n "%USERPROFILE%\.claude\plugins\cache\*\ff-agents\*\skills\watch-video\%SCRIPT%" 2^>nul') do set "PY=%%I"
    if not defined PY (
        for /f "delims=" %%I in ('dir /b /s /o:n "%USERPROFILE%\.codex\plugins\cache\*\ff-agents\*\skills\watch-video\%SCRIPT%" 2^>nul') do set "PY=%%I"
    )
    if not defined PY (
        if exist "%USERPROFILE%\.claude\final-factory-agents-checkout" (
            set /p CHECKOUT=<"%USERPROFILE%\.claude\final-factory-agents-checkout"
            if exist "!CHECKOUT!\plugins\ff-agents\skills\watch-video\%SCRIPT%" set "PY=!CHECKOUT!\plugins\ff-agents\skills\watch-video\%SCRIPT%"
        )
    )
)
if not defined PY (
    echo record_clip: cannot locate %SCRIPT%. Install the plugin: sh registerAgents.sh 1>&2
    exit /b 69
)
uv run --quiet --script "%PY%" %*
