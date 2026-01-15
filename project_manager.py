#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
프로젝트 관리 모듈
- BOM, Centroid, 설정을 하나의 프로젝트로 관리
- 분석 결과 저장/로드
- 프로젝트 히스토리
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
import pandas as pd


@dataclass
class ProjectFiles:
    """프로젝트 파일 정보"""
    bom_file: str = ""              # BOM 파일 경로
    centroid_file: str = ""         # Centroid 파일 경로
    gerber_folder: str = ""         # Gerber 폴더 (향후)
    output_folder: str = ""         # 출력 폴더


@dataclass 
class BoardInfo:
    """기판 정보"""
    name: str = "PCB"
    width: float = 100.0            # mm
    height: float = 100.0           # mm
    thickness: float = 1.6          # mm
    layers: int = 2
    fiducials: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class ProcessingResult:
    """처리 결과"""
    timestamp: str = ""
    bom_rows: int = 0
    centroid_rows: int = 0
    smd_count: int = 0
    dip_count: int = 0
    unknown_count: int = 0
    dfm_issues: int = 0
    pnp_generated: bool = False
    output_files: List[str] = field(default_factory=list)


@dataclass
class Project:
    """NPI 프로젝트"""
    name: str = "New Project"
    created: str = ""
    modified: str = ""
    version: str = "1.0"
    files: ProjectFiles = field(default_factory=ProjectFiles)
    board: BoardInfo = field(default_factory=BoardInfo)
    machine_type: str = "SM471"     # Samsung SM 기본값
    settings: Dict[str, Any] = field(default_factory=dict)
    results: List[ProcessingResult] = field(default_factory=list)
    notes: str = ""


class ProjectManager:
    """프로젝트 관리자"""
    
    PROJECT_EXT = ".npiproj"
    PROJECT_VERSION = "1.0"
    
    def __init__(self):
        self.current_project: Optional[Project] = None
        self.project_path: Optional[str] = None
        self.is_modified: bool = False
        
        # 캐시된 데이터
        self._bom_df: Optional[pd.DataFrame] = None
        self._centroid_df: Optional[pd.DataFrame] = None
        self._merged_df: Optional[pd.DataFrame] = None
    
    def new_project(self, name: str = "New Project") -> Project:
        """새 프로젝트 생성"""
        now = datetime.now().isoformat()
        self.current_project = Project(
            name=name,
            created=now,
            modified=now,
            version=self.PROJECT_VERSION,
        )
        self.project_path = None
        self.is_modified = True
        self._clear_cache()
        
        return self.current_project
    
    def save_project(self, file_path: str = None) -> Tuple[bool, str]:
        """프로젝트 저장"""
        if self.current_project is None:
            return False, "저장할 프로젝트가 없습니다."
        
        if file_path:
            self.project_path = file_path
        
        if not self.project_path:
            return False, "저장 경로를 지정해주세요."
        
        # 확장자 확인
        if not self.project_path.endswith(self.PROJECT_EXT):
            self.project_path += self.PROJECT_EXT
        
        try:
            self.current_project.modified = datetime.now().isoformat()
            
            # dataclass를 dict로 변환
            project_dict = self._project_to_dict(self.current_project)
            
            with open(self.project_path, 'w', encoding='utf-8') as f:
                json.dump(project_dict, f, ensure_ascii=False, indent=2)
            
            self.is_modified = False
            return True, f"프로젝트 저장 완료: {self.project_path}"
            
        except Exception as e:
            return False, f"프로젝트 저장 실패: {str(e)}"
    
    def load_project(self, file_path: str) -> Tuple[bool, str]:
        """프로젝트 로드"""
        if not os.path.exists(file_path):
            return False, f"파일을 찾을 수 없습니다: {file_path}"
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                project_dict = json.load(f)
            
            self.current_project = self._dict_to_project(project_dict)
            self.project_path = file_path
            self.is_modified = False
            self._clear_cache()
            
            return True, f"프로젝트 로드 완료: {self.current_project.name}"
            
        except Exception as e:
            return False, f"프로젝트 로드 실패: {str(e)}"
    
    def _project_to_dict(self, project: Project) -> Dict[str, Any]:
        """Project를 dict로 변환"""
        return {
            'name': project.name,
            'created': project.created,
            'modified': project.modified,
            'version': project.version,
            'files': asdict(project.files),
            'board': {
                'name': project.board.name,
                'width': project.board.width,
                'height': project.board.height,
                'thickness': project.board.thickness,
                'layers': project.board.layers,
                'fiducials': project.board.fiducials,
            },
            'machine_type': project.machine_type,
            'settings': project.settings,
            'results': [asdict(r) for r in project.results],
            'notes': project.notes,
        }
    
    def _dict_to_project(self, d: Dict[str, Any]) -> Project:
        """dict를 Project로 변환"""
        project = Project(
            name=d.get('name', 'Unnamed'),
            created=d.get('created', ''),
            modified=d.get('modified', ''),
            version=d.get('version', '1.0'),
            machine_type=d.get('machine_type', 'SM471'),
            settings=d.get('settings', {}),
            notes=d.get('notes', ''),
        )
        
        # Files
        files_dict = d.get('files', {})
        project.files = ProjectFiles(
            bom_file=files_dict.get('bom_file', ''),
            centroid_file=files_dict.get('centroid_file', ''),
            gerber_folder=files_dict.get('gerber_folder', ''),
            output_folder=files_dict.get('output_folder', ''),
        )
        
        # Board
        board_dict = d.get('board', {})
        project.board = BoardInfo(
            name=board_dict.get('name', 'PCB'),
            width=board_dict.get('width', 100.0),
            height=board_dict.get('height', 100.0),
            thickness=board_dict.get('thickness', 1.6),
            layers=board_dict.get('layers', 2),
            fiducials=board_dict.get('fiducials', []),
        )
        
        # Results
        project.results = []
        for r_dict in d.get('results', []):
            project.results.append(ProcessingResult(
                timestamp=r_dict.get('timestamp', ''),
                bom_rows=r_dict.get('bom_rows', 0),
                centroid_rows=r_dict.get('centroid_rows', 0),
                smd_count=r_dict.get('smd_count', 0),
                dip_count=r_dict.get('dip_count', 0),
                unknown_count=r_dict.get('unknown_count', 0),
                dfm_issues=r_dict.get('dfm_issues', 0),
                pnp_generated=r_dict.get('pnp_generated', False),
                output_files=r_dict.get('output_files', []),
            ))
        
        return project
    
    def _clear_cache(self):
        """캐시 초기화"""
        self._bom_df = None
        self._centroid_df = None
        self._merged_df = None
    
    def set_bom_file(self, file_path: str) -> bool:
        """BOM 파일 설정"""
        if self.current_project is None:
            return False
        
        self.current_project.files.bom_file = file_path
        self.is_modified = True
        self._bom_df = None
        self._merged_df = None
        return True
    
    def set_centroid_file(self, file_path: str) -> bool:
        """Centroid 파일 설정"""
        if self.current_project is None:
            return False
        
        self.current_project.files.centroid_file = file_path
        self.is_modified = True
        self._centroid_df = None
        self._merged_df = None
        return True
    
    def set_board_info(self, name: str = None, width: float = None, 
                       height: float = None, thickness: float = None) -> bool:
        """기판 정보 설정"""
        if self.current_project is None:
            return False
        
        if name is not None:
            self.current_project.board.name = name
        if width is not None:
            self.current_project.board.width = width
        if height is not None:
            self.current_project.board.height = height
        if thickness is not None:
            self.current_project.board.thickness = thickness
        
        self.is_modified = True
        return True
    
    def set_machine_type(self, machine_type: str) -> bool:
        """장비 타입 설정"""
        if self.current_project is None:
            return False
        
        self.current_project.machine_type = machine_type.upper()
        self.is_modified = True
        return True
    
    def add_result(self, result: ProcessingResult) -> bool:
        """처리 결과 추가"""
        if self.current_project is None:
            return False
        
        result.timestamp = datetime.now().isoformat()
        self.current_project.results.append(result)
        self.is_modified = True
        
        # 최근 10개만 유지
        if len(self.current_project.results) > 10:
            self.current_project.results = self.current_project.results[-10:]
        
        return True
    
    def get_latest_result(self) -> Optional[ProcessingResult]:
        """최근 처리 결과 조회"""
        if self.current_project and self.current_project.results:
            return self.current_project.results[-1]
        return None
    
    def get_project_summary(self) -> Dict[str, Any]:
        """프로젝트 요약 정보"""
        if self.current_project is None:
            return {}
        
        p = self.current_project
        latest = self.get_latest_result()
        
        return {
            'name': p.name,
            'created': p.created,
            'modified': p.modified,
            'has_bom': bool(p.files.bom_file),
            'has_centroid': bool(p.files.centroid_file),
            'board': f"{p.board.width}x{p.board.height}mm",
            'machine': p.machine_type,
            'process_count': len(p.results),
            'latest_result': {
                'smd': latest.smd_count if latest else 0,
                'dip': latest.dip_count if latest else 0,
                'dfm_issues': latest.dfm_issues if latest else 0,
            } if latest else None,
        }
    
    def export_project_report(self, output_path: str) -> Tuple[bool, str]:
        """프로젝트 보고서 내보내기"""
        if self.current_project is None:
            return False, "프로젝트가 없습니다."
        
        try:
            p = self.current_project
            
            lines = [
                "=" * 60,
                f"NPI 프로젝트 보고서: {p.name}",
                "=" * 60,
                "",
                f"생성일: {p.created}",
                f"수정일: {p.modified}",
                "",
                "--- 기판 정보 ---",
                f"이름: {p.board.name}",
                f"크기: {p.board.width} x {p.board.height} mm",
                f"두께: {p.board.thickness} mm",
                f"레이어: {p.board.layers}",
                "",
                "--- 파일 ---",
                f"BOM: {p.files.bom_file or '없음'}",
                f"Centroid: {p.files.centroid_file or '없음'}",
                f"출력 폴더: {p.files.output_folder or '없음'}",
                "",
                "--- 장비 ---",
                f"타입: {p.machine_type}",
                "",
            ]
            
            if p.results:
                lines.append("--- 처리 이력 ---")
                for idx, r in enumerate(reversed(p.results[-5:]), 1):
                    lines.append(f"\n{idx}. {r.timestamp}")
                    lines.append(f"   SMD: {r.smd_count}, DIP: {r.dip_count}, 미확정: {r.unknown_count}")
                    lines.append(f"   DFM 이슈: {r.dfm_issues}, P&P 생성: {'예' if r.pnp_generated else '아니오'}")
            
            if p.notes:
                lines.append("")
                lines.append("--- 메모 ---")
                lines.append(p.notes)
            
            lines.append("")
            lines.append("=" * 60)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            return True, f"보고서 저장 완료: {output_path}"
            
        except Exception as e:
            return False, f"보고서 생성 실패: {str(e)}"


# 전역 프로젝트 매니저 인스턴스
project_manager = ProjectManager()


def get_recent_projects(folder: str = None, limit: int = 10) -> List[Dict[str, str]]:
    """최근 프로젝트 목록 조회"""
    if folder is None:
        folder = str(Path.home() / "Documents" / "NPI_Projects")
    
    if not os.path.exists(folder):
        return []
    
    projects = []
    for file in Path(folder).glob(f"*{ProjectManager.PROJECT_EXT}"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            projects.append({
                'path': str(file),
                'name': data.get('name', file.stem),
                'modified': data.get('modified', ''),
            })
        except:
            continue
    
    # 수정일 기준 정렬
    projects.sort(key=lambda x: x['modified'], reverse=True)
    return projects[:limit]
