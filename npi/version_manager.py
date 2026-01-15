#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOM 버전 관리 모듈
- 프로젝트별 BOM 이력 저장
- 버전 간 비교 (추가/삭제/변경)
- 변경 이력 타임라인
"""

import os
import json
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
import pandas as pd


@dataclass
class BOMItem:
    """BOM 항목 데이터"""
    no: int
    item_type: str  # 품목
    spec: str  # 스펙
    quantity: int  # 수량
    location: str  # 위치/RefDes
    mpn: str = ""  # 제조사 부품번호
    manufacturer: str = ""  # 제조사
    mounting_type: str = ""  # 장착방식 (SMD/DIP)
    package: str = ""  # 패키지
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'BOMItem':
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
    
    def get_key(self) -> str:
        """고유 키 생성 (비교용)"""
        # 위치(RefDes) 또는 MPN + 스펙으로 키 생성
        if self.location:
            return f"{self.location}"
        return f"{self.mpn}_{self.spec}"
    
    def get_hash(self) -> str:
        """항목 해시 생성 (변경 감지용)"""
        content = f"{self.item_type}|{self.spec}|{self.quantity}|{self.location}|{self.mpn}|{self.manufacturer}|{self.mounting_type}"
        return hashlib.md5(content.encode()).hexdigest()[:8]


@dataclass
class BOMVersion:
    """BOM 버전 정보"""
    version_id: str
    project_name: str
    version_name: str  # v1.0, Rev.A 등
    created_at: str
    description: str = ""
    file_path: str = ""
    item_count: int = 0
    smd_count: int = 0
    dip_count: int = 0
    items: List[BOMItem] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['items'] = [item.to_dict() for item in self.items]
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'BOMVersion':
        items = [BOMItem.from_dict(item) for item in d.pop('items', [])]
        return cls(**d, items=items)


@dataclass
class BOMDiffItem:
    """BOM 차이 항목"""
    change_type: str  # 'added', 'removed', 'modified'
    key: str  # RefDes 또는 MPN
    old_item: Optional[BOMItem] = None
    new_item: Optional[BOMItem] = None
    changed_fields: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'change_type': self.change_type,
            'key': self.key,
            'old_item': self.old_item.to_dict() if self.old_item else None,
            'new_item': self.new_item.to_dict() if self.new_item else None,
            'changed_fields': self.changed_fields,
        }


@dataclass
class BOMDiff:
    """BOM 버전 간 차이"""
    old_version: str
    new_version: str
    compared_at: str
    added_count: int = 0
    removed_count: int = 0
    modified_count: int = 0
    diff_items: List[BOMDiffItem] = field(default_factory=list)
    
    @property
    def total_changes(self) -> int:
        return self.added_count + self.removed_count + self.modified_count
    
    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'old_version': self.old_version,
            'new_version': self.new_version,
            'compared_at': self.compared_at,
            'added_count': self.added_count,
            'removed_count': self.removed_count,
            'modified_count': self.modified_count,
            'diff_items': [item.to_dict() for item in self.diff_items],
        }
    
    def get_summary(self) -> str:
        """변경 요약 문자열"""
        parts = []
        if self.added_count:
            parts.append(f"+{self.added_count} 추가")
        if self.removed_count:
            parts.append(f"-{self.removed_count} 삭제")
        if self.modified_count:
            parts.append(f"~{self.modified_count} 변경")
        return ", ".join(parts) if parts else "변경 없음"


class BOMVersionManager:
    """BOM 버전 관리자"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Args:
            db_path: SQLite DB 경로 (None이면 기본 경로 사용)
        """
        if db_path is None:
            app_dir = Path(__file__).parent.parent
            db_path = str(app_dir / "data" / "bom_versions.db")
        
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_db()
    
    def _ensure_db_dir(self):
        """DB 디렉토리 생성"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_db(self):
        """DB 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 프로젝트 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    description TEXT DEFAULT ''
                )
            ''')
            
            # 버전 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS versions (
                    version_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    version_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    file_path TEXT DEFAULT '',
                    item_count INTEGER DEFAULT 0,
                    smd_count INTEGER DEFAULT 0,
                    dip_count INTEGER DEFAULT 0,
                    items_json TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id)
                )
            ''')
            
            # 비교 이력 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comparisons (
                    comparison_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    old_version_id TEXT NOT NULL,
                    new_version_id TEXT NOT NULL,
                    compared_at TEXT NOT NULL,
                    diff_json TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id)
                )
            ''')
            
            conn.commit()
    
    def _generate_id(self, prefix: str = "") -> str:
        """고유 ID 생성"""
        import uuid
        return f"{prefix}{uuid.uuid4().hex[:12]}"
    
    # ==================== 프로젝트 관리 ====================
    
    def create_project(self, project_name: str, description: str = "") -> str:
        """
        새 프로젝트 생성
        
        Returns:
            project_id
        """
        project_id = self._generate_id("proj_")
        now = datetime.now().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO projects (project_id, project_name, created_at, updated_at, description)
                VALUES (?, ?, ?, ?, ?)
            ''', (project_id, project_name, now, now, description))
            conn.commit()
        
        return project_id
    
    def get_projects(self) -> List[Dict[str, Any]]:
        """모든 프로젝트 목록"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.*, COUNT(v.version_id) as version_count
                FROM projects p
                LEFT JOIN versions v ON p.project_id = v.project_id
                GROUP BY p.project_id
                ORDER BY p.updated_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """프로젝트 정보 조회"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM projects WHERE project_id = ?', (project_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def delete_project(self, project_id: str) -> bool:
        """프로젝트 삭제 (관련 버전도 모두 삭제)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM comparisons WHERE project_id = ?', (project_id,))
                cursor.execute('DELETE FROM versions WHERE project_id = ?', (project_id,))
                cursor.execute('DELETE FROM projects WHERE project_id = ?', (project_id,))
                conn.commit()
            return True
        except Exception as e:
            print(f"프로젝트 삭제 실패: {e}")
            return False
    
    # ==================== 버전 관리 ====================
    
    def save_version(self, project_id: str, version_name: str, 
                     items: List[BOMItem], description: str = "",
                     file_path: str = "") -> Optional[str]:
        """
        BOM 버전 저장
        
        Args:
            project_id: 프로젝트 ID
            version_name: 버전명 (v1.0, Rev.A 등)
            items: BOM 항목 리스트
            description: 설명
            file_path: 원본 파일 경로
            
        Returns:
            version_id 또는 None
        """
        try:
            version_id = self._generate_id("ver_")
            now = datetime.now().isoformat()
            
            # 통계 계산
            item_count = len(items)
            smd_count = sum(1 for item in items if 'SMD' in item.mounting_type.upper())
            dip_count = sum(1 for item in items if 'DIP' in item.mounting_type.upper())
            
            # JSON 직렬화
            items_json = json.dumps([item.to_dict() for item in items], ensure_ascii=False)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 버전 저장
                cursor.execute('''
                    INSERT INTO versions 
                    (version_id, project_id, version_name, created_at, description, 
                     file_path, item_count, smd_count, dip_count, items_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (version_id, project_id, version_name, now, description,
                      file_path, item_count, smd_count, dip_count, items_json))
                
                # 프로젝트 업데이트 시간 갱신
                cursor.execute('''
                    UPDATE projects SET updated_at = ? WHERE project_id = ?
                ''', (now, project_id))
                
                conn.commit()
            
            return version_id
            
        except Exception as e:
            print(f"버전 저장 실패: {e}")
            return None
    
    def save_version_from_df(self, project_id: str, version_name: str,
                             df: pd.DataFrame, description: str = "",
                             file_path: str = "") -> Optional[str]:
        """
        DataFrame에서 BOM 버전 저장
        
        Args:
            df: BOM DataFrame (표준 컬럼 포함)
        """
        items = []
        for idx, row in df.iterrows():
            item = BOMItem(
                no=int(row.get('NO', idx + 1)),
                item_type=str(row.get('품목', '')),
                spec=str(row.get('스펙', '')),
                quantity=int(row.get('수량', 0)),
                location=str(row.get('위치', '')),
                mpn=str(row.get('mpn', row.get('공식부품명', ''))),
                manufacturer=str(row.get('manufacturer', row.get('제조사', ''))),
                mounting_type=str(row.get('장착방식', '')),
                package=str(row.get('package', '')),
            )
            items.append(item)
        
        return self.save_version(project_id, version_name, items, description, file_path)
    
    def get_versions(self, project_id: str) -> List[Dict[str, Any]]:
        """프로젝트의 모든 버전 목록"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT version_id, project_id, version_name, created_at, 
                       description, file_path, item_count, smd_count, dip_count
                FROM versions 
                WHERE project_id = ?
                ORDER BY created_at DESC
            ''', (project_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_version(self, version_id: str) -> Optional[BOMVersion]:
        """버전 상세 조회 (항목 포함)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT v.*, p.project_name
                FROM versions v
                JOIN projects p ON v.project_id = p.project_id
                WHERE v.version_id = ?
            ''', (version_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            row_dict = dict(row)
            items_data = json.loads(row_dict.pop('items_json', '[]'))
            items = [BOMItem.from_dict(item) for item in items_data]
            
            return BOMVersion(
                version_id=row_dict['version_id'],
                project_name=row_dict['project_name'],
                version_name=row_dict['version_name'],
                created_at=row_dict['created_at'],
                description=row_dict.get('description', ''),
                file_path=row_dict.get('file_path', ''),
                item_count=row_dict.get('item_count', 0),
                smd_count=row_dict.get('smd_count', 0),
                dip_count=row_dict.get('dip_count', 0),
                items=items,
            )
    
    def delete_version(self, version_id: str) -> bool:
        """버전 삭제"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM comparisons WHERE old_version_id = ? OR new_version_id = ?', 
                             (version_id, version_id))
                cursor.execute('DELETE FROM versions WHERE version_id = ?', (version_id,))
                conn.commit()
            return True
        except Exception as e:
            print(f"버전 삭제 실패: {e}")
            return False
    
    # ==================== 버전 비교 ====================
    
    def compare_versions(self, old_version_id: str, new_version_id: str) -> Optional[BOMDiff]:
        """
        두 버전 비교
        
        Args:
            old_version_id: 이전 버전 ID
            new_version_id: 새 버전 ID
            
        Returns:
            BOMDiff 객체
        """
        old_version = self.get_version(old_version_id)
        new_version = self.get_version(new_version_id)
        
        if not old_version or not new_version:
            return None
        
        # 항목을 키로 인덱싱
        old_items_map: Dict[str, BOMItem] = {item.get_key(): item for item in old_version.items}
        new_items_map: Dict[str, BOMItem] = {item.get_key(): item for item in new_version.items}
        
        old_keys = set(old_items_map.keys())
        new_keys = set(new_items_map.keys())
        
        diff_items: List[BOMDiffItem] = []
        
        # 추가된 항목
        added_keys = new_keys - old_keys
        for key in added_keys:
            diff_items.append(BOMDiffItem(
                change_type='added',
                key=key,
                new_item=new_items_map[key],
            ))
        
        # 삭제된 항목
        removed_keys = old_keys - new_keys
        for key in removed_keys:
            diff_items.append(BOMDiffItem(
                change_type='removed',
                key=key,
                old_item=old_items_map[key],
            ))
        
        # 변경된 항목
        common_keys = old_keys & new_keys
        for key in common_keys:
            old_item = old_items_map[key]
            new_item = new_items_map[key]
            
            if old_item.get_hash() != new_item.get_hash():
                # 변경된 필드 찾기
                changed_fields = []
                for field_name in ['item_type', 'spec', 'quantity', 'mpn', 
                                   'manufacturer', 'mounting_type', 'package']:
                    old_val = getattr(old_item, field_name, '')
                    new_val = getattr(new_item, field_name, '')
                    if str(old_val) != str(new_val):
                        changed_fields.append(field_name)
                
                if changed_fields:
                    diff_items.append(BOMDiffItem(
                        change_type='modified',
                        key=key,
                        old_item=old_item,
                        new_item=new_item,
                        changed_fields=changed_fields,
                    ))
        
        # 정렬 (추가 -> 변경 -> 삭제)
        type_order = {'added': 0, 'modified': 1, 'removed': 2}
        diff_items.sort(key=lambda x: (type_order.get(x.change_type, 9), x.key))
        
        diff = BOMDiff(
            old_version=f"{old_version.project_name} - {old_version.version_name}",
            new_version=f"{new_version.project_name} - {new_version.version_name}",
            compared_at=datetime.now().isoformat(),
            added_count=len(added_keys),
            removed_count=len(removed_keys),
            modified_count=len([d for d in diff_items if d.change_type == 'modified']),
            diff_items=diff_items,
        )
        
        # 비교 이력 저장
        self._save_comparison(old_version.version_id, new_version.version_id, diff)
        
        return diff
    
    def _save_comparison(self, old_version_id: str, new_version_id: str, diff: BOMDiff):
        """비교 이력 저장"""
        try:
            comparison_id = self._generate_id("cmp_")
            
            # project_id 조회
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT project_id FROM versions WHERE version_id = ?', (old_version_id,))
                row = cursor.fetchone()
                if not row:
                    return
                project_id = row[0]
                
                cursor.execute('''
                    INSERT INTO comparisons 
                    (comparison_id, project_id, old_version_id, new_version_id, compared_at, diff_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (comparison_id, project_id, old_version_id, new_version_id,
                      diff.compared_at, json.dumps(diff.to_dict(), ensure_ascii=False)))
                conn.commit()
        except Exception as e:
            print(f"비교 이력 저장 실패: {e}")
    
    def get_comparison_history(self, project_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """프로젝트의 비교 이력"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.*, 
                       v1.version_name as old_version_name,
                       v2.version_name as new_version_name
                FROM comparisons c
                JOIN versions v1 ON c.old_version_id = v1.version_id
                JOIN versions v2 ON c.new_version_id = v2.version_id
                WHERE c.project_id = ?
                ORDER BY c.compared_at DESC
                LIMIT ?
            ''', (project_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== 유틸리티 ====================
    
    def export_version_to_df(self, version_id: str) -> Optional[pd.DataFrame]:
        """버전을 DataFrame으로 내보내기"""
        version = self.get_version(version_id)
        if not version:
            return None
        
        data = []
        for item in version.items:
            data.append({
                'NO': item.no,
                '품목': item.item_type,
                '스펙': item.spec,
                '수량': item.quantity,
                '위치': item.location,
                '장착방식': item.mounting_type,
                '공식부품명': item.mpn,
                '제조사': item.manufacturer,
                '패키지': item.package,
            })
        
        return pd.DataFrame(data)
    
    def export_diff_to_df(self, diff: BOMDiff) -> pd.DataFrame:
        """차이점을 DataFrame으로 내보내기"""
        data = []
        for item in diff.diff_items:
            row = {
                '변경유형': {'added': '추가', 'removed': '삭제', 'modified': '변경'}.get(item.change_type, ''),
                '위치/키': item.key,
            }
            
            if item.change_type == 'added' and item.new_item:
                row['품목'] = item.new_item.item_type
                row['스펙'] = item.new_item.spec
                row['수량'] = item.new_item.quantity
                row['MPN'] = item.new_item.mpn
            elif item.change_type == 'removed' and item.old_item:
                row['품목'] = item.old_item.item_type
                row['스펙'] = item.old_item.spec
                row['수량'] = item.old_item.quantity
                row['MPN'] = item.old_item.mpn
            elif item.change_type == 'modified':
                if item.old_item and item.new_item:
                    row['품목'] = f"{item.old_item.item_type} → {item.new_item.item_type}" if 'item_type' in item.changed_fields else item.new_item.item_type
                    row['스펙'] = f"{item.old_item.spec} → {item.new_item.spec}" if 'spec' in item.changed_fields else item.new_item.spec
                    row['수량'] = f"{item.old_item.quantity} → {item.new_item.quantity}" if 'quantity' in item.changed_fields else item.new_item.quantity
                    row['MPN'] = f"{item.old_item.mpn} → {item.new_item.mpn}" if 'mpn' in item.changed_fields else item.new_item.mpn
                row['변경필드'] = ', '.join(item.changed_fields)
            
            data.append(row)
        
        return pd.DataFrame(data)
