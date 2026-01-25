#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Centroid (XY 좌표) 파일 파서 모듈
- Pick & Place에 필요한 부품 좌표 정보 파싱
- CSV, TXT, Excel 형식 지원
- BOM 데이터와 매칭
"""

import os
import re
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class CentroidData:
    """Centroid 데이터 항목"""
    refdes: str              # Reference Designator (예: R1, C1, U1)
    x: float                 # X 좌표 (mm)
    y: float                 # Y 좌표 (mm)
    rotation: float          # 회전 각도 (도)
    layer: str               # 레이어 (Top/Bottom)
    footprint: str = ""      # 풋프린트/패키지명
    value: str = ""          # 부품 값 (10K, 100nF 등)
    mpn: str = ""            # 제조사 부품번호
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'RefDes': self.refdes,
            'X': self.x,
            'Y': self.y,
            'Rotation': self.rotation,
            'Layer': self.layer,
            'Footprint': self.footprint,
            'Value': self.value,
            'MPN': self.mpn,
        }


class CentroidParser:
    """Centroid 파일 파서"""
    
    # 컬럼명 후보 (대소문자 무시)
    COLUMN_CANDIDATES = {
        'refdes': ['refdes', 'ref', 'reference', 'designator', 'ref des', 'ref_des', 
                   'reference designator', 'part', 'component', '위치', 'ref-des'],
        'x': ['x', 'center-x', 'center_x', 'centerx', 'pos_x', 'posx', 'mid x', 
              'midx', 'x (mm)', 'x(mm)', 'x (mil)', 'location x'],
        'y': ['y', 'center-y', 'center_y', 'centery', 'pos_y', 'posy', 'mid y', 
              'midy', 'y (mm)', 'y(mm)', 'y (mil)', 'location y'],
        'rotation': ['rotation', 'rot', 'angle', 'rotate', 'orientation', 'theta', 'r', 
                     'orient', 'orient.'],
        'layer': ['layer', 'side', 'tb', 'top/bottom', 'surface', 'top_bottom', 
                  'pcb side', 'board side'],
        'footprint': ['footprint', 'package', 'pkg', 'case', 'pattern', '패키지', 
                      'fp', 'part type', 'package type', 'parttype', 'partdecal', 'part decal'],
        'value': ['value', 'val', 'comment', 'description', 'desc', 'spec', '값', '스펙'],
        'mpn': ['mpn', 'part number', 'pn', 'mfr pn', 'manufacturer part number', 
                '부품번호', 'mfg pn'],
        # 이미지 2번 포맷 추가 컬럼
        'pins': ['pins', 'pin count', 'pin_count', '핀수'],
        'smd': ['smd', 'smt', 'surface mount', 'is_smd'],
        'glued': ['glued', 'adhesive', '접착', 'glue'],
    }
    
    # 메트릭 패키지 크기를 인치 크기로 변환 (mm → inch)
    METRIC_TO_INCH_SIZE = {
        '01005': '01005', '0201': '008004',
        '1005': '0402', '1608': '0603', '2012': '0805',
        '3216': '1206', '3225': '1210', '4532': '1812',
        '5025': '2010', '6332': '2512',
    }
    
    # 레이어 값 정규화
    LAYER_MAP = {
        'top': 'Top', 't': 'Top', '1': 'Top', 'front': 'Top', 'primary': 'Top',
        'bottom': 'Bottom', 'bot': 'Bottom', 'b': 'Bottom', '2': 'Bottom', 
        'back': 'Bottom', 'secondary': 'Bottom',
    }
    
    def __init__(self):
        self.raw_df: Optional[pd.DataFrame] = None
        self.centroid_data: List[CentroidData] = []
        self.file_path: str = ""
        self.unit: str = "mm"  # mm 또는 mil
        self.column_mapping: Dict[str, str] = {}
    
    @staticmethod
    def normalize_refdes(refdes: str) -> str:
        """RefDes 정규화 (R011 -> R11, C025 -> C25)"""
        match = re.match(r'^([A-Za-z_]+)0*(\d+)$', refdes)
        if match:
            prefix = match.group(1)
            number = match.group(2)
            return f"{prefix}{number}"
        return refdes
    
    def load_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Centroid 파일 로드
        
        Args:
            file_path: 파일 경로
            
        Returns:
            (성공여부, 메시지)
        """
        self.file_path = file_path
        ext = Path(file_path).suffix.lower()
        
        try:
            if ext == '.csv':
                self.raw_df = self._load_csv(file_path)
            elif ext in ['.txt', '.pos', '.xy']:
                self.raw_df = self._load_text(file_path)
            elif ext in ['.xls', '.xlsx', '.xlsm']:
                self.raw_df = self._load_excel(file_path)
            else:
                return False, f"지원하지 않는 파일 형식: {ext}"
            
            if self.raw_df is None or self.raw_df.empty:
                return False, "파일에서 데이터를 읽을 수 없습니다."
            
            # 컬럼 자동 매핑
            self.column_mapping = self._auto_detect_columns()
            
            # 필수 컬럼 확인
            required = ['refdes', 'x', 'y']
            missing = [k for k in required if k not in self.column_mapping]
            if missing:
                return False, f"필수 컬럼 누락: {', '.join(missing)}"
            
            # 데이터 파싱
            self._parse_data()
            
            return True, f"{len(self.centroid_data)}개 부품 좌표 로드 완료"
            
        except Exception as e:
            return False, f"파일 로드 실패: {str(e)}"
    
    def _load_csv(self, file_path: str) -> pd.DataFrame:
        """CSV 파일 로드 (다양한 구분자 시도)"""
        for sep in [',', '\t', ';', ' ']:
            try:
                df = pd.read_csv(file_path, sep=sep, encoding='utf-8-sig')
                if len(df.columns) > 2:
                    return df
            except:
                pass
            try:
                df = pd.read_csv(file_path, sep=sep, encoding='cp949')
                if len(df.columns) > 2:
                    return df
            except:
                pass
        
        # 기본 로드
        return pd.read_csv(file_path)
    
    def _load_text(self, file_path: str) -> pd.DataFrame:
        """TXT/POS/XY 파일 로드"""
        # 공백 또는 탭 구분자 시도
        for sep in ['\t', r'\s+']:
            try:
                df = pd.read_csv(file_path, sep=sep, encoding='utf-8-sig', engine='python')
                if len(df.columns) > 2:
                    return df
            except:
                pass
            try:
                df = pd.read_csv(file_path, sep=sep, encoding='cp949', engine='python')
                if len(df.columns) > 2:
                    return df
            except:
                pass
        
        return pd.read_csv(file_path, sep=r'\s+', engine='python')
    
    def _load_excel(self, file_path: str) -> pd.DataFrame:
        """Excel 파일 로드"""
        return pd.read_excel(file_path, engine='openpyxl' if file_path.endswith('xlsx') else 'xlrd')
    
    def _auto_detect_columns(self) -> Dict[str, str]:
        """컬럼 자동 감지"""
        mapping = {}
        columns_lower = {col: col.lower().strip() for col in self.raw_df.columns}
        
        for std_key, candidates in self.COLUMN_CANDIDATES.items():
            for orig_col, col_lower in columns_lower.items():
                if col_lower in candidates:
                    mapping[std_key] = orig_col
                    break
            
            # 부분 매칭 시도
            if std_key not in mapping:
                for orig_col, col_lower in columns_lower.items():
                    for candidate in candidates:
                        if candidate in col_lower or col_lower in candidate:
                            mapping[std_key] = orig_col
                            break
                    if std_key in mapping:
                        break
        
        return mapping
    
    def _parse_data(self):
        """데이터 파싱 및 CentroidData 리스트 생성"""
        self.centroid_data = []
        
        # 단위 감지
        self._detect_unit()
        
        refdes_col = self.column_mapping.get('refdes')
        x_col = self.column_mapping.get('x')
        y_col = self.column_mapping.get('y')
        rotation_col = self.column_mapping.get('rotation')
        layer_col = self.column_mapping.get('layer')
        footprint_col = self.column_mapping.get('footprint')
        value_col = self.column_mapping.get('value')
        mpn_col = self.column_mapping.get('mpn')
        
        for _, row in self.raw_df.iterrows():
            try:
                refdes = str(row[refdes_col]).strip() if refdes_col else ""
                if not refdes or refdes.lower() in ['nan', 'none', '']:
                    continue
                
                x = self._parse_coordinate(row.get(x_col, 0))
                y = self._parse_coordinate(row.get(y_col, 0))
                rotation = self._parse_float(row.get(rotation_col, 0)) if rotation_col else 0
                
                # 레이어 정규화
                layer_raw = str(row.get(layer_col, 'Top')).lower().strip() if layer_col else 'top'
                layer = self.LAYER_MAP.get(layer_raw, 'Top')
                
                footprint = str(row.get(footprint_col, '')).strip() if footprint_col else ""
                value = str(row.get(value_col, '')).strip() if value_col else ""
                mpn = str(row.get(mpn_col, '')).strip() if mpn_col else ""
                
                # nan 처리
                for attr in [footprint, value, mpn]:
                    if attr.lower() == 'nan':
                        attr = ""
                
                self.centroid_data.append(CentroidData(
                    refdes=self.normalize_refdes(refdes),  # 정규화 적용
                    x=x,
                    y=y,
                    rotation=rotation % 360,  # 0-359 범위로 정규화
                    layer=layer,
                    footprint=footprint if footprint.lower() != 'nan' else "",
                    value=value if value.lower() != 'nan' else "",
                    mpn=mpn if mpn.lower() != 'nan' else "",
                ))
            except Exception:
                continue
    
    def _detect_unit(self):
        """좌표 단위 감지 (mm vs mil)"""
        x_col = self.column_mapping.get('x', '')
        
        # 컬럼명에서 단위 확인
        if 'mil' in x_col.lower():
            self.unit = 'mil'
            return
        if 'mm' in x_col.lower():
            self.unit = 'mm'
            return
        
        # 값 범위로 추정 (mil은 일반적으로 큰 값)
        try:
            x_values = pd.to_numeric(self.raw_df[x_col], errors='coerce').dropna()
            if len(x_values) > 0:
                max_val = x_values.abs().max()
                if max_val > 1000:  # 1000 이상이면 mil로 추정
                    self.unit = 'mil'
                else:
                    self.unit = 'mm'
        except:
            self.unit = 'mm'
    
    def _parse_coordinate(self, value) -> float:
        """좌표값 파싱 및 mm로 변환"""
        val = self._parse_float(value)
        if self.unit == 'mil':
            return val * 0.0254  # mil to mm
        return val
    
    def _parse_float(self, value) -> float:
        """숫자 파싱"""
        if pd.isna(value):
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            # 문자 제거 후 재시도
            cleaned = re.sub(r'[^\d.\-+]', '', str(value))
            try:
                return float(cleaned) if cleaned else 0.0
            except:
                return 0.0
    
    def get_data(self) -> List[CentroidData]:
        """파싱된 Centroid 데이터 반환"""
        return self.centroid_data
    
    def get_dataframe(self) -> pd.DataFrame:
        """DataFrame 형태로 반환"""
        if not self.centroid_data:
            return pd.DataFrame()
        return pd.DataFrame([d.to_dict() for d in self.centroid_data])
    
    def get_refdes_set(self) -> set:
        """RefDes 집합 반환 (BOM 매칭용)"""
        return {d.refdes for d in self.centroid_data}
    
    def get_top_components(self) -> List[CentroidData]:
        """Top 레이어 부품만 반환"""
        return [d for d in self.centroid_data if d.layer == 'Top']
    
    def get_bottom_components(self) -> List[CentroidData]:
        """Bottom 레이어 부품만 반환"""
        return [d for d in self.centroid_data if d.layer == 'Bottom']
    
    def get_summary(self) -> Dict[str, Any]:
        """요약 정보 반환"""
        return {
            'total': len(self.centroid_data),
            'top_count': len(self.get_top_components()),
            'bottom_count': len(self.get_bottom_components()),
            'unit': self.unit,
            'file': self.file_path,
        }


def match_bom_centroid(bom_df: pd.DataFrame, centroid_parser: CentroidParser, 
                       refdes_column: str = '위치') -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    BOM 데이터와 Centroid 데이터 매칭
    
    Args:
        bom_df: BOM DataFrame
        centroid_parser: 파싱된 CentroidParser
        refdes_column: BOM에서 RefDes 컬럼명
        
    Returns:
        (매칭된 DataFrame, 매칭 통계)
    """
    centroid_data = {d.refdes: d for d in centroid_parser.get_data()}
    centroid_refdes = set(centroid_data.keys())
    
    # RefDes 정규화 함수 (R011 -> R11, C025 -> C25)
    def normalize_refdes(refdes: str) -> str:
        """RefDes에서 앞의 0 제거 (R011 -> R11)"""
        match = re.match(r'^([A-Za-z_]+)0*(\d+)$', refdes)
        if match:
            prefix = match.group(1)
            number = match.group(2)
            return f"{prefix}{number}"
        return refdes
    
    # BOM RefDes 파싱 (R1,R2,R3 또는 R1-R3 형태 처리)
    def parse_refdes_list(refdes_str: str) -> List[str]:
        """RefDes 문자열을 개별 RefDes 리스트로 분해"""
        if pd.isna(refdes_str):
            return []
        
        result = []
        parts = re.split(r'[,\s]+', str(refdes_str))
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 범위 형태 처리 (R1-R3 → R1, R2, R3)
            range_match = re.match(r'^([A-Z]+)0*(\d+)-([A-Z]+)?0*(\d+)$', part, re.IGNORECASE)
            if range_match:
                prefix = range_match.group(1)
                start = int(range_match.group(2))
                end = int(range_match.group(4))
                for i in range(start, end + 1):
                    result.append(f"{prefix}{i}")
            else:
                # 정규화 적용
                result.append(normalize_refdes(part))
        
        return result
    
    # 매칭 통계
    stats = {
        'bom_total': len(bom_df),
        'centroid_total': len(centroid_data),
        'matched': 0,
        'bom_only': [],      # BOM에만 있는 RefDes
        'centroid_only': [], # Centroid에만 있는 RefDes
    }
    
    # BOM의 모든 RefDes 추출
    bom_refdes_all = set()
    for _, row in bom_df.iterrows():
        refdes_list = parse_refdes_list(row.get(refdes_column, ''))
        bom_refdes_all.update(refdes_list)
    
    # 디버그: 샘플 RefDes 출력
    print(f"[DEBUG] BOM RefDes 샘플 (처음 10개): {list(bom_refdes_all)[:10]}")
    print(f"[DEBUG] Centroid RefDes 샘플 (처음 10개): {list(centroid_refdes)[:10]}")
    print(f"[DEBUG] BOM 전체 RefDes 수: {len(bom_refdes_all)}, Centroid 전체 RefDes 수: {len(centroid_refdes)}")
    
    # 매칭 분석
    stats['matched'] = len(bom_refdes_all & centroid_refdes)
    stats['bom_only'] = list(bom_refdes_all - centroid_refdes)
    stats['centroid_only'] = list(centroid_refdes - bom_refdes_all)
    
    # BOM에 좌표 정보 추가
    def add_coordinates(row):
        refdes_list = parse_refdes_list(row.get(refdes_column, ''))
        if not refdes_list:
            return pd.Series({'X': None, 'Y': None, 'Rotation': None, 'Layer': None})
        
        # 첫 번째 RefDes의 좌표 사용
        first_refdes = refdes_list[0]
        if first_refdes in centroid_data:
            cd = centroid_data[first_refdes]
            return pd.Series({'X': cd.x, 'Y': cd.y, 'Rotation': cd.rotation, 'Layer': cd.layer})
        
        return pd.Series({'X': None, 'Y': None, 'Rotation': None, 'Layer': None})
    
    # 좌표 컬럼 추가
    coord_df = bom_df.apply(add_coordinates, axis=1)
    result_df = pd.concat([bom_df, coord_df], axis=1)
    
    return result_df, stats
