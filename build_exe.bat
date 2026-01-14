@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
echo ========================================
echo BOM Standardizer - EXE Build Script
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed.
    echo Please install Python 3.9+ from https://www.python.org
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
if exist ".venv" (
    echo Virtual environment already exists.
) else (
    python -m venv .venv
)

echo [2/4] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [3/4] Installing packages...
pip install pandas openpyxl xlrd requests requests-oauthlib pyinstaller --quiet

echo.
echo [4/4] Building EXE... (takes 2-5 minutes)
python -m PyInstaller --onefile --windowed --name "BOM_Standardizer" --hidden-import=pandas --hidden-import=openpyxl --hidden-import=openpyxl.cell._writer --hidden-import=xlrd --hidden-import=requests --collect-all openpyxl --noconfirm run.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    call deactivate
    pause
    exit /b 1
)

echo.
echo Cleaning up...
rmdir /s /q build 2>nul
del /q *.spec 2>nul

call deactivate

echo.
echo ========================================
echo Build Complete!
echo.
echo EXE file: dist\BOM_Standardizer.exe
echo.
echo You can copy this file anywhere and run it
echo without Python installation.
echo ========================================
echo.

explorer dist
pause
