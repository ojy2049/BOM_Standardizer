#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOM 파일 파서 모듈
- CSV, XLS, XLSX 파일 읽기
- 컬럼 자동 매핑 및 정규화
"""

import os
import re
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from config import COLUMN_MAP_CANDIDATES


class BOMParser:
    """BOM 파일 파서 클래스"""
    
    def __init__(self):
        self.raw_df: Optional[pd.DataFrame] = None
        self.normalized_df: Optional[pd.DataFrame] = None
        self.column_mapping: Dict[str, str] = {}
        self.unmapped_columns: List[str] = []
        self.file_path: str = ""
        
    def load_file(self, file_path: str) -> Tuple[bool, str]:
        """
        BOM 파일 로드
        
        Args:
            file_path: 파일 경로
            
        Returns:
            (성공여부, 메시지)
        """
        self.file_path = file_path
        ext = Path(file_path).suffix.lower()
        
        try:
            if ext == '.csv':
                # 인코딩 자동 감지 시도
                for encoding in ['utf-8', 'cp949', 'euc-kr', 'utf-16', 'latin-1']:
                    try:
                        self.raw_df = pd.read_csv(file_path, encoding=encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    return False, "CSV 파일 인코딩을 인식할 수 없습니다."
                    
            elif ext in ['.xlsx', '.xlsm']:
                self.raw_df = pd.read_excel(file_path, engine='openpyxl')
                
            elif ext == '.xls':
                self.raw_df = pd.read_excel(file_path, engine='xlrd')
                
            else:
                return False, f"지원하지 않는 파일 형식: {ext}"
            
            # 빈 데이터프레임 체크
            if self.raw_df is None or self.raw_df.empty:
                return False, "파일에 데이터가 없습니다."
            
            # 컬럼명 정리 (앞뒤 공백 제거)
            self.raw_df.columns = [str(c).strip() for c in self.raw_df.columns]
            
            return True, f"파일 로드 완료: {len(self.raw_df)}개 행, {len(self.raw_df.columns)}개 컬럼"
            
        except Exception as e:
            return False, f"파일 로드 실패: {str(e)}"
    
    def get_columns(self) -> List[str]:
        """원본 컬럼 목록 반환"""
        if self.raw_df is not None:
            return list(self.raw_df.columns)
        return []
    
    def get_preview(self, rows: int = 10) -> pd.DataFrame:
        """데이터 미리보기"""
        if self.raw_df is not None:
            return self.raw_df.head(rows)
        return pd.DataFrame()
    
    def auto_detect_mapping(self) -> Dict[str, str]:
        """
        컬럼 자동 매핑 감지
        
        Returns:
            {표준키: 원본컬럼명} 딕셔너리
        """
        if self.raw_df is None:
            return {}
        
        mapping = {}
        used_cols = set()
        
        for std_key, candidates in COLUMN_MAP_CANDIDATES.items():
            for col in self.raw_df.columns:
                col_lower = str(col).strip().lower()
                col_cleaned = re.sub(r'[^a-z0-9가-힣]', '', col_lower)
                
                for cand in candidates:
                    cand_lower = cand.lower()
                    cand_cleaned = re.sub(r'[^a-z0-9가-힣]', '', cand_lower)
                    
                    # 정확한 매칭 또는 부분 매칭
                    if col_lower == cand_lower or col_cleaned == cand_cleaned:
                        if col not in used_cols:
                            mapping[std_key] = col
                            used_cols.add(col)
                            break
                    # 포함 매칭 (긴 문자열)
                    elif len(cand_lower) > 2 and (cand_lower in col_lower or cand_cleaned in col_cleaned):
                        if col not in used_cols:
                            mapping[std_key] = col
                            used_cols.add(col)
                            break
                
                if std_key in mapping:
                    break
        
        self.column_mapping = mapping
        self.unmapped_columns = [c for c in self.raw_df.columns if c not in used_cols]
        
        return mapping
    
    def set_mapping(self, mapping: Dict[str, str]):
        """수동 컬럼 매핑 설정"""
        self.column_mapping = mapping
        used = set(mapping.values())
        self.unmapped_columns = [c for c in self.raw_df.columns if c not in used]
    
    def normalize(self) -> Tuple[bool, str]:
        """
        컬럼 매핑을 적용하여 정규화된 데이터프레임 생성
        
        Returns:
            (성공여부, 메시지)
        """
        if self.raw_df is None:
            return False, "먼저 파일을 로드하세요."
        
        if not self.column_mapping:
            self.auto_detect_mapping()
        
        try:
            rows = len(self.raw_df)
            
            # NO 컬럼
            if 'no' in self.column_mapping:
                no_col = self.raw_df[self.column_mapping['no']]
            else:
                no_col = pd.Series(range(1, rows + 1))
            
            # 기타 컬럼
            def get_col(key: str) -> pd.Series:
                if key in self.column_mapping:
                    return self.raw_df[self.column_mapping[key]].fillna('')
                return pd.Series([''] * rows)
            
            self.normalized_df = pd.DataFrame({
                'NO': no_col,
                '규격': get_col('규격'),
                '스펙': get_col('스펙'),
                '수량': pd.to_numeric(get_col('수량'), errors='coerce').fillna(0).astype(int),
                '위치': get_col('위치').astype(str),
                'mpn': get_col('mpn'),
                'manufacturer': get_col('manufacturer'),
                'digi_pn': get_col('digi_pn'),
                'mouser_pn': get_col('mouser_pn'),
                'package': get_col('package'),
            })
            
            # 빈 행 제거 (규격과 스펙, mpn 모두 비어있는 경우)
            mask = (
                (self.normalized_df['규격'].astype(str).str.strip() != '') |
                (self.normalized_df['스펙'].astype(str).str.strip() != '') |
                (self.normalized_df['mpn'].astype(str).str.strip() != '')
            )
            self.normalized_df = self.normalized_df[mask].reset_index(drop=True)
            
            # NO 재정렬
            self.normalized_df['NO'] = range(1, len(self.normalized_df) + 1)
            
            return True, f"정규화 완료: {len(self.normalized_df)}개 항목"
            
        except Exception as e:
            return False, f"정규화 실패: {str(e)}"
    
    def get_normalized_data(self) -> pd.DataFrame:
        """정규화된 데이터프레임 반환"""
        if self.normalized_df is not None:
            return self.normalized_df.copy()
        return pd.DataFrame()
    
    def get_row_count(self) -> int:
        """정규화된 행 수 반환"""
        if self.normalized_df is not None:
            return len(self.normalized_df)
        return 0


def parse_bom_file(file_path: str, custom_mapping: Dict[str, str] = None) -> Tuple[Optional[pd.DataFrame], str]:
    """
    BOM 파일 파싱 편의 함수
    
    Args:
        file_path: 파일 경로
        custom_mapping: 사용자 정의 컬럼 매핑 (선택)
        
    Returns:
        (DataFrame 또는 None, 메시지)
    """
    parser = BOMParser()
    
    success, msg = parser.load_file(file_path)
    if not success:
        return None, msg
    
    if custom_mapping:
        parser.set_mapping(custom_mapping)
    else:
        parser.auto_detect_mapping()
    
    success, msg = parser.normalize()
    if not success:
        return None, msg
    
    return parser.get_normalized_data(), msg
