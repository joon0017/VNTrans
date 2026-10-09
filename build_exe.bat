@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -c "import tkinter; tkinter.Tcl()"
if errorlevel 1 (
    echo Python's Tcl/Tk files are unavailable. Repair Python with the Tcl/Tk feature selected.
    goto failed
)
".venv\Scripts\python.exe" -m pip install --only-binary=:all: "pyinstaller>=6,<7"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" prepare_eztrans.py
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name VNTrans --collect-submodules winrt --add-data "runtime32;runtime32" --add-data "eztrans_helper.py;." vntrans.py
if errorlevel 1 goto failed
echo Executable created: dist\VNTrans.exe
pause
exit /b 0
:failed
echo Build failed. See the error above.
pause
exit /b 1
