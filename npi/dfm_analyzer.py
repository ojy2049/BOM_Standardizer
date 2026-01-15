#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DFM/DFA 분석 모듈
- Gerber/CAD 파일 파싱
- IPC 기준 DFM 체크
- 부품 배치 검증
- 열 분석 기본 검증
"""

import os
import re
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import zipfile
import tempfile


class Severity(Enum):
    """위반 심각도"""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class ViolationType(Enum):
    """위반 유형"""
    COMPONENT_OVERLAP = "component_overlap"
    SPACING_VIOLATION = "spacing_violation"
    EDGE_CLEARANCE = "edge_clearance"
    POLARITY_UNCLEAR = "polarity_unclear"
    THERMAL_ISSUE = "thermal_issue"
    FIDUCIAL_MISSING = "fiducial_missing"
    FIDUCIAL_PLACEMENT = "fiducial_placement"
    PAD_VIOLATION = "pad_violation"
    VIA_VIOLATION = "via_violation"
    SILKSCREEN_OVERLAP = "silkscreen_overlap"
    TESTPOINT_MISSING = "testpoint_missing"
    FINE_PITCH_WARNING = "fine_pitch_warning"
    HEIGHT_WARNING = "height_warning"
    ORIENTATION_INCONSISTENT = "orientation_inconsistent"


@dataclass
class Point:
    """2D 좌표"""
    x: float
    y: float
    
    def distance_to(self, other: 'Point') -> float:
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)


@dataclass
class BoundingBox:
    """경계 박스"""
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    
    @property
    def width(self) -> float:
        return self.max_x - self.min_x
    
    @property
    def height(self) -> float:
        return self.max_y - self.min_y
    
    @property
    def center(self) -> Point:
        return Point((self.min_x + self.max_x) / 2, (self.min_y + self.max_y) / 2)
    
    @property
    def area(self) -> float:
        return self.width * self.height
    
    def overlaps(self, other: 'BoundingBox', margin: float = 0) -> bool:
        """다른 박스와 겹치는지 확인"""
        return not (
            self.max_x + margin < other.min_x or
            self.min_x - margin > other.max_x or
            self.max_y + margin < other.min_y or
            self.min_y - margin > other.max_y
        )
    
    def distance_to(self, other: 'BoundingBox') -> float:
        """다른 박스까지의 최소 거리"""
        dx = max(other.min_x - self.max_x, self.min_x - other.max_x, 0)
        dy = max(other.min_y - self.max_y, self.min_y - other.max_y, 0)
        return math.sqrt(dx**2 + dy**2)
    
    def expand(self, margin: float) -> 'BoundingBox':
        """마진만큼 확장"""
        return BoundingBox(
            self.min_x - margin,
            self.min_y - margin,
            self.max_x + margin,
            self.max_y + margin
        )


@dataclass
class Component:
    """부품 정보"""
    ref_des: str  # Reference Designator
    package: str  # 패키지 유형
    x: float  # X 좌표 (mm)
    y: float  # Y 좌표 (mm)
    rotation: float = 0  # 회전 각도 (degrees)
    layer: str = "top"  # top/bottom
    value: str = ""  # 부품 값
    mounting_type: str = ""  # SMD/TH
    height_mm: float = 0  # 부품 높이
    is_polarized: bool = False  # 극성 부품 여부
    pitch_mm: float = 0  # 핀 피치
    pin_count: int = 0  # 핀 수
    thermal_power_w: float = 0  # 발열량 (W)
    bbox: Optional[BoundingBox] = None
    
    def get_type_category(self) -> str:
        """부품 유형 카테고리"""
        ref = self.ref_des.upper()
        if ref.startswith('R'):
            return 'resistor'
        elif ref.startswith('C'):
            return 'capacitor'
        elif ref.startswith('L'):
            return 'inductor'
        elif ref.startswith(('U', 'IC')):
            return 'ic'
        elif ref.startswith('D'):
            return 'diode'
        elif ref.startswith('Q'):
            return 'transistor'
        elif ref.startswith(('J', 'P', 'CN')):
            return 'connector'
        elif ref.startswith('LED'):
            return 'led'
        elif ref.startswith('Y'):
            return 'crystal'
        elif ref.startswith('F'):
            return 'fuse'
        elif ref.startswith('SW'):
            return 'switch'
        else:
            return 'other'
    
    def get_size_category(self) -> str:
        """부품 크기 카테고리"""
        pkg = self.package.upper()
        if any(s in pkg for s in ['0201', '0402', '0603']):
            return 'small'
        elif any(s in pkg for s in ['0805', '1206', 'SOT']):
            return 'medium'
        elif any(s in pkg for s in ['SOIC', 'TSSOP', 'QFN']):
            return 'large'
        elif any(s in pkg for s in ['TQFP', 'LQFP', 'BGA', 'QFP']):
            return 'xlarge'
        else:
            return 'unknown'


@dataclass
class Pad:
    """패드 정보"""
    x: float
    y: float
    width: float
    height: float
    layer: str
    shape: str = "rect"  # rect, circle, oblong
    net_name: str = ""
    component_ref: str = ""
    is_thermal_pad: bool = False


@dataclass
class Via:
    """비아 정보"""
    x: float
    y: float
    drill_diameter: float
    outer_diameter: float
    net_name: str = ""
    is_filled: bool = False


@dataclass
class Fiducial:
    """피듀셜 마크"""
    x: float
    y: float
    diameter: float
    clearance: float
    layer: str
    fiducial_type: str = "global"  # global/local


@dataclass
class BoardOutline:
    """PCB 외곽선"""
    points: List[Point]
    bbox: Optional[BoundingBox] = None
    
    def __post_init__(self):
        if self.points and not self.bbox:
            xs = [p.x for p in self.points]
            ys = [p.y for p in self.points]
            self.bbox = BoundingBox(min(xs), min(ys), max(xs), max(ys))


@dataclass
class DFMRule:
    """DFM 규칙"""
    rule_id: str
    name: str
    description: str
    category: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    recommended_value: Optional[float] = None
    unit: str = "mm"
    severity: Severity = Severity.MAJOR
    
    def check_value(self, value: float) -> Tuple[bool, str]:
        """값 검사"""
        if self.min_value is not None and value < self.min_value:
            return False, f"값 {value}{self.unit} < 최소값 {self.min_value}{self.unit}"
        if self.max_value is not None and value > self.max_value:
            return False, f"값 {value}{self.unit} > 최대값 {self.max_value}{self.unit}"
        return True, ""


@dataclass
class DFMViolation:
    """DFM 위반 사항"""
    violation_type: ViolationType
    severity: Severity
    message: str
    location: Optional[Point] = None
    affected_components: List[str] = field(default_factory=list)
    rule_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.violation_type.value,
            'severity': self.severity.value,
            'message': self.message,
            'location': {'x': self.location.x, 'y': self.location.y} if self.location else None,
            'affected_components': self.affected_components,
            'rule_id': self.rule_id,
            'details': self.details,
        }


@dataclass
class DFMAnalysisResult:
    """DFM 분석 결과"""
    total_components: int = 0
    smd_count: int = 0
    th_count: int = 0
    violations: List[DFMViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    board_size: Optional[BoundingBox] = None
    fiducial_count: int = 0
    fine_pitch_components: List[str] = field(default_factory=list)
    high_power_components: List[str] = field(default_factory=list)
    
    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.CRITICAL)
    
    @property
    def major_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.MAJOR)
    
    @property
    def minor_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.MINOR)
    
    @property
    def pass_status(self) -> bool:
        return self.critical_count == 0
    
    def get_summary(self) -> Dict[str, Any]:
        return {
            'total_components': self.total_components,
            'smd_count': self.smd_count,
            'th_count': self.th_count,
            'board_size': {
                'width': self.board_size.width if self.board_size else 0,
                'height': self.board_size.height if self.board_size else 0,
            },
            'violations': {
                'critical': self.critical_count,
                'major': self.major_count,
                'minor': self.minor_count,
                'total': len(self.violations),
            },
            'pass_status': self.pass_status,
            'fiducial_count': self.fiducial_count,
            'fine_pitch_components': len(self.fine_pitch_components),
            'high_power_components': len(self.high_power_components),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        result = self.get_summary()
        result['violation_details'] = [v.to_dict() for v in self.violations]
        result['warnings'] = self.warnings
        return result


class GerberParser:
    """Gerber 파일 파서"""
    
    def __init__(self):
        self.units = "mm"
        self.format_spec = (2, 4)  # 정수부, 소수부
        self.apertures: Dict[str, Dict] = {}
        self.current_aperture = None
        self.polarity = "dark"
        
    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """Gerber 파일 파싱"""
        result = {
            'type': 'unknown',
            'pads': [],
            'traces': [],
            'regions': [],
            'outline': [],
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            return result
        
        # 파일 유형 감지
        result['type'] = self._detect_layer_type(file_path, content)
        
        # 포맷 스펙 파싱
        fs_match = re.search(r'%FSLAX(\d)(\d)Y\d+\*%', content)
        if fs_match:
            self.format_spec = (int(fs_match.group(1)), int(fs_match.group(2)))
        
        # 단위 파싱
        if '%MOIN*%' in content:
            self.units = "inch"
        elif '%MOMM*%' in content:
            self.units = "mm"
        
        # Aperture 정의 파싱
        aperture_pattern = r'%ADD(\d+)([A-Z]+),?([\d.X]*)\*%'
        for match in re.finditer(aperture_pattern, content):
            ap_id = match.group(1)
            ap_type = match.group(2)
            ap_params = match.group(3)
            self.apertures[ap_id] = self._parse_aperture(ap_type, ap_params)
        
        # 플래시 (패드) 파싱
        flash_pattern = r'X(-?\d+)Y(-?\d+)D03\*'
        for match in re.finditer(flash_pattern, content):
            x = self._parse_coord(match.group(1))
            y = self._parse_coord(match.group(2))
            result['pads'].append({'x': x, 'y': y, 'aperture': self.current_aperture})
        
        # 외곽선 파싱 (Profile)
        if result['type'] == 'outline':
            result['outline'] = self._parse_outline(content)
        
        return result
    
    def _detect_layer_type(self, file_path: str, content: str) -> str:
        """레이어 유형 감지"""
        name = Path(file_path).name.lower()
        
        # 파일명 기반 감지
        if any(x in name for x in ['gtl', 'top', 'copper_l1']):
            return 'top_copper'
        elif any(x in name for x in ['gbl', 'bottom', 'bot', 'copper_l2']):
            return 'bottom_copper'
        elif any(x in name for x in ['gto', 'top_silk', 'silktop']):
            return 'top_silk'
        elif any(x in name for x in ['gbo', 'bot_silk', 'silkbot']):
            return 'bottom_silk'
        elif any(x in name for x in ['gts', 'topmask', 'soldertop']):
            return 'top_mask'
        elif any(x in name for x in ['gbs', 'botmask', 'solderbot']):
            return 'bottom_mask'
        elif any(x in name for x in ['gtp', 'toppaste', 'pastetop']):
            return 'top_paste'
        elif any(x in name for x in ['gbp', 'botpaste', 'pastebot']):
            return 'bottom_paste'
        elif any(x in name for x in ['gko', 'outline', 'profile', 'edge', 'border']):
            return 'outline'
        elif any(x in name for x in ['drl', 'drill', 'xln']):
            return 'drill'
        
        return 'unknown'
    
    def _parse_coord(self, coord_str: str) -> float:
        """좌표 파싱"""
        try:
            val = int(coord_str)
            divisor = 10 ** self.format_spec[1]
            result = val / divisor
            if self.units == "inch":
                result *= 25.4
            return result
        except:
            return 0.0
    
    def _parse_aperture(self, ap_type: str, params: str) -> Dict:
        """Aperture 정의 파싱"""
        result = {'type': ap_type, 'params': []}
        if params:
            result['params'] = [float(p) for p in params.replace('X', ',').split(',') if p]
        return result
    
    def _parse_outline(self, content: str) -> List[Point]:
        """외곽선 파싱"""
        points = []
        coord_pattern = r'X(-?\d+)Y(-?\d+)D0[12]\*'
        for match in re.finditer(coord_pattern, content):
            x = self._parse_coord(match.group(1))
            y = self._parse_coord(match.group(2))
            points.append(Point(x, y))
        return points


class PickPlaceParser:
    """Pick & Place 파일 파서"""
    
    # 패키지 크기 매핑 (mm)
    PACKAGE_SIZES = {
        '0201': (0.6, 0.3),
        '0402': (1.0, 0.5),
        '0603': (1.6, 0.8),
        '0805': (2.0, 1.25),
        '1206': (3.2, 1.6),
        '1210': (3.2, 2.5),
        '1812': (4.5, 3.2),
        '2010': (5.0, 2.5),
        '2512': (6.3, 3.2),
        'SOT-23': (2.9, 1.3),
        'SOT-89': (4.5, 2.5),
        'SOT-223': (6.5, 3.5),
        'SOIC-8': (5.0, 4.0),
        'SOIC-14': (8.75, 4.0),
        'SOIC-16': (10.0, 4.0),
        'TSSOP-8': (3.0, 4.4),
        'TSSOP-14': (5.0, 4.4),
        'TSSOP-16': (5.0, 4.4),
        'TSSOP-20': (6.5, 4.4),
        'QFN-16': (4.0, 4.0),
        'QFN-20': (4.0, 4.0),
        'QFN-24': (4.0, 4.0),
        'QFN-32': (5.0, 5.0),
        'TQFP-32': (7.0, 7.0),
        'TQFP-44': (10.0, 10.0),
        'TQFP-48': (9.0, 9.0),
        'TQFP-64': (12.0, 12.0),
        'TQFP-100': (14.0, 14.0),
        'LQFP-32': (7.0, 7.0),
        'LQFP-48': (9.0, 9.0),
        'LQFP-64': (12.0, 12.0),
        'LQFP-100': (14.0, 14.0),
        'BGA-256': (17.0, 17.0),
    }
    
    POLARIZED_PREFIXES = {'D', 'LED', 'Q', 'U', 'IC', 'CN', 'J', 'P'}
    
    def parse_file(self, file_path: str) -> List[Component]:
        """Pick & Place 파일 파싱"""
        components = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            return components
        
        # 헤더 분석
        header_idx = -1
        header_map = {}
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(col in line_lower for col in ['refdes', 'designator', 'ref', 'component']):
                header_idx = i
                parts = self._split_line(line)
                for j, part in enumerate(parts):
                    part_lower = part.lower().strip()
                    if any(x in part_lower for x in ['refdes', 'designator', 'ref']):
                        header_map['ref'] = j
                    elif any(x in part_lower for x in ['footprint', 'package', 'pattern']):
                        header_map['package'] = j
                    elif part_lower == 'x' or 'posx' in part_lower or 'mid x' in part_lower:
                        header_map['x'] = j
                    elif part_lower == 'y' or 'posy' in part_lower or 'mid y' in part_lower:
                        header_map['y'] = j
                    elif any(x in part_lower for x in ['rotation', 'rot', 'angle']):
                        header_map['rotation'] = j
                    elif any(x in part_lower for x in ['layer', 'side', 'tb']):
                        header_map['layer'] = j
                    elif any(x in part_lower for x in ['value', 'val']):
                        header_map['value'] = j
                break
        
        if header_idx < 0 or 'ref' not in header_map:
            return components
        
        # 데이터 파싱
        for line in lines[header_idx + 1:]:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = self._split_line(line)
            if len(parts) <= max(header_map.values()):
                continue
            
            try:
                ref_des = parts[header_map['ref']].strip().strip('"')
                if not ref_des:
                    continue
                
                package = parts[header_map.get('package', 0)].strip().strip('"') if 'package' in header_map else ''
                x = self._parse_float(parts[header_map.get('x', 0)]) if 'x' in header_map else 0
                y = self._parse_float(parts[header_map.get('y', 0)]) if 'y' in header_map else 0
                rotation = self._parse_float(parts[header_map.get('rotation', 0)]) if 'rotation' in header_map else 0
                layer = parts[header_map.get('layer', 0)].strip().lower() if 'layer' in header_map else 'top'
                value = parts[header_map.get('value', 0)].strip().strip('"') if 'value' in header_map else ''
                
                # 레이어 정규화
                if any(x in layer for x in ['bottom', 'bot', 'b']):
                    layer = 'bottom'
                else:
                    layer = 'top'
                
                # 패키지 크기로 bbox 계산
                size = self._get_package_size(package)
                bbox = BoundingBox(
                    x - size[0]/2, y - size[1]/2,
                    x + size[0]/2, y + size[1]/2
                )
                
                # 극성 여부 판단
                is_polarized = any(ref_des.upper().startswith(p) for p in self.POLARIZED_PREFIXES)
                
                # 피치 추정
                pitch = self._estimate_pitch(package)
                
                comp = Component(
                    ref_des=ref_des,
                    package=package,
                    x=x,
                    y=y,
                    rotation=rotation,
                    layer=layer,
                    value=value,
                    mounting_type='SMD',  # P&P 파일은 대부분 SMD
                    is_polarized=is_polarized,
                    pitch_mm=pitch,
                    bbox=bbox,
                )
                components.append(comp)
                
            except Exception as e:
                continue
        
        return components
    
    def _split_line(self, line: str) -> List[str]:
        """라인 분할 (CSV 또는 공백)"""
        if ',' in line:
            return line.split(',')
        elif '\t' in line:
            return line.split('\t')
        else:
            return line.split()
    
    def _parse_float(self, s: str) -> float:
        """문자열을 float로 파싱"""
        try:
            s = s.strip().strip('"').replace(',', '.')
            # mil to mm 변환 체크
            if 'mil' in s.lower():
                s = s.lower().replace('mil', '')
                return float(s) * 0.0254
            return float(s)
        except:
            return 0.0
    
    def _get_package_size(self, package: str) -> Tuple[float, float]:
        """패키지 크기 반환"""
        pkg_upper = package.upper().replace('-', '').replace('_', '')
        
        for name, size in self.PACKAGE_SIZES.items():
            if name.replace('-', '').replace('_', '') in pkg_upper:
                return size
        
        # 기본 크기
        return (2.0, 1.0)
    
    def _estimate_pitch(self, package: str) -> float:
        """핀 피치 추정"""
        pkg_upper = package.upper()
        
        if 'BGA' in pkg_upper:
            return 0.5
        elif any(x in pkg_upper for x in ['QFN', 'DFN']):
            return 0.5
        elif 'TQFP' in pkg_upper or 'LQFP' in pkg_upper:
            return 0.5 if '100' in pkg_upper else 0.65
        elif 'TSSOP' in pkg_upper or 'SSOP' in pkg_upper:
            return 0.65
        elif 'SOIC' in pkg_upper:
            return 1.27
        elif 'SOT' in pkg_upper:
            return 0.95
        else:
            return 1.0


class DFMAnalyzer:
    """DFM 분석기"""
    
    def __init__(self, rules_path: Optional[str] = None):
        """
        Args:
            rules_path: IPC 규칙 JSON 파일 경로
        """
        if rules_path is None:
            app_dir = Path(__file__).parent.parent
            rules_path = str(app_dir / "data" / "dfm_rules" / "ipc_rules.json")
        
        self.rules = self._load_rules(rules_path)
        self.components: List[Component] = []
        self.pads: List[Pad] = []
        self.vias: List[Via] = []
        self.fiducials: List[Fiducial] = []
        self.board_outline: Optional[BoardOutline] = None
        self.gerber_parser = GerberParser()
        self.pnp_parser = PickPlaceParser()
    
    def _load_rules(self, rules_path: str) -> Dict:
        """규칙 로드"""
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"규칙 파일 로드 실패: {e}")
            return self._get_default_rules()
    
    def _get_default_rules(self) -> Dict:
        """기본 규칙"""
        return {
            'component_spacing': {
                'rules': {
                    'chip_to_chip': {'default': {'min': 0.5}},
                    'component_to_board_edge': {'min': 0.5, 'for_vcut': 3.0},
                }
            },
            'fiducial_rules': {
                'rules': {
                    'global_fiducials': {'count': {'min': 2}},
                    'fiducial_design': {'diameter_mm': {'min': 1.0, 'max': 3.0}},
                }
            },
            'assembly_rules': {
                'rules': {
                    'fine_pitch': {'threshold_mm': 0.5},
                    'component_height': {'max_mm': 25},
                }
            },
        }
    
    def load_project(self, 
                     gerber_dir: Optional[str] = None,
                     pnp_file: Optional[str] = None,
                     gerber_zip: Optional[str] = None) -> bool:
        """
        프로젝트 로드
        
        Args:
            gerber_dir: Gerber 파일 디렉토리
            pnp_file: Pick & Place 파일 경로
            gerber_zip: Gerber ZIP 파일 경로
        """
        # ZIP 파일 처리
        if gerber_zip and os.path.exists(gerber_zip):
            temp_dir = tempfile.mkdtemp()
            try:
                with zipfile.ZipFile(gerber_zip, 'r') as z:
                    z.extractall(temp_dir)
                gerber_dir = temp_dir
            except Exception as e:
                print(f"ZIP 파일 추출 실패: {e}")
                return False
        
        # Gerber 파일 로드
        if gerber_dir and os.path.exists(gerber_dir):
            self._load_gerber_files(gerber_dir)
        
        # Pick & Place 파일 로드
        if pnp_file and os.path.exists(pnp_file):
            self.components = self.pnp_parser.parse_file(pnp_file)
        
        return len(self.components) > 0 or self.board_outline is not None
    
    def _load_gerber_files(self, gerber_dir: str):
        """Gerber 파일들 로드"""
        for file_name in os.listdir(gerber_dir):
            file_path = os.path.join(gerber_dir, file_name)
            if not os.path.isfile(file_path):
                continue
            
            result = self.gerber_parser.parse_file(file_path)
            
            if result['type'] == 'outline' and result['outline']:
                self.board_outline = BoardOutline(points=result['outline'])
    
    def analyze(self) -> DFMAnalysisResult:
        """DFM 분석 실행"""
        result = DFMAnalysisResult()
        
        # 기본 통계
        result.total_components = len(self.components)
        result.smd_count = sum(1 for c in self.components if c.mounting_type == 'SMD')
        result.th_count = sum(1 for c in self.components if c.mounting_type != 'SMD')
        result.board_size = self.board_outline.bbox if self.board_outline else None
        result.fiducial_count = len(self.fiducials)
        
        # 분석 실행
        self._check_component_overlap(result)
        self._check_component_spacing(result)
        self._check_edge_clearance(result)
        self._check_polarity(result)
        self._check_fiducials(result)
        self._check_fine_pitch(result)
        self._check_orientation_consistency(result)
        self._check_thermal_issues(result)
        
        return result
    
    def _check_component_overlap(self, result: DFMAnalysisResult):
        """부품 겹침 검사"""
        for i, comp1 in enumerate(self.components):
            if not comp1.bbox:
                continue
            
            for j, comp2 in enumerate(self.components[i+1:], i+1):
                if not comp2.bbox:
                    continue
                
                # 같은 레이어만 검사
                if comp1.layer != comp2.layer:
                    continue
                
                if comp1.bbox.overlaps(comp2.bbox):
                    result.violations.append(DFMViolation(
                        violation_type=ViolationType.COMPONENT_OVERLAP,
                        severity=Severity.CRITICAL,
                        message=f"부품 겹침: {comp1.ref_des}와 {comp2.ref_des}",
                        location=comp1.bbox.center,
                        affected_components=[comp1.ref_des, comp2.ref_des],
                        rule_id="OVERLAP_001",
                    ))
    
    def _check_component_spacing(self, result: DFMAnalysisResult):
        """부품 간격 검사"""
        spacing_rules = self.rules.get('component_spacing', {}).get('rules', {})
        default_min = spacing_rules.get('chip_to_chip', {}).get('default', {}).get('min', 0.5)
        
        for i, comp1 in enumerate(self.components):
            if not comp1.bbox:
                continue
            
            for j, comp2 in enumerate(self.components[i+1:], i+1):
                if not comp2.bbox:
                    continue
                
                # 같은 레이어만 검사
                if comp1.layer != comp2.layer:
                    continue
                
                distance = comp1.bbox.distance_to(comp2.bbox)
                
                # 크기별 최소 간격 결정
                size1 = comp1.get_size_category()
                size2 = comp2.get_size_category()
                
                min_spacing = default_min
                if size1 in ['xlarge', 'large'] or size2 in ['xlarge', 'large']:
                    min_spacing = spacing_rules.get('ic_to_ic', {}).get('min', 0.75)
                
                if distance < min_spacing:
                    result.violations.append(DFMViolation(
                        violation_type=ViolationType.SPACING_VIOLATION,
                        severity=Severity.MAJOR,
                        message=f"간격 부족: {comp1.ref_des}~{comp2.ref_des} ({distance:.2f}mm < {min_spacing}mm)",
                        location=Point((comp1.x + comp2.x)/2, (comp1.y + comp2.y)/2),
                        affected_components=[comp1.ref_des, comp2.ref_des],
                        rule_id="SPACING_001",
                        details={'actual': distance, 'required': min_spacing},
                    ))
    
    def _check_edge_clearance(self, result: DFMAnalysisResult):
        """보드 가장자리 간격 검사"""
        if not self.board_outline or not self.board_outline.bbox:
            return
        
        edge_rules = self.rules.get('component_spacing', {}).get('rules', {}).get('component_to_board_edge', {})
        min_clearance = edge_rules.get('min', 0.5)
        vcut_clearance = edge_rules.get('for_vcut', 3.0)
        
        board = self.board_outline.bbox
        
        for comp in self.components:
            if not comp.bbox:
                continue
            
            # 각 가장자리까지의 거리
            clearances = [
                comp.bbox.min_x - board.min_x,  # 왼쪽
                board.max_x - comp.bbox.max_x,  # 오른쪽
                comp.bbox.min_y - board.min_y,  # 아래
                board.max_y - comp.bbox.max_y,  # 위
            ]
            
            min_dist = min(clearances)
            
            if min_dist < min_clearance:
                result.violations.append(DFMViolation(
                    violation_type=ViolationType.EDGE_CLEARANCE,
                    severity=Severity.MAJOR,
                    message=f"가장자리 간격 부족: {comp.ref_des} ({min_dist:.2f}mm < {min_clearance}mm)",
                    location=Point(comp.x, comp.y),
                    affected_components=[comp.ref_des],
                    rule_id="EDGE_001",
                    details={'actual': min_dist, 'required': min_clearance},
                ))
            elif min_dist < vcut_clearance:
                result.warnings.append(
                    f"V-cut 시 주의: {comp.ref_des}가 가장자리에서 {min_dist:.2f}mm (권장 {vcut_clearance}mm)"
                )
    
    def _check_polarity(self, result: DFMAnalysisResult):
        """극성 부품 검사"""
        polarized_components = [c for c in self.components if c.is_polarized]
        
        # 실크스크린/마킹 확인은 Gerber 분석 필요
        # 여기서는 극성 부품 목록만 경고
        if polarized_components:
            result.warnings.append(
                f"극성 부품 {len(polarized_components)}개: 실크스크린 마킹 확인 필요"
            )
    
    def _check_fiducials(self, result: DFMAnalysisResult):
        """피듀셜 검사"""
        fid_rules = self.rules.get('fiducial_rules', {}).get('rules', {})
        required_count = fid_rules.get('global_fiducials', {}).get('count', {}).get('min', 2)
        
        if len(self.fiducials) < required_count:
            result.violations.append(DFMViolation(
                violation_type=ViolationType.FIDUCIAL_MISSING,
                severity=Severity.MAJOR,
                message=f"글로벌 피듀셜 부족: {len(self.fiducials)}개 (최소 {required_count}개 필요)",
                rule_id="FID_001",
                details={'actual': len(self.fiducials), 'required': required_count},
            ))
        
        # Fine pitch 부품에 로컬 피듀셜 필요 여부
        fine_pitch_threshold = self.rules.get('assembly_rules', {}).get('rules', {}).get('fine_pitch', {}).get('threshold_mm', 0.5)
        
        for comp in self.components:
            if comp.pitch_mm > 0 and comp.pitch_mm <= fine_pitch_threshold:
                result.fine_pitch_components.append(comp.ref_des)
        
        if result.fine_pitch_components:
            result.warnings.append(
                f"Fine pitch 부품 {len(result.fine_pitch_components)}개: 로컬 피듀셜 권장"
            )
    
    def _check_fine_pitch(self, result: DFMAnalysisResult):
        """Fine pitch 부품 검사"""
        threshold = self.rules.get('assembly_rules', {}).get('rules', {}).get('fine_pitch', {}).get('threshold_mm', 0.5)
        
        for comp in self.components:
            if comp.pitch_mm > 0 and comp.pitch_mm <= threshold:
                result.violations.append(DFMViolation(
                    violation_type=ViolationType.FINE_PITCH_WARNING,
                    severity=Severity.MINOR,
                    message=f"Fine pitch 부품: {comp.ref_des} (피치 {comp.pitch_mm}mm)",
                    location=Point(comp.x, comp.y),
                    affected_components=[comp.ref_des],
                    rule_id="PITCH_001",
                    details={'pitch': comp.pitch_mm, 'threshold': threshold},
                ))
    
    def _check_orientation_consistency(self, result: DFMAnalysisResult):
        """부품 방향 일관성 검사"""
        # 같은 유형의 부품끼리 그룹화
        type_groups: Dict[str, List[Component]] = {}
        
        for comp in self.components:
            category = comp.get_type_category()
            if category not in type_groups:
                type_groups[category] = []
            type_groups[category].append(comp)
        
        # 극성 부품 유형별 방향 검사
        for category in ['diode', 'led', 'capacitor']:
            if category not in type_groups:
                continue
            
            comps = type_groups[category]
            if len(comps) < 2:
                continue
            
            # 회전 각도 분석 (0, 90, 180, 270 정규화)
            rotations = {}
            for comp in comps:
                rot = int(comp.rotation) % 360
                rot = (rot // 90) * 90  # 90도 단위로 정규화
                rotations[rot] = rotations.get(rot, 0) + 1
            
            # 가장 많은 방향 외의 부품 찾기
            if len(rotations) > 1:
                dominant_rot = max(rotations, key=rotations.get)
                inconsistent = [c.ref_des for c in comps if (int(c.rotation) % 360 // 90 * 90) != dominant_rot]
                
                if inconsistent:
                    result.violations.append(DFMViolation(
                        violation_type=ViolationType.ORIENTATION_INCONSISTENT,
                        severity=Severity.MINOR,
                        message=f"{category} 부품 방향 불일치: {', '.join(inconsistent[:5])}{'...' if len(inconsistent) > 5 else ''}",
                        affected_components=inconsistent,
                        rule_id="ORIENT_001",
                        details={'category': category, 'inconsistent_count': len(inconsistent)},
                    ))
    
    def _check_thermal_issues(self, result: DFMAnalysisResult):
        """열 문제 검사"""
        # 고발열 부품 식별 (IC, 전력 부품 등)
        high_power_keywords = ['REG', 'LDO', 'DC-DC', 'PWR', 'POWER', 'FET', 'MOSFET', 'IGBT']
        
        for comp in self.components:
            is_high_power = (
                comp.ref_des.upper().startswith(('U', 'VR', 'Q')) or
                any(kw in comp.package.upper() for kw in high_power_keywords) or
                any(kw in comp.value.upper() for kw in high_power_keywords)
            )
            
            if is_high_power:
                result.high_power_components.append(comp.ref_des)
        
        # 고발열 부품 간 간격 검사
        thermal_rules = self.rules.get('thermal_rules', {}).get('rules', {})
        min_spacing = thermal_rules.get('component_spacing_thermal', {}).get('between_high_power', {}).get('min', 5.0)
        
        hp_comps = [c for c in self.components if c.ref_des in result.high_power_components]
        
        for i, comp1 in enumerate(hp_comps):
            if not comp1.bbox:
                continue
            
            for comp2 in hp_comps[i+1:]:
                if not comp2.bbox:
                    continue
                
                distance = comp1.bbox.distance_to(comp2.bbox)
                
                if distance < min_spacing:
                    result.violations.append(DFMViolation(
                        violation_type=ViolationType.THERMAL_ISSUE,
                        severity=Severity.MAJOR,
                        message=f"고발열 부품 간격 부족: {comp1.ref_des}~{comp2.ref_des} ({distance:.2f}mm < {min_spacing}mm)",
                        location=Point((comp1.x + comp2.x)/2, (comp1.y + comp2.y)/2),
                        affected_components=[comp1.ref_des, comp2.ref_des],
                        rule_id="THERMAL_001",
                        details={'actual': distance, 'required': min_spacing},
                    ))
    
    def generate_report(self, result: DFMAnalysisResult, output_path: Optional[str] = None) -> str:
        """분석 보고서 생성"""
        lines = []
        lines.append("=" * 60)
        lines.append("DFM/DFA 분석 보고서")
        lines.append("=" * 60)
        lines.append("")
        
        # 요약
        lines.append("## 요약")
        lines.append(f"- 총 부품 수: {result.total_components}")
        lines.append(f"- SMD: {result.smd_count}, TH: {result.th_count}")
        if result.board_size:
            lines.append(f"- 보드 크기: {result.board_size.width:.2f} x {result.board_size.height:.2f} mm")
        lines.append(f"- 피듀셜: {result.fiducial_count}개")
        lines.append(f"- Fine Pitch 부품: {len(result.fine_pitch_components)}개")
        lines.append(f"- 고발열 부품: {len(result.high_power_components)}개")
        lines.append("")
        
        # 판정
        lines.append("## 판정")
        status = "PASS" if result.pass_status else "FAIL"
        lines.append(f"- 상태: {status}")
        lines.append(f"- Critical: {result.critical_count}")
        lines.append(f"- Major: {result.major_count}")
        lines.append(f"- Minor: {result.minor_count}")
        lines.append("")
        
        # 위반 상세
        if result.violations:
            lines.append("## 위반 사항")
            for i, v in enumerate(result.violations, 1):
                severity_kr = {'critical': '심각', 'major': '주요', 'minor': '경미', 'info': '정보'}
                lines.append(f"{i}. [{severity_kr.get(v.severity.value, v.severity.value)}] {v.message}")
                if v.affected_components:
                    lines.append(f"   관련 부품: {', '.join(v.affected_components[:10])}")
            lines.append("")
        
        # 경고
        if result.warnings:
            lines.append("## 경고")
            for w in result.warnings:
                lines.append(f"- {w}")
            lines.append("")
        
        report = "\n".join(lines)
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
        
        return report
