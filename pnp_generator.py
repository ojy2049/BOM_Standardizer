#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pick & Place 프로그램 생성 모듈
- Samsung SM 시리즈 (SM421, SM411, SM471, SM482) 지원
- 범용 CSV 형식 지원
- BOM + Centroid 데이터 통합
"""

import os
import csv
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class PlacementData:
    """배치 데이터 항목"""
    refdes: str              # Reference Designator
    x: float                 # X 좌표 (mm)
    y: float                 # Y 좌표 (mm)
    rotation: float          # 회전 각도 (도)
    layer: str               # 레이어 (Top/Bottom)
    footprint: str           # 패키지/풋프린트
    value: str               # 값/스펙
    mpn: str                 # 제조사 부품번호
    mounting_type: str       # 장착방식 (SMD/DIP)
    feeder: str = ""         # 피더 슬롯 (선택)
    nozzle: str = ""         # 노즐 타입 (선택)
    skip: bool = False       # 스킵 여부


class SamsungSMGenerator:
    """
    Samsung SM 시리즈 Pick & Place 프로그램 생성기
    
    지원 장비:
    - SM421 (칩마운터)
    - SM411 (칩마운터)
    - SM471 PLUS (고속 칩마운터)
    - SM482 PLUS (이형부품 마운터)
    
    출력 형식:
    - SSA (Samsung Standard ASCII) 형식
    - CSV 임포트 형식
    """
    
    # 패키지별 노즐 매핑 (기본값)
    NOZZLE_MAP = {
        # 칩 사이즈별
        '0201': 'CN020', '0402': 'CN040', '0603': 'CN065',
        '0805': 'CN140', '1206': 'CN220', '1210': 'CN220',
        '1812': 'CN400', '2010': 'CN400', '2512': 'CN400',
        # IC 패키지별
        'SOT-23': 'CN140', 'SOT-89': 'CN220', 'SOT-223': 'CN400',
        'SOIC-8': 'CN400', 'SOIC-14': 'CN400', 'SOIC-16': 'CN400',
        'SSOP': 'CN400', 'TSSOP': 'CN220', 'MSOP': 'CN140',
        'QFN': 'CN750', 'QFP': 'CN750', 'LQFP': 'CN750',
        'BGA': 'CN750',
        # 기타
        'LED': 'CN140', 'DIODE': 'CN140',
        'DEFAULT': 'CN220',
    }
    
    # 패키지별 피더 폭 매핑 (mm)
    FEEDER_WIDTH_MAP = {
        '0201': 8, '0402': 8, '0603': 8, '0805': 8,
        '1206': 8, '1210': 12, '1812': 12, '2010': 12, '2512': 16,
        'SOT-23': 8, 'SOT-89': 12, 'SOT-223': 12,
        'SOIC-8': 12, 'SOIC-14': 16, 'SOIC-16': 16,
        'SSOP': 12, 'TSSOP': 8, 'MSOP': 8,
        'QFN': 12, 'QFP': 24, 'LQFP': 24,
        'DEFAULT': 8,
    }
    
    def __init__(self, machine_type: str = "SM471"):
        """
        Args:
            machine_type: 장비 타입 (SM421, SM411, SM471, SM482)
        """
        self.machine_type = machine_type.upper()
        self.placement_data: List[PlacementData] = []
        self.board_info = {
            'name': '',
            'size_x': 0.0,
            'size_y': 0.0,
            'thickness': 1.6,
            'fiducial': [],
        }
    
    def set_board_info(self, name: str, size_x: float, size_y: float, 
                       thickness: float = 1.6, fiducials: List[Tuple[float, float]] = None):
        """기판 정보 설정"""
        self.board_info = {
            'name': name,
            'size_x': size_x,
            'size_y': size_y,
            'thickness': thickness,
            'fiducials': fiducials or [],
        }
    
    def load_from_dataframe(self, df: pd.DataFrame, 
                           column_mapping: Dict[str, str] = None) -> int:
        """
        DataFrame에서 배치 데이터 로드
        
        Args:
            df: BOM+Centroid 통합 DataFrame
            column_mapping: 컬럼 매핑 (선택)
            
        Returns:
            로드된 부품 수
        """
        # 기본 컬럼 매핑
        default_mapping = {
            'refdes': '위치',
            'x': 'X',
            'y': 'Y',
            'rotation': 'Rotation',
            'layer': 'Layer',
            'footprint': '패키지',
            'value': '스펙',
            'mpn': '공식부품명',
            'mounting': '장착방식',
        }
        mapping = {**default_mapping, **(column_mapping or {})}
        
        self.placement_data = []
        
        for _, row in df.iterrows():
            # RefDes 파싱 (여러 개인 경우 첫 번째 사용)
            refdes_raw = str(row.get(mapping['refdes'], '')).strip()
            if not refdes_raw or refdes_raw.lower() == 'nan':
                continue
            
            # 좌표 확인
            x = row.get(mapping['x'])
            y = row.get(mapping['y'])
            if pd.isna(x) or pd.isna(y):
                continue
            
            # 장착방식 확인 (DIP는 스킵)
            mounting = str(row.get(mapping['mounting'], '')).upper()
            if 'DIP' in mounting:
                continue
            
            # 첫 번째 RefDes만 사용 (나머지는 별도 처리 필요)
            refdes_list = refdes_raw.replace(',', ' ').split()
            refdes = refdes_list[0] if refdes_list else refdes_raw
            
            rotation = float(row.get(mapping['rotation'], 0)) if not pd.isna(row.get(mapping['rotation'])) else 0
            layer = str(row.get(mapping['layer'], 'Top'))
            footprint = str(row.get(mapping['footprint'], ''))
            value = str(row.get(mapping['value'], ''))
            mpn = str(row.get(mapping['mpn'], ''))
            
            # nan 처리
            for var in ['footprint', 'value', 'mpn']:
                if locals()[var].lower() == 'nan':
                    locals()[var] = ''
            
            self.placement_data.append(PlacementData(
                refdes=refdes,
                x=float(x),
                y=float(y),
                rotation=rotation % 360,
                layer=layer if layer.lower() != 'nan' else 'Top',
                footprint=footprint if footprint.lower() != 'nan' else '',
                value=value if value.lower() != 'nan' else '',
                mpn=mpn if mpn.lower() != 'nan' else '',
                mounting_type='SMD',
                nozzle=self._get_nozzle(footprint),
            ))
        
        return len(self.placement_data)
    
    def _get_nozzle(self, footprint: str) -> str:
        """패키지에 맞는 노즐 선택"""
        footprint_upper = footprint.upper()
        
        for pattern, nozzle in self.NOZZLE_MAP.items():
            if pattern in footprint_upper:
                return nozzle
        
        return self.NOZZLE_MAP['DEFAULT']
    
    def _get_feeder_width(self, footprint: str) -> int:
        """패키지에 맞는 피더 폭 선택"""
        footprint_upper = footprint.upper()
        
        for pattern, width in self.FEEDER_WIDTH_MAP.items():
            if pattern in footprint_upper:
                return width
        
        return self.FEEDER_WIDTH_MAP['DEFAULT']
    
    def generate_csv(self, output_path: str, layer: str = "Top") -> Tuple[bool, str]:
        """
        Samsung SM용 CSV 파일 생성
        
        Args:
            output_path: 출력 파일 경로
            layer: 레이어 (Top/Bottom)
            
        Returns:
            (성공여부, 메시지)
        """
        try:
            # 해당 레이어 부품만 필터
            layer_data = [d for d in self.placement_data if d.layer.lower() == layer.lower()]
            
            if not layer_data:
                return False, f"{layer} 레이어에 배치할 부품이 없습니다."
            
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                
                # 헤더
                writer.writerow([
                    'Ref', 'X(mm)', 'Y(mm)', 'Rotation', 'Side', 
                    'Package', 'Value', 'Part Number', 'Nozzle', 'Feeder'
                ])
                
                # 데이터
                for idx, d in enumerate(layer_data, 1):
                    writer.writerow([
                        d.refdes,
                        f"{d.x:.3f}",
                        f"{d.y:.3f}",
                        f"{d.rotation:.1f}",
                        d.layer,
                        d.footprint,
                        d.value,
                        d.mpn,
                        d.nozzle,
                        d.feeder if d.feeder else f"F{idx:03d}",
                    ])
            
            return True, f"{len(layer_data)}개 부품 CSV 파일 생성 완료: {output_path}"
            
        except Exception as e:
            return False, f"CSV 생성 실패: {str(e)}"
    
    def generate_ssa(self, output_path: str, layer: str = "Top") -> Tuple[bool, str]:
        """
        Samsung SSA (Samsung Standard ASCII) 형식 파일 생성
        
        Args:
            output_path: 출력 파일 경로
            layer: 레이어 (Top/Bottom)
            
        Returns:
            (성공여부, 메시지)
        """
        try:
            layer_data = [d for d in self.placement_data if d.layer.lower() == layer.lower()]
            
            if not layer_data:
                return False, f"{layer} 레이어에 배치할 부품이 없습니다."
            
            with open(output_path, 'w', encoding='utf-8') as f:
                # 헤더 섹션
                f.write(f"# Samsung {self.machine_type} Pick & Place Program\n")
                f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Board: {self.board_info.get('name', 'Unknown')}\n")
                f.write(f"# Layer: {layer}\n")
                f.write(f"# Total Components: {len(layer_data)}\n")
                f.write("#\n")
                
                # 보드 정보 섹션
                f.write("[BOARD_INFO]\n")
                f.write(f"NAME={self.board_info.get('name', 'PCB')}\n")
                f.write(f"SIZE_X={self.board_info.get('size_x', 100.0):.2f}\n")
                f.write(f"SIZE_Y={self.board_info.get('size_y', 100.0):.2f}\n")
                f.write(f"THICKNESS={self.board_info.get('thickness', 1.6):.2f}\n")
                f.write("\n")
                
                # 피듀셜 섹션
                fiducials = self.board_info.get('fiducials', [])
                if fiducials:
                    f.write("[FIDUCIALS]\n")
                    for idx, (fx, fy) in enumerate(fiducials, 1):
                        f.write(f"FID{idx}={fx:.3f},{fy:.3f}\n")
                    f.write("\n")
                
                # 배치 데이터 섹션
                f.write("[PLACEMENT_DATA]\n")
                f.write("# REF,X,Y,R,PACKAGE,VALUE,PART_NO,NOZZLE,FEEDER\n")
                
                for idx, d in enumerate(layer_data, 1):
                    line = f"{d.refdes},{d.x:.3f},{d.y:.3f},{d.rotation:.1f},"
                    line += f"{d.footprint},{d.value},{d.mpn},{d.nozzle},"
                    line += f"{d.feeder if d.feeder else f'F{idx:03d}'}\n"
                    f.write(line)
                
                f.write("\n[END]\n")
            
            return True, f"{len(layer_data)}개 부품 SSA 파일 생성 완료: {output_path}"
            
        except Exception as e:
            return False, f"SSA 생성 실패: {str(e)}"
    
    def generate_feeder_list(self, output_path: str, layer: str = "Top") -> Tuple[bool, str]:
        """
        피더 리스트 생성 (부품별 피더 배치 계획)
        
        Args:
            output_path: 출력 파일 경로
            layer: 레이어
            
        Returns:
            (성공여부, 메시지)
        """
        try:
            layer_data = [d for d in self.placement_data if d.layer.lower() == layer.lower()]
            
            if not layer_data:
                return False, f"{layer} 레이어에 부품이 없습니다."
            
            # 부품별 그룹화 (동일 부품은 하나의 피더)
            feeder_groups: Dict[str, Dict] = {}
            
            for d in layer_data:
                # 그룹 키: 패키지 + 값 또는 MPN
                key = f"{d.footprint}|{d.value or d.mpn}"
                
                if key not in feeder_groups:
                    feeder_groups[key] = {
                        'package': d.footprint,
                        'value': d.value,
                        'mpn': d.mpn,
                        'refdes_list': [],
                        'count': 0,
                        'feeder_width': self._get_feeder_width(d.footprint),
                        'nozzle': d.nozzle,
                    }
                
                feeder_groups[key]['refdes_list'].append(d.refdes)
                feeder_groups[key]['count'] += 1
            
            # CSV 출력
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Feeder', 'Package', 'Value', 'Part Number', 
                    'Qty', 'Feeder Width(mm)', 'Nozzle', 'RefDes List'
                ])
                
                for idx, (key, grp) in enumerate(sorted(feeder_groups.items()), 1):
                    writer.writerow([
                        f"F{idx:03d}",
                        grp['package'],
                        grp['value'],
                        grp['mpn'],
                        grp['count'],
                        grp['feeder_width'],
                        grp['nozzle'],
                        ', '.join(grp['refdes_list'][:10]) + ('...' if len(grp['refdes_list']) > 10 else ''),
                    ])
            
            return True, f"{len(feeder_groups)}개 피더 슬롯 리스트 생성: {output_path}"
            
        except Exception as e:
            return False, f"피더 리스트 생성 실패: {str(e)}"
    
    def get_summary(self) -> Dict[str, Any]:
        """배치 요약 정보"""
        top_count = len([d for d in self.placement_data if d.layer == 'Top'])
        bottom_count = len([d for d in self.placement_data if d.layer == 'Bottom'])
        
        # 패키지별 통계
        package_stats = {}
        for d in self.placement_data:
            pkg = d.footprint or 'Unknown'
            package_stats[pkg] = package_stats.get(pkg, 0) + 1
        
        return {
            'total': len(self.placement_data),
            'top': top_count,
            'bottom': bottom_count,
            'machine': self.machine_type,
            'package_stats': package_stats,
            'board': self.board_info,
        }


class GenericPnPGenerator:
    """범용 Pick & Place CSV 생성기"""
    
    def __init__(self):
        self.placement_data: List[PlacementData] = []
    
    def load_from_dataframe(self, df: pd.DataFrame) -> int:
        """DataFrame에서 로드"""
        # SamsungSMGenerator와 동일한 로직 사용
        samsung_gen = SamsungSMGenerator()
        count = samsung_gen.load_from_dataframe(df)
        self.placement_data = samsung_gen.placement_data
        return count
    
    def generate_csv(self, output_path: str, layer: str = "Top") -> Tuple[bool, str]:
        """범용 CSV 형식 출력"""
        try:
            layer_data = [d for d in self.placement_data if d.layer.lower() == layer.lower()]
            
            if not layer_data:
                return False, f"{layer} 레이어에 배치할 부품이 없습니다."
            
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                
                # 표준 Centroid 형식
                writer.writerow([
                    'Designator', 'Mid X', 'Mid Y', 'Rotation', 'Layer',
                    'Footprint', 'Comment'
                ])
                
                for d in layer_data:
                    writer.writerow([
                        d.refdes,
                        f"{d.x:.4f}mm",
                        f"{d.y:.4f}mm",
                        f"{d.rotation:.2f}",
                        d.layer,
                        d.footprint,
                        d.value or d.mpn,
                    ])
            
            return True, f"{len(layer_data)}개 부품 CSV 생성: {output_path}"
            
        except Exception as e:
            return False, f"CSV 생성 실패: {str(e)}"


def generate_pnp_files(bom_df: pd.DataFrame, output_dir: str, 
                       board_name: str = "PCB",
                       machine_type: str = "SM471") -> Tuple[bool, str, List[str]]:
    """
    BOM+좌표 데이터에서 P&P 파일들 일괄 생성
    
    Args:
        bom_df: BOM + 좌표 통합 DataFrame
        output_dir: 출력 디렉토리
        board_name: 기판 이름
        machine_type: 장비 타입
        
    Returns:
        (성공여부, 메시지, 생성된 파일 리스트)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    generated_files = []
    
    try:
        # Samsung SM 생성기
        generator = SamsungSMGenerator(machine_type)
        generator.set_board_info(board_name, 100, 100)  # 기본 크기
        count = generator.load_from_dataframe(bom_df)
        
        if count == 0:
            return False, "배치 가능한 SMD 부품이 없습니다.", []
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name = f"{board_name}_{timestamp}"
        
        # Top 레이어 파일 생성
        top_data = [d for d in generator.placement_data if d.layer == 'Top']
        if top_data:
            # SSA 파일
            ssa_path = output_dir / f"{base_name}_Top.ssa"
            success, msg = generator.generate_ssa(str(ssa_path), "Top")
            if success:
                generated_files.append(str(ssa_path))
            
            # CSV 파일
            csv_path = output_dir / f"{base_name}_Top.csv"
            success, msg = generator.generate_csv(str(csv_path), "Top")
            if success:
                generated_files.append(str(csv_path))
            
            # 피더 리스트
            feeder_path = output_dir / f"{base_name}_Top_Feeder.csv"
            success, msg = generator.generate_feeder_list(str(feeder_path), "Top")
            if success:
                generated_files.append(str(feeder_path))
        
        # Bottom 레이어 파일 생성
        bottom_data = [d for d in generator.placement_data if d.layer == 'Bottom']
        if bottom_data:
            ssa_path = output_dir / f"{base_name}_Bottom.ssa"
            success, msg = generator.generate_ssa(str(ssa_path), "Bottom")
            if success:
                generated_files.append(str(ssa_path))
            
            csv_path = output_dir / f"{base_name}_Bottom.csv"
            success, msg = generator.generate_csv(str(csv_path), "Bottom")
            if success:
                generated_files.append(str(csv_path))
        
        summary = generator.get_summary()
        msg = f"""P&P 파일 생성 완료!
- 장비: {machine_type}
- 총 부품: {summary['total']}개
- Top: {summary['top']}개, Bottom: {summary['bottom']}개
- 생성 파일: {len(generated_files)}개"""
        
        return True, msg, generated_files
        
    except Exception as e:
        return False, f"P&P 파일 생성 실패: {str(e)}", generated_files
