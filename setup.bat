@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    echo Install Python 3.10-3.14 from python.org, including Tcl/Tk and the Python launcher.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    py -3 -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,14) else 1)"
    if errorlevel 1 (
        echo This setup supports CPython 3.10-3.14. See README.md to choose a specific version.
        goto failed
    )
    py -3 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install --only-binary=:all: -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" prepare_eztrans.py
if errorlevel 1 goto failed
echo Setup complete. Double-click run.bat to launch VNTrans.
pause
exit /b 0
:failed
echo Setup failed. Check your internet connection and use CPython 3.10-3.14.
echo Binary wheels are required; no Visual Studio or compilation is needed.
pause
exit /b 1
