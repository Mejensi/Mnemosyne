REM SPDX-License-Identifier: GPL-3.0-or-later
@echo off
REM ============================================================================
REM                              MNEMOSYNE
REM                     The Keeper of Digital Memory
REM ============================================================================
REM Copyright (C) 2026 Mejensi
REM Licensed under GNU General Public License v3.0
REM ============================================================================
REM Windows launcher only. Requires mnemosyne.py in the same folder.
REM Python code is intentionally not embedded to reduce antivirus false positives.
REM ============================================================================
setlocal enabledelayedexpansion
title Mnemosyne v2.0

chcp 65001 >nul
set "PYTHONNOUSERSITE=1"
set "PYTHONIOENCODING=utf-8"
set "MNEMOSYNE_LAUNCHER_DIR=%~dp0"
set "MNEMOSYNE_APP=%~dp0mnemosyne.py"
pushd "%~dp0" >nul 2>&1

if not exist "%MNEMOSYNE_APP%" (
    echo [!] mnemosyne.py is required.
    echo [!] Keep mnemosyne.py in the same folder as mnemosyne.bat.
    echo [!] This BAT file is only a launcher and does not contain the app.
    set EXIT_CODE=1
    goto :Finished
)

set "PYTHON_CMD="
for %%P in ("py -3" "python" "python3") do (
    if not defined PYTHON_CMD (
        %%~P -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON_CMD=%%~P"
    )
)

if not defined PYTHON_CMD (
    echo [!] Python 3.8 or newer required but not found.
    set /p "install=>> Install Python via winget? (Y/N): "
    if /i "!install!"=="Y" (
        winget install Python.Python.3 --silent --accept-package-agreements --accept-source-agreements
        if !errorlevel! neq 0 (
            echo [!] Failed. Install Python from python.org.
            set EXIT_CODE=1
            goto :Finished
        )
        echo [+] Python installed. Please restart this script.
        set EXIT_CODE=0
        goto :Finished
    ) else (
        echo [!] Python required. Exiting.
        set EXIT_CODE=1
        goto :Finished
    )
)

%PYTHON_CMD% -X utf8 "%MNEMOSYNE_APP%" %*
set EXIT_CODE=!errorlevel!

if exist "%~dp0.mnemosyne_runtime\Mnemosyne_Log.txt" copy /Y "%~dp0.mnemosyne_runtime\Mnemosyne_Log.txt" "%~dp0Mnemosyne_Log.txt" >nul 2>&1

:Finished
if defined MNEMOSYNE_NO_PAUSE goto :NoPause
if not "%~1"=="" goto :NoPause
echo.
pause

:NoPause
popd >nul 2>&1
exit /b %EXIT_CODE%
