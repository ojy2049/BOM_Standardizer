# 실행 파일(EXE) 빌드 가이드

이 문서는 BOM 정규화 도구를 독립 실행 파일로 패키징하는 방법을 설명합니다.

## PyInstaller를 이용한 EXE 빌드

### 1. PyInstaller 설치

```bash
pip install pyinstaller
```

### 2. 기본 빌드

```bash
pyinstaller --onefile --windowed --name "BOM정규화도구" run.py
```

옵션 설명:
- `--onefile`: 단일 EXE 파일로 패키징
- `--windowed`: 콘솔 창 없이 GUI만 표시
- `--name`: 출력 파일명

### 3. 아이콘 추가 (선택사항)

1. 아이콘 파일 준비 (icon.ico)
2. 빌드 명령어에 아이콘 추가:

```bash
pyinstaller --onefile --windowed --name "BOM정규화도구" --icon=icon.ico run.py
```

### 4. 데이터 파일 포함

설정 파일이나 캐시를 포함하려면:

```bash
pyinstaller --onefile --windowed --name "BOM정규화도구" \
  --add-data "sample_bom.csv;." \
  run.py
```

### 5. 상세 빌드 설정 (spec 파일 사용)

`bom_standardizer.spec` 파일 생성:

```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('sample_bom.csv', '.'),
    ],
    hiddenimports=[
        'pandas',
        'openpyxl',
        'xlrd',
        'requests',
        'requests_oauthlib',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BOM정규화도구',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

빌드 실행:
```bash
pyinstaller bom_standardizer.spec
```

### 6. 빌드 결과

빌드가 완료되면:
- `dist/` 폴더에 실행 파일 생성
- `build/` 폴더에 빌드 임시 파일 생성

### 7. 배포

`dist/BOM정규화도구.exe` 파일을 사용자에게 배포합니다.

## 주의사항

1. **빌드 환경**: 빌드는 대상 OS에서 수행해야 합니다.
   - Windows EXE: Windows에서 빌드
   - macOS App: macOS에서 빌드
   - Linux: Linux에서 빌드

2. **파일 크기**: 단일 파일로 패키징하면 100MB 이상이 될 수 있습니다.

3. **첫 실행 시간**: 단일 파일 모드는 첫 실행 시 임시 폴더에 압축 해제되어 약간의 지연이 있을 수 있습니다.

4. **안티바이러스**: 일부 안티바이러스가 PyInstaller 빌드 파일을 오탐할 수 있습니다.

## 트러블슈팅

### tkinter 관련 오류
```
ModuleNotFoundError: No module named 'tkinter'
```

해결: Python 설치 시 tkinter 포함 여부 확인

### pandas 관련 오류
```
ImportError: Unable to import required dependencies
```

해결: numpy, pandas 최신 버전으로 업데이트
```bash
pip install --upgrade numpy pandas
```

### openpyxl 관련 오류

해결: hidden import 추가
```bash
pyinstaller --hidden-import=openpyxl.cell._writer run.py
```
