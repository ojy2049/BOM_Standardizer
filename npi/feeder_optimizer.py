#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMT 피더 최적화 모듈
- Hanwha/Samsung SM 시리즈 지원 (SM411, SM421, SM471 Plus, SM482 Plus)
- 피더 슬롯 배치 최적화
- 라인 밸런싱
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import math


class MachineType(Enum):
    """장비 유형"""
    SM411 = "SM411"
    SM421 = "SM421"
    SM471_PLUS = "SM471_PLUS"
    SM482_PLUS = "SM482_PLUS"


class FeederType(Enum):
    """피더 유형"""
    SME_8MM = "SME_8mm"
    SME_8MM_L = "SME_8mm_L"
    SME_12MM = "SME_12mm"
    SME_16MM = "SME_16mm"
    SME_24MM = "SME_24mm"
    SME_32MM = "SME_32mm"
    SME_44MM = "SME_44mm"
    SME_56MM = "SME_56mm"
    SME_72MM = "SME_72mm"
    TRAY_MATRIX = "TRAY_MATRIX"
    STICK_FEEDER = "STICK_FEEDER"


@dataclass
class FeederSpec:
    """피더 스펙"""
    feeder_type: FeederType
    tape_width_mm: int
    feed_pitch_mm: List[int]
    reel_diameter_mm: Dict[str, int]
    slots_occupied: int
    component_sizes: List[str]
    features: List[str] = field(default_factory=list)


@dataclass
class MachineSpec:
    """장비 스펙"""
    name: str
    machine_type: MachineType
    speed_cph: int
    accuracy_mm: float
    pcb_size: Dict[str, float]
    pcb_thickness: Dict[str, float]
    feeder_capacity: Dict[str, int]
    feeder_bank_slots: int
    heads: int
    nozzles_per_head: int
    

@dataclass
class ComponentForFeeder:
    """피더 배치용 부품 정보"""
    ref_des: str
    mpn: str
    package: str
    quantity: int
    placement_count: int  # 실장 횟수 (위치 수)
    tape_width_mm: int = 8
    feed_pitch_mm: int = 4
    feeder_type: Optional[FeederType] = None
    nozzle_type: str = ""
    is_polarized: bool = False
    
    def get_key(self) -> str:
        """동일 부품 그룹화를 위한 키"""
        return f"{self.mpn}_{self.package}"


@dataclass
class FeederSlot:
    """피더 슬롯"""
    slot_number: int
    bank: str  # "front", "rear"
    feeder_type: Optional[FeederType] = None
    component: Optional[ComponentForFeeder] = None
    is_occupied: bool = False
    slots_used: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'slot_number': self.slot_number,
            'bank': self.bank,
            'feeder_type': self.feeder_type.value if self.feeder_type else None,
            'component': {
                'ref_des': self.component.ref_des,
                'mpn': self.component.mpn,
                'package': self.component.package,
                'placement_count': self.component.placement_count,
            } if self.component else None,
            'is_occupied': self.is_occupied,
            'slots_used': self.slots_used,
        }


@dataclass
class FeederAssignment:
    """피더 배치 결과"""
    machine: str
    total_slots: int
    used_slots: int
    slot_utilization: float
    assignments: List[FeederSlot]
    unassigned_components: List[ComponentForFeeder]
    optimization_score: float
    estimated_cycle_time_sec: float
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'machine': self.machine,
            'total_slots': self.total_slots,
            'used_slots': self.used_slots,
            'slot_utilization': self.slot_utilization,
            'assignments': [s.to_dict() for s in self.assignments if s.is_occupied],
            'unassigned_components': [
                {'mpn': c.mpn, 'package': c.package, 'reason': 'no_suitable_feeder'}
                for c in self.unassigned_components
            ],
            'optimization_score': self.optimization_score,
            'estimated_cycle_time_sec': self.estimated_cycle_time_sec,
            'warnings': self.warnings,
        }


class FeederOptimizer:
    """피더 최적화기"""
    
    # 패키지별 테이프 폭 매핑
    PACKAGE_TAPE_WIDTH = {
        # 칩 부품 (mm)
        '0201': 8, '0402': 8, '0603': 8, '0805': 8, '1005': 8,
        '1206': 12, '1210': 12, '1812': 12, '2010': 12, '2512': 16,
        # SOT
        'SOT-23': 12, 'SOT-89': 12, 'SOT-223': 12,
        'SOT-323': 8, 'SOT-363': 8, 'SOT-563': 8,
        # SOIC
        'SOIC-8': 16, 'SOIC-14': 16, 'SOIC-16': 16,
        'SOIC-18': 24, 'SOIC-20': 24, 'SOIC-24': 32, 'SOIC-28': 32,
        # TSSOP
        'TSSOP-8': 12, 'TSSOP-14': 16, 'TSSOP-16': 16,
        'TSSOP-20': 24, 'TSSOP-24': 24, 'TSSOP-28': 32,
        # SSOP
        'SSOP-8': 12, 'SSOP-14': 16, 'SSOP-16': 16, 'SSOP-20': 24,
        # MSOP
        'MSOP-8': 8, 'MSOP-10': 12,
        # QFN/DFN
        'QFN-8': 12, 'QFN-12': 16, 'QFN-16': 16, 'QFN-20': 24,
        'QFN-24': 24, 'QFN-28': 32, 'QFN-32': 32, 'QFN-36': 44,
        'QFN-40': 44, 'QFN-48': 56, 'DFN-6': 8, 'DFN-8': 12,
        # TQFP/LQFP
        'TQFP-32': 32, 'TQFP-44': 44, 'TQFP-48': 44,
        'TQFP-64': 56, 'TQFP-100': 72,
        'LQFP-32': 32, 'LQFP-44': 44, 'LQFP-48': 44,
        'LQFP-64': 56, 'LQFP-100': 72,
    }
    
    # 테이프 폭별 슬롯 수
    TAPE_WIDTH_SLOTS = {
        8: 1, 12: 2, 16: 2, 24: 3, 32: 4, 44: 4, 56: 5, 72: 6
    }
    
    # 테이프 폭별 피더 타입
    TAPE_WIDTH_FEEDER = {
        8: FeederType.SME_8MM,
        12: FeederType.SME_12MM,
        16: FeederType.SME_16MM,
        24: FeederType.SME_24MM,
        32: FeederType.SME_32MM,
        44: FeederType.SME_44MM,
        56: FeederType.SME_56MM,
        72: FeederType.SME_72MM,
    }
    
    # 패키지별 노즐 타입
    PACKAGE_NOZZLE = {
        '0201': 'CN020', '0402': 'CN040',
        '0603': 'CN065', '0805': 'CN065',
        '1206': 'CN140', '1210': 'CN140',
        'SOT-23': 'CN140', 'SOT-223': 'CN220',
        'SOIC-8': 'CN220', 'SOIC-16': 'CN220',
        'TSSOP': 'CN220', 'QFN': 'CN400',
        'TQFP-32': 'CN400', 'TQFP-48': 'CN400',
        'TQFP-64': 'CN750', 'LQFP-100': 'CN750',
        'BGA': 'CN1100',
    }
    
    def __init__(self, machine_type: MachineType = MachineType.SM471_PLUS,
                 machine_config_path: Optional[str] = None):
        """
        Args:
            machine_type: 장비 유형
            machine_config_path: 장비 설정 JSON 경로
        """
        self.machine_type = machine_type
        
        if machine_config_path is None:
            app_dir = Path(__file__).parent.parent
            machine_config_path = str(app_dir / "data" / "machines" / "hanwha_sm_series.json")
        
        self.machine_config = self._load_machine_config(machine_config_path)
        self.machine_spec = self._get_machine_spec()
        
        # 슬롯 초기화
        self.front_bank: List[FeederSlot] = []
        self.rear_bank: List[FeederSlot] = []
        self._init_slots()
    
    def _load_machine_config(self, config_path: str) -> Dict:
        """장비 설정 로드"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"장비 설정 로드 실패: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """기본 장비 설정"""
        return {
            'machines': {
                'SM471_PLUS': {
                    'name': 'SM471 Plus',
                    'speed_cph': 78000,
                    'accuracy_mm': 0.025,
                    'feeder_capacity': {'standard': 120, 'with_docking_cart': 112},
                    'feeder_bank_slots': 60,
                    'heads': 10,
                    'nozzles_per_head': 2,
                }
            },
            'feeders': {},
            'package_to_feeder_mapping': {},
        }
    
    def _get_machine_spec(self) -> MachineSpec:
        """장비 스펙 반환"""
        machine_key = self.machine_type.value
        machines = self.machine_config.get('machines', {})
        
        if machine_key in machines:
            m = machines[machine_key]
            return MachineSpec(
                name=m.get('name', machine_key),
                machine_type=self.machine_type,
                speed_cph=m.get('speed_cph', 21000),
                accuracy_mm=m.get('accuracy_mm', 0.05),
                pcb_size=m.get('pcb_size', {'max_x': 510, 'max_y': 460}),
                pcb_thickness=m.get('pcb_thickness', {'min': 0.4, 'max': 4.0}),
                feeder_capacity=m.get('feeder_capacity', {'standard': 120}),
                feeder_bank_slots=m.get('feeder_bank_slots', 60),
                heads=m.get('heads', 8),
                nozzles_per_head=m.get('nozzles_per_head', 1),
            )
        
        # 기본값
        return MachineSpec(
            name=machine_key,
            machine_type=self.machine_type,
            speed_cph=21000,
            accuracy_mm=0.05,
            pcb_size={'max_x': 510, 'max_y': 460},
            pcb_thickness={'min': 0.4, 'max': 4.0},
            feeder_capacity={'standard': 120},
            feeder_bank_slots=60,
            heads=8,
            nozzles_per_head=1,
        )
    
    def _init_slots(self):
        """슬롯 초기화"""
        slots_per_bank = self.machine_spec.feeder_bank_slots
        
        self.front_bank = [
            FeederSlot(slot_number=i+1, bank="front")
            for i in range(slots_per_bank)
        ]
        self.rear_bank = [
            FeederSlot(slot_number=i+1, bank="rear")
            for i in range(slots_per_bank)
        ]
    
    def _reset_slots(self):
        """슬롯 리셋"""
        for slot in self.front_bank + self.rear_bank:
            slot.feeder_type = None
            slot.component = None
            slot.is_occupied = False
            slot.slots_used = 1
    
    def get_tape_width(self, package: str) -> int:
        """패키지에 필요한 테이프 폭"""
        pkg_upper = package.upper().replace('-', '').replace('_', '')
        
        # 정확한 매칭
        for key, width in self.PACKAGE_TAPE_WIDTH.items():
            if key.replace('-', '').replace('_', '') == pkg_upper:
                return width
        
        # 부분 매칭
        for key, width in self.PACKAGE_TAPE_WIDTH.items():
            if key.replace('-', '').replace('_', '') in pkg_upper:
                return width
        
        # 숫자 추출 (예: SOIC-8 -> 8)
        numbers = re.findall(r'\d+', package)
        if numbers:
            num = int(numbers[-1])
            if num <= 8:
                return 8
            elif num <= 16:
                return 12
            elif num <= 24:
                return 16
            elif num <= 32:
                return 24
            elif num <= 48:
                return 32
            elif num <= 64:
                return 44
            else:
                return 56
        
        # 기본값
        return 8
    
    def get_feeder_type(self, tape_width: int) -> FeederType:
        """테이프 폭에 해당하는 피더 타입"""
        return self.TAPE_WIDTH_FEEDER.get(tape_width, FeederType.SME_8MM)
    
    def get_slots_required(self, tape_width: int) -> int:
        """필요한 슬롯 수"""
        return self.TAPE_WIDTH_SLOTS.get(tape_width, 1)
    
    def get_nozzle_type(self, package: str) -> str:
        """패키지에 적합한 노즐 타입"""
        pkg_upper = package.upper()
        
        for key, nozzle in self.PACKAGE_NOZZLE.items():
            if key in pkg_upper:
                return nozzle
        
        # 기본값 (중간 크기)
        return 'CN140'
    
    def prepare_components(self, bom_data: List[Dict]) -> List[ComponentForFeeder]:
        """BOM 데이터에서 피더용 부품 리스트 생성"""
        components = []
        
        for item in bom_data:
            mpn = str(item.get('mpn', item.get('공식부품명', '')))
            package = str(item.get('package', item.get('패키지', '')))
            ref_des = str(item.get('위치', item.get('ref_des', '')))
            quantity = int(item.get('수량', 1))
            mounting = str(item.get('장착방식', 'SMD')).upper()
            
            # SMD만 처리
            if 'DIP' in mounting or 'TH' in mounting:
                continue
            
            # RefDes에서 실장 횟수 계산
            if ref_des:
                placement_count = len(ref_des.replace(' ', '').split(','))
            else:
                placement_count = quantity
            
            tape_width = self.get_tape_width(package)
            feeder_type = self.get_feeder_type(tape_width)
            nozzle_type = self.get_nozzle_type(package)
            
            comp = ComponentForFeeder(
                ref_des=ref_des,
                mpn=mpn,
                package=package,
                quantity=quantity,
                placement_count=placement_count,
                tape_width_mm=tape_width,
                feeder_type=feeder_type,
                nozzle_type=nozzle_type,
            )
            components.append(comp)
        
        return components
    
    def optimize(self, components: List[ComponentForFeeder],
                 strategy: str = "balanced") -> FeederAssignment:
        """
        피더 배치 최적화
        
        Args:
            components: 부품 리스트
            strategy: 최적화 전략
                - "balanced": 양쪽 밸런스
                - "front_first": 전면 우선
                - "usage_based": 사용량 기반 (많이 쓰는 부품 중앙)
                
        Returns:
            FeederAssignment
        """
        self._reset_slots()
        
        # 중복 부품 병합 (같은 MPN+Package)
        merged = self._merge_components(components)
        
        # 정렬 (전략에 따라)
        if strategy == "usage_based":
            # 실장 횟수 많은 것부터
            sorted_comps = sorted(merged, key=lambda c: -c.placement_count)
        else:
            # 슬롯 적게 쓰는 것부터 (효율적 배치)
            sorted_comps = sorted(merged, key=lambda c: (c.tape_width_mm, -c.placement_count))
        
        assignments: List[FeederSlot] = []
        unassigned: List[ComponentForFeeder] = []
        
        if strategy == "balanced":
            # 양쪽 밸런스 배치
            front_idx = 0
            rear_idx = 0
            use_front = True
            
            for comp in sorted_comps:
                slots_needed = self.get_slots_required(comp.tape_width_mm)
                
                if use_front:
                    slot_idx = self._find_consecutive_slots(self.front_bank, front_idx, slots_needed)
                    if slot_idx >= 0:
                        self._assign_to_slots(self.front_bank, slot_idx, comp, slots_needed)
                        front_idx = slot_idx + slots_needed
                    else:
                        # 전면 불가, 후면 시도
                        slot_idx = self._find_consecutive_slots(self.rear_bank, rear_idx, slots_needed)
                        if slot_idx >= 0:
                            self._assign_to_slots(self.rear_bank, slot_idx, comp, slots_needed)
                            rear_idx = slot_idx + slots_needed
                        else:
                            unassigned.append(comp)
                else:
                    slot_idx = self._find_consecutive_slots(self.rear_bank, rear_idx, slots_needed)
                    if slot_idx >= 0:
                        self._assign_to_slots(self.rear_bank, slot_idx, comp, slots_needed)
                        rear_idx = slot_idx + slots_needed
                    else:
                        slot_idx = self._find_consecutive_slots(self.front_bank, front_idx, slots_needed)
                        if slot_idx >= 0:
                            self._assign_to_slots(self.front_bank, slot_idx, comp, slots_needed)
                            front_idx = slot_idx + slots_needed
                        else:
                            unassigned.append(comp)
                
                use_front = not use_front
        
        elif strategy == "usage_based":
            # 많이 쓰는 부품 중앙 배치
            center_front = len(self.front_bank) // 2
            center_rear = len(self.rear_bank) // 2
            
            front_left = center_front
            front_right = center_front
            rear_left = center_rear
            rear_right = center_rear
            
            use_front = True
            go_left = True
            
            for comp in sorted_comps:
                slots_needed = self.get_slots_required(comp.tape_width_mm)
                assigned = False
                
                # 4방향 시도 (중앙에서 양쪽으로)
                for _ in range(4):
                    if use_front:
                        if go_left:
                            start = max(0, front_left - slots_needed)
                            slot_idx = self._find_consecutive_slots(self.front_bank, start, slots_needed)
                            if slot_idx >= 0 and slot_idx <= front_left:
                                self._assign_to_slots(self.front_bank, slot_idx, comp, slots_needed)
                                front_left = slot_idx - 1
                                assigned = True
                                break
                        else:
                            slot_idx = self._find_consecutive_slots(self.front_bank, front_right, slots_needed)
                            if slot_idx >= 0:
                                self._assign_to_slots(self.front_bank, slot_idx, comp, slots_needed)
                                front_right = slot_idx + slots_needed
                                assigned = True
                                break
                    else:
                        if go_left:
                            start = max(0, rear_left - slots_needed)
                            slot_idx = self._find_consecutive_slots(self.rear_bank, start, slots_needed)
                            if slot_idx >= 0 and slot_idx <= rear_left:
                                self._assign_to_slots(self.rear_bank, slot_idx, comp, slots_needed)
                                rear_left = slot_idx - 1
                                assigned = True
                                break
                        else:
                            slot_idx = self._find_consecutive_slots(self.rear_bank, rear_right, slots_needed)
                            if slot_idx >= 0:
                                self._assign_to_slots(self.rear_bank, slot_idx, comp, slots_needed)
                                rear_right = slot_idx + slots_needed
                                assigned = True
                                break
                    
                    # 다음 시도로
                    if go_left:
                        go_left = False
                    else:
                        go_left = True
                        use_front = not use_front
                
                if not assigned:
                    # 어디든 빈 곳에 배치
                    slot_idx = self._find_consecutive_slots(self.front_bank, 0, slots_needed)
                    if slot_idx >= 0:
                        self._assign_to_slots(self.front_bank, slot_idx, comp, slots_needed)
                    else:
                        slot_idx = self._find_consecutive_slots(self.rear_bank, 0, slots_needed)
                        if slot_idx >= 0:
                            self._assign_to_slots(self.rear_bank, slot_idx, comp, slots_needed)
                        else:
                            unassigned.append(comp)
        
        else:  # front_first
            slot_idx = 0
            bank = self.front_bank
            
            for comp in sorted_comps:
                slots_needed = self.get_slots_required(comp.tape_width_mm)
                
                idx = self._find_consecutive_slots(bank, slot_idx, slots_needed)
                if idx >= 0:
                    self._assign_to_slots(bank, idx, comp, slots_needed)
                    slot_idx = idx + slots_needed
                else:
                    # 현재 뱅크에서 처음부터
                    idx = self._find_consecutive_slots(bank, 0, slots_needed)
                    if idx >= 0:
                        self._assign_to_slots(bank, idx, comp, slots_needed)
                    elif bank == self.front_bank:
                        # 후면으로 전환
                        bank = self.rear_bank
                        slot_idx = 0
                        idx = self._find_consecutive_slots(bank, 0, slots_needed)
                        if idx >= 0:
                            self._assign_to_slots(bank, idx, comp, slots_needed)
                            slot_idx = idx + slots_needed
                        else:
                            unassigned.append(comp)
                    else:
                        unassigned.append(comp)
        
        # 결과 집계
        all_slots = self.front_bank + self.rear_bank
        used_slots = sum(1 for s in all_slots if s.is_occupied)
        total_slots = len(all_slots)
        
        # 최적화 점수 계산
        opt_score = self._calculate_optimization_score()
        
        # 예상 사이클 타임
        total_placements = sum(c.placement_count for c in components)
        cycle_time = total_placements / (self.machine_spec.speed_cph / 3600)
        
        # 경고 생성
        warnings = []
        if unassigned:
            warnings.append(f"{len(unassigned)}개 부품 배치 불가")
        if used_slots / total_slots > 0.9:
            warnings.append("슬롯 사용률 90% 이상 - 여유 슬롯 부족")
        
        return FeederAssignment(
            machine=self.machine_spec.name,
            total_slots=total_slots,
            used_slots=used_slots,
            slot_utilization=used_slots / total_slots if total_slots > 0 else 0,
            assignments=all_slots,
            unassigned_components=unassigned,
            optimization_score=opt_score,
            estimated_cycle_time_sec=cycle_time,
            warnings=warnings,
        )
    
    def _merge_components(self, components: List[ComponentForFeeder]) -> List[ComponentForFeeder]:
        """동일 부품 병합"""
        merged: Dict[str, ComponentForFeeder] = {}
        
        for comp in components:
            key = comp.get_key()
            if key in merged:
                merged[key].placement_count += comp.placement_count
                merged[key].quantity += comp.quantity
                if comp.ref_des:
                    merged[key].ref_des += f", {comp.ref_des}"
            else:
                merged[key] = ComponentForFeeder(
                    ref_des=comp.ref_des,
                    mpn=comp.mpn,
                    package=comp.package,
                    quantity=comp.quantity,
                    placement_count=comp.placement_count,
                    tape_width_mm=comp.tape_width_mm,
                    feeder_type=comp.feeder_type,
                    nozzle_type=comp.nozzle_type,
                )
        
        return list(merged.values())
    
    def _find_consecutive_slots(self, bank: List[FeederSlot], 
                                 start_idx: int, count: int) -> int:
        """연속된 빈 슬롯 찾기"""
        for i in range(start_idx, len(bank) - count + 1):
            if all(not bank[i+j].is_occupied for j in range(count)):
                return i
        return -1
    
    def _assign_to_slots(self, bank: List[FeederSlot], 
                         start_idx: int, comp: ComponentForFeeder, count: int):
        """슬롯에 부품 배치"""
        for i in range(count):
            bank[start_idx + i].is_occupied = True
            bank[start_idx + i].feeder_type = comp.feeder_type
            bank[start_idx + i].slots_used = count
            
            # 첫 슬롯에만 부품 정보
            if i == 0:
                bank[start_idx + i].component = comp
    
    def _calculate_optimization_score(self) -> float:
        """최적화 점수 계산 (0-100)"""
        score = 100.0
        
        # 슬롯 사용률 (적당히 사용할수록 좋음 - 50-80%가 이상적)
        all_slots = self.front_bank + self.rear_bank
        used = sum(1 for s in all_slots if s.is_occupied)
        util_ratio = used / len(all_slots) if all_slots else 0
        
        if util_ratio < 0.3:
            score -= 10  # 너무 적음
        elif util_ratio > 0.9:
            score -= 15  # 너무 많음
        
        # 밸런스 (전면/후면 균형)
        front_used = sum(1 for s in self.front_bank if s.is_occupied)
        rear_used = sum(1 for s in self.rear_bank if s.is_occupied)
        
        if front_used > 0 and rear_used > 0:
            balance = min(front_used, rear_used) / max(front_used, rear_used)
            if balance < 0.5:
                score -= 10 * (1 - balance)
        
        # 노즐 그룹화 (같은 노즐 타입이 인접할수록 좋음)
        nozzle_changes = 0
        prev_nozzle = None
        
        for slot in self.front_bank + self.rear_bank:
            if slot.component:
                if prev_nozzle and prev_nozzle != slot.component.nozzle_type:
                    nozzle_changes += 1
                prev_nozzle = slot.component.nozzle_type
        
        score -= nozzle_changes * 0.5
        
        return max(0, min(100, score))
    
    def generate_feeder_list(self, assignment: FeederAssignment) -> str:
        """피더 리스트 출력 생성"""
        lines = []
        lines.append("=" * 80)
        lines.append(f"피더 배치 리스트 - {assignment.machine}")
        lines.append("=" * 80)
        lines.append("")
        
        # 요약
        lines.append("## 요약")
        lines.append(f"- 총 슬롯: {assignment.total_slots}")
        lines.append(f"- 사용 슬롯: {assignment.used_slots}")
        lines.append(f"- 사용률: {assignment.slot_utilization * 100:.1f}%")
        lines.append(f"- 최적화 점수: {assignment.optimization_score:.1f}/100")
        lines.append(f"- 예상 사이클 타임: {assignment.estimated_cycle_time_sec:.1f}초")
        lines.append("")
        
        # 전면 뱅크
        lines.append("## 전면 뱅크 (Front)")
        lines.append("-" * 60)
        lines.append(f"{'슬롯':>4} | {'피더':>10} | {'부품번호':<25} | {'패키지':<15} | {'실장수':>6}")
        lines.append("-" * 60)
        
        for slot in self.front_bank:
            if slot.component:
                lines.append(
                    f"{slot.slot_number:>4} | "
                    f"{slot.feeder_type.value if slot.feeder_type else '-':>10} | "
                    f"{slot.component.mpn[:25]:<25} | "
                    f"{slot.component.package[:15]:<15} | "
                    f"{slot.component.placement_count:>6}"
                )
        lines.append("")
        
        # 후면 뱅크
        lines.append("## 후면 뱅크 (Rear)")
        lines.append("-" * 60)
        lines.append(f"{'슬롯':>4} | {'피더':>10} | {'부품번호':<25} | {'패키지':<15} | {'실장수':>6}")
        lines.append("-" * 60)
        
        for slot in self.rear_bank:
            if slot.component:
                lines.append(
                    f"{slot.slot_number:>4} | "
                    f"{slot.feeder_type.value if slot.feeder_type else '-':>10} | "
                    f"{slot.component.mpn[:25]:<25} | "
                    f"{slot.component.package[:15]:<15} | "
                    f"{slot.component.placement_count:>6}"
                )
        lines.append("")
        
        # 미배치 부품
        if assignment.unassigned_components:
            lines.append("## 미배치 부품")
            for comp in assignment.unassigned_components:
                lines.append(f"- {comp.mpn} ({comp.package})")
        
        # 경고
        if assignment.warnings:
            lines.append("")
            lines.append("## 경고")
            for w in assignment.warnings:
                lines.append(f"- {w}")
        
        return "\n".join(lines)
    
    def export_to_csv(self, assignment: FeederAssignment, output_path: str):
        """CSV로 내보내기"""
        lines = []
        lines.append("Bank,Slot,FeederType,MPN,Package,PlacementCount,RefDes")
        
        for slot in self.front_bank:
            if slot.component:
                lines.append(
                    f"Front,{slot.slot_number},{slot.feeder_type.value if slot.feeder_type else ''},"
                    f"{slot.component.mpn},{slot.component.package},"
                    f"{slot.component.placement_count},{slot.component.ref_des}"
                )
        
        for slot in self.rear_bank:
            if slot.component:
                lines.append(
                    f"Rear,{slot.slot_number},{slot.feeder_type.value if slot.feeder_type else ''},"
                    f"{slot.component.mpn},{slot.component.package},"
                    f"{slot.component.placement_count},{slot.component.ref_des}"
                )
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
    
    def get_required_feeders(self, components: List[ComponentForFeeder]) -> Dict[str, int]:
        """필요한 피더 목록"""
        feeders: Dict[str, int] = defaultdict(int)
        
        merged = self._merge_components(components)
        for comp in merged:
            feeder_type = self.get_feeder_type(comp.tape_width_mm)
            feeders[feeder_type.value] += 1
        
        return dict(feeders)
    
    def get_required_nozzles(self, components: List[ComponentForFeeder]) -> Dict[str, int]:
        """필요한 노즐 목록"""
        nozzles: Dict[str, int] = defaultdict(int)
        
        for comp in components:
            nozzle = self.get_nozzle_type(comp.package)
            nozzles[nozzle] += comp.placement_count
        
        return dict(nozzles)
