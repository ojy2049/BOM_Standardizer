#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
설정 파일 - API 키, 컬럼 매핑 규칙 등
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any

# ============== 경로 설정 ==============
APP_DIR = Path(__file__).parent
CONFIG_FILE = APP_DIR / "user_config.json"
CACHE_FILE = APP_DIR / "resolver_cache.json"
COMPONENTS_DB_FILE = APP_DIR / "components_db.json"

# ============== 기본 설정 ==============
DEFAULT_CONFIG = {
    # Digi-Key API 설정
    "digikey_client_id": "",
    "digikey_client_secret": "",
    "digikey_access_token": "",
    "digikey_refresh_token": "",
    "digikey_token_expires": 0,
    
    # Mouser API 설정
    "mouser_api_key": "",
    
    # 일반 설정
    "api_call_delay": 0.5,  # API 호출 간격 (초)
    "cache_ttl_days": 30,   # 캐시 유효기간 (일)
    "use_cache": True,
    "last_input_dir": "",
    "last_output_dir": "",
}

# ============== 컬럼 매핑 후보 ==============
# 업체별 BOM에서 사용할 수 있는 컬럼명 후보들
# 참고: 'no' (번호)는 자동 생성되므로 매핑하지 않음
COLUMN_MAP_CANDIDATES = {
    '품목': [
        '품목', '품명', '품목명', 'item', 'type', 'category', '부품종류', 'part type', 'component type', 
        'component', 'part name', 'parts', '부품',
        'component name', 'comp', 'comp type', '부품명',
        'p_code', 'name',  # 이미지 3번 포맷 추가
    ],
    '스펙': [
        '스펙', '규격', 'spec', 'specification', 'desc', 'description', 'value', '값', 
        '전기적특성', 'electrical', 'parameters', 'details', 'remark', 'remarks', 'note',
        'name',  # 이미지 3번 포맷 - 부품명에 스펙 포함
    ],
    '수량': ['수량', '소요량', '소요', 'qty', 'quantity', 'q\'ty', 'count', 'ea', 'pcs', '개수', 'amount',
             'b_qty'],  # 이미지 3번 포맷 추가
    '위치': ['위치', 'refdes', 'ref', 'reference', 'location', 'pos', 'R-No', 'position', 'designator', 'ref designator', 'ref des',
             'b_code', 'loc'],  # 이미지 3번 포맷 추가
    'mpn': [
        'mpn', 'manufacturer part number', '제조사부품번호', 
        'mfr_pn', 'mfr pn', 'mfg pn', 'mfg p/n', 
        'part number', 'p/n', 'pn', 'part no', 'part#', '부품번호',
        'p_code',  # 이미지 3번 포맷 추가
    ],
    'manufacturer': [
        'manufacturer', 'manufacture', 'mfr', 'mfg', '제조사', 
        'brand', 'make', 'maker',
        'supplyer', 'supplier', '공급사',  # 이미지 3번 포맷 추가
    ],
    'digi_pn': ['digikey_pn', 'digikey part number', 'dk_pn', 'digi-key', 'digikey', 'dk pn', 'dk p/n'],
    'mouser_pn': ['mouser_pn', 'mouser part number', 'ms_pn', 'mouser', 'mouser p/n'],
    'package': ['package', 'pkg', '패키지', 'footprint', 'case', 'package/case', 'size'],
    # 이미지 3번 포맷 추가 컬럼
    'gubun': ['gubun', '구분', 'mounting', 'mounting type', '장착방식'],  # SMD/DIP 구분
}

# ============== 부품 종류 키워드 (규격 컬럼 내용 탐지용) ==============
# 컬럼 내용에 이 키워드들이 많이 포함되어 있으면 '품목' 컬럼으로 인식
COMPONENT_TYPE_KEYWORDS = [
    # 반도체 - IC
    'IC', 'MCU', 'CPU', 'MPU', 'DSP', 'FPGA', 'CPLD', 'ASIC', 'SOC',
    'OPAMP', 'OP-AMP', 'OP AMP', 'COMPARATOR', 'ADC', 'DAC',
    'REGULATOR', 'LDO', 'DCDC', 'DC-DC', 'CONVERTER', 'DRIVER',
    'AMPLIFIER', 'AMP', 'TRANSISTOR', 'MOSFET', 'FET', 'BJT', 'IGBT',
    'EEPROM', 'FLASH', 'SRAM', 'DRAM', 'MEMORY', 'ROM',
    
    # 반도체 - 다이오드
    'DIODE', 'LED', 'ZENER', 'SCHOTTKY', 'TVS', 'ESD', 'RECTIFIER',
    
    # 수동소자
    'RESISTOR', 'CAPACITOR', 'INDUCTOR', 'FERRITE', 'BEAD',
    'RES', 'CAP', 'IND', 'COIL', 'CHOKE',
    
    # 커넥터
    'CONNECTOR', 'HEADER', 'SOCKET', 'JACK', 'PLUG', 'TERMINAL',
    'USB', 'HDMI', 'RJ45', 'RJ11', 'FPC', 'FFC', 'ZIF',
    
    # 기구/기타
    'CRYSTAL', 'OSCILLATOR', 'OSC', 'XTAL', 'RESONATOR',
    'FUSE', 'PTC', 'NTC', 'THERMISTOR', 'VARISTOR',
    'RELAY', 'SWITCH', 'BUTTON', 'ENCODER',
    'TRANSFORMER', 'HEATSINK', 'HEAT SINK', 'FAN',
    'SENSOR', 'TRANSDUCER', 'PHOTODIODE', 'PHOTOTRANSISTOR',
    'OPTOCOUPLER', 'OPTO', 'ISOLATOR',
    'ANTENNA', 'FILTER', 'EMI', 'RF',
    'BATTERY', 'HOLDER', 'CLIP', 'STANDOFF', 'SCREW', 'NUT', 'WASHER',
    
    # 한글 부품명
    '저항', '콘덴서', '캐패시터', '인덕터', '코일', '다이오드',
    '트랜지스터', '커넥터', '헤더', '소켓', '릴레이', '스위치',
    '퓨즈', '크리스탈', '오실레이터', '센서', '히트싱크', '방열판',
    '안테나', '필터', '변압기', '배터리', '홀더',
    'LED', 'IC', '칩', 'CHIP',
]

# ============== 알려진 제조사 목록 (헤더 없는 BOM 컬럼 추론용) ==============
KNOWN_MANUFACTURERS = [
    # 대형 반도체
    'TI', 'TEXAS INSTRUMENTS', 'ST', 'STMICROELECTRONICS', 'NXP', 'INFINEON',
    'MICROCHIP', 'ANALOG DEVICES', 'ADI', 'MAXIM', 'ON SEMI', 'ONSEMI',
    'RENESAS', 'ROHM', 'TOSHIBA', 'NEXPERIA', 'DIODES', 'VISHAY',
    # 수동소자
    'MURATA', 'TDK', 'YAGEO', 'SAMSUNG', 'SAMSUNG ELECTRO', 'AVX', 'KEMET',
    'PANASONIC', 'NICHICON', 'NIPPON CHEMI-CON', 'RUBYCON', 'WÜRTH', 'WURTH',
    'BOURNS', 'SUSUMU', 'KOA', 'WALSIN',
    # 커넥터
    'MOLEX', 'TE CONNECTIVITY', 'TE', 'JST', 'HIROSE', 'AMPHENOL', 'SAMTEC',
    'PHOENIX CONTACT', 'WAGO', 'HARTING',
    # LED/광학
    'LITE-ON', 'LITEON', 'CREE', 'OSRAM', 'LUMILEDS', 'KINGBRIGHT', 'EVERLIGHT',
    # 기타
    'ABRACON', 'EPSON', 'NDK', 'BEL FUSE', 'LITTELFUSE', 'EATON', 'SCHURTER',
    'OMRON', 'ALPS', 'CUI', 'MEAN WELL', 'MORNSUN', 'XP POWER',
]

# ============== RefDes 패턴 (위치 컬럼 추론용) ==============
# RefDes 접두어 패턴: R(저항), C(콘덴서), L(인덕터), U(IC), Q(트랜지스터), D(다이오드) 등
REFDES_PREFIXES = [
    'R', 'C', 'L', 'U', 'Q', 'D', 'LED', 'J', 'P', 'CN', 'CON',
    'T', 'TR', 'F', 'FB', 'Y', 'X', 'SW', 'BT', 'TP', 'M', 'K',
]


SMD_KEYWORDS = [
    # 명시적 표면실장
    'SMD', 'SMT', 'SURFACE MOUNT', 'SURFACE-MOUNT',
    
    # ===== IC 패키지 (웹 검색 결과 기반 확장) =====
    # QFP 계열 (Quad Flat Package) - 4면에 핀
    'QFN', 'QFP', 'TQFP', 'LQFP', 'VQFP', 'MQFP', 'PQFP', 'CQFP', 'HQFP', 
    'EQFP', 'BQFP', 'FQFP',  # 추가된 QFP 변형
    
    # SOIC/SOP 계열 (Small Outline) - 2면에 핀
    'SOIC', 'SOP', 'SSOP', 'TSSOP', 'TSOP', 'MSOP', 'QSOP', 'VSOP', 'HSOP',
    'SO-8', 'SO-14', 'SO-16', 'SO-20', 'SO-24', 'SO-28',  # SO + 핀 수
    'SOIC-8', 'SOIC-14', 'SOIC-16', 'SOIC-20',  # SOIC + 핀 수
    'SOP-8', 'SOP-16', 'SOP-24',  # SOP + 핀 수
    
    # SOT 계열 (Small Outline Transistor) - 3~8핀 소형 트랜지스터/IC
    'SOT-23', 'SOT-89', 'SOT-223', 'SOT-323', 'SOT-363', 'SOT-523', 
    'SOT-563', 'SOT-723', 'SOT-883', 'SOT-953', 'SOT',
    'SOT23-3', 'SOT23-5', 'SOT23-6',  # SOT23 핀 수 변형
    
    # SOD 계열 (Small Outline Diode) - SMD 다이오드
    'SOD-123', 'SOD-323', 'SOD-523', 'SOD-723', 'SOD-923', 
    'SOD-128', 'SOD-80', 'SOD-57', 'SOD-87', 'SOD',
    'SODFL',  # Flat Lead 버전
    
    # BGA/CSP 계열 (Ball Grid Array) - 고밀도
    'BGA', 'FBGA', 'PBGA', 'CBGA', 'TBGA', 'UBGA', 'MBGA',
    'WLCSP', 'CSP', 'FCBGA', 'μBGA', 'MICROBGA', 'LFBGA',
    'TFBGA', 'VFBGA', 'UFBGA', 'DSBGA',  # 추가 BGA 변형
    
    # DFN/SON/LLP 계열 (Dual/Quad Flat No-leads) - 리드 없음
    'DFN', 'SON', 'WSON', 'VSON', 'UDFN', 'UQFN', 'TDFN', 'XDFN',
    'QFN', 'VQFN', 'WQFN', 'TQFN', 'UQFN',  # QFN 변형
    'LLP', 'MLF', 'MLP',  # Leadless Leadframe Package
    'HVSON', 'HVQFN',  # High Voltage 버전
    
    # LGA/LCC 계열 (Land Grid Array / Leadless Chip Carrier)
    'LGA', 'PLCC', 'CLCC', 'LCC', 'LLCC',
    
    # ===== 칩 저항/캡 사이즈 코드 (인치 단위) =====
    '01005', '0201', '0402', '0603', '0805', '1206', '1210', 
    '1218', '1812', '1825', '2010', '2512', '2220', '2225',
    '3012', '3025', '4020', '5025', '6030',  # 대형 칩 추가
    
    # ===== 칩 저항/캡 사이즈 코드 (메트릭 단위) =====
    '0402M', '0603M', '1005M', '1608M', '2012M', '3216M', 
    '3225M', '4532M', '5025M', '6332M',
    '0603 METRIC', '1005 METRIC',  # 명시적 메트릭
    
    # 기타 SMD 용어
    'CHIP', 'MLCC', 'CHIP CAP', 'CHIP RES', 'CHIP IND',
    
    # ===== DO 계열 SMD (SMD 다이오드/정류기) =====
    'DO-214', 'DO-218', 'DO-219', 'DO-214AA', 'DO-214AB', 'DO-214AC',
    'SMA', 'SMB', 'SMC', 'SMAJ', 'SMBJ', 'SMCJ',  # TVS 다이오드
    'MELF', 'MINIMELF', 'MICROMELF',  # Metal Electrode Leadless Face
    
    # SC 계열 (SMD 트랜지스터 - JEDEC 표준)
    'SC-70', 'SC-88', 'SC-89', 'SC-90', 'SC-59', 'SC-75',
    
    # 기타 SMD IC 패키지
    'LFCSP', 'FCSP', 'WLGA', 'UTQFN', 'XSON',
    'MSOP-8', 'MSOP-10',  # MSOP 핀 수
    'TSSOP-8', 'TSSOP-14', 'TSSOP-16', 'TSSOP-20',  # TSSOP 핀 수
    
    # ===== SMD 커넥터 (명시적 SMD) =====
    'SMD CONNECTOR', 'SMT CONNECTOR', 'SMD HEADER', 'SMT HEADER',
]

# HC/SMD 크리스탈 및 오실레이터 패키지
SMD_CRYSTAL_PACKAGES = [
    'HC49S', 'HC49SM', 'HC49SMD',  # SMD 버전 HC49
    '3215', '2520', '2016', '1612', '5032', '7050', '3225',  # 크리스탈 사이즈 코드
    '2012', '2512', '4025', '6035',  # 추가 크리스탈 사이즈
]

THT_CRYSTAL_PACKAGES = ['HC49', 'HC49U', 'HC18', 'HC6', 'HC51', 'HC52']

DIP_KEYWORDS = [
    # 명시적 스루홀
    'THROUGH HOLE', 'THROUGH-HOLE', 'THT', 'TH', 'PTH',
    'LEADED', 'LEAD',  # 리드 있음
    
    # ===== DIP IC 패키지 계열 =====
    'DIP', 'PDIP', 'CDIP', 'SDIP', 'SPDIP', 'HDIP',
    'DIP-8', 'DIP-14', 'DIP-16', 'DIP-20', 'DIP-24', 'DIP-28', 'DIP-40',  # DIP + 핀 수
    'SKINNY DIP', 'SHRINK DIP',  # DIP 변형
    
    # PGA 계열 (Pin Grid Array) - 스루홀
    'PGA', 'CPGA', 'PPGA', 'FCPGA', 'SPGA', 'OPGA',
    
    # SIP/ZIP 계열 (Single/Zigzag In-line)
    'SIP', 'ZIP',
    
    # ===== TO 패키지 (Through-Hole 버전) =====
    'TO-92', 'TO-92L', 'TO-92MOD',
    'TO-126', 'TO-127',
    'TO-220', 'TO-220F', 'TO-220AB', 'TO-220AC', 'TO-220FP',
    'TO-247', 'TO-247AC', 'TO-247AD', 'TO-264',
    'TO-251', 'TO-262',
    'TO-3', 'TO-3P', 'TO-66', 'TO-99', 'TO-5', 'TO-18', 'TO-39',
    
    # ===== DO 계열 THT (Through-Hole 다이오드) =====
    'DO-35', 'DO-41', 'DO-15', 'DO-27', 'DO-201', 'DO-201AD',
    'DO-4', 'DO-5', 'DO-34', 'DO-204',
    
    # ===== 축형/방사형 부품 =====
    'AXIAL', 'RADIAL', 'AXIAL LEAD', 'RADIAL LEAD',
    'CARBON FILM', 'METAL FILM',  # 저항 유형
    
    # ===== 기계부품 / 하드웨어 =====
    'JUMPER', 'WIRE', 'SCREW', 'NUT', 'BOLT', 'STANDOFF', 'SPACER',
    'HEATSINK', 'HEAT SINK', 'HEAT-SINK',
    'CLIP', 'CLAMP', 'BRACKET', 'HOLDER',
    
    # ===== 커넥터 (수삽형) =====
    'WAFER', 'WAFER CONNECTOR',
    'PIN HEADER', 'BOX HEADER', 'SHROUDED HEADER',
    'IDC', 'IDC CONNECTOR',  # Insulation Displacement Connector
    'TERMINAL BLOCK',
    'BARRIER BLOCK', 'SCREW TERMINAL',
    'DB9', 'DB15', 'DB25', 'D-SUB',  # D-Sub 커넥터 (주로 THT)
    
    # ===== 패널 마운트 =====
    'PANEL MOUNT', 'CHASSIS MOUNT', 'FLANGE MOUNT',
    
    # ===== 전원/고전류 부품 =====
    'POWER CONNECTOR', 'BARREL JACK', 'DC JACK',
]

# ============== 메트릭 SMD 사이즈 코드 (확장) ==============
SMD_METRIC_SIZES = [
    '0402', '0603', '1005', '1608', '2012', '3216', '3225', 
    '4532', '5750', '6432',
    '1005M', '1608M', '2012M', '3216M',  # M 접미사 버전
]

# ============== 전해콘덴서 키워드 (DIP 추정) ==============
ELECTROLYTIC_KEYWORDS = [
    'ELECTROLYTIC', 'ELEC', 'ELEC CAP',
    'AL CAP', 'ALUMINUM', 'ALUMINUM CAP', 'ALUMINUM ELECTROLYTIC',
    'RADIAL CAP', 'RADIAL CAPACITOR', 'RADIAL ELECTROLYTIC',
    '전해', 'POLARIZED',  # 유극성
]

# ============== SMD 알루미늄 전해콘덴서 (SMD 버전도 있음) ==============
SMD_ELECTROLYTIC_KEYWORDS = [
    'SMD ELECTROLYTIC', 'SMT ELECTROLYTIC', 'CHIP ELECTROLYTIC',
    'V-CHIP', 'SMD AL CAP',
]

# ============== 확인필요 부품 키워드 (SMD/DIP 혼용) ==============
UNCERTAIN_PART_KEYWORDS = [
    # 커넥터 (SMD/DIP 혼용)
    'HEADER', 'SOCKET', 'CONNECTOR', 'RECEPTACLE',
    # 스위치 (SMD/DIP 혼용)
    'SWITCH', 'SW', 'TACT', 'TACTILE', 'PUSHBUTTON', 'TOGGLE',
    # 세라믹 콘덴서 (패키지 미명시 시)
    'CERAMIC', 'DISC CERAMIC',
    # 릴레이 (SMD/DIP 혼용)
    'RELAY',
    # 퓨즈 (SMD/DIP 혼용)
    'FUSE',
]

# ============== TO 패키지 예외 처리 (SMD 버전) ==============
TO_PACKAGE_SMD_VARIANTS = [
    # D-PAK / D2PAK 계열
    'TO-252', 'TO-263', 'D-PAK', 'D2PAK', 'DPAK', 'D2-PAK',
    'TO-252AA', 'TO-263AB',
    # I-PAK / I2PAK 계열
    'TO-251AA', 'I-PAK', 'IPAK',
    # SOT 스타일 TO 패키지
    'TO-261', 'SOT-89', 'TO-236', 'SOT-23', 'TO-243',
    # 기타 SMD 파워 패키지
    'LFPAK', 'LFPAK33', 'LFPAK56', 'LFPAK88',
    'PowerPAK', 'PowerFLAT',
]

# ============== 표준 출력 컬럼 ==============
STANDARD_OUTPUT_COLUMNS = [
    'NO',
    '품목',
    '스펙',
    '수량',
    '위치',
    '장착방식',
    '공식부품명',
    '공급사',
    '공급사부품번호',
    '데이터시트URL',
]


def load_config() -> Dict[str, Any]:
    """사용자 설정 로드"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                # 기본값과 병합
                config = DEFAULT_CONFIG.copy()
                config.update(user_config)
                return config
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> bool:
    """사용자 설정 저장"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"설정 저장 실패: {e}")
        return False


def get_env_or_config(key: str, config: Dict[str, Any] = None) -> str:
    """환경변수 우선, 없으면 설정파일에서 가져오기"""
    env_map = {
        'digikey_client_id': 'DIGIKEY_CLIENT_ID',
        'digikey_client_secret': 'DIGIKEY_CLIENT_SECRET',
        'mouser_api_key': 'MOUSER_API_KEY',
    }
    
    if key in env_map:
        env_val = os.getenv(env_map[key])
        if env_val:
            return env_val
    
    if config is None:
        config = load_config()
    
    return config.get(key, '')


def load_components_db() -> Dict[str, Any]:
    """전자부품 데이터베이스 로드"""
    if COMPONENTS_DB_FILE.exists():
        try:
            with open(COMPONENTS_DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"컴포넌트 DB 로드 실패: {e}")
    return {}


def get_mounting_type_from_package(package: str) -> str:
    """패키지명으로 장착방식(SMD/DIP) 판별"""
    db = load_components_db()
    package_map = db.get("package_mounting_map", {})
    if not package_map:
        return "확인필요"
    
    package_upper = package.upper().strip()
    
    # SMD 패키지 확인
    for smd_pkg in package_map.get("SMD", []):
        if smd_pkg.upper() in package_upper or package_upper in smd_pkg.upper():
            return "SMD"
    
    # DIP 패키지 확인
    for dip_pkg in package_map.get("DIP", []):
        if dip_pkg.upper() in package_upper or package_upper in dip_pkg.upper():
            return "DIP"
    
    return "확인필요"

