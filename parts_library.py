#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
부품 라이브러리 모듈
- 확장된 부품 정보 데이터베이스
- AVL (Approved Vendor List) 관리
- 부품 위험도 평가
- 대체품 제안
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum


class RiskLevel(Enum):
    """부품 위험도 등급"""
    LOW = "낮음"
    MEDIUM = "보통"
    HIGH = "높음"
    CRITICAL = "매우높음"
    UNKNOWN = "미확인"


class LifecycleStatus(Enum):
    """부품 생산 상태"""
    ACTIVE = "생산중"
    NRND = "신규설계비권장"  # Not Recommended for New Designs
    LAST_TIME_BUY = "마지막구매"
    OBSOLETE = "단종"
    UNKNOWN = "미확인"


@dataclass
class PartLibraryEntry:
    """부품 라이브러리 항목"""
    mpn: str                              # 제조사 부품번호
    manufacturer: str = ""                # 제조사
    description: str = ""                 # 설명
    category: str = ""                    # 카테고리
    package: str = ""                     # 패키지
    mounting_type: str = ""               # SMD/DIP
    
    # 공급 정보
    lifecycle: str = LifecycleStatus.UNKNOWN.value  # 생산 상태
    lead_time_days: int = 0               # 리드타임 (일)
    min_order_qty: int = 1                # 최소 주문 수량
    
    # 가격 정보 (참고용)
    unit_price_krw: float = 0.0           # 단가 (원)
    price_break_qty: int = 1              # 가격 기준 수량
    
    # 대체품
    alternates: List[str] = field(default_factory=list)
    
    # 메타데이터
    datasheet_url: str = ""
    notes: str = ""
    last_updated: str = ""
    source: str = ""                      # 데이터 출처
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'PartLibraryEntry':
        # alternates가 문자열이면 리스트로 변환
        if 'alternates' in d and isinstance(d['alternates'], str):
            d['alternates'] = json.loads(d['alternates']) if d['alternates'] else []
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AVLEntry:
    """Approved Vendor List 항목"""
    mpn: str                              # 부품번호
    manufacturer: str                     # 제조사
    vendor: str                           # 공급업체 (Digi-Key, Mouser 등)
    vendor_pn: str = ""                   # 공급업체 부품번호
    status: str = "approved"              # approved, preferred, restricted, banned
    approved_date: str = ""               # 승인일
    approved_by: str = ""                 # 승인자
    notes: str = ""                       # 비고
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskAssessment:
    """부품 위험도 평가 결과"""
    mpn: str
    risk_level: RiskLevel
    risk_score: float                     # 0-100
    factors: List[Dict[str, Any]] = field(default_factory=list)
    recommendation: str = ""
    alternates: List[str] = field(default_factory=list)
    assessed_date: str = ""


class PartsLibrary:
    """부품 라이브러리 관리자"""
    
    DB_FILE = "parts_library.db"
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent / self.DB_FILE)
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """데이터베이스 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 부품 라이브러리 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS parts (
                mpn TEXT PRIMARY KEY,
                manufacturer TEXT,
                description TEXT,
                category TEXT,
                package TEXT,
                mounting_type TEXT,
                lifecycle TEXT,
                lead_time_days INTEGER DEFAULT 0,
                min_order_qty INTEGER DEFAULT 1,
                unit_price_krw REAL DEFAULT 0,
                price_break_qty INTEGER DEFAULT 1,
                alternates TEXT,
                datasheet_url TEXT,
                notes TEXT,
                last_updated TEXT,
                source TEXT
            )
        ''')
        
        # AVL 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS avl (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mpn TEXT NOT NULL,
                manufacturer TEXT NOT NULL,
                vendor TEXT NOT NULL,
                vendor_pn TEXT,
                status TEXT DEFAULT 'approved',
                approved_date TEXT,
                approved_by TEXT,
                notes TEXT,
                UNIQUE(mpn, manufacturer, vendor)
            )
        ''')
        
        # 위험도 히스토리 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS risk_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mpn TEXT NOT NULL,
                risk_level TEXT,
                risk_score REAL,
                factors TEXT,
                recommendation TEXT,
                assessed_date TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    # ===== 부품 CRUD =====
    
    def add_part(self, entry: PartLibraryEntry) -> bool:
        """부품 추가/업데이트"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            entry.last_updated = datetime.now().isoformat()
            data = entry.to_dict()
            data['alternates'] = json.dumps(data['alternates'])
            
            cursor.execute('''
                INSERT OR REPLACE INTO parts 
                (mpn, manufacturer, description, category, package, mounting_type,
                 lifecycle, lead_time_days, min_order_qty, unit_price_krw, price_break_qty,
                 alternates, datasheet_url, notes, last_updated, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['mpn'], data['manufacturer'], data['description'],
                data['category'], data['package'], data['mounting_type'],
                data['lifecycle'], data['lead_time_days'], data['min_order_qty'],
                data['unit_price_krw'], data['price_break_qty'],
                data['alternates'], data['datasheet_url'], data['notes'],
                data['last_updated'], data['source']
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"부품 추가 실패: {e}")
            return False
    
    def get_part(self, mpn: str) -> Optional[PartLibraryEntry]:
        """부품 조회"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM parts WHERE mpn = ?', (mpn,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return PartLibraryEntry.from_dict(dict(row))
            return None
        except Exception:
            return None
    
    def search_parts(self, query: str, limit: int = 50) -> List[PartLibraryEntry]:
        """부품 검색"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            search_pattern = f'%{query}%'
            cursor.execute('''
                SELECT * FROM parts 
                WHERE mpn LIKE ? OR manufacturer LIKE ? OR description LIKE ? OR category LIKE ?
                LIMIT ?
            ''', (search_pattern, search_pattern, search_pattern, search_pattern, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [PartLibraryEntry.from_dict(dict(row)) for row in rows]
        except Exception:
            return []
    
    def delete_part(self, mpn: str) -> bool:
        """부품 삭제"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM parts WHERE mpn = ?', (mpn,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False
    
    def get_all_parts(self, limit: int = 1000) -> List[PartLibraryEntry]:
        """모든 부품 조회"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM parts LIMIT ?', (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [PartLibraryEntry.from_dict(dict(row)) for row in rows]
        except Exception:
            return []
    
    # ===== AVL 관리 =====
    
    def add_avl_entry(self, entry: AVLEntry) -> bool:
        """AVL 항목 추가"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if not entry.approved_date:
                entry.approved_date = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT OR REPLACE INTO avl 
                (mpn, manufacturer, vendor, vendor_pn, status, approved_date, approved_by, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                entry.mpn, entry.manufacturer, entry.vendor, entry.vendor_pn,
                entry.status, entry.approved_date, entry.approved_by, entry.notes
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"AVL 추가 실패: {e}")
            return False
    
    def get_avl_for_part(self, mpn: str) -> List[AVLEntry]:
        """특정 부품의 AVL 조회"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM avl WHERE mpn = ?', (mpn,))
            rows = cursor.fetchall()
            conn.close()
            
            return [AVLEntry(**{k: v for k, v in dict(row).items() if k != 'id'}) for row in rows]
        except Exception:
            return []
    
    def check_avl_status(self, mpn: str, manufacturer: str, vendor: str) -> str:
        """AVL 상태 확인"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT status FROM avl 
                WHERE mpn = ? AND manufacturer = ? AND vendor = ?
            ''', (mpn, manufacturer, vendor))
            
            row = cursor.fetchone()
            conn.close()
            
            return row[0] if row else "not_found"
        except Exception:
            return "error"
    
    def get_all_avl(self, status_filter: str = None) -> List[AVLEntry]:
        """모든 AVL 조회"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if status_filter:
                cursor.execute('SELECT * FROM avl WHERE status = ?', (status_filter,))
            else:
                cursor.execute('SELECT * FROM avl')
            
            rows = cursor.fetchall()
            conn.close()
            
            return [AVLEntry(**{k: v for k, v in dict(row).items() if k != 'id'}) for row in rows]
        except Exception:
            return []
    
    # ===== 위험도 평가 =====
    
    def assess_risk(self, mpn: str, 
                   lead_time_days: int = None,
                   lifecycle: str = None,
                   single_source: bool = False,
                   usage_qty: int = 1) -> RiskAssessment:
        """
        부품 위험도 평가
        
        Args:
            mpn: 부품번호
            lead_time_days: 리드타임 (일)
            lifecycle: 생산 상태
            single_source: 단일 공급원 여부
            usage_qty: 사용 수량
            
        Returns:
            RiskAssessment 결과
        """
        factors = []
        risk_score = 0.0
        
        # 부품 정보 조회
        part = self.get_part(mpn)
        if part:
            if lead_time_days is None:
                lead_time_days = part.lead_time_days
            if lifecycle is None:
                lifecycle = part.lifecycle
        
        # 1. 리드타임 위험도 (최대 30점)
        if lead_time_days:
            if lead_time_days > 52 * 7:  # 52주 이상
                lt_score = 30
                lt_desc = "매우 긴 리드타임 (52주+)"
            elif lead_time_days > 26 * 7:  # 26주 이상
                lt_score = 20
                lt_desc = "긴 리드타임 (26-52주)"
            elif lead_time_days > 12 * 7:  # 12주 이상
                lt_score = 10
                lt_desc = "보통 리드타임 (12-26주)"
            else:
                lt_score = 0
                lt_desc = "정상 리드타임"
            
            risk_score += lt_score
            factors.append({'factor': '리드타임', 'score': lt_score, 'detail': lt_desc})
        
        # 2. 생산 상태 위험도 (최대 40점)
        if lifecycle:
            lifecycle_upper = lifecycle.upper()
            if 'OBSOLETE' in lifecycle_upper or '단종' in lifecycle:
                lc_score = 40
                lc_desc = "단종됨"
            elif 'LAST' in lifecycle_upper or '마지막' in lifecycle:
                lc_score = 30
                lc_desc = "마지막 구매 기간"
            elif 'NRND' in lifecycle_upper or '비권장' in lifecycle:
                lc_score = 20
                lc_desc = "신규 설계 비권장"
            elif 'ACTIVE' in lifecycle_upper or '생산' in lifecycle:
                lc_score = 0
                lc_desc = "정상 생산중"
            else:
                lc_score = 10
                lc_desc = "생산 상태 미확인"
            
            risk_score += lc_score
            factors.append({'factor': '생산상태', 'score': lc_score, 'detail': lc_desc})
        
        # 3. 단일 공급원 위험도 (최대 20점)
        if single_source:
            ss_score = 20
            ss_desc = "단일 공급원"
            risk_score += ss_score
            factors.append({'factor': '공급원', 'score': ss_score, 'detail': ss_desc})
        
        # 4. 사용량 위험도 (최대 10점)
        if usage_qty > 100:
            uq_score = 10
            uq_desc = f"대량 사용 ({usage_qty}개)"
        elif usage_qty > 50:
            uq_score = 5
            uq_desc = f"중량 사용 ({usage_qty}개)"
        else:
            uq_score = 0
            uq_desc = f"소량 사용 ({usage_qty}개)"
        
        if uq_score > 0:
            risk_score += uq_score
            factors.append({'factor': '사용량', 'score': uq_score, 'detail': uq_desc})
        
        # 위험 등급 결정
        if risk_score >= 60:
            risk_level = RiskLevel.CRITICAL
            recommendation = "즉시 대체품 검토 필요. 재고 확보 권장."
        elif risk_score >= 40:
            risk_level = RiskLevel.HIGH
            recommendation = "대체품 검토 권장. 공급 상황 모니터링 필요."
        elif risk_score >= 20:
            risk_level = RiskLevel.MEDIUM
            recommendation = "공급 상황 주시. 장기 프로젝트 시 대체품 검토."
        else:
            risk_level = RiskLevel.LOW
            recommendation = "현재 공급 안정적."
        
        # 대체품 조회
        alternates = []
        if part and part.alternates:
            alternates = part.alternates
        
        assessment = RiskAssessment(
            mpn=mpn,
            risk_level=risk_level,
            risk_score=risk_score,
            factors=factors,
            recommendation=recommendation,
            alternates=alternates,
            assessed_date=datetime.now().isoformat()
        )
        
        # 히스토리 저장
        self._save_risk_history(assessment)
        
        return assessment
    
    def _save_risk_history(self, assessment: RiskAssessment):
        """위험도 평가 히스토리 저장"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO risk_history 
                (mpn, risk_level, risk_score, factors, recommendation, assessed_date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                assessment.mpn,
                assessment.risk_level.value,
                assessment.risk_score,
                json.dumps(assessment.factors, ensure_ascii=False),
                assessment.recommendation,
                assessment.assessed_date
            ))
            
            conn.commit()
            conn.close()
        except Exception:
            pass
    
    def batch_assess_risk(self, parts_list: List[Dict[str, Any]]) -> List[RiskAssessment]:
        """
        여러 부품 일괄 위험도 평가
        
        Args:
            parts_list: [{'mpn': str, 'qty': int, ...}, ...]
            
        Returns:
            RiskAssessment 리스트
        """
        results = []
        for part in parts_list:
            mpn = part.get('mpn', '')
            if not mpn:
                continue
            
            assessment = self.assess_risk(
                mpn=mpn,
                usage_qty=part.get('qty', 1)
            )
            results.append(assessment)
        
        return results
    
    # ===== 통계 =====
    
    def get_stats(self) -> Dict[str, Any]:
        """라이브러리 통계"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM parts')
            parts_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM avl')
            avl_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT lifecycle, COUNT(*) FROM parts GROUP BY lifecycle')
            lifecycle_stats = dict(cursor.fetchall())
            
            conn.close()
            
            return {
                'total_parts': parts_count,
                'total_avl': avl_count,
                'by_lifecycle': lifecycle_stats,
            }
        except Exception:
            return {}
    
    # ===== 가져오기/내보내기 =====
    
    def export_to_json(self, output_path: str) -> Tuple[bool, str]:
        """JSON으로 내보내기"""
        try:
            data = {
                'parts': [p.to_dict() for p in self.get_all_parts()],
                'avl': [a.to_dict() for a in self.get_all_avl()],
                'exported_at': datetime.now().isoformat(),
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True, f"내보내기 완료: {len(data['parts'])}개 부품, {len(data['avl'])}개 AVL"
        except Exception as e:
            return False, f"내보내기 실패: {str(e)}"
    
    def import_from_json(self, input_path: str, merge: bool = True) -> Tuple[bool, str]:
        """JSON에서 가져오기"""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            parts_imported = 0
            avl_imported = 0
            
            for p_dict in data.get('parts', []):
                entry = PartLibraryEntry.from_dict(p_dict)
                if self.add_part(entry):
                    parts_imported += 1
            
            for a_dict in data.get('avl', []):
                entry = AVLEntry(**a_dict)
                if self.add_avl_entry(entry):
                    avl_imported += 1
            
            return True, f"가져오기 완료: {parts_imported}개 부품, {avl_imported}개 AVL"
        except Exception as e:
            return False, f"가져오기 실패: {str(e)}"


# 전역 인스턴스
_library_instance: Optional[PartsLibrary] = None


def get_parts_library() -> PartsLibrary:
    """전역 부품 라이브러리 인스턴스"""
    global _library_instance
    if _library_instance is None:
        _library_instance = PartsLibrary()
    return _library_instance
