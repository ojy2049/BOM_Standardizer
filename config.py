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
COLUMN_MAP_CANDIDATES = {
    'no': ['no', '번호', 'seq', 'sequence', 'item', 'item no', 'item#', '#', 'line'],
    '규격': ['규격', 'type', 'category', '부품종류', 'part type', 'component type', '품명', 'name', 'description', 'part name'],
    '스펙': ['스펙', 'spec', 'specification', 'desc', 'value', '값', '전기적특성', 'electrical', 'parameters', 'details'],
    '수량': ['수량', 'qty', 'quantity', 'q\'ty', 'count', 'ea', 'pcs', '개수'],
    '위치': ['위치', 'refdes', 'ref', 'reference', 'location', 'pos', 'position', 'designator', 'ref designator', 'ref des'],
    'mpn': ['mpn', 'manufacturer part number', '제조사부품번호', 'mfr_pn', 'mfr pn', 'mfg pn', 'mfg p/n', 'part number', 'p/n', 'pn', 'part no', 'part#', '부품번호'],
    'manufacturer': ['manufacturer', 'mfr', 'mfg', '제조사', 'vendor', 'brand', 'make'],
    'digi_pn': ['digikey_pn', 'digikey part number', 'dk_pn', 'digi-key', 'digikey', 'dk pn', 'dk p/n'],
    'mouser_pn': ['mouser_pn', 'mouser part number', 'ms_pn', 'mouser', 'mouser p/n'],
    'package': ['package', 'pkg', '패키지', 'footprint', 'case', 'package/case', 'size'],
}

# ============== SMD/DIP 분류 키워드 ==============
SMD_KEYWORDS = [
    # 명시적 표면실장
    'SMD', 'SMT', 'SURFACE MOUNT', 'SURFACE-MOUNT',
    # QFP 계열 (숫자 포함 패턴)
    'QFN', 'QFP', 'TQFP', 'LQFP', 'VQFP', 'MQFP', 'PQFP', 'CQFP', 'HQFP',
    # SOIC/SOP 계열
    'SOIC', 'SOP', 'SSOP', 'TSSOP', 'TSOP', 'MSOP', 'QSOP', 'VSOP', 'HSOP',
    # SOT 계열
    'SOT-23', 'SOT-89', 'SOT-223', 'SOT-323', 'SOT-363', 'SOT-523', 'SOT-563', 'SOT-723', 'SOT-883', 'SOT-953', 'SOT',
    # SOD 계열 (SMD 다이오드)
    'SOD-123', 'SOD-323', 'SOD-523', 'SOD-723', 'SOD-923', 'SOD-128', 'SOD-80', 'SOD',
    # BGA/CSP 계열
    'BGA', 'FBGA', 'PBGA', 'CBGA', 'TBGA', 'UBGA', 'WLCSP', 'CSP', 'FCBGA',
    # DFN/SON 계열
    'DFN', 'SON', 'WSON', 'VSON', 'UDFN', 'UQFN', 'TDFN', 'XDFN',
    # 칩 저항/캡 (인치)
    '0201', '0402', '0603', '0805', '1206', '1210', '1812', '2010', '2512',
    # 칩 저항/캡 (메트릭)
    '0603M', '1005M', '1608M', '2012M', '3216M', '3225M', '4532M', '5025M', '6332M',
    # 기타
    'CHIP', 'MLCC', 'WAFER', 'LGA', 'PLCC', 'CLCC', 'LCC',
    # DO 계열 SMD
    'DO-214', 'DO-218', 'DO-219', 'SMA', 'SMB', 'SMC', 'SMAJ', 'SMBJ', 'SMCJ',
    # SC 계열 (SMD 트랜지스터)
    'SC-70', 'SC-88', 'SC-89', 'SC-90',
    # 기타 SMD IC 패키지
    'LFCSP', 'UFBGA', 'WLGA', 'VFBGA', 'FCSP',
]

# HC/SMD 크리스탈 및 오실레이터 패키지
SMD_CRYSTAL_PACKAGES = ['HC49S', 'SMD', '3215', '2520', '2016', '1612', '5032', '7050', '3225']
THT_CRYSTAL_PACKAGES = ['HC49', 'HC49U', 'HC18', 'HC6']

DIP_KEYWORDS = [
    # 명시적 스루홀
    'THROUGH HOLE', 'THROUGH-HOLE', 'THT', 'TH', 'PTH',
    # DIP 계열
    'DIP', 'PDIP', 'CDIP', 'SDIP', 'SPDIP', 'HDIP',
    # TO 패키지 (스루홀)
    'TO-92', 'TO-126', 'TO-220', 'TO-247', 'TO-251', 'TO-252', 'TO-262', 'TO-263', 'TO-3', 'TO-66', 'TO-99',
    # 축형/방사형
    'AXIAL', 'RADIAL', 'LEADED',
    # 커넥터/헤더
    'PIN HEADER', 'HEADER', 'CONNECTOR',
    # 기타
    'PANEL MOUNT', 'CHASSIS MOUNT', 'SIP', 'ZIP',
    # DO 계열 THT
    'DO-35', 'DO-41', 'DO-15', 'DO-27', 'DO-201',
]

# TO 패키지 예외 처리 (SMD 버전)
TO_PACKAGE_SMD_VARIANTS = [
    'TO-252', 'TO-263', 'D-PAK', 'D2PAK', 'DPAK',
    'TO-261', 'SOT-89', 'TO-236', 'SOT-23',
]

# ============== 표준 출력 컬럼 ==============
STANDARD_OUTPUT_COLUMNS = [
    'NO',
    '규격',
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
