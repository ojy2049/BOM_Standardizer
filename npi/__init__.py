#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NPI Pro 모듈
- BOM 버전 관리
- DFM/DFA 분석
- 피더 최적화
- 패널라이제이션
"""

from .version_manager import BOMVersionManager, BOMVersion, BOMDiff
from .dfm_analyzer import DFMAnalyzer, DFMRule, DFMViolation
from .feeder_optimizer import FeederOptimizer, FeederSlot, FeederAssignment
from .panelization import Panelizer, PanelConfig, PanelResult

__version__ = "1.0.0"
__all__ = [
    'BOMVersionManager', 'BOMVersion', 'BOMDiff',
    'DFMAnalyzer', 'DFMRule', 'DFMViolation',
    'FeederOptimizer', 'FeederSlot', 'FeederAssignment',
    'Panelizer', 'PanelConfig', 'PanelResult',
]
