# BOM 정규화 도구 (BOM Standardizer)

업체별 제각각 포맷의 BOM 파일을 자사 표준 BOM 양식으로 변환하는 GUI 프로그램입니다.

## 주요 기능

### 1. 다양한 입력 형식 지원
- CSV, XLS, XLSX, XLSM 파일 지원
- 업체별 컬럼명 자동 감지 및 매핑
- 다양한 인코딩 자동 감지 (UTF-8, CP949, EUC-KR 등)

### 2. 공급사 API 연동 (선택사항)
- **Digi-Key Product Information API V4**: OAuth 인증 기반 부품 조회
- **Mouser Search API**: 부품번호/키워드 검색
- 공식 부품명, 패키지, 장착방식, 데이터시트 URL 자동 추출
- API 조회 결과 캐싱으로 중복 호출 방지

### 3. SMD/DIP 자동 분류
- 공급사 API 응답의 Mounting Type/Style 우선 사용
- 패키지명 기반 휴리스틱 분류:
  - **SMD**: QFN, QFP, SOIC, SOT, SOD, BGA, DFN, 0402, 0603, 0805 등
  - **DIP**: DIP, TO-220, Axial, Radial, Pin Header 등
- IPC-7351 패키지 표준 참고

### 4. 표준 BOM 엑셀 출력
- 표준 컬럼: NO, 규격, 스펙, 수량, 위치, 장착방식, 공식부품명, 공급사, 공급사부품번호, 데이터시트URL
- Excel Table + AutoFilter 자동 적용
- 장착방식별 색상 구분 (SMD: 연두, DIP: 주황, 미확정: 노랑)
- 미확정 항목 별도 검토 시트 생성

## 설치 방법

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

## 실행 방법

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

## 사용 방법

### 1. 파일 선택
- "파일 찾기..." 버튼 클릭
- BOM 파일 선택 (CSV, XLS, XLSX)

### 2. 데이터 확인 및 매핑
- 상위 10행 미리보기 확인
- 필요시 컬럼 매핑 수정 (대부분 자동 감지됨)

### 3. API 설정 (선택사항)
- "설정" 탭에서 API 키 입력
- Digi-Key: Client ID + Client Secret
- Mouser: API Key
- API 없이도 휴리스틱 분류 가능

### 4. 처리 시작
- "처리 시작" 버튼 클릭
- 진행률 확인

### 5. 결과 확인 및 저장
- "결과" 탭에서 처리 결과 확인
- SMD/DIP/미확정 통계 확인
- "엑셀 저장" 버튼으로 저장

## API 키 발급 방법

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

## 파일 구조

```
webapp/
├── run.py              # 실행 진입점
├── run.bat             # Windows 실행 스크립트
├── run.sh              # Linux/Mac 실행 스크립트
├── main_gui.py         # GUI 메인 애플리케이션
├── config.py           # 설정 및 상수
├── bom_parser.py       # BOM 파일 파싱 모듈
├── api_resolver.py     # 공급사 API 조회 모듈
├── excel_writer.py     # 엑셀 출력 모듈
├── requirements.txt    # 의존성 목록
├── sample_bom.csv      # 샘플 BOM 파일
└── README.md           # 이 문서
```

## 환경변수 (선택사항)

API 키를 환경변수로 설정하면 설정 파일보다 우선 적용됩니다:

```bash
export DIGIKEY_CLIENT_ID="your_client_id"
export DIGIKEY_CLIENT_SECRET="your_client_secret"
export MOUSER_API_KEY="your_api_key"
```

## 출력 엑셀 예시

| NO | 규격 | 스펙 | 수량 | 위치 | 장착방식 | 공식부품명 | 공급사 | 공급사부품번호 | 데이터시트URL |
|----|------|------|------|------|----------|------------|--------|----------------|---------------|
| 1 | 저항 | 10K 0402 | 10 | R1-R10 | SMD | RC0402FR-0710KL | Digi-Key | RC0402FR-0710KLCT-ND | https://... |
| 2 | IC | LM7805 TO-220 | 1 | U2 | DIP | LM7805CT | Mouser | 863-LM7805CT | https://... |

## 주의사항

- API 조회 시 호출 제한이 있으므로 대량 처리 시 캐시 활용 권장
- 일부 부품은 패키지 정보가 없어 "미확정"으로 분류될 수 있음
- 미확정 항목은 별도 검토 시트에서 수동 확인 필요

## 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.

## 버전 정보

- v1.0.0 (2025-01-10): 초기 릴리즈
