#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOM 파일 파서 모듈
- CSV, XLS, XLSX 파일 읽기
- 컬럼 자동 매핑 및 정규화
- 셀 병합 해제 및 헤더행 자동 탐지
"""

import os
import re
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from config import COLUMN_MAP_CANDIDATES, COMPONENT_TYPE_KEYWORDS, KNOWN_MANUFACTURERS, REFDES_PREFIXES


class BOMParser:
    """BOM 파일 파서 클래스"""
    
    def __init__(self):
        self.raw_df: Optional[pd.DataFrame] = None
        self.normalized_df: Optional[pd.DataFrame] = None
        self.column_mapping: Dict[str, str] = {}
        self.unmapped_columns: List[str] = []
        self.file_path: str = ""
        self.detected_header_row: int = 0
        self.skipped_rows: Optional[pd.DataFrame] = None
        self.headerless_mode: bool = False  # 헤더 없는 BOM 모드
    
    def _unmerge_excel_cells(self, file_path: str) -> pd.DataFrame:
        """
        엑셀 파일의 병합 셀을 해제하고 값 복사
        
        Args:
            file_path: 엑셀 파일 경로
            
        Returns:
            병합 해제된 DataFrame
        """
        from openpyxl import load_workbook
        
        wb = load_workbook(file_path, data_only=True)
        ws = wb.active
        
        # 병합된 셀 목록 복사 (순회 중 변경 방지)
        merged_ranges = list(ws.merged_cells.ranges)
        
        for merged_range in merged_ranges:
            # 병합 범위의 좌상단 값 가져오기
            top_left_value = ws.cell(merged_range.min_row, merged_range.min_col).value
            ws.unmerge_cells(str(merged_range))
            
            # 병합 해제된 모든 셀에 값 복사
            for row in range(merged_range.min_row, merged_range.max_row + 1):
                for col in range(merged_range.min_col, merged_range.max_col + 1):
                    ws.cell(row, col, value=top_left_value)
        
        # DataFrame으로 변환
        data = list(ws.values)
        if not data:
            return pd.DataFrame()
        
        return pd.DataFrame(data)
    
    def _detect_header_row(self, df: pd.DataFrame, max_rows: int = 15) -> int:
        """
        실제 헤더행 위치 자동 탐지
        2행 헤더 구조(상위 병합 헤더 + 하위 세부 헤더)를 처리
        
        Args:
            df: 원본 DataFrame (헤더 없이 로드된 상태)
            max_rows: 검색할 최대 행 수
            
        Returns:
            헤더행 인덱스 (0-based), 헤더가 없으면 -1
        """
        # 모든 컬럼 매핑 후보를 소문자로 수집
        all_candidates = []
        for candidates in COLUMN_MAP_CANDIDATES.values():
            all_candidates.extend([c.lower() for c in candidates])
        
        # 세부 헤더 키워드 (하위 컬럼명에서 자주 사용됨) - 높은 점수 부여
        specific_keywords = [
            'item', 'spec', 'qty', 'quantity', 'unit', 'price', 'amount', 
            'location', 'refdes', 'value', 'package', 'footprint',
            '품명', '품목', '스펙', '수량', '위치', '단가', '금액', '비고'
        ]
        
        # 일반적인 병합 헤더 키워드 (상위 컬럼에서 사용됨) - 낮은 점수
        general_keywords = [
            'description', 'information', 'detail', 'data', 'part', 'component',
            '설명', '정보', '부품', '상세'
        ]
        
        all_candidates.extend(specific_keywords)
        all_candidates.extend(general_keywords)
        
        best_row = -1  # 기본값: 헤더 없음
        best_score = 0
        
        for row_idx in range(min(max_rows, len(df))):
            row_values = []
            for v in df.iloc[row_idx]:
                if pd.notna(v):
                    row_values.append(str(v).strip().lower())
            
            # 매칭 점수 계산
            score = 0
            specific_matches = 0
            unique_values = set()
            
            for val in row_values:
                # 빈 값이나 숫자만 있는 경우 스킵
                if not val or val.replace('.', '').replace('-', '').isdigit():
                    continue
                
                unique_values.add(val)
                
                # 세부 키워드 매칭 (높은 점수)
                for kw in specific_keywords:
                    if kw == val or kw in val:
                        score += 3  # 세부 키워드는 3점
                        specific_matches += 1
                        break
                else:
                    # 일반 키워드 매칭 (낮은 점수)
                    for cand in all_candidates:
                        if cand in val or val in cand:
                            score += 1
                            break
            
            # 고유값이 많을수록 보너스 (병합 헤더는 중복값이 많음)
            unique_bonus = len(unique_values)
            total_score = score + unique_bonus
            
            if total_score > best_score:
                best_score = total_score
                best_row = row_idx
        
        # 최소 점수 기준: 세부 키워드 2개 이상 매칭 (score >= 6) 또는 
        # 일반적인 매칭 포함 총점 8점 이상일 때만 헤더로 인정
        # 기존보다 엄격하게 변경하여 헤더 없는 경우를 더 잘 감지
        if best_score >= 6:
            return best_row
        else:
            return -1  # 헤더 없음
    
    def _is_likely_header(self, value: Any) -> bool:
        """값이 헤더일 가능성 확인"""
        if pd.isna(value):
            return False
        
        val_str = str(value).strip().lower()
        if not val_str:
            return False
        
        # 숫자만 있으면 헤더 아님
        if val_str.replace('.', '').replace('-', '').isdigit():
            return False
        
        # 컬럼 매핑 후보와 매칭
        for candidates in COLUMN_MAP_CANDIDATES.values():
            for cand in candidates:
                if cand.lower() in val_str or val_str in cand.lower():
                    return True
        
        return False
    
    def _infer_columns_from_data(self) -> Dict[str, str]:
        """
        헤더 없는 BOM에서 데이터 패턴을 분석하여 컬럼 타입 추론
        
        Returns:
            {표준키: 컬럼명} 딕셔너리
        """
        if self.raw_df is None or len(self.raw_df) == 0:
            return {}
        
        inferred_mapping = {}
        used_cols = set()
        sample_size = min(20, len(self.raw_df))  # 상위 20행 분석
        
        column_scores = {col: {} for col in self.raw_df.columns}
        
        for col in self.raw_df.columns:
            scores = {
                '수량': 0,
                '위치': 0,
                '품목': 0,
                'mpn': 0,
                'manufacturer': 0,
                '스펙': 0,
            }
            
            for idx in range(sample_size):
                try:
                    value = self.raw_df.iloc[idx][col]
                    if pd.isna(value) or str(value).strip() == '':
                        continue
                    
                    val_str = str(value).strip()
                    val_upper = val_str.upper()
                    
                    # 1. 수량 컬럼 추론: 양의 정수
                    if self._is_quantity_value(val_str):
                        scores['수량'] += 3
                    
                    # 2. 위치 컬럼 추론: RefDes 패턴
                    if self._is_refdes_value(val_str):
                        scores['위치'] += 4
                    
                    # 3. 규격 컬럼 추론: 부품 종류 키워드
                    if self._is_component_type_value(val_upper):
                        scores['품목'] += 3
                    
                    # 4. MPN 컬럼 추론: 부품번호 패턴
                    if self._is_mpn_value(val_str):
                        scores['mpn'] += 2
                    
                    # 5. 제조사 컬럼 추론: 알려진 제조사명
                    if self._is_manufacturer_value(val_upper):
                        scores['manufacturer'] += 4
                    
                    # 6. 스펙 컬럼 추론: 값 + 단위 패턴 (10K, 100nF 등)
                    if self._is_spec_value(val_str):
                        scores['스펙'] += 2
                        
                except Exception:
                    continue
            
            column_scores[col] = scores
        
        # 점수가 높은 순으로 매핑 (각 컬럼 타입별로 가장 높은 점수의 컬럼 선택)
        for std_key in ['위치', '수량', '품목', 'manufacturer', 'mpn', '스펙']:
            best_col = None
            best_score = 0
            
            for col in self.raw_df.columns:
                if col in used_cols:
                    continue
                score = column_scores[col].get(std_key, 0)
                if score > best_score:
                    best_score = score
                    best_col = col
            
            # 최소 점수 기준 충족 시 매핑
            min_scores = {'위치': 8, '수량': 6, '품목': 6, 'manufacturer': 8, 'mpn': 4, '스펙': 4}
            if best_col and best_score >= min_scores.get(std_key, 4):
                inferred_mapping[std_key] = best_col
                used_cols.add(best_col)
        
        return inferred_mapping
    
    def _is_quantity_value(self, val: str) -> bool:
        """수량 값인지 확인 (양의 정수)"""
        try:
            num = int(val)
            return 1 <= num <= 10000  # 합리적인 수량 범위
        except ValueError:
            return False
    
    def _is_refdes_value(self, val: str) -> bool:
        """RefDes 값인지 확인 (R1, C1-C10, U1,U2 등)"""
        import re
        val_upper = val.upper().strip()
        
        # RefDes 패턴: 접두어 + 숫자, 콤마/하이픈으로 연결 가능
        for prefix in REFDES_PREFIXES:
            # 단일 RefDes: R1, C10, U5 등
            if re.match(rf'^{prefix}\d+$', val_upper):
                return True
            # 범위: R1-R10, C1-C5 등
            if re.match(rf'^{prefix}\d+\s*[-~]\s*{prefix}?\d+$', val_upper):
                return True
            # 목록: R1,R2,R3 또는 R1, R2, R3 등
            if re.match(rf'^{prefix}\d+(\s*,\s*{prefix}?\d+)+$', val_upper):
                return True
        
        return False
    
    def _is_component_type_value(self, val_upper: str) -> bool:
        """부품 종류 값인지 확인"""
        for keyword in COMPONENT_TYPE_KEYWORDS:
            if keyword == val_upper or keyword in val_upper:
                return True
        return False
    
    def _is_mpn_value(self, val: str) -> bool:
        """MPN(부품번호) 값인지 확인"""
        import re
        # 부품번호 패턴: 알파벳+숫자 혼합, 하이픈/언더스코어 포함 가능
        # 예: RC0402FR-0710KL, STM32F103C8T6, LM7805CT
        if len(val) < 4 or len(val) > 40:
            return False
        
        # 알파벳과 숫자가 모두 포함되어야 함
        has_alpha = any(c.isalpha() for c in val)
        has_digit = any(c.isdigit() for c in val)
        
        if not (has_alpha and has_digit):
            return False
        
        # 너무 단순한 패턴 제외 (R1, C10 같은 RefDes)
        if re.match(r'^[A-Z]{1,3}\d{1,3}$', val.upper()):
            return False
        
        return True
    
    def _is_manufacturer_value(self, val_upper: str) -> bool:
        """제조사명인지 확인"""
        for mfr in KNOWN_MANUFACTURERS:
            if mfr == val_upper or mfr in val_upper:
                return True
        return False
    
    def _is_spec_value(self, val: str) -> bool:
        """스펙 값인지 확인 (10K, 100nF, 0.1uF 등)"""
        import re
        # 저항/커패시터/인덕터 스펙 패턴
        spec_patterns = [
            r'^\d+(\.\d+)?[KkMmRr]?$',  # 저항: 10K, 4.7K, 100R
            r'^\d+(\.\d+)?[pnuμm]?[Ff]$',  # 캐패시터: 100nF, 10uF
            r'^\d+(\.\d+)?[nuμm]?[Hh]$',  # 인덕터: 10uH, 100nH
            r'^\d+(\.\d+)?[VvAa]$',  # 전압/전류: 5V, 1A
            r'^\d+(\.\d+)?%$',  # 오차: 1%, 5%
            r'^\d{4}$',  # 패키지 크기: 0402, 0603, 0805
        ]
        
        for pattern in spec_patterns:
            if re.match(pattern, val):
                return True
        
        # 복합 스펙: "10K 0402", "100nF 16V" 등
        if ' ' in val:
            parts = val.split()
            match_count = sum(1 for p in parts for pattern in spec_patterns if re.match(pattern, p))
            if match_count >= 1:
                return True
        
        return False
        
    def load_file(self, file_path: str, header_row: Optional[int] = None) -> Tuple[bool, str]:
        """
        BOM 파일 로드
        
        Args:
            file_path: 파일 경로
            header_row: 헤더행 번호 (0-based, None이면 자동 탐지, -1이면 헤더 없음)
            
        Returns:
            (성공여부, 메시지)
        """
        self.file_path = file_path
        self.headerless_mode = False  # 초기화
        ext = Path(file_path).suffix.lower()
        
        try:
            if ext == '.csv':
                # 인코딩 자동 감지 시도
                temp_df = None
                for encoding in ['utf-8', 'cp949', 'euc-kr', 'utf-16', 'latin-1']:
                    try:
                        temp_df = pd.read_csv(file_path, encoding=encoding, header=None)
                        break
                    except UnicodeDecodeError:
                        continue
                
                if temp_df is None:
                    return False, "CSV 파일 인코딩을 인식할 수 없습니다."
                
                # 헤더행 탐지
                if header_row is None:
                    header_row = self._detect_header_row(temp_df)
                
                self.detected_header_row = header_row
                
                # 헤더 없음 처리
                if header_row == -1:
                    self.headerless_mode = True
                    self.raw_df = temp_df.copy()
                    self.raw_df.columns = [f'Column_{i}' for i in range(len(temp_df.columns))]
                else:
                    # 스킵할 행 저장
                    if header_row > 0:
                        self.skipped_rows = temp_df.iloc[:header_row].copy()
                    
                    # 헤더 적용
                    self.raw_df = temp_df.iloc[header_row:].reset_index(drop=True)
                    self.raw_df.columns = [str(c).strip() for c in self.raw_df.iloc[0]]
                    self.raw_df = self.raw_df.iloc[1:].reset_index(drop=True)
                    
            elif ext in ['.xlsx', '.xlsm']:
                # 병합 셀 해제 후 로드
                temp_df = self._unmerge_excel_cells(file_path)
                
                if temp_df.empty:
                    return False, "파일에 데이터가 없습니다."
                
                # 헤더행 탐지
                if header_row is None:
                    header_row = self._detect_header_row(temp_df)
                
                self.detected_header_row = header_row
                
                # 헤더 없음 처리
                if header_row == -1:
                    self.headerless_mode = True
                    self.raw_df = temp_df.copy()
                    self.raw_df.columns = [f'Column_{i}' for i in range(len(temp_df.columns))]
                else:
                    # 스킵할 행 저장
                    if header_row > 0:
                        self.skipped_rows = temp_df.iloc[:header_row].copy()
                    
                    # 헤더 적용
                    self.raw_df = temp_df.iloc[header_row:].reset_index(drop=True)
                    self.raw_df.columns = [str(c).strip() if pd.notna(c) else f'Column_{i}' 
                                           for i, c in enumerate(self.raw_df.iloc[0])]
                    self.raw_df = self.raw_df.iloc[1:].reset_index(drop=True)
                
            elif ext == '.xls':
                # xlrd는 병합 셀 처리가 다름 - 기본 방식 사용
                temp_df = pd.read_excel(file_path, engine='xlrd', header=None)
                
                # 헤더행 탐지
                if header_row is None:
                    header_row = self._detect_header_row(temp_df)
                
                self.detected_header_row = header_row
                
                # 헤더 없음 처리
                if header_row == -1:
                    self.headerless_mode = True
                    self.raw_df = temp_df.copy()
                    self.raw_df.columns = [f'Column_{i}' for i in range(len(temp_df.columns))]
                else:
                    if header_row > 0:
                        self.skipped_rows = temp_df.iloc[:header_row].copy()
                    
                    self.raw_df = temp_df.iloc[header_row:].reset_index(drop=True)
                    self.raw_df.columns = [str(c).strip() if pd.notna(c) else f'Column_{i}' 
                                           for i, c in enumerate(self.raw_df.iloc[0])]
                    self.raw_df = self.raw_df.iloc[1:].reset_index(drop=True)
                
            else:
                return False, f"지원하지 않는 파일 형식: {ext}"
            
            # 빈 데이터프레임 체크
            if self.raw_df is None or self.raw_df.empty:
                return False, "파일에 데이터가 없습니다."
            
            # 컬럼명 정리 (앞뒤 공백 제거, NaN 처리)
            self.raw_df.columns = [str(c).strip() if pd.notna(c) else f'Column_{i}' 
                                   for i, c in enumerate(self.raw_df.columns)]
            
            # 완전히 빈 행 제거
            self.raw_df = self.raw_df.dropna(how='all').reset_index(drop=True)
            
            # 결과 메시지 생성
            if self.headerless_mode:
                header_msg = "(헤더 없음 - 데이터 패턴으로 컬럼 추론)"
            elif header_row > 0:
                header_msg = f"(헤더: {header_row + 1}행)"
            else:
                header_msg = ""
            
            return True, f"파일 로드 완료: {len(self.raw_df)}개 행, {len(self.raw_df.columns)}개 컬럼 {header_msg}"
            
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
        - 헤더 있음: 컬럼명 기반 매핑
        - 헤더 없음: 데이터 패턴 기반 추론
        
        Returns:
            {표준키: 원본컬럼명} 딕셔너리
        """
        if self.raw_df is None:
            return {}
        
        # 헤더 없는 모드: 데이터 패턴 기반 추론
        if self.headerless_mode:
            mapping = self._infer_columns_from_data()
            self.column_mapping = mapping
            self.unmapped_columns = [c for c in self.raw_df.columns if c not in mapping.values()]
            return mapping
        
        # 헤더 있는 모드: 기존 컬럼명 기반 매핑
        mapping = {}
        used_cols = set()
        
        # 1단계: 컬럼명 기반 매핑
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
        
        # 규격 컬럼이 없는 경우 빈 상태로 둠
        
        self.column_mapping = mapping
        self.unmapped_columns = [c for c in self.raw_df.columns if c not in used_cols]
        
        return mapping
    
    def _count_component_keywords(self, column: str) -> int:
        """
        특정 컬럼에서 부품 종류 키워드 개수 카운트
        
        Args:
            column: 컬럼명
            
        Returns:
            발견된 키워드 개수
        """
        if self.raw_df is None or column not in self.raw_df.columns:
            return 0
        
        count = 0
        
        # 상위 50행만 검사 (성능)
        sample_size = min(50, len(self.raw_df))
        
        for idx in range(sample_size):
            try:
                value = self.raw_df.iloc[idx][column]
                # NaN 체크 (스칼라 값으로 처리)
                if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == '':
                    continue
                
                value_str = str(value).strip()
                value_upper = value_str.upper()
                
                # 부품 코드처럼 보이는 값은 스킵 (숫자-문자 패턴, 예: 2000-PMA0-0107-)
                # 대시가 2개 이상이고 숫자가 4개 이상인 경우 코드로 간주
                dash_count = value_str.count('-')
                digit_count = sum(c.isdigit() for c in value_str)
                if dash_count >= 2 and digit_count >= 4:
                    continue
                
                for keyword in COMPONENT_TYPE_KEYWORDS:
                    # 단어 경계 매칭 (IC가 CIRCUIT에서 매칭되지 않도록)
                    if len(keyword) <= 2:
                        # 짧은 키워드는 정확한 매칭 또는 단어 시작
                        if value_upper == keyword or value_upper.startswith(keyword + ' ') or \
                           value_upper.startswith(keyword + '-') or value_upper.startswith(keyword + '_'):
                            count += 1
                            break
                    else:
                        # 긴 키워드는 포함 매칭
                        if keyword in value_upper:
                            count += 1
                            break
            except Exception:
                continue
        
        return count
    
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
            
            if rows == 0:
                return False, "데이터가 없습니다."
            
            # 기타 컬럼 추출 함수 (문자열로 변환하여 datetime 추론 방지)
            def get_col(key: str) -> list:
                if key in self.column_mapping:
                    col_name = self.column_mapping[key]
                    if col_name in self.raw_df.columns:
                        col_data = self.raw_df[col_name]
                        # 중복 컬럼명인 경우 DataFrame이 반환될 수 있음 - 첫 번째 컬럼 사용
                        if isinstance(col_data, pd.DataFrame):
                            col_data = col_data.iloc[:, 0]
                        return col_data.fillna('').astype(str).tolist()
                return [''] * rows
            
            # 수량 컬럼 추출 (숫자로 변환)
            def get_qty_col() -> list:
                if '수량' in self.column_mapping:
                    col_name = self.column_mapping['수량']
                    if col_name in self.raw_df.columns:
                        col_data = self.raw_df[col_name]
                        if isinstance(col_data, pd.DataFrame):
                            col_data = col_data.iloc[:, 0]
                        return pd.to_numeric(col_data, errors='coerce').fillna(0).astype(int).tolist()
                return [0] * rows
            
            self.normalized_df = pd.DataFrame({
                'NO': list(range(1, rows + 1)),
                '품목': get_col('품목'),
                '스펙': get_col('스펙'),
                '수량': get_qty_col(),
                '위치': get_col('위치'),
                'mpn': get_col('mpn'),
                'manufacturer': get_col('manufacturer'),
                'digi_pn': get_col('digi_pn'),
                'mouser_pn': get_col('mouser_pn'),
                'package': get_col('package'),
            })
            
            # 의미없는 행 제거 (total, 합계, 소계 등)
            skip_keywords = ['TOTAL', '합계', '소계', 'SUBTOTAL', 'SUM', '계', '총계']
            
            # 헤더처럼 보이는 행 제거용 키워드
            header_keywords = [
                'ITEM', 'SPEC', 'QTY', 'QUANTITY', 'LOCATION', 'REFDES', 
                'DESCRIPTION', 'UNIT', 'PRICE', 'AMOUNT', 'REMARKS', 'NO',
                'PART', 'MPN', 'MANUFACTURER', 'PACKAGE', 'VALUE',
                '품명', '품목', '스펙', '수량', '위치', '비고', '단가', '금액'
            ]
            
            def is_valid_row(row) -> bool:
                # 품목, 스펙, mpn 중 하나라도 유효한 값이 있어야 함
                품목 = str(row['품목']).strip().upper()
                스펙 = str(row['스펙']).strip().upper()
                mpn = str(row['mpn']).strip().upper()
                위치 = str(row['위치']).strip().upper()
                
                # 모두 비어있으면 제거
                if not 품목 and not 스펙 and not mpn:
                    return False
                
                # skip 키워드 포함 시 제거
                all_text = f"{품목} {스펙} {mpn}"
                for kw in skip_keywords:
                    if kw in all_text:
                        return False
                
                # 헤더처럼 보이는 행 제거 (여러 필드가 헤더 키워드와 정확히 일치)
                header_match_count = 0
                for val in [품목, 스펙, mpn, 위치]:
                    if val in header_keywords:
                        header_match_count += 1
                
                # 2개 이상의 필드가 헤더 키워드와 일치하면 헤더 행으로 간주
                if header_match_count >= 2:
                    return False
                
                return True
            
            # 유효한 행만 필터링
            valid_mask = self.normalized_df.apply(is_valid_row, axis=1)
            self.normalized_df = self.normalized_df[valid_mask].reset_index(drop=True)
            
            # NO 재정렬
            self.normalized_df['NO'] = range(1, len(self.normalized_df) + 1)
            
            if len(self.normalized_df) == 0:
                return False, "유효한 부품 데이터가 없습니다."
            
            return True, f"정규화 완료: {len(self.normalized_df)}개 항목"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
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
