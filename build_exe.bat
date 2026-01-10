@echo off
REM ============================================
REM BOM 정규화 도구 - Windows EXE 빌드 스크립트
REM ============================================
REM 
REM 사용법:
REM 1. Python 3.9+ 설치 (https://www.python.org)
REM 2. 이 폴더에서 build_exe.bat 더블클릭
REM 3. dist 폴더에 BOM_Standardizer.exe 생성됨
REM
REM ============================================

echo.
echo ========================================
echo BOM 정규화 도구 EXE 빌드 시작
echo ========================================
echo.

REM 현재 디렉토리로 이동
cd /d "%~dp0"

REM Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되지 않았습니다.
    echo https://www.python.org 에서 Python 3.9 이상을 설치하세요.
    pause
    exit /b 1
)

echo [1/3] 필요한 패키지 설치 중...
pip install pandas openpyxl xlrd requests requests-oauthlib pyinstaller --quiet

echo.
echo [2/3] EXE 파일 빌드 중... (2-5분 소요)
pyinstaller --onefile --windowed --name "BOM_Standardizer" ^
    --hidden-import=pandas ^
    --hidden-import=openpyxl ^
    --hidden-import=openpyxl.cell._writer ^
    --hidden-import=xlrd ^
    --hidden-import=requests ^
    --collect-all openpyxl ^
    --noconfirm ^
    run.py

if errorlevel 1 (
    echo.
    echo [오류] 빌드 실패!
    pause
    exit /b 1
)

echo.
echo [3/3] 정리 중...
rmdir /s /q build 2>nul
del /q *.spec 2>nul

echo.
echo ========================================
echo 빌드 완료!
echo.
echo 실행 파일: dist\BOM_Standardizer.exe
echo.
echo 이 파일을 원하는 곳에 복사해서 사용하세요.
echo (Python 설치 없이 실행 가능)
echo ========================================
echo.

REM dist 폴더 열기
explorer dist

pause
