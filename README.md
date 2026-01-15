# BOM Standardizer & NPI Platform

업체별 제각각인 BOM을 표준화하고, SMT 장비 프로그램 생성 및 제조 성 검토(DFM)까지 지원하는 통합 NPI 플랫폼입니다.

업체별 제각각인 BOM을 표준화하고, SMT 장비 프로그램 생성 및 제조 성 검토(DFM)까지 지원하는 통합 NPI 플랫폼입니다.

업체별 제각각 포맷의 BOM 파일을 자사 표준 BOM 양식으로 변환하는 GUI 프로그램입니다.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

## 📋 주요 기능

### 1. 다양한 입력 형식 지원
- **파일 형식**: CSV, XLS, XLSX, XLSM
- **자동 컬럼 매핑**: 업체별 컬럼명 자동 감지 및 표준화
- **헤더 없는 BOM 처리**: 데이터 패턴 분석으로 컬럼 타입 자동 추론
- **다양한 인코딩**: UTF-8, CP949, EUC-KR 등 자동 감지

### 2. SMD/DIP 자동 분류
- **패키지명 기반**: QFN, SOIC, 0402, TO-220, DIP 등 250+ 패키지 키워드
- **API 응답 활용**: Digi-Key/Mouser의 Mounting Type 정보 우선
- **카테고리 기반**: 칩저항, 칩콘덴서 → SMD / 전해콘덴서 → DIP
- **분류 결과**: SMD, DIP, SMD(추정), DIP(추정), 확인필요, 미확정

### 3. 부품 정보 조회 (선택사항)
- **웹 검색**: DuckDuckGo 기반 빠른 검색 (API 키 불필요)
- **Digi-Key API**: OAuth 인증 기반 Product Information V4
- **Mouser API**: API Key 기반 Search API
- **캐싱**: API 조회 결과 캐싱으로 중복 호출 방지 (기본 30일)

### 4. 표준 BOM 엑셀 출력
- **표준 컬럼**: NO, 품목, 스펙, 수량, 위치, 장착방식, 공식부품명, 공급사, 공급사부품번호, 데이터시트URL
- **테이블 서식**: Excel Table + AutoFilter 자동 적용
- **색상 구분**: SMD(연두), DIP(주황), 미확정(노랑)
- **검토 시트**: 미확정 항목 별도 시트 자동 생성

### 5. 별칭 관리
- **부품 별칭**: 동일 부품의 다양한 표기 통합 관리
- **카테고리 매핑**: 부품 카테고리 표준화 (RESISTOR-CHIP → 칩저항)
- **가져오기/내보내기**: JSON 형식 별칭 사전 관리

### 6. NPI 및 P&P 생성 (New)
- **Centroid 파일 파싱**: PCB 좌표 파일 자동 인식 (CSV, TXT, Excel)
- **Samsung SM 지원**: SM421, SM471 등 장비용 SSA, CSV, 피더리스트 출력
- **DFM 분석**: 부품 간격, 극성, Tombstone 위험 등 제조성 검토
- **BOM 매칭**: BOM과 좌표 데이터 자동 매칭 및 누락 검사

### 7. 부품 라이브러리 및 AVL (New)
- **부품 DB**: SQLite 기반 부품 라이브러리 (생산상태, 리드타임 관리)
- **AVL 관리**: 승인 공급업체 (Approved Vendor List) 관리
- **위험도 분석**: 단종, 긴 리드타임, 단일 공급원 등 리스크 자동 평가

---

## 🚀 설치 방법

### 1. Python 설치
Python 3.9 이상이 필요합니다.
- [Python 공식 사이트](https://www.python.org/downloads/)에서 다운로드

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

또는 직접 설치:
```bash
pip install pandas openpyxl xlrd requests requests-oauthlib
```

**참고**: GUI는 Python 표준 라이브러리인 tkinter를 사용합니다.
- Windows: Python 설치 시 기본 포함
- macOS: Python 설치 시 기본 포함
- Linux: `sudo apt-get install python3-tk` (Ubuntu/Debian)

---

## ▶️ 실행 방법

### Windows
```batch
run.bat
```
또는
```batch
python run.py
```

### Linux/macOS
```bash
chmod +x run.sh
./run.sh
```
또는
```bash
python3 run.py
```

---

## 📖 사용 방법

### 1. 파일 선택
- "파일 찾기..." 버튼 클릭
- BOM 파일 선택 (CSV, XLS, XLSX, XLSM)

### 2. 데이터 확인 및 매핑
- 상위 10행 미리보기 확인
- 필요시 컬럼 매핑 수정 (대부분 자동 감지됨)
- 헤더 없는 파일도 자동 감지 및 처리

### 3. API 설정 (선택사항)
- "설정" 탭에서 API 키 입력
- 웹 검색 활성화 (API 키 불필요, 빠른 검색)
- Digi-Key: Client ID + Client Secret
- Mouser: API Key
- **API 없이도 휴리스틱 분류로 SMD/DIP 판별 가능**

### 4. 처리 시작
- "처리 시작" 버튼 클릭
- 진행률 및 현재 처리 중인 부품 확인

### 5. 결과 확인 및 저장
- "결과" 탭에서 처리 결과 확인
- SMD/DIP/미확정 통계 확인
- "엑셀 저장" 버튼으로 표준 BOM 저장

---

## 🔑 API 키 발급 방법

### Digi-Key API
1. [Digi-Key API Portal](https://developer.digikey.com/) 접속
2. 계정 생성 및 로그인
3. "My Apps" → "Create App" 선택
4. Product Information API 선택
5. Client ID와 Client Secret 발급

### Mouser API
1. [Mouser API Portal](https://www.mouser.com/api-hub/) 접속
2. 계정 생성 및 로그인
3. Search API 신청
4. API Key 발급

---

## 📁 파일 구조

```
BOM_Standardizer/
├── run.py              # 실행 진입점
├── run.bat             # Windows 실행 스크립트
├── run.sh              # Linux/Mac 실행 스크립트
│
├── main_gui.py         # GUI 메인 애플리케이션
├── npi_gui.py          # NPI/P&P 기능 GUI
├── library_gui.py      # 부품 라이브러리 GUI
├── config.py           # 설정 및 상수 정의
├── bom_parser.py       # BOM 파일 파싱 모듈
├── centroid_parser.py  # Centroid 파일 파싱 모듈
├── api_resolver.py     # API 조회 및 SMD/DIP 분류 모듈
├── parts_library.py    # 부품 DB 및 라이브러리 로직
├── dfm_analyzer.py     # DFM 분석 모듈
├── pnp_generator.py    # P&P 생성 모듈
├── project_manager.py  # 프로젝트 관리 모듈
├── excel_writer.py     # 엑셀 출력 모듈
│
├── user_config.json    # 사용자 설정
├── parts_library.db    # 부품 및 AVL 데이터베이스 (SQLite)
├── part_aliases.json   # 부품 별칭 사전
├── components_db.json  # 전자부품 DB
├── resolver_cache.json # API 조회 캐시
│
├── requirements.txt    # 의존성 목록
├── sample_bom.csv      # 샘플 BOM 파일
│
├── README.md           # 사용자 가이드
├── DOCS.md             # 기술 문서
├── BUILD_EXE.md        # EXE 빌드 가이드
└── build_exe.bat       # EXE 빌드 스크립트
```

---

## ⚙️ 환경변수 (선택사항)

API 키를 환경변수로 설정하면 설정 파일보다 우선 적용됩니다:

```bash
export DIGIKEY_CLIENT_ID="your_client_id"
export DIGIKEY_CLIENT_SECRET="your_client_secret"
export MOUSER_API_KEY="your_api_key"
```

---

## 📊 출력 엑셀 예시

| NO | 품목 | 스펙 | 수량 | 위치 | 장착방식 | 공식부품명 | 공급사 | 공급사부품번호 | 데이터시트URL |
|----|------|------|------|------|----------|------------|--------|----------------|---------------|
| 1 | 저항 | 10K 0402 1% | 10 | R1-R10 | SMD | RC0402FR-0710KL | Digi-Key | RC0402FR-0710KLCT-ND | https://... |
| 2 | IC | STM32F103C8T6 | 1 | U1 | SMD | STM32F103C8T6 | Digi-Key | 497-10798-ND | https://... |
| 3 | IC | LM7805 TO-220 | 1 | U2 | DIP | LM7805CT | Mouser | 863-LM7805CT | https://... |
| 4 | 커넥터 | Pin Header 10P | 2 | J1-J2 | DIP | PH1-10-UA | - | - | - |

---

## ⚠️ 주의사항

- **API 호출 제한**: 대량 처리 시 캐시 활용 권장 (기본 30일 유효)
- **미확정 항목**: 일부 부품은 패키지 정보가 없어 "미확정"으로 분류되며, 별도 검토 시트에서 수동 확인 필요
- **크로스 플랫폼**: Windows, macOS, Linux에서 동작하지만 EXE 빌드는 Windows 전용

---

## 📚 문서

| 문서 | 설명 |
|------|------|
| [README.md](README.md) | 사용자 가이드 (이 문서) |
| [DOCS.md](DOCS.md) | 개발자용 상세 기술 문서 |
| [BUILD_EXE.md](BUILD_EXE.md) | EXE 빌드 가이드 |

---

## 📜 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.

---

## 📝 버전 히스토리

### v2.2.0 (2026-01-15)
- **NPI 기능 통합**: Centroid 파싱, DFM 분석, Samsung SM P&P 생성
- **부품 라이브러리**: SQLite 기반 로컬 부품 DB 및 AVL 관리
- **위험도 분석**: 부품 수급 리스크 자동 평가

### v2.1.1 (2026-01-15)
- **분류 로직 버그 수정**: DB 순회 시 2단 구조(IC → LinearRegulator) 미인식 문제 해결
- **패키지 비교 정규화**: "TO 220"과 "TO-220" 동일 인식
- **코드 정리**: 디버그 print문 제거

### v2.1.0 (2026-01-15)
- **전자부품 데이터베이스 도입**: `components_db.json` 파일 추가
  - MPN 패턴 기반 정밀 분류 (LM7805, LM2576T 등)
  - 패키지명 기반 SMD/DIP 판별 정확도 향상 (TO-220, TO-263 등)
- **분류 로직 개선**: 하이픈/공백 무시 매칭 (예: "TO 220" = "TO-220")
- **캐시 기능 비활성화**: 실시간 분류 결과 반영을 위해 캐시 OFF (필요시 설정에서 재활성화)
- **Diode 분류 강화**: 일반/스위칭/쇼트키/제너 다이오드 패턴 추가


### v2.0.0 (2026-01-14)
- 웹 검색 기능 추가 (DuckDuckGo 기반, API 키 불필요)
- 헤더 없는 BOM 파일 자동 처리
- 별칭 관리 기능 강화
- SMD/DIP 분류 로직 개선 (250+ 패키지 키워드)
- 버저 분류 로직 추가

### v1.0.0 (2025-01-10)
- 초기 릴리즈
- CSV/XLS/XLSX 파일 지원
- Digi-Key/Mouser API 연동
- SMD/DIP 휴리스틱 분류
- 표준 BOM 엑셀 출력

