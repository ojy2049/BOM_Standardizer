# BOM 정규화 도구 - 기술 문서

> 이 문서는 초보 개발자도 코드를 이해하고 수정할 수 있도록 상세하게 작성되었습니다.

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [폴더 및 파일 구조](#2-폴더-및-파일-구조)
3. [모듈별 상세 설명](#3-모듈별-상세-설명)
4. [데이터 흐름](#4-데이터-흐름)
5. [주요 클래스 설명](#5-주요-클래스-설명)
6. [설정 및 설정 파일](#6-설정-및-설정-파일)
7. [SMD/DIP 분류 로직](#7-smddip-분류-로직)
8. [API 연동 방식](#8-api-연동-방식)
9. [확장 및 커스터마이징](#9-확장-및-커스터마이징)

---

## 1. 프로젝트 개요

### 1.1 이 프로그램이 하는 일

**BOM 정규화 도구**는 다양한 업체에서 받은 BOM(Bill of Materials, 부품목록) 파일을 회사 내부 표준 양식으로 변환하는 GUI 프로그램입니다.

각 업체마다 BOM 파일의 컬럼명이 제각각인 문제를 해결합니다:
- A업체: `Part Number`, `Qty`, `Reference`
- B업체: `부품번호`, `수량`, `위치`
- C업체: `MPN`, `Q'ty`, `RefDes`

이 프로그램은 이러한 다양한 형식을 자동으로 인식하고, 통일된 표준 양식으로 변환합니다.

### 1.2 주요 기능

| 기능 | 설명 |
|------|------|
| **파일 읽기** | CSV, XLS, XLSX, XLSM 파일 지원 |
| **자동 매핑** | 컬럼명을 자동으로 인식 (품목, 스펙, 수량, 위치 등) |
| **헤더 없는 BOM 처리** | 헤더가 없는 파일도 데이터 패턴 분석으로 처리 |
| **SMD/DIP 분류** | 부품의 장착 방식 자동 분류 |
| **API 조회** | Digi-Key, Mouser API로 공식 부품 정보 조회 |
| **웹 검색** | DuckDuckGo 검색으로 부품 정보 보완 |
| **엑셀 출력** | 테이블 서식, 색상 구분이 적용된 표준 BOM 생성 |

### 1.3 사용 기술

- **Python 3.9+**: 메인 프로그래밍 언어
- **tkinter**: GUI 프레임워크 (Python 표준 라이브러리)
- **pandas**: 데이터 처리 및 분석
- **openpyxl**: 엑셀 파일 읽기/쓰기
- **xlrd**: 레거시 .xls 파일 지원
- **requests**: HTTP API 통신
- **requests-oauthlib**: OAuth 인증 (Digi-Key API)

---

## 2. 폴더 및 파일 구조

```
BOM_Standardizer/
│
├── run.py                 # 🚀 실행 진입점 (이 파일을 실행하면 됨)
├── run.bat                # Windows 실행 스크립트 (더블클릭)
├── run.sh                 # Linux/Mac 실행 스크립트
│
├── main_gui.py            # 🖥️ GUI 메인 (1,090줄)
├── config.py              # ⚙️ 설정 및 상수 정의 (370줄)
├── bom_parser.py          # 📄 BOM 파일 파싱 (753줄)
├── api_resolver.py        # 🌐 API 조회 및 분류 (1,259줄)
├── excel_writer.py        # 📊 엑셀 출력 (256줄)
│
├── user_config.json       # 사용자 설정 파일 (자동 생성)
├── part_aliases.json      # 부품 별칭 사전
├── resolver_cache.json    # API 조회 캐시 (자동 생성)
│
├── requirements.txt       # Python 패키지 의존성
├── sample_bom.csv         # 테스트용 샘플 BOM
├── sample_bom_no_header.csv # 헤더 없는 샘플 BOM
│
├── README.md              # 사용자 가이드
├── DOCS.md                # 이 기술 문서
├── BUILD_EXE.md           # EXE 빌드 가이드
│
├── build_exe.bat          # EXE 빌드 스크립트
└── dist/                  # 빌드된 EXE 출력 폴더
```

---

## 3. 모듈별 상세 설명

### 3.1 run.py - 실행 진입점

```python
#!/usr/bin/env python3
from main_gui import main

if __name__ == "__main__":
    main()
```

**역할**: 프로그램의 시작점입니다. 이 파일을 실행하면 `main_gui.py`의 `main()` 함수가 호출됩니다.

**왜 별도 파일로 분리했나요?**
- EXE 빌드 시 진입점 지정이 쉬움
- 경로 설정을 한 곳에서 관리

---

### 3.2 config.py - 설정 및 상수

**역할**: 프로그램 전체에서 사용하는 설정값과 상수를 정의합니다.

#### 주요 상수들

##### 경로 설정
```python
APP_DIR = Path(__file__).parent        # 프로그램 폴더 경로
CONFIG_FILE = APP_DIR / "user_config.json"  # 설정 파일 경로
CACHE_FILE = APP_DIR / "resolver_cache.json"  # 캐시 파일 경로
```

##### 컬럼 매핑 후보 (COLUMN_MAP_CANDIDATES)
업체마다 다른 컬럼명을 표준 키로 매핑하기 위한 사전입니다:
```python
COLUMN_MAP_CANDIDATES = {
    '품목': ['품목', '품명', 'item', 'type', 'category', '부품종류', ...],
    '스펙': ['스펙', '규격', 'spec', 'description', 'value', ...],
    '수량': ['수량', 'qty', 'quantity', 'count', ...],
    '위치': ['위치', 'refdes', 'ref', 'reference', 'location', ...],
    'mpn': ['mpn', 'manufacturer part number', 'part number', ...],
    # ...
}
```

##### SMD/DIP 키워드
패키지명으로 장착방식을 판별하는 키워드 목록:
```python
SMD_KEYWORDS = [
    'SMD', 'SMT', 'QFN', 'QFP', 'SOIC', 'SOP', 'SOT-23', 
    'BGA', '0402', '0603', '0805', '1206', ...
]

DIP_KEYWORDS = [
    'DIP', 'THROUGH HOLE', 'THT', 'TO-92', 'TO-220', 
    'AXIAL', 'RADIAL', 'PIN HEADER', ...
]
```

#### 주요 함수

| 함수 | 역할 |
|------|------|
| `load_config()` | user_config.json에서 설정 로드 |
| `save_config(config)` | 설정을 user_config.json에 저장 |
| `get_env_or_config(key)` | 환경변수 우선, 없으면 설정파일에서 값 가져오기 |

---

### 3.3 bom_parser.py - BOM 파일 파싱

**역할**: 다양한 형식의 BOM 파일을 읽고 정규화된 DataFrame으로 변환합니다.

#### BOMParser 클래스

##### 초기화
```python
parser = BOMParser()
```

##### 주요 속성
```python
parser.raw_df           # 원본 DataFrame
parser.normalized_df    # 정규화된 DataFrame
parser.column_mapping   # {표준키: 원본컬럼명} 매핑
parser.has_header       # 헤더 존재 여부
parser.file_path        # 로드한 파일 경로
```

##### 파일 로드 과정

```python
# 1. 파일 로드
success, message = parser.load_file("input.xlsx")

# 2. 컬럼 자동 매핑 감지
auto_mapping = parser.auto_detect_mapping()
# 결과: {'품목': 'Component Type', '스펙': 'Value', '수량': 'Qty', ...}

# 3. 매핑 적용 및 정규화
parser.set_mapping(auto_mapping)
success, message = parser.normalize()

# 4. 결과 데이터 가져오기
df = parser.get_normalized_data()
```

##### 헤더 자동 탐지 (`_detect_header_row`)

BOM 파일은 종종 상단에 제목이나 빈 행이 있습니다:
```
[빈 행]
[회사 로고 또는 제목]
[빈 행]
품목, 스펙, 수량, 위치  ← 실제 헤더 (3번 행)
저항, 10K, 10, R1
...
```

이 메서드는 최대 15행까지 스캔하여 헤더행을 찾습니다:
- 문자열 비율이 70% 이상인 행
- 알려진 컬럼명 후보가 포함된 행

##### 헤더 없는 BOM 처리 (`_infer_columns_from_data`)

헤더가 없는 경우 데이터 패턴을 분석합니다:
```
저항, 10K 0402, 10, R1-R10, RC0402FR-0710KL, Yageo
콘덴서, 100nF, 5, C1-C5, ...
```

각 컬럼의 값들을 분석하여 타입을 추론:
- 숫자만 있으면 → 수량
- "R1, R2" 패턴이면 → 위치(RefDes)
- "저항", "콘덴서" 등이 있으면 → 품목
- "10K", "100nF" 패턴이면 → 스펙

---

### 3.4 api_resolver.py - API 조회 및 분류

**역할**: 부품 정보를 외부 소스(API, 웹 검색)에서 조회하고 SMD/DIP를 분류합니다.

#### 클래스 구조도

```
api_resolver.py
│
├── PartInfo            # 부품 정보 데이터 클래스
├── MPNNormalizer       # MPN(부품번호) 정규화 유틸리티
├── AliasManager        # 부품 별칭 관리자
├── CacheManager        # API 조회 결과 캐싱
│
├── DigiKeyAPI          # Digi-Key API 클라이언트
├── MouserAPI           # Mouser API 클라이언트
├── WebSearchResolver   # DuckDuckGo 웹 검색
│
├── MountingClassifier  # SMD/DIP 분류기
└── PartResolver        # 통합 부품 정보 조회기
```

#### PartInfo 클래스

부품 정보를 담는 데이터 구조:
```python
class PartInfo:
    official_name: str    # 공식 부품명 (MPN)
    description: str      # 부품 설명
    package: str          # 패키지 (예: QFN-24, 0402)
    mounting_type: str    # 장착방식 (SMD, DIP, 미확정)
    datasheet_url: str    # 데이터시트 URL
    supplier: str         # 공급사 (Digi-Key, Mouser)
    supplier_pn: str      # 공급사 부품번호
    manufacturer: str     # 제조사
    source: str           # 정보 출처 (api/cache/heuristic/web)
```

#### MountingClassifier 클래스

SMD/DIP 분류 로직을 담당합니다. [7장](#7-smddip-분류-로직)에서 자세히 설명합니다.

#### PartResolver 클래스

모든 조회 방법을 통합하는 메인 클래스:

```python
resolver = PartResolver(config)

# 부품 정보 조회
info = resolver.resolve(
    mpn="STM32F103C8T6",      # 제조사 부품번호
    spec="MCU ARM 64KB",      # 스펙 (휴리스틱 분류용)
    manufacturer="ST",         # 제조사
    refdes="U1"               # 위치 (RefDes)
)

print(info.official_name)     # STM32F103C8T6
print(info.package)           # LQFP-48
print(info.mounting_type)     # SMD
print(info.source)            # api
```

##### 조회 우선순위

1. **캐시 확인** - 이전에 조회한 결과가 있으면 재사용
2. **웹 검색** (활성화 시) - DuckDuckGo로 빠르게 검색
3. **Digi-Key API** - OAuth 인증 필요
4. **Mouser API** - API 키 필요
5. **휴리스틱 분류** - 키워드 기반 분류 (API 없이도 동작)

---

### 3.5 excel_writer.py - 엑셀 출력

**역할**: 처리된 BOM 데이터를 서식이 적용된 엑셀 파일로 저장합니다.

#### ExcelWriter 클래스

```python
writer = ExcelWriter()

# 데이터 준비
writer.prepare_data(processed_df)

# 엑셀 파일 생성
success, message = writer.write("output.xlsx", include_review_sheet=True)

# 통계 확인
stats = writer.get_statistics()
print(f"SMD: {stats['smd_count']}, DIP: {stats['dip_count']}")
```

#### 출력 엑셀 특징

| 기능 | 설명 |
|------|------|
| **테이블 서식** | Excel Table + AutoFilter 자동 적용 |
| **색상 구분** | SMD=연두, DIP=주황, 미확정=노랑 |
| **검토 시트** | 미확정 항목만 모은 별도 시트 생성 |
| **열 너비 자동 조정** | 내용에 맞게 열 너비 최적화 |

#### 표준 출력 컬럼

```python
STANDARD_OUTPUT_COLUMNS = [
    'NO',           # 순번 (자동 생성)
    '품목',         # 부품 종류 (저항, 콘덴서, IC 등)
    '스펙',         # 사양 (10K 0402, 100nF 25V 등)
    '수량',         # 수량
    '위치',         # RefDes (R1, C1-C5 등)
    '장착방식',     # SMD / DIP / 미확정
    '공식부품명',   # 제조사 MPN
    '공급사',       # Digi-Key / Mouser
    '공급사부품번호', # 공급사 고유 번호
    '데이터시트URL', # 데이터시트 링크
]
```

---

### 3.6 main_gui.py - GUI 메인

**역할**: tkinter 기반 GUI를 제공하고 전체 워크플로우를 조율합니다.

#### 주요 클래스

| 클래스 | 역할 |
|--------|------|
| `MainApplication` | 메인 윈도우 및 전체 흐름 관리 |
| `ColumnMappingFrame` | 컬럼 매핑 UI |
| `SettingsFrame` | API 설정 UI |
| `AliasManagerFrame` | 별칭 관리 UI |
| `DataTableFrame` | 데이터 테이블 표시 |
| `ProcessWorker` | 백그라운드 처리 스레드 |
| `ToolTip` | 툴팁 도우미 |

#### MainApplication 클래스

```python
class MainApplication(tk.Tk):
    def __init__(self):
        self.parser = None          # BOMParser 인스턴스
        self.result_df = None       # 처리 결과 DataFrame
        self.worker = None          # 백그라운드 워커
        self._init_ui()             # UI 초기화
```

##### 주요 메서드

| 메서드 | 역할 |
|--------|------|
| `_browse_file()` | 파일 선택 다이얼로그 |
| `_load_file(path)` | 파일 로드 및 미리보기 |
| `_start_process()` | 처리 시작 (백그라운드) |
| `_on_progress(value, msg)` | 진행률 업데이트 |
| `_handle_finished(...)` | 처리 완료 핸들러 |
| `_save_excel()` | 엑셀 저장 |

#### GUI 탭 구조

```
┌─────────────────────────────────────────┐
│  📁 파일 선택: [___________] [찾기...] │
├─────────────────────────────────────────┤
│  [파일] [설정] [별칭관리] [결과]        │
├─────────────────────────────────────────┤
│                                         │
│     탭 내용 영역                        │
│                                         │
├─────────────────────────────────────────┤
│  [처리 시작]  [========] 50%           │
│  ▶ 현재 처리 중: R1-R10                │
└─────────────────────────────────────────┘
```

---

## 4. 데이터 흐름

### 4.1 전체 처리 흐름도

```
┌────────────────────────────────────────────────────────────────┐
│                         사용자                                  │
│                           │                                    │
│                           ▼                                    │
│                    ┌─────────────┐                             │
│                    │  파일 선택  │                              │
│                    └──────┬──────┘                             │
│                           │                                    │
│                           ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    bom_parser.py                         │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │   │
│  │  │ 파일 로드   │ → │ 헤더 탐지   │ → │ 컬럼 매핑   │   │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘  │   │
│  │                                              │          │   │
│  │                                              ▼          │   │
│  │                                    ┌─────────────────┐  │   │
│  │                                    │ 정규화 DataFrame│  │   │
│  │                                    └────────┬────────┘  │   │
│  └─────────────────────────────────────────────┼───────────┘   │
│                                                │               │
│                                                ▼               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   api_resolver.py                        │   │
│  │                                                          │   │
│  │  각 행(부품)에 대해:                                     │   │
│  │  ┌────────┐   ┌────────────┐   ┌───────────────────┐    │   │
│  │  │ 캐시   │ → │ 웹 검색    │ → │ API 조회          │    │   │
│  │  │ 확인   │   │(DuckDuckGo)│   │(Digi-Key/Mouser)  │    │   │
│  │  └────────┘   └────────────┘   └───────────────────┘    │   │
│  │       │              │                   │              │   │
│  │       └──────────────┴───────────────────┘              │   │
│  │                       │                                 │   │
│  │                       ▼                                 │   │
│  │              ┌─────────────────┐                        │   │
│  │              │ MountingClassifier                       │   │
│  │              │ (SMD/DIP 분류)  │                        │   │
│  │              └────────┬────────┘                        │   │
│  └───────────────────────┼─────────────────────────────────┘   │
│                          │                                     │
│                          ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   excel_writer.py                        │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │   │
│  │  │ 데이터 정리 │ → │ 엑셀 쓰기   │ → │ 스타일 적용 │   │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                     │
│                          ▼                                     │
│                   ┌─────────────┐                              │
│                   │ 표준 BOM.xlsx│                             │
│                   └─────────────┘                              │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 데이터 변환 예시

#### 입력 (sample_bom.csv)
```csv
NO,규격,스펙,수량,위치,MPN,제조사
1,저항,10K 0402,10,R1-R10,RC0402FR-0710KL,Yageo
2,IC,STM32F103C8T6,1,U1,STM32F103C8T6,ST
3,커넥터,2.54mm Pin Header 10P,2,J1-J2,PH1-10-UA,Samtec
```

#### 처리 후 (DataFrame)
```
품목    | 스펙                    | 수량 | 위치    | 장착방식 | 공식부품명        | ...
--------|------------------------|------|---------|---------|-------------------|----
저항    | 10K 0402               | 10   | R1-R10  | SMD     | RC0402FR-0710KL   | ...
IC      | STM32F103C8T6          | 1    | U1      | SMD     | STM32F103C8T6     | ...
커넥터  | 2.54mm Pin Header 10P  | 2    | J1-J2   | DIP     | PH1-10-UA         | ...
```

---

## 5. 주요 클래스 설명

### 5.1 BOMParser - 파서 클래스

#### 클래스 다이어그램

```
BOMParser
├── 속성
│   ├── raw_df: DataFrame          # 원본 데이터
│   ├── normalized_df: DataFrame   # 정규화된 데이터
│   ├── column_mapping: Dict       # 컬럼 매핑
│   ├── has_header: bool           # 헤더 존재 여부
│   └── file_path: str             # 파일 경로
│
├── 핵심 메서드
│   ├── load_file(path, header_row) → (bool, str)
│   ├── auto_detect_mapping() → Dict[str, str]
│   ├── set_mapping(mapping)
│   ├── normalize() → (bool, str)
│   ├── get_normalized_data() → DataFrame
│   └── get_preview(rows) → DataFrame
│
└── 내부 메서드
    ├── _unmerge_excel_cells(path)      # 병합 셀 해제
    ├── _detect_header_row(df)           # 헤더행 탐지
    ├── _infer_columns_from_data()       # 헤더리스 컬럼 추론
    ├── _is_quantity_value(val)          # 수량 값 확인
    ├── _is_refdes_value(val)            # RefDes 값 확인
    └── _is_mpn_value(val)               # MPN 값 확인
```

### 5.2 PartResolver - 통합 조회 클래스

#### 클래스 다이어그램

```
PartResolver
├── 속성
│   ├── config: Dict               # 설정
│   ├── cache: CacheManager        # 캐시 관리자
│   ├── alias_manager: AliasManager # 별칭 관리자
│   ├── digikey: DigiKeyAPI        # Digi-Key 클라이언트
│   ├── mouser: MouserAPI          # Mouser 클라이언트
│   ├── web_search: WebSearchResolver # 웹 검색
│   └── classifier: MountingClassifier # 분류기
│
└── 메서드
    ├── resolve(mpn, spec, ...) → PartInfo
    │   # 부품 정보 통합 조회
    │   # 1. 캐시 확인
    │   # 2. 웹 검색 (활성화 시)
    │   # 3. API 조회 (Digi-Key, Mouser)
    │   # 4. 휴리스틱 분류
    │
    └── get_api_status() → Dict
        # API 설정 상태 확인
```

### 5.3 ExcelWriter - 엑셀 출력 클래스

#### 클래스 다이어그램

```
ExcelWriter
├── 스타일 상수
│   ├── HEADER_FONT: Font          # 헤더 폰트
│   ├── HEADER_FILL: PatternFill   # 헤더 배경색
│   ├── SMD_FILL: PatternFill      # SMD 행 색상 (연두)
│   ├── DIP_FILL: PatternFill      # DIP 행 색상 (주황)
│   └── UNCERTAIN_FILL: PatternFill # 미확정 색상 (노랑)
│
├── 속성
│   ├── df: DataFrame              # 출력할 데이터
│   └── statistics: Dict           # 통계 정보
│
└── 메서드
    ├── prepare_data(df)           # 데이터 준비
    ├── write(path, include_review_sheet) → (bool, str)
    │   # 엑셀 파일 생성
    ├── _apply_styles(path)        # 스타일 적용
    ├── _style_sheet(ws, ...)      # 시트 스타일링
    └── get_statistics() → Dict    # 통계 반환
```

---

## 6. 설정 및 설정 파일

### 6.1 user_config.json

사용자 설정을 저장하는 JSON 파일입니다. 프로그램 실행 시 자동 생성됩니다.

```json
{
  "digikey_client_id": "your_client_id",
  "digikey_client_secret": "your_client_secret",
  "digikey_access_token": "",
  "digikey_refresh_token": "",
  "digikey_token_expires": 0,
  "mouser_api_key": "",
  "api_call_delay": 0.5,
  "cache_ttl_days": 30,
  "use_cache": true,
  "use_web_search": false,
  "last_input_dir": "",
  "last_output_dir": ""
}
```

| 키 | 설명 | 기본값 |
|----|------|--------|
| `digikey_client_id` | Digi-Key OAuth Client ID | (빈 문자열) |
| `digikey_client_secret` | Digi-Key OAuth Client Secret | (빈 문자열) |
| `mouser_api_key` | Mouser API Key | (빈 문자열) |
| `api_call_delay` | API 호출 간격 (초) | 0.5 |
| `cache_ttl_days` | 캐시 유효기간 (일) | 30 |
| `use_cache` | 캐시 사용 여부 | true |
| `use_web_search` | 웹 검색 사용 여부 | false |

### 6.2 part_aliases.json

동일 부품의 다양한 표기를 관리하는 별칭 사전입니다.

```json
{
  "_description": "동일 부품의 다양한 표기를 관리하는 별칭 사전",
  "aliases": {
    "RC0402FR-0710KL": {
      "variants": ["RC0402FR0710KL", "RC0402FR-07-10K"],
      "category": "칩저항",
      "package": "0402"
    }
  },
  "category_mappings": {
    "RESISTOR-CHIP": "칩저항",
    "CAPACITOR-CHIP": "칩콘덴서",
    "CHIP LED": "칩LED"
  },
  "ignore_patterns": ["^\\s*$", "^N/A$", "^TBD$"]
}
```

### 6.3 resolver_cache.json

API 조회 결과를 캐싱하여 중복 호출을 방지합니다.

```json
{
  "STM32F103C8T6": {
    "info": {
      "official_name": "STM32F103C8T6",
      "package": "LQFP-48",
      "mounting_type": "SMD",
      ...
    },
    "timestamp": 1704931200
  }
}
```

---

## 7. SMD/DIP 분류 로직

### 7.1 분류 우선순위

`MountingClassifier.classify()` 메서드는 다음 우선순위로 장착방식을 결정합니다:

```
1. 공급사 API 제공 정보 (가장 신뢰도 높음)
   └─ mounting 파라미터가 "SMD"/"Surface Mount" 또는 "Through Hole"

2. 패키지명 기반 분류
   └─ SMD 키워드: QFN, SOIC, 0402, BGA, SOT-23 등
   └─ DIP 키워드: DIP, TO-220, AXIAL, PIN HEADER 등

3. 카테고리 기반 분류
   └─ SMD 카테고리: 칩저항, 칩콘덴서, MLCC 등
   └─ DIP 카테고리: 전해콘덴서, 커넥터 등

4. RefDes 기반 추정
   └─ R, C, L (수동소자) → SMD 가능성 높음
   └─ J, CN (커넥터) → 확인 필요

5. 스펙 분석
   └─ 사이즈 코드 (0402, 0603, 1206 등) → SMD
   └─ TO-220, Radial 등 → DIP
```

### 7.2 분류 결과

| 결과 | 의미 | 색상 |
|------|------|------|
| `SMD` | 표면실장 (확실함) | 연두 |
| `DIP` | 수삽/스루홀 (확실함) | 주황 |
| `SMD(추정)` | SMD로 추정 (확인 권장) | 연두 |
| `DIP(추정)` | DIP로 추정 (확인 권장) | 주황 |
| `확인필요` | SMD/DIP 혼용 부품 | 노랑 |
| `미확정` | 판단 불가 | 노랑 |

### 7.3 특수 케이스 처리

#### 크리스탈/오실레이터
```python
# SMD 크리스탈 패키지
SMD_CRYSTAL_PACKAGES = ['HC49S', 'HC49SM', '3215', '2520', '5032']

# THT 크리스탈 패키지  
THT_CRYSTAL_PACKAGES = ['HC49', 'HC49U', 'HC18']
```

#### TO 패키지 (SMD 버전 존재)
```python
# 일반적으로 DIP인 TO 패키지 중 SMD 버전
TO_PACKAGE_SMD_VARIANTS = ['TO-252', 'TO-263', 'D-PAK', 'D2PAK', 'DPAK']
```

#### 전해콘덴서
```python
# 일반 전해콘덴서 → DIP (Radial)
ELECTROLYTIC_KEYWORDS = ['ELECTROLYTIC', 'RADIAL CAP', '전해']

# SMD 전해콘덴서 → SMD
SMD_ELECTROLYTIC_KEYWORDS = ['SMD ELECTROLYTIC', 'V-CHIP']
```

### 7.4 분류 예시

```python
classifier = MountingClassifier()

# 예시 1: 패키지명으로 확실히 분류
result, reason = classifier.classify(package="QFN-24")
# → ("SMD", "패키지 QFN-24 → SMD")

# 예시 2: 사이즈 코드로 분류
result, reason = classifier.classify(spec="10K 0402 1%")
# → ("SMD", "사이즈 코드 0402 → SMD")

# 예시 3: TO 패키지 (DIP 버전)
result, reason = classifier.classify(package="TO-220")
# → ("DIP", "패키지 TO-220 → DIP")

# 예시 4: 커넥터 (혼용 부품)
result, reason = classifier.classify(spec="Pin Header 10P")
# → ("확인필요", "커넥터/헤더류 - SMD/DIP 혼용")
```

---

## 8. API 연동 방식

### 8.1 Digi-Key API

#### 인증 방식
OAuth 2.0 Client Credentials Grant를 사용합니다.

```python
class DigiKeyAPI:
    BASE_URL = "https://api.digikey.com/products/v4"
    AUTH_URL = "https://api.digikey.com/v1/oauth2/token"
    
    def _get_access_token(self):
        """OAuth 토큰 발급"""
        response = requests.post(self.AUTH_URL, data={
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        })
        # 토큰 저장 및 만료 시간 관리
```

#### 검색 API
```python
def search_part(self, keyword: str) -> Optional[PartInfo]:
    """부품 검색"""
    headers = {
        'Authorization': f'Bearer {self.access_token}',
        'X-DIGIKEY-Client-Id': self.client_id
    }
    response = requests.get(
        f"{self.BASE_URL}/search/{keyword}/productdetails",
        headers=headers
    )
    # 응답 파싱 및 PartInfo 생성
```

### 8.2 Mouser API

#### 인증 방식
API Key를 URL 파라미터로 전달합니다.

```python
class MouserAPI:
    BASE_URL = "https://api.mouser.com/api/v1"
    
    def search_part(self, keyword: str) -> Optional[PartInfo]:
        """부품 검색"""
        response = requests.post(
            f"{self.BASE_URL}/search/partnumber",
            params={'apiKey': self.api_key},
            json={'SearchByPartRequest': {'mouserPartNumber': keyword}}
        )
        # 응답 파싱 및 PartInfo 생성
```

### 8.3 웹 검색 (DuckDuckGo)

API 없이도 부품 정보를 조회할 수 있는 대안입니다.

```python
class WebSearchResolver:
    TRUSTED_DOMAINS = [
        'digikey.com', 'mouser.com', 'lcsc.com',
        'element14.com', 'arrow.com', 'octopart.com'
    ]
    
    def search_part(self, query: str) -> Optional[PartInfo]:
        """DuckDuckGo 검색으로 부품 정보 조회"""
        # duckduckgo-search 라이브러리 사용
        # 신뢰할 수 있는 도메인의 결과만 파싱
```

### 8.4 API 조회 흐름

```
resolve() 호출
     │
     ▼
┌─────────────┐
│ 캐시 확인   │───────────────────┐
└──────┬──────┘                   │
       │ 캐시 없음               │ 캐시 있음
       ▼                         │
┌─────────────┐                   │
│ 웹 검색     │─── 결과 있음 ──┐ │
│ (선택)      │                 │ │
└──────┬──────┘                 │ │
       │ 결과 없음             │ │
       ▼                       │ │
┌─────────────┐                 │ │
│ Digi-Key    │─── 결과 있음 ─┐│ │
│ API         │               ││ │
└──────┬──────┘               ││ │
       │ 결과 없음           ││ │
       ▼                     ││ │
┌─────────────┐               ││ │
│ Mouser API  │─── 결과 있음 ┐││ │
└──────┬──────┘              │││ │
       │ 결과 없음          │││ │
       ▼                    │││ │
┌─────────────┐              │││ │
│ 휴리스틱    │              │││ │
│ 분류        │              │││ │
└──────┬──────┘              │││ │
       │                     ││││
       └─────────────────────┘│││
              ┌───────────────┘││
              │  ┌─────────────┘│
              │  │  ┌───────────┘
              ▼  ▼  ▼
        ┌─────────────┐
        │ 캐시 저장   │
        └──────┬──────┘
               │
               ▼
          PartInfo 반환
```

---

## 9. 확장 및 커스터마이징

### 9.1 새로운 컬럼명 후보 추가

`config.py`의 `COLUMN_MAP_CANDIDATES`에 추가:

```python
COLUMN_MAP_CANDIDATES = {
    '품목': [
        '품목', '품명', 
        # 새로운 컬럼명 추가
        'part_type', 'component_category',
    ],
    # ...
}
```

### 9.2 새로운 SMD/DIP 키워드 추가

```python
# SMD 키워드 추가
SMD_KEYWORDS = [
    # 기존 키워드들...
    'NEW_SMD_PACKAGE',  # 새로운 SMD 패키지
]

# DIP 키워드 추가
DIP_KEYWORDS = [
    # 기존 키워드들...
    'NEW_DIP_PACKAGE',  # 새로운 DIP 패키지
]
```

### 9.3 새로운 API 추가

`api_resolver.py`에 새 클래스 추가:

```python
class NewSupplierAPI:
    """새 공급사 API"""
    BASE_URL = "https://api.newsupplier.com"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def search_part(self, keyword: str) -> Optional[PartInfo]:
        """부품 검색 구현"""
        # API 호출 및 파싱 로직
        pass
    
    def is_configured(self) -> bool:
        return bool(self.api_key)
```

그리고 `PartResolver`에 통합:
```python
class PartResolver:
    def __init__(self, config):
        # ...
        self.new_supplier = NewSupplierAPI(config.get('new_api_key', ''))
    
    def resolve(self, ...):
        # ...
        # 새 API 조회 추가
        if self.new_supplier.is_configured():
            info = self.new_supplier.search_part(mpn)
            if info:
                return info
```

### 9.4 출력 컬럼 수정

`config.py`의 `STANDARD_OUTPUT_COLUMNS` 수정:

```python
STANDARD_OUTPUT_COLUMNS = [
    'NO',
    '품목',
    '스펙',
    '수량',
    '위치',
    '장착방식',
    '공식부품명',
    '제조사',     # 새 컬럼 추가
    '단가',       # 새 컬럼 추가
    '공급사',
    '공급사부품번호',
    '데이터시트URL',
]
```

---

## 부록: 자주 묻는 질문 (FAQ)

### Q1: API 키 없이도 사용할 수 있나요?
**A:** 네, 가능합니다. 휴리스틱 분류 기능으로 패키지명이나 스펙에서 SMD/DIP를 판별합니다. 다만 공식 부품명이나 데이터시트 URL은 조회할 수 없습니다.

### Q2: 캐시 파일이 너무 커졌어요.
**A:** `resolver_cache.json` 파일을 삭제하면 됩니다. 다음 조회 시 새로 생성됩니다.

### Q3: 특정 부품이 계속 잘못 분류됩니다.
**A:** 두 가지 방법이 있습니다:
1. **별칭 관리** 탭에서 해당 부품의 카테고리/패키지 정보 등록
2. `config.py`의 키워드 목록에 해당 패키지 추가

### Q4: 새로운 파일 형식을 지원하고 싶어요.
**A:** `bom_parser.py`의 `load_file()` 메서드에 새 형식 처리 로직을 추가하세요:
```python
def load_file(self, file_path, ...):
    ext = Path(file_path).suffix.lower()
    if ext == '.new_format':
        # 새 형식 처리 로직
        pass
```

### Q5: GUI 디자인을 변경하고 싶어요.
**A:** `main_gui.py`의 각 Frame 클래스를 수정하세요. tkinter 위젯 배치는 `_create_widgets()` 메서드에서 관리합니다.

---

## 문서 정보

- **버전**: 2.0.0
- **최종 수정**: 2026-01-14
- **작성 기준 코드 버전**: 현재 main 브랜치

---

*이 문서는 초보 개발자도 이해할 수 있도록 작성되었습니다. 추가 질문이 있으시면 이슈를 등록해 주세요.*
