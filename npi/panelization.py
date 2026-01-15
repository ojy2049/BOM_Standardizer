#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PCB 패널라이제이션 모듈
- V-cut / Tab routing 지원
- 패널 배열 최적화
- 레일 및 피듀셜 자동 배치
"""

import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class SeparationType(Enum):
    """분리 방식"""
    V_CUT = "v_cut"
    TAB_ROUTING = "tab_routing"
    MOUSE_BITES = "mouse_bites"
    FULL_ROUTING = "full_routing"


class PanelOrientation(Enum):
    """패널 방향"""
    PORTRAIT = "portrait"  # 세로
    LANDSCAPE = "landscape"  # 가로
    AUTO = "auto"


@dataclass
class BoardSize:
    """PCB 크기"""
    width: float  # mm
    height: float  # mm
    thickness: float = 1.6  # mm
    
    @property
    def area(self) -> float:
        return self.width * self.height
    
    def rotated(self) -> 'BoardSize':
        """90도 회전된 크기"""
        return BoardSize(self.height, self.width, self.thickness)


@dataclass
class PanelSize:
    """패널 크기"""
    width: float  # mm
    height: float  # mm
    
    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class RailConfig:
    """레일 설정"""
    top: float = 10.0  # mm
    bottom: float = 10.0
    left: float = 10.0
    right: float = 10.0
    
    @property
    def total_width(self) -> float:
        return self.left + self.right
    
    @property
    def total_height(self) -> float:
        return self.top + self.bottom


@dataclass
class FiducialConfig:
    """피듀셜 설정"""
    diameter: float = 1.5  # mm
    clearance: float = 3.0  # mm (마스크 클리어런스)
    count: int = 3
    position: str = "corners"  # corners, diagonal, custom


@dataclass
class ToolingHoleConfig:
    """툴링홀 설정"""
    diameter: float = 3.0  # mm
    count: int = 3
    edge_distance: float = 5.0  # mm (레일 가장자리에서 거리)


@dataclass
class VCutConfig:
    """V-Cut 설정"""
    depth_percent: float = 70  # 보드 두께의 %
    angle: float = 30  # 각도 (도)
    min_board_thickness: float = 0.6  # mm
    component_clearance: float = 3.0  # mm (부품까지 거리)


@dataclass
class TabRoutingConfig:
    """Tab routing 설정"""
    tab_width: float = 5.0  # mm
    tab_spacing: float = 50.0  # mm (탭 간격)
    routing_width: float = 2.0  # mm
    mouse_bite_holes: int = 5
    mouse_bite_diameter: float = 0.5  # mm
    mouse_bite_pitch: float = 0.8  # mm


@dataclass
class PanelConfig:
    """패널 설정"""
    panel_size: PanelSize
    rails: RailConfig = field(default_factory=RailConfig)
    fiducials: FiducialConfig = field(default_factory=FiducialConfig)
    tooling_holes: ToolingHoleConfig = field(default_factory=ToolingHoleConfig)
    separation: SeparationType = SeparationType.V_CUT
    v_cut: VCutConfig = field(default_factory=VCutConfig)
    tab_routing: TabRoutingConfig = field(default_factory=TabRoutingConfig)
    board_spacing: float = 0  # mm (V-cut은 0, routing은 2)
    
    @property
    def usable_width(self) -> float:
        return self.panel_size.width - self.rails.total_width
    
    @property
    def usable_height(self) -> float:
        return self.panel_size.height - self.rails.total_height


@dataclass
class BoardPlacement:
    """보드 배치 위치"""
    row: int
    col: int
    x: float  # mm (왼쪽 하단 기준)
    y: float  # mm
    rotation: float = 0  # 도
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'row': self.row,
            'col': self.col,
            'x': round(self.x, 3),
            'y': round(self.y, 3),
            'rotation': self.rotation,
        }


@dataclass
class FiducialPlacement:
    """피듀셜 배치 위치"""
    x: float
    y: float
    fiducial_type: str = "global"  # global, local
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'x': round(self.x, 3),
            'y': round(self.y, 3),
            'type': self.fiducial_type,
        }


@dataclass
class ToolingHolePlacement:
    """툴링홀 배치 위치"""
    x: float
    y: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'x': round(self.x, 3),
            'y': round(self.y, 3),
        }


@dataclass
class VCutLine:
    """V-Cut 라인"""
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    direction: str = "horizontal"  # horizontal, vertical
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'start': {'x': round(self.start_x, 3), 'y': round(self.start_y, 3)},
            'end': {'x': round(self.end_x, 3), 'y': round(self.end_y, 3)},
            'direction': self.direction,
        }


@dataclass
class TabPlacement:
    """Tab 배치 위치"""
    x: float
    y: float
    width: float
    direction: str = "horizontal"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'x': round(self.x, 3),
            'y': round(self.y, 3),
            'width': self.width,
            'direction': self.direction,
        }


@dataclass
class PanelResult:
    """패널 결과"""
    boards_x: int
    boards_y: int
    total_boards: int
    board_placements: List[BoardPlacement]
    fiducials: List[FiducialPlacement]
    tooling_holes: List[ToolingHolePlacement]
    v_cut_lines: List[VCutLine]
    tabs: List[TabPlacement]
    panel_utilization: float
    waste_area: float
    estimated_cost_factor: float  # 상대 비용 인자
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'layout': {
                'boards_x': self.boards_x,
                'boards_y': self.boards_y,
                'total_boards': self.total_boards,
            },
            'board_placements': [p.to_dict() for p in self.board_placements],
            'fiducials': [f.to_dict() for f in self.fiducials],
            'tooling_holes': [t.to_dict() for t in self.tooling_holes],
            'v_cut_lines': [v.to_dict() for v in self.v_cut_lines],
            'tabs': [t.to_dict() for t in self.tabs],
            'efficiency': {
                'utilization': round(self.panel_utilization * 100, 2),
                'waste_area': round(self.waste_area, 2),
                'cost_factor': round(self.estimated_cost_factor, 2),
            },
            'warnings': self.warnings,
        }
    
    def get_summary(self) -> str:
        """요약 문자열"""
        return (
            f"배열: {self.boards_x} x {self.boards_y} = {self.total_boards}개, "
            f"활용률: {self.panel_utilization * 100:.1f}%, "
            f"비용 인자: {self.estimated_cost_factor:.2f}"
        )


class Panelizer:
    """패널라이저"""
    
    # 표준 패널 크기 (mm)
    STANDARD_PANEL_SIZES = [
        PanelSize(250, 200),
        PanelSize(300, 250),
        PanelSize(350, 250),
        PanelSize(400, 300),
        PanelSize(450, 350),
        PanelSize(457, 406),  # 18" x 16"
        PanelSize(500, 400),
        PanelSize(600, 500),
    ]
    
    def __init__(self, board_size: BoardSize, config: Optional[PanelConfig] = None):
        """
        Args:
            board_size: PCB 크기
            config: 패널 설정 (None이면 자동 계산)
        """
        self.board_size = board_size
        self.config = config or self._auto_config()
    
    def _auto_config(self) -> PanelConfig:
        """자동 패널 설정"""
        # 최적 패널 크기 선택
        best_panel = None
        best_count = 0
        
        for panel_size in self.STANDARD_PANEL_SIZES:
            config = PanelConfig(panel_size=panel_size)
            count = self._calculate_board_count(config)
            
            if count > best_count:
                best_count = count
                best_panel = panel_size
        
        if best_panel is None:
            best_panel = PanelSize(300, 250)
        
        # 분리 방식 결정
        if self.board_size.thickness < 0.6:
            separation = SeparationType.TAB_ROUTING
            board_spacing = 2.0
        else:
            separation = SeparationType.V_CUT
            board_spacing = 0
        
        return PanelConfig(
            panel_size=best_panel,
            separation=separation,
            board_spacing=board_spacing,
        )
    
    def _calculate_board_count(self, config: PanelConfig) -> int:
        """배열 가능한 보드 수 계산"""
        usable_w = config.usable_width
        usable_h = config.usable_height
        spacing = config.board_spacing
        
        # 가로 방향
        boards_x = int((usable_w + spacing) / (self.board_size.width + spacing))
        boards_y = int((usable_h + spacing) / (self.board_size.height + spacing))
        count1 = boards_x * boards_y
        
        # 90도 회전
        boards_x_r = int((usable_w + spacing) / (self.board_size.height + spacing))
        boards_y_r = int((usable_h + spacing) / (self.board_size.width + spacing))
        count2 = boards_x_r * boards_y_r
        
        return max(count1, count2)
    
    def calculate_layout(self, 
                        orientation: PanelOrientation = PanelOrientation.AUTO
                        ) -> Tuple[int, int, bool]:
        """
        최적 배열 계산
        
        Returns:
            (boards_x, boards_y, is_rotated)
        """
        config = self.config
        usable_w = config.usable_width
        usable_h = config.usable_height
        spacing = config.board_spacing
        
        def calc_fit(bw: float, bh: float) -> Tuple[int, int, int]:
            bx = max(1, int((usable_w + spacing) / (bw + spacing)))
            by = max(1, int((usable_h + spacing) / (bh + spacing)))
            return bx, by, bx * by
        
        # 원본 방향
        bx1, by1, count1 = calc_fit(self.board_size.width, self.board_size.height)
        
        # 90도 회전
        bx2, by2, count2 = calc_fit(self.board_size.height, self.board_size.width)
        
        if orientation == PanelOrientation.PORTRAIT:
            return bx1, by1, False
        elif orientation == PanelOrientation.LANDSCAPE:
            return bx2, by2, True
        else:  # AUTO
            if count2 > count1:
                return bx2, by2, True
            else:
                return bx1, by1, False
    
    def panelize(self, 
                orientation: PanelOrientation = PanelOrientation.AUTO
                ) -> PanelResult:
        """
        패널라이제이션 실행
        
        Args:
            orientation: 보드 방향
            
        Returns:
            PanelResult
        """
        config = self.config
        boards_x, boards_y, is_rotated = self.calculate_layout(orientation)
        
        # 실제 보드 크기
        if is_rotated:
            board_w = self.board_size.height
            board_h = self.board_size.width
        else:
            board_w = self.board_size.width
            board_h = self.board_size.height
        
        spacing = config.board_spacing
        
        # 보드 배치 계산
        placements = []
        start_x = config.rails.left
        start_y = config.rails.bottom
        
        # 중앙 정렬을 위한 오프셋
        total_board_width = boards_x * board_w + (boards_x - 1) * spacing
        total_board_height = boards_y * board_h + (boards_y - 1) * spacing
        offset_x = (config.usable_width - total_board_width) / 2
        offset_y = (config.usable_height - total_board_height) / 2
        
        for row in range(boards_y):
            for col in range(boards_x):
                x = start_x + offset_x + col * (board_w + spacing)
                y = start_y + offset_y + row * (board_h + spacing)
                
                placements.append(BoardPlacement(
                    row=row,
                    col=col,
                    x=x,
                    y=y,
                    rotation=90 if is_rotated else 0,
                ))
        
        # 피듀셜 배치
        fiducials = self._place_fiducials(config)
        
        # 툴링홀 배치
        tooling_holes = self._place_tooling_holes(config)
        
        # V-Cut 라인 또는 탭
        v_cut_lines = []
        tabs = []
        
        if config.separation == SeparationType.V_CUT:
            v_cut_lines = self._generate_v_cut_lines(
                placements, board_w, board_h, config
            )
        else:
            tabs = self._generate_tabs(
                placements, board_w, board_h, config
            )
        
        # 효율성 계산
        total_board_area = boards_x * boards_y * board_w * board_h
        panel_area = config.panel_size.area
        utilization = total_board_area / panel_area
        waste_area = panel_area - total_board_area
        
        # 비용 인자 (보드 수 기반)
        cost_factor = 1.0 / (boards_x * boards_y) if boards_x * boards_y > 0 else float('inf')
        
        # 경고 생성
        warnings = []
        if utilization < 0.5:
            warnings.append(f"패널 활용률 낮음: {utilization*100:.1f}%")
        
        if config.separation == SeparationType.V_CUT:
            if self.board_size.thickness < config.v_cut.min_board_thickness:
                warnings.append(
                    f"보드 두께({self.board_size.thickness}mm)가 V-Cut 최소 두께"
                    f"({config.v_cut.min_board_thickness}mm) 미만"
                )
        
        if boards_x * boards_y < 2:
            warnings.append("패널당 1개 보드만 배치됨 - 패널 크기 확인 필요")
        
        return PanelResult(
            boards_x=boards_x,
            boards_y=boards_y,
            total_boards=boards_x * boards_y,
            board_placements=placements,
            fiducials=fiducials,
            tooling_holes=tooling_holes,
            v_cut_lines=v_cut_lines,
            tabs=tabs,
            panel_utilization=utilization,
            waste_area=waste_area,
            estimated_cost_factor=cost_factor,
            warnings=warnings,
        )
    
    def _place_fiducials(self, config: PanelConfig) -> List[FiducialPlacement]:
        """피듀셜 배치"""
        fiducials = []
        panel_w = config.panel_size.width
        panel_h = config.panel_size.height
        margin = config.fiducials.clearance + config.fiducials.diameter / 2
        
        if config.fiducials.position == "corners":
            # 세 모서리에 배치 (비대칭 삼각형)
            fiducials.append(FiducialPlacement(margin, margin))
            fiducials.append(FiducialPlacement(panel_w - margin, margin))
            fiducials.append(FiducialPlacement(margin, panel_h - margin))
        
        elif config.fiducials.position == "diagonal":
            # 대각선 배치
            fiducials.append(FiducialPlacement(margin, margin))
            fiducials.append(FiducialPlacement(panel_w - margin, panel_h - margin))
            if config.fiducials.count >= 3:
                fiducials.append(FiducialPlacement(panel_w - margin, margin))
        
        return fiducials
    
    def _place_tooling_holes(self, config: PanelConfig) -> List[ToolingHolePlacement]:
        """툴링홀 배치"""
        holes = []
        panel_w = config.panel_size.width
        panel_h = config.panel_size.height
        edge = config.tooling_holes.edge_distance
        
        if config.tooling_holes.count >= 2:
            # 좌하단, 우하단
            holes.append(ToolingHolePlacement(edge, edge))
            holes.append(ToolingHolePlacement(panel_w - edge, edge))
        
        if config.tooling_holes.count >= 3:
            # 상단 중앙
            holes.append(ToolingHolePlacement(panel_w / 2, panel_h - edge))
        
        return holes
    
    def _generate_v_cut_lines(self, placements: List[BoardPlacement],
                              board_w: float, board_h: float,
                              config: PanelConfig) -> List[VCutLine]:
        """V-Cut 라인 생성"""
        v_cuts = []
        panel_w = config.panel_size.width
        panel_h = config.panel_size.height
        
        # 수평 V-Cut (보드 사이)
        y_positions: set = set()
        for p in placements:
            y_positions.add(p.y)
            y_positions.add(p.y + board_h)
        
        # 레일 영역 제외
        min_y = config.rails.bottom
        max_y = panel_h - config.rails.top
        
        for y in sorted(y_positions):
            if min_y < y < max_y:
                v_cuts.append(VCutLine(
                    start_x=0,
                    start_y=y,
                    end_x=panel_w,
                    end_y=y,
                    direction="horizontal"
                ))
        
        # 수직 V-Cut
        x_positions: set = set()
        for p in placements:
            x_positions.add(p.x)
            x_positions.add(p.x + board_w)
        
        min_x = config.rails.left
        max_x = panel_w - config.rails.right
        
        for x in sorted(x_positions):
            if min_x < x < max_x:
                v_cuts.append(VCutLine(
                    start_x=x,
                    start_y=0,
                    end_x=x,
                    end_y=panel_h,
                    direction="vertical"
                ))
        
        return v_cuts
    
    def _generate_tabs(self, placements: List[BoardPlacement],
                      board_w: float, board_h: float,
                      config: PanelConfig) -> List[TabPlacement]:
        """Tab 배치 생성"""
        tabs = []
        tab_cfg = config.tab_routing
        
        for p in placements:
            # 상단 탭
            tabs.append(TabPlacement(
                x=p.x + board_w / 2,
                y=p.y + board_h,
                width=tab_cfg.tab_width,
                direction="horizontal"
            ))
            
            # 하단 탭
            tabs.append(TabPlacement(
                x=p.x + board_w / 2,
                y=p.y,
                width=tab_cfg.tab_width,
                direction="horizontal"
            ))
            
            # 좌측 탭
            tabs.append(TabPlacement(
                x=p.x,
                y=p.y + board_h / 2,
                width=tab_cfg.tab_width,
                direction="vertical"
            ))
            
            # 우측 탭
            tabs.append(TabPlacement(
                x=p.x + board_w,
                y=p.y + board_h / 2,
                width=tab_cfg.tab_width,
                direction="vertical"
            ))
        
        return tabs
    
    def optimize_panel_size(self, 
                           min_boards: int = 4,
                           max_panel: Optional[PanelSize] = None
                           ) -> List[Dict[str, Any]]:
        """
        최적 패널 크기 추천
        
        Args:
            min_boards: 최소 보드 수
            max_panel: 최대 패널 크기 제한
            
        Returns:
            추천 패널 목록 (효율순)
        """
        results = []
        
        for panel_size in self.STANDARD_PANEL_SIZES:
            if max_panel:
                if panel_size.width > max_panel.width or panel_size.height > max_panel.height:
                    continue
            
            config = PanelConfig(
                panel_size=panel_size,
                separation=self.config.separation,
                board_spacing=self.config.board_spacing,
            )
            
            temp_panelizer = Panelizer(self.board_size, config)
            result = temp_panelizer.panelize()
            
            if result.total_boards >= min_boards:
                results.append({
                    'panel_size': f"{panel_size.width} x {panel_size.height} mm",
                    'boards': result.total_boards,
                    'layout': f"{result.boards_x} x {result.boards_y}",
                    'utilization': result.panel_utilization,
                    'cost_factor': result.estimated_cost_factor,
                })
        
        # 효율순 정렬
        results.sort(key=lambda x: (-x['utilization'], x['cost_factor']))
        
        return results
    
    def generate_report(self, result: PanelResult) -> str:
        """패널 보고서 생성"""
        lines = []
        lines.append("=" * 60)
        lines.append("패널라이제이션 보고서")
        lines.append("=" * 60)
        lines.append("")
        
        # 보드 정보
        lines.append("## 보드 정보")
        lines.append(f"- 크기: {self.board_size.width} x {self.board_size.height} mm")
        lines.append(f"- 두께: {self.board_size.thickness} mm")
        lines.append("")
        
        # 패널 정보
        lines.append("## 패널 설정")
        lines.append(f"- 패널 크기: {self.config.panel_size.width} x {self.config.panel_size.height} mm")
        lines.append(f"- 분리 방식: {self.config.separation.value}")
        lines.append(f"- 보드 간격: {self.config.board_spacing} mm")
        lines.append(f"- 레일: 상{self.config.rails.top}/하{self.config.rails.bottom}/"
                    f"좌{self.config.rails.left}/우{self.config.rails.right} mm")
        lines.append("")
        
        # 배열 결과
        lines.append("## 배열 결과")
        lines.append(f"- 배열: {result.boards_x} x {result.boards_y}")
        lines.append(f"- 총 보드 수: {result.total_boards}개")
        lines.append(f"- 패널 활용률: {result.panel_utilization * 100:.1f}%")
        lines.append(f"- 손실 면적: {result.waste_area:.1f} mm²")
        lines.append(f"- 비용 인자: {result.estimated_cost_factor:.3f}")
        lines.append("")
        
        # 보드 위치
        lines.append("## 보드 배치")
        for p in result.board_placements:
            lines.append(f"- [{p.row},{p.col}]: ({p.x:.2f}, {p.y:.2f}) mm, 회전: {p.rotation}°")
        lines.append("")
        
        # 피듀셜
        if result.fiducials:
            lines.append("## 피듀셜")
            for i, f in enumerate(result.fiducials, 1):
                lines.append(f"- FID{i}: ({f.x:.2f}, {f.y:.2f}) mm")
            lines.append("")
        
        # 툴링홀
        if result.tooling_holes:
            lines.append("## 툴링홀")
            for i, t in enumerate(result.tooling_holes, 1):
                lines.append(f"- TH{i}: ({t.x:.2f}, {t.y:.2f}) mm")
            lines.append("")
        
        # V-Cut
        if result.v_cut_lines:
            lines.append("## V-Cut 라인")
            for v in result.v_cut_lines:
                lines.append(f"- {v.direction}: ({v.start_x:.1f},{v.start_y:.1f}) -> ({v.end_x:.1f},{v.end_y:.1f})")
            lines.append("")
        
        # 경고
        if result.warnings:
            lines.append("## 경고")
            for w in result.warnings:
                lines.append(f"- {w}")
        
        return "\n".join(lines)
    
    def export_to_dxf(self, result: PanelResult, output_path: str) -> bool:
        """
        DXF 파일로 내보내기 (간단한 버전)
        
        Note: 실제 구현에서는 ezdxf 라이브러리 사용 권장
        """
        try:
            lines = []
            
            # DXF 헤더
            lines.append("0\nSECTION\n2\nENTITIES")
            
            # 패널 외곽
            panel_w = self.config.panel_size.width
            panel_h = self.config.panel_size.height
            lines.append(self._dxf_rectangle(0, 0, panel_w, panel_h))
            
            # 보드 위치
            for p in result.board_placements:
                if p.rotation == 90:
                    w, h = self.board_size.height, self.board_size.width
                else:
                    w, h = self.board_size.width, self.board_size.height
                lines.append(self._dxf_rectangle(p.x, p.y, p.x + w, p.y + h))
            
            # V-Cut 라인
            for v in result.v_cut_lines:
                lines.append(self._dxf_line(v.start_x, v.start_y, v.end_x, v.end_y))
            
            # 피듀셜
            for f in result.fiducials:
                lines.append(self._dxf_circle(f.x, f.y, self.config.fiducials.diameter / 2))
            
            # 툴링홀
            for t in result.tooling_holes:
                lines.append(self._dxf_circle(t.x, t.y, self.config.tooling_holes.diameter / 2))
            
            # DXF 푸터
            lines.append("0\nENDSEC\n0\nEOF")
            
            with open(output_path, 'w') as f:
                f.write("\n".join(lines))
            
            return True
            
        except Exception as e:
            print(f"DXF 내보내기 실패: {e}")
            return False
    
    def _dxf_line(self, x1: float, y1: float, x2: float, y2: float) -> str:
        return f"0\nLINE\n10\n{x1}\n20\n{y1}\n11\n{x2}\n21\n{y2}"
    
    def _dxf_rectangle(self, x1: float, y1: float, x2: float, y2: float) -> str:
        return (
            self._dxf_line(x1, y1, x2, y1) + "\n" +
            self._dxf_line(x2, y1, x2, y2) + "\n" +
            self._dxf_line(x2, y2, x1, y2) + "\n" +
            self._dxf_line(x1, y2, x1, y1)
        )
    
    def _dxf_circle(self, x: float, y: float, radius: float) -> str:
        return f"0\nCIRCLE\n10\n{x}\n20\n{y}\n40\n{radius}"
