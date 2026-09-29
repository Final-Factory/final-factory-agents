@echo off
rem watch_video launcher for Windows shells (cmd, PowerShell); the POSIX twin beside this file
rem covers git-bash. Same resolution: WATCH_VIDEO_PY, the newest installed plugin copy, then the
rem checkout recorded by registerAgents.sh. Runs the script with uv (installs its dependencies).
setlocal enabledelayedexpansion
set "SCRIPT=watch_video.py"
set "PY="
if defined WATCH_VIDEO_PY (
    set "PY=%WATCH_VIDEO_PY%"
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
    echo watch_video: cannot locate %SCRIPT%. Install the plugin: sh registerAgents.sh 1>&2
    exit /b 69
)
uv run --quiet --script "%PY%" %*
