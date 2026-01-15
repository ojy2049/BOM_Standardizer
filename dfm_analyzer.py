#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DFM (Design for Manufacturability) 분석 모듈
- 부품 간격 검사
- 극성 부품 확인
- 패키지 호환성 검증
- 실장 가능성 분석
"""

import math
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    """문제 심각도"""
    INFO = "정보"
    WARNING = "주의"
    ERROR = "오류"
    CRITICAL = "치명"


@dataclass
class DFMIssue:
    """DFM 문제 항목"""
    rule_id: str             # 규칙 ID
    severity: Severity       # 심각도
    category: str            # 카테고리
    message: str             # 메시지
    refdes: str = ""         # 관련 RefDes
    details: Dict = field(default_factory=dict)  # 상세 정보
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'rule_id': self.rule_id,
            'severity': self.severity.value,
            'category': self.category,
            'message': self.message,
            'refdes': self.refdes,
            'details': self.details,
        }


class DFMAnalyzer:
    """DFM 분석기"""
    
    # 패키지별 최소 간격 규칙 (mm)
    MIN_SPACING_RULES = {
        # 칩 부품
        '0201': 0.15,
        '0402': 0.20,
        '0603': 0.25,
        '0805': 0.30,
        '1206': 0.40,
        # IC 패키지
        'SOT-23': 0.30,
        'SOIC': 0.40,
        'QFN': 0.30,
        'QFP': 0.40,
        'BGA': 0.50,
        # 기본값
        'DEFAULT': 0.25,
    }
    
    # 극성 부품 패턴
    POLARITY_PATTERNS = [
        'DIODE', 'LED', 'ELECTROLYTIC', 'TANTALUM', 'POLAR',
        'TRANSISTOR', 'MOSFET', 'FET', 'IC', 'MCU', 'CONNECTOR',
    ]
    
    # 열에 민감한 부품 패턴
    HEAT_SENSITIVE_PATTERNS = [
        'ELECTROLYTIC', 'TANTALUM', 'LED', 'CRYSTAL', 'OSCILLATOR',
        'SENSOR', 'OPTOCOUPLER', 'RELAY',
    ]
    
    # SMD 대형 부품 (리플로우 시 tombstone 주의)
    LARGE_SMD_PACKAGES = [
        '1206', '1210', '1812', '2010', '2512',
        'SOT-223', 'DPAK', 'D2PAK', 'TO-252', 'TO-263',
    ]
    
    def __init__(self):
        self.issues: List[DFMIssue] = []
        self.components_data = []
        self.board_size = (0, 0)  # (width, height) in mm
    
    def analyze(self, df: pd.DataFrame, 
                board_width: float = 100, 
                board_height: float = 100) -> List[DFMIssue]:
        """
        DFM 분석 수행
        
        Args:
            df: BOM + Centroid 통합 DataFrame
            board_width: 기판 너비 (mm)
            board_height: 기판 높이 (mm)
            
        Returns:
            발견된 DFM 문제 리스트
        """
        self.issues = []
        self.board_size = (board_width, board_height)
        
        # 데이터 준비
        self._prepare_data(df)
        
        if not self.components_data:
            self.issues.append(DFMIssue(
                rule_id="DFM-000",
                severity=Severity.WARNING,
                category="데이터",
                message="분석할 부품 데이터가 없습니다.",
            ))
            return self.issues
        
        # 분석 규칙 실행
        self._check_board_edge_clearance()
        self._check_component_spacing()
        self._check_polarity_components()
        self._check_thermal_issues()
        self._check_tombstone_risk()
        self._check_mixed_technology()
        self._check_fiducial_placement()
        self._check_bom_centroid_mismatch(df)
        
        return self.issues
    
    def _prepare_data(self, df: pd.DataFrame):
        """데이터 준비"""
        self.components_data = []
        
        for _, row in df.iterrows():
            x = row.get('X')
            y = row.get('Y')
            
            if pd.isna(x) or pd.isna(y):
                continue
            
            self.components_data.append({
                'refdes': str(row.get('위치', '')).split(',')[0].strip(),
                'x': float(x),
                'y': float(y),
                'rotation': float(row.get('Rotation', 0)) if not pd.isna(row.get('Rotation')) else 0,
                'layer': str(row.get('Layer', 'Top')),
                'footprint': str(row.get('패키지', '') if not pd.isna(row.get('패키지')) else ''),
                'value': str(row.get('스펙', '') if not pd.isna(row.get('스펙')) else ''),
                'mounting': str(row.get('장착방식', '') if not pd.isna(row.get('장착방식')) else ''),
            })
    
    def _check_board_edge_clearance(self):
        """기판 가장자리 간격 검사"""
        min_edge_clearance = 3.0  # mm
        
        for comp in self.components_data:
            x, y = comp['x'], comp['y']
            refdes = comp['refdes']
            
            # 가장자리 거리 계산
            distances = [
                ('왼쪽', x),
                ('오른쪽', self.board_size[0] - x),
                ('아래', y),
                ('위', self.board_size[1] - y),
            ]
            
            for edge_name, distance in distances:
                if 0 < distance < min_edge_clearance:
                    self.issues.append(DFMIssue(
                        rule_id="DFM-101",
                        severity=Severity.WARNING,
                        category="가장자리 간격",
                        message=f"기판 {edge_name} 가장자리와의 간격이 부족합니다 ({distance:.2f}mm < {min_edge_clearance}mm)",
                        refdes=refdes,
                        details={'edge': edge_name, 'distance': distance, 'min_required': min_edge_clearance}
                    ))
    
    def _check_component_spacing(self):
        """부품 간격 검사"""
        min_spacing = 0.25  # 기본 최소 간격 (mm)
        
        for i, comp1 in enumerate(self.components_data):
            for comp2 in self.components_data[i+1:]:
                # 같은 레이어만 검사
                if comp1['layer'] != comp2['layer']:
                    continue
                
                distance = math.sqrt(
                    (comp1['x'] - comp2['x'])**2 + 
                    (comp1['y'] - comp2['y'])**2
                )
                
                # 패키지별 최소 간격 결정
                pkg1 = comp1['footprint'].upper()
                pkg2 = comp2['footprint'].upper()
                
                req_spacing = max(
                    self._get_min_spacing(pkg1),
                    self._get_min_spacing(pkg2)
                )
                
                if distance < req_spacing:
                    self.issues.append(DFMIssue(
                        rule_id="DFM-102",
                        severity=Severity.ERROR if distance < req_spacing * 0.5 else Severity.WARNING,
                        category="부품 간격",
                        message=f"부품 간격 부족: {comp1['refdes']} ↔ {comp2['refdes']} ({distance:.2f}mm < {req_spacing:.2f}mm)",
                        refdes=f"{comp1['refdes']}, {comp2['refdes']}",
                        details={'distance': distance, 'required': req_spacing}
                    ))
    
    def _get_min_spacing(self, footprint: str) -> float:
        """패키지별 최소 간격 조회"""
        for pattern, spacing in self.MIN_SPACING_RULES.items():
            if pattern in footprint:
                return spacing
        return self.MIN_SPACING_RULES['DEFAULT']
    
    def _check_polarity_components(self):
        """극성 부품 확인"""
        polarity_count = 0
        
        for comp in self.components_data:
            footprint = comp['footprint'].upper()
            value = comp['value'].upper()
            
            is_polarity = any(p in footprint or p in value for p in self.POLARITY_PATTERNS)
            
            if is_polarity:
                polarity_count += 1
                # 회전 각도가 비표준인 경우 경고
                rotation = comp['rotation']
                if rotation not in [0, 90, 180, 270]:
                    self.issues.append(DFMIssue(
                        rule_id="DFM-201",
                        severity=Severity.INFO,
                        category="극성 부품",
                        message=f"극성 부품이 비표준 각도로 배치됨 ({rotation}°). 극성 방향 확인 필요",
                        refdes=comp['refdes'],
                        details={'rotation': rotation, 'footprint': footprint}
                    ))
        
        if polarity_count > 0:
            self.issues.append(DFMIssue(
                rule_id="DFM-200",
                severity=Severity.INFO,
                category="극성 부품",
                message=f"극성 부품 {polarity_count}개 발견. 실장 전 극성 방향 확인 필요",
                details={'count': polarity_count}
            ))
    
    def _check_thermal_issues(self):
        """열 관련 문제 검사"""
        heat_sensitive = []
        
        for comp in self.components_data:
            footprint = comp['footprint'].upper()
            value = comp['value'].upper()
            
            if any(p in footprint or p in value for p in self.HEAT_SENSITIVE_PATTERNS):
                heat_sensitive.append(comp['refdes'])
        
        if heat_sensitive:
            self.issues.append(DFMIssue(
                rule_id="DFM-301",
                severity=Severity.INFO,
                category="열 관리",
                message=f"열에 민감한 부품 {len(heat_sensitive)}개 발견. 리플로우 프로파일 주의",
                details={'components': heat_sensitive[:10]}
            ))
    
    def _check_tombstone_risk(self):
        """Tombstone 위험 검사 (소형 칩 부품)"""
        small_chips = ['0201', '0402', '0603']
        at_risk = []
        
        for comp in self.components_data:
            footprint = comp['footprint'].upper()
            
            if any(chip in footprint for chip in small_chips):
                at_risk.append(comp['refdes'])
        
        if at_risk:
            self.issues.append(DFMIssue(
                rule_id="DFM-401",
                severity=Severity.INFO,
                category="실장 품질",
                message=f"소형 칩 부품 {len(at_risk)}개 - Tombstone 현상 주의 (솔더 페이스트 양, 패드 균형 확인)",
                details={'count': len(at_risk), 'components': at_risk[:10]}
            ))
    
    def _check_mixed_technology(self):
        """SMD/THT 혼용 검사"""
        smd_count = 0
        tht_count = 0
        
        for comp in self.components_data:
            mounting = comp['mounting'].upper()
            if 'DIP' in mounting or 'THT' in mounting:
                tht_count += 1
            elif 'SMD' in mounting or 'SMT' in mounting:
                smd_count += 1
        
        if smd_count > 0 and tht_count > 0:
            self.issues.append(DFMIssue(
                rule_id="DFM-501",
                severity=Severity.INFO,
                category="혼합 기술",
                message=f"SMD ({smd_count}개)와 THT ({tht_count}개) 혼용 설계. 양면 리플로우 + 수삽 공정 필요",
                details={'smd_count': smd_count, 'tht_count': tht_count}
            ))
    
    def _check_fiducial_placement(self):
        """피듀셜 마크 확인"""
        # 피듀셜은 일반적으로 FID, FIDUCIAL 등의 RefDes 사용
        fiducials = [c for c in self.components_data if 'FID' in c['refdes'].upper()]
        
        if len(fiducials) < 2:
            self.issues.append(DFMIssue(
                rule_id="DFM-601",
                severity=Severity.WARNING,
                category="피듀셜",
                message=f"피듀셜 마크가 부족합니다 (발견: {len(fiducials)}개, 권장: 2~3개). SMT 장비 정렬 정확도에 영향",
                details={'found': len(fiducials)}
            ))
    
    def _check_bom_centroid_mismatch(self, df: pd.DataFrame):
        """BOM과 Centroid 불일치 검사"""
        missing_coords = []
        
        for _, row in df.iterrows():
            refdes = str(row.get('위치', '')).split(',')[0].strip()
            x = row.get('X')
            y = row.get('Y')
            mounting = str(row.get('장착방식', '')).upper()
            
            # SMD 부품인데 좌표가 없는 경우
            if 'SMD' in mounting and (pd.isna(x) or pd.isna(y)):
                missing_coords.append(refdes)
        
        if missing_coords:
            self.issues.append(DFMIssue(
                rule_id="DFM-701",
                severity=Severity.ERROR,
                category="데이터 불일치",
                message=f"SMD 부품 {len(missing_coords)}개의 좌표 정보 누락. Centroid 파일 확인 필요",
                refdes=', '.join(missing_coords[:5]) + ('...' if len(missing_coords) > 5 else ''),
                details={'count': len(missing_coords), 'components': missing_coords[:20]}
            ))
    
    def get_summary(self) -> Dict[str, Any]:
        """분석 요약"""
        severity_counts = {s.value: 0 for s in Severity}
        category_counts = {}
        
        for issue in self.issues:
            severity_counts[issue.severity.value] += 1
            category_counts[issue.category] = category_counts.get(issue.category, 0) + 1
        
        return {
            'total_issues': len(self.issues),
            'by_severity': severity_counts,
            'by_category': category_counts,
            'components_analyzed': len(self.components_data),
            'board_size': self.board_size,
        }
    
    def get_issues_dataframe(self) -> pd.DataFrame:
        """이슈를 DataFrame으로 반환"""
        if not self.issues:
            return pd.DataFrame()
        return pd.DataFrame([i.to_dict() for i in self.issues])
    
    def generate_report(self) -> str:
        """텍스트 보고서 생성"""
        summary = self.get_summary()
        
        lines = [
            "=" * 60,
            "DFM 분석 보고서",
            "=" * 60,
            "",
            f"분석 부품 수: {summary['components_analyzed']}개",
            f"기판 크기: {summary['board_size'][0]} x {summary['board_size'][1]} mm",
            "",
            "--- 문제 요약 ---",
            f"총 발견 문제: {summary['total_issues']}개",
        ]
        
        for severity, count in summary['by_severity'].items():
            if count > 0:
                lines.append(f"  - {severity}: {count}개")
        
        if self.issues:
            lines.append("")
            lines.append("--- 상세 내용 ---")
            
            for issue in sorted(self.issues, key=lambda x: list(Severity).index(x.severity)):
                lines.append(f"\n[{issue.severity.value}] {issue.rule_id}: {issue.category}")
                lines.append(f"  {issue.message}")
                if issue.refdes:
                    lines.append(f"  관련 부품: {issue.refdes}")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)


def analyze_dfm(df: pd.DataFrame, 
                board_width: float = 100, 
                board_height: float = 100) -> Tuple[List[DFMIssue], Dict[str, Any], str]:
    """
    DFM 분석 편의 함수
    
    Args:
        df: BOM + Centroid DataFrame
        board_width: 기판 너비 (mm)
        board_height: 기판 높이 (mm)
        
    Returns:
        (이슈 리스트, 요약 딕셔너리, 텍스트 보고서)
    """
    analyzer = DFMAnalyzer()
    issues = analyzer.analyze(df, board_width, board_height)
    summary = analyzer.get_summary()
    report = analyzer.generate_report()
    
    return issues, summary, report
