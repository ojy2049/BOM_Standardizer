#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NPI Pro GUI 프레임 모듈
- BOM 버전 관리 탭
- DFM 분석 탭
- 피더 설정 탭
- 패널라이제이션 탭
"""

import os
import json
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import pandas as pd

from .version_manager import BOMVersionManager, BOMVersion, BOMDiff, BOMItem
from .dfm_analyzer import DFMAnalyzer, DFMAnalysisResult, Severity
from .feeder_optimizer import FeederOptimizer, MachineType, FeederAssignment
from .panelization import Panelizer, PanelConfig, PanelSize, BoardSize, PanelResult


class ToolTip:
    """툴팁 클래스"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)
    
    def show(self, event=None):
        if self.tip_window:
            return
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 25
        
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                        background="#ffffe0", relief=tk.SOLID, borderwidth=1)
        label.pack()
    
    def hide(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class NPIProFrame(ttk.Frame):
    """NPI Pro 메인 프레임"""
    
    def __init__(self, parent, bom_df_getter: Callable = None):
        super().__init__(parent, padding=5)
        
        self.bom_df_getter = bom_df_getter  # 현재 BOM 데이터 가져오는 함수
        
        self._create_widgets()
    
    def _create_widgets(self):
        # 내부 노트북 (NPI 기능별 탭)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True)
        
        # BOM 버전 관리 탭
        self.version_frame = BOMVersionFrame(self.notebook, self.bom_df_getter)
        self.notebook.add(self.version_frame, text="📁 BOM 버전 관리")
        
        # DFM 분석 탭
        self.dfm_frame = DFMAnalysisFrame(self.notebook)
        self.notebook.add(self.dfm_frame, text="🔍 DFM 분석")
        
        # 피더 설정 탭
        self.feeder_frame = FeederSetupFrame(self.notebook, self.bom_df_getter)
        self.notebook.add(self.feeder_frame, text="⚙️ 피더 설정")
        
        # 패널라이제이션 탭
        self.panel_frame = PanelizationFrame(self.notebook)
        self.notebook.add(self.panel_frame, text="📐 패널라이제이션")


class BOMVersionFrame(ttk.Frame):
    """BOM 버전 관리 프레임"""
    
    def __init__(self, parent, bom_df_getter: Callable = None):
        super().__init__(parent, padding=10)
        
        self.bom_df_getter = bom_df_getter
        self.version_manager = BOMVersionManager()
        self.current_project_id: Optional[str] = None
        
        self._create_widgets()
        self._refresh_projects()
    
    def _create_widgets(self):
        # 상단: 프로젝트 선택
        project_frame = ttk.LabelFrame(self, text="프로젝트", padding=5)
        project_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(project_frame, text="프로젝트:").pack(side='left', padx=5)
        
        self.project_combo = ttk.Combobox(project_frame, state='readonly', width=40)
        self.project_combo.pack(side='left', padx=5)
        self.project_combo.bind('<<ComboboxSelected>>', self._on_project_selected)
        
        ttk.Button(project_frame, text="새 프로젝트", command=self._create_project, width=12).pack(side='left', padx=5)
        ttk.Button(project_frame, text="삭제", command=self._delete_project, width=8).pack(side='left', padx=5)
        ttk.Button(project_frame, text="새로고침", command=self._refresh_projects, width=10).pack(side='right', padx=5)
        
        # 중앙: 분할 창
        paned = ttk.PanedWindow(self, orient='horizontal')
        paned.pack(fill='both', expand=True, pady=(0, 10))
        
        # 왼쪽: 버전 목록
        version_frame = ttk.LabelFrame(paned, text="버전 목록", padding=5)
        paned.add(version_frame, weight=1)
        
        # 버전 트리뷰
        columns = ('version', 'date', 'items', 'smd', 'dip')
        self.version_tree = ttk.Treeview(version_frame, columns=columns, show='headings', height=10)
        
        self.version_tree.heading('version', text='버전')
        self.version_tree.heading('date', text='생성일')
        self.version_tree.heading('items', text='항목수')
        self.version_tree.heading('smd', text='SMD')
        self.version_tree.heading('dip', text='DIP')
        
        self.version_tree.column('version', width=100)
        self.version_tree.column('date', width=140)
        self.version_tree.column('items', width=60)
        self.version_tree.column('smd', width=50)
        self.version_tree.column('dip', width=50)
        
        vsb = ttk.Scrollbar(version_frame, orient="vertical", command=self.version_tree.yview)
        self.version_tree.configure(yscrollcommand=vsb.set)
        
        self.version_tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        
        self.version_tree.bind('<<TreeviewSelect>>', self._on_version_selected)
        
        # 버전 버튼
        ver_btn_frame = ttk.Frame(version_frame)
        ver_btn_frame.pack(fill='x', pady=5)
        
        ttk.Button(ver_btn_frame, text="현재 BOM 저장", command=self._save_current_bom, width=14).pack(side='left', padx=2)
        ttk.Button(ver_btn_frame, text="파일에서 추가", command=self._add_from_file, width=14).pack(side='left', padx=2)
        ttk.Button(ver_btn_frame, text="삭제", command=self._delete_version, width=8).pack(side='left', padx=2)
        
        # 오른쪽: 비교 결과
        compare_frame = ttk.LabelFrame(paned, text="버전 비교", padding=5)
        paned.add(compare_frame, weight=1)
        
        # 비교 대상 선택
        compare_select_frame = ttk.Frame(compare_frame)
        compare_select_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Label(compare_select_frame, text="이전:").pack(side='left', padx=2)
        self.old_version_combo = ttk.Combobox(compare_select_frame, state='readonly', width=15)
        self.old_version_combo.pack(side='left', padx=2)
        
        ttk.Label(compare_select_frame, text="새:").pack(side='left', padx=2)
        self.new_version_combo = ttk.Combobox(compare_select_frame, state='readonly', width=15)
        self.new_version_combo.pack(side='left', padx=2)
        
        ttk.Button(compare_select_frame, text="비교", command=self._compare_versions, width=8).pack(side='left', padx=5)
        
        # 비교 결과 표시
        self.compare_text = scrolledtext.ScrolledText(compare_frame, width=40, height=15)
        self.compare_text.pack(fill='both', expand=True)
        
        # 하단: 통계
        self.stats_var = tk.StringVar(value="프로젝트를 선택하세요")
        ttk.Label(self, textvariable=self.stats_var, font=('맑은 고딕', 9)).pack(pady=5)
    
    def _refresh_projects(self):
        """프로젝트 목록 새로고침"""
        projects = self.version_manager.get_projects()
        project_names = [f"{p['project_name']} ({p['version_count']}개 버전)" for p in projects]
        self.project_combo['values'] = project_names
        
        self._project_data = {p['project_name']: p for p in projects}
        
        if projects:
            self.project_combo.current(0)
            self._on_project_selected(None)
    
    def _on_project_selected(self, event):
        """프로젝트 선택"""
        selection = self.project_combo.get()
        if not selection:
            return
        
        project_name = selection.split(' (')[0]
        project = self._project_data.get(project_name)
        
        if project:
            self.current_project_id = project['project_id']
            self._refresh_versions()
            self.stats_var.set(f"프로젝트: {project_name} | 버전: {project['version_count']}개")
    
    def _refresh_versions(self):
        """버전 목록 새로고침"""
        self.version_tree.delete(*self.version_tree.get_children())
        
        if not self.current_project_id:
            return
        
        versions = self.version_manager.get_versions(self.current_project_id)
        
        for v in versions:
            date_str = v['created_at'][:10] if v['created_at'] else ''
            self.version_tree.insert('', 'end', iid=v['version_id'], values=(
                v['version_name'],
                date_str,
                v['item_count'],
                v['smd_count'],
                v['dip_count'],
            ))
        
        # 비교 콤보 업데이트
        version_names = [v['version_name'] for v in versions]
        self.old_version_combo['values'] = version_names
        self.new_version_combo['values'] = version_names
        
        self._version_data = {v['version_name']: v for v in versions}
    
    def _on_version_selected(self, event):
        """버전 선택"""
        pass
    
    def _create_project(self):
        """새 프로젝트 생성"""
        dialog = tk.Toplevel(self)
        dialog.title("새 프로젝트")
        dialog.geometry("400x150")
        dialog.transient(self)
        dialog.grab_set()
        
        ttk.Label(dialog, text="프로젝트 이름:").pack(pady=10)
        name_var = tk.StringVar()
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=40)
        name_entry.pack(pady=5)
        name_entry.focus()
        
        ttk.Label(dialog, text="설명:").pack(pady=5)
        desc_var = tk.StringVar()
        desc_entry = ttk.Entry(dialog, textvariable=desc_var, width=40)
        desc_entry.pack(pady=5)
        
        def create():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("오류", "프로젝트 이름을 입력하세요.")
                return
            
            project_id = self.version_manager.create_project(name, desc_var.get())
            if project_id:
                dialog.destroy()
                self._refresh_projects()
                messagebox.showinfo("완료", f"프로젝트 '{name}'이 생성되었습니다.")
            else:
                messagebox.showwarning("오류", "프로젝트 생성에 실패했습니다.")
        
        ttk.Button(dialog, text="생성", command=create).pack(pady=10)
    
    def _delete_project(self):
        """프로젝트 삭제"""
        if not self.current_project_id:
            messagebox.showinfo("알림", "삭제할 프로젝트를 선택하세요.")
            return
        
        if messagebox.askyesno("확인", "프로젝트와 모든 버전을 삭제하시겠습니까?"):
            if self.version_manager.delete_project(self.current_project_id):
                self.current_project_id = None
                self._refresh_projects()
                messagebox.showinfo("완료", "프로젝트가 삭제되었습니다.")
    
    def _save_current_bom(self):
        """현재 BOM을 새 버전으로 저장"""
        if not self.current_project_id:
            messagebox.showinfo("알림", "먼저 프로젝트를 선택하세요.")
            return
        
        if not self.bom_df_getter:
            messagebox.showinfo("알림", "BOM 데이터가 없습니다.")
            return
        
        df = self.bom_df_getter()
        if df is None or df.empty:
            messagebox.showinfo("알림", "저장할 BOM 데이터가 없습니다.\n먼저 BOM 파일을 처리하세요.")
            return
        
        # 버전명 입력 다이얼로그
        dialog = tk.Toplevel(self)
        dialog.title("버전 저장")
        dialog.geometry("350x150")
        dialog.transient(self)
        dialog.grab_set()
        
        ttk.Label(dialog, text="버전명 (예: v1.0, Rev.A):").pack(pady=10)
        ver_var = tk.StringVar(value="v1.0")
        ver_entry = ttk.Entry(dialog, textvariable=ver_var, width=30)
        ver_entry.pack(pady=5)
        ver_entry.focus()
        
        ttk.Label(dialog, text="설명:").pack(pady=5)
        desc_var = tk.StringVar()
        desc_entry = ttk.Entry(dialog, textvariable=desc_var, width=30)
        desc_entry.pack(pady=5)
        
        def save():
            version_name = ver_var.get().strip()
            if not version_name:
                messagebox.showwarning("오류", "버전명을 입력하세요.")
                return
            
            version_id = self.version_manager.save_version_from_df(
                self.current_project_id,
                version_name,
                df,
                desc_var.get()
            )
            
            if version_id:
                dialog.destroy()
                self._refresh_versions()
                messagebox.showinfo("완료", f"버전 '{version_name}'이 저장되었습니다.")
            else:
                messagebox.showwarning("오류", "버전 저장에 실패했습니다.")
        
        ttk.Button(dialog, text="저장", command=save).pack(pady=10)
    
    def _add_from_file(self):
        """파일에서 버전 추가"""
        if not self.current_project_id:
            messagebox.showinfo("알림", "먼저 프로젝트를 선택하세요.")
            return
        
        file_path = filedialog.askopenfilename(
            title="BOM 파일 선택",
            filetypes=[
                ("Excel/CSV", "*.xlsx *.xls *.csv"),
                ("All Files", "*.*")
            ]
        )
        
        if not file_path:
            return
        
        # 간단한 파일 로드
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            
            version_name = Path(file_path).stem
            version_id = self.version_manager.save_version_from_df(
                self.current_project_id,
                version_name,
                df,
                f"파일: {Path(file_path).name}"
            )
            
            if version_id:
                self._refresh_versions()
                messagebox.showinfo("완료", f"버전 '{version_name}'이 추가되었습니다.")
        except Exception as e:
            messagebox.showwarning("오류", f"파일 로드 실패: {e}")
    
    def _delete_version(self):
        """버전 삭제"""
        selected = self.version_tree.selection()
        if not selected:
            messagebox.showinfo("알림", "삭제할 버전을 선택하세요.")
            return
        
        version_id = selected[0]
        
        if messagebox.askyesno("확인", "선택한 버전을 삭제하시겠습니까?"):
            if self.version_manager.delete_version(version_id):
                self._refresh_versions()
                messagebox.showinfo("완료", "버전이 삭제되었습니다.")
    
    def _compare_versions(self):
        """버전 비교"""
        old_name = self.old_version_combo.get()
        new_name = self.new_version_combo.get()
        
        if not old_name or not new_name:
            messagebox.showinfo("알림", "비교할 버전을 선택하세요.")
            return
        
        old_ver = self._version_data.get(old_name)
        new_ver = self._version_data.get(new_name)
        
        if not old_ver or not new_ver:
            return
        
        diff = self.version_manager.compare_versions(old_ver['version_id'], new_ver['version_id'])
        
        if diff:
            self.compare_text.delete('1.0', 'end')
            
            # 요약
            self.compare_text.insert('end', f"=== 버전 비교 결과 ===\n")
            self.compare_text.insert('end', f"이전: {old_name} → 새: {new_name}\n\n")
            self.compare_text.insert('end', f"📊 요약: {diff.get_summary()}\n\n")
            
            # 상세 변경 사항
            if diff.diff_items:
                for item in diff.diff_items:
                    if item.change_type == 'added':
                        self.compare_text.insert('end', f"➕ 추가: {item.key}")
                        if item.new_item:
                            self.compare_text.insert('end', f" ({item.new_item.item_type})\n")
                        else:
                            self.compare_text.insert('end', "\n")
                    elif item.change_type == 'removed':
                        self.compare_text.insert('end', f"➖ 삭제: {item.key}")
                        if item.old_item:
                            self.compare_text.insert('end', f" ({item.old_item.item_type})\n")
                        else:
                            self.compare_text.insert('end', "\n")
                    elif item.change_type == 'modified':
                        self.compare_text.insert('end', f"✏️ 변경: {item.key}\n")
                        self.compare_text.insert('end', f"   변경 필드: {', '.join(item.changed_fields)}\n")
            else:
                self.compare_text.insert('end', "변경 사항 없음\n")


class DFMAnalysisFrame(ttk.Frame):
    """DFM 분석 프레임"""
    
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        
        self.analyzer = DFMAnalyzer()
        self.current_result: Optional[DFMAnalysisResult] = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        # 상단: 파일 입력
        input_frame = ttk.LabelFrame(self, text="입력 파일", padding=10)
        input_frame.pack(fill='x', pady=(0, 10))
        
        # Gerber 파일
        gerber_frame = ttk.Frame(input_frame)
        gerber_frame.pack(fill='x', pady=2)
        
        ttk.Label(gerber_frame, text="Gerber 폴더:").pack(side='left', padx=5)
        self.gerber_path_var = tk.StringVar()
        ttk.Entry(gerber_frame, textvariable=self.gerber_path_var, width=50).pack(side='left', padx=5)
        ttk.Button(gerber_frame, text="찾기...", command=self._browse_gerber).pack(side='left', padx=5)
        
        # P&P 파일
        pnp_frame = ttk.Frame(input_frame)
        pnp_frame.pack(fill='x', pady=2)
        
        ttk.Label(pnp_frame, text="P&P 파일:").pack(side='left', padx=5)
        self.pnp_path_var = tk.StringVar()
        ttk.Entry(pnp_frame, textvariable=self.pnp_path_var, width=50).pack(side='left', padx=5)
        ttk.Button(pnp_frame, text="찾기...", command=self._browse_pnp).pack(side='left', padx=5)
        
        # 분석 버튼
        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(fill='x', pady=5)
        
        ttk.Button(btn_frame, text="DFM 분석 실행", command=self._run_analysis, width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="보고서 저장", command=self._save_report, width=12).pack(side='left', padx=5)
        
        # 중앙: 결과 표시
        result_frame = ttk.LabelFrame(self, text="분석 결과", padding=5)
        result_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        # 요약 패널
        summary_frame = ttk.Frame(result_frame)
        summary_frame.pack(fill='x', pady=5)
        
        self.summary_var = tk.StringVar(value="파일을 선택하고 분석을 실행하세요")
        ttk.Label(summary_frame, textvariable=self.summary_var, font=('맑은 고딕', 10, 'bold')).pack()
        
        # 위반 사항 트리뷰
        columns = ('severity', 'type', 'message', 'components')
        self.violation_tree = ttk.Treeview(result_frame, columns=columns, show='headings', height=10)
        
        self.violation_tree.heading('severity', text='심각도')
        self.violation_tree.heading('type', text='유형')
        self.violation_tree.heading('message', text='메시지')
        self.violation_tree.heading('components', text='관련 부품')
        
        self.violation_tree.column('severity', width=70)
        self.violation_tree.column('type', width=120)
        self.violation_tree.column('message', width=300)
        self.violation_tree.column('components', width=150)
        
        vsb = ttk.Scrollbar(result_frame, orient="vertical", command=self.violation_tree.yview)
        self.violation_tree.configure(yscrollcommand=vsb.set)
        
        self.violation_tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        
        # 태그 색상
        self.violation_tree.tag_configure('critical', background='#FFD0D0')
        self.violation_tree.tag_configure('major', background='#FFE4B3')
        self.violation_tree.tag_configure('minor', background='#FFFFCC')
    
    def _browse_gerber(self):
        """Gerber 폴더 선택"""
        folder = filedialog.askdirectory(title="Gerber 폴더 선택")
        if folder:
            self.gerber_path_var.set(folder)
    
    def _browse_pnp(self):
        """P&P 파일 선택"""
        file_path = filedialog.askopenfilename(
            title="Pick & Place 파일 선택",
            filetypes=[
                ("P&P Files", "*.csv *.txt *.xlsx"),
                ("All Files", "*.*")
            ]
        )
        if file_path:
            self.pnp_path_var.set(file_path)
    
    def _run_analysis(self):
        """DFM 분석 실행"""
        gerber_dir = self.gerber_path_var.get()
        pnp_file = self.pnp_path_var.get()
        
        if not gerber_dir and not pnp_file:
            messagebox.showinfo("알림", "Gerber 폴더 또는 P&P 파일을 선택하세요.")
            return
        
        # 데이터 로드
        self.analyzer = DFMAnalyzer()
        success = self.analyzer.load_project(
            gerber_dir=gerber_dir if gerber_dir else None,
            pnp_file=pnp_file if pnp_file else None
        )
        
        if not success:
            messagebox.showwarning("오류", "파일 로드에 실패했습니다.")
            return
        
        # 분석 실행
        self.current_result = self.analyzer.analyze()
        
        # 결과 표시
        self._display_result(self.current_result)
    
    def _display_result(self, result: DFMAnalysisResult):
        """분석 결과 표시"""
        # 요약
        status = "✅ PASS" if result.pass_status else "❌ FAIL"
        self.summary_var.set(
            f"{status} | 부품: {result.total_components}개 | "
            f"Critical: {result.critical_count} | Major: {result.major_count} | Minor: {result.minor_count}"
        )
        
        # 위반 목록
        self.violation_tree.delete(*self.violation_tree.get_children())
        
        severity_kr = {
            'critical': '심각',
            'major': '주요',
            'minor': '경미',
            'info': '정보'
        }
        
        for v in result.violations:
            tag = v.severity.value
            components = ', '.join(v.affected_components[:5])
            if len(v.affected_components) > 5:
                components += f' +{len(v.affected_components) - 5}'
            
            self.violation_tree.insert('', 'end', values=(
                severity_kr.get(v.severity.value, v.severity.value),
                v.violation_type.value,
                v.message,
                components
            ), tags=(tag,))
    
    def _save_report(self):
        """보고서 저장"""
        if not self.current_result:
            messagebox.showinfo("알림", "먼저 분석을 실행하세요.")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="보고서 저장",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        
        if file_path:
            report = self.analyzer.generate_report(self.current_result, file_path)
            messagebox.showinfo("완료", f"보고서가 저장되었습니다:\n{file_path}")


class FeederSetupFrame(ttk.Frame):
    """피더 설정 프레임"""
    
    def __init__(self, parent, bom_df_getter: Callable = None):
        super().__init__(parent, padding=10)
        
        self.bom_df_getter = bom_df_getter
        self.optimizer: Optional[FeederOptimizer] = None
        self.current_assignment: Optional[FeederAssignment] = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        # 상단: 장비 선택
        machine_frame = ttk.LabelFrame(self, text="장비 설정", padding=10)
        machine_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(machine_frame, text="장비:").pack(side='left', padx=5)
        
        self.machine_combo = ttk.Combobox(machine_frame, state='readonly', width=20, values=[
            "SM411", "SM421", "SM471 Plus", "SM482 Plus"
        ])
        self.machine_combo.current(2)  # SM471 Plus 기본값
        self.machine_combo.pack(side='left', padx=5)
        
        ttk.Label(machine_frame, text="전략:").pack(side='left', padx=15)
        
        self.strategy_combo = ttk.Combobox(machine_frame, state='readonly', width=15, values=[
            "balanced", "front_first", "usage_based"
        ])
        self.strategy_combo.current(0)
        self.strategy_combo.pack(side='left', padx=5)
        
        ToolTip(self.strategy_combo, 
               "balanced: 전면/후면 균형 배치\n"
               "front_first: 전면 우선\n"
               "usage_based: 사용량 많은 부품 중앙 배치")
        
        ttk.Button(machine_frame, text="최적화 실행", command=self._run_optimization, width=12).pack(side='left', padx=20)
        
        # 중앙: 결과
        result_paned = ttk.PanedWindow(self, orient='horizontal')
        result_paned.pack(fill='both', expand=True, pady=(0, 10))
        
        # 전면 뱅크
        front_frame = ttk.LabelFrame(result_paned, text="전면 뱅크 (Front)", padding=5)
        result_paned.add(front_frame, weight=1)
        
        columns = ('slot', 'feeder', 'mpn', 'package', 'count')
        self.front_tree = ttk.Treeview(front_frame, columns=columns, show='headings', height=12)
        
        for col, text, width in [('slot', '슬롯', 50), ('feeder', '피더', 80), 
                                  ('mpn', 'MPN', 150), ('package', '패키지', 80), ('count', '수량', 50)]:
            self.front_tree.heading(col, text=text)
            self.front_tree.column(col, width=width)
        
        vsb1 = ttk.Scrollbar(front_frame, orient="vertical", command=self.front_tree.yview)
        self.front_tree.configure(yscrollcommand=vsb1.set)
        
        self.front_tree.pack(side='left', fill='both', expand=True)
        vsb1.pack(side='right', fill='y')
        
        # 후면 뱅크
        rear_frame = ttk.LabelFrame(result_paned, text="후면 뱅크 (Rear)", padding=5)
        result_paned.add(rear_frame, weight=1)
        
        self.rear_tree = ttk.Treeview(rear_frame, columns=columns, show='headings', height=12)
        
        for col, text, width in [('slot', '슬롯', 50), ('feeder', '피더', 80), 
                                  ('mpn', 'MPN', 150), ('package', '패키지', 80), ('count', '수량', 50)]:
            self.rear_tree.heading(col, text=text)
            self.rear_tree.column(col, width=width)
        
        vsb2 = ttk.Scrollbar(rear_frame, orient="vertical", command=self.rear_tree.yview)
        self.rear_tree.configure(yscrollcommand=vsb2.set)
        
        self.rear_tree.pack(side='left', fill='both', expand=True)
        vsb2.pack(side='right', fill='y')
        
        # 하단: 요약 및 내보내기
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill='x')
        
        self.feeder_stats_var = tk.StringVar(value="BOM을 로드하고 최적화를 실행하세요")
        ttk.Label(bottom_frame, textvariable=self.feeder_stats_var, font=('맑은 고딕', 9)).pack(side='left')
        
        ttk.Button(bottom_frame, text="CSV 내보내기", command=self._export_csv, width=12).pack(side='right', padx=5)
        ttk.Button(bottom_frame, text="텍스트 보기", command=self._show_text_report, width=12).pack(side='right', padx=5)
    
    def _get_machine_type(self) -> MachineType:
        """선택된 장비 유형 반환"""
        machine_map = {
            "SM411": MachineType.SM411,
            "SM421": MachineType.SM421,
            "SM471 Plus": MachineType.SM471_PLUS,
            "SM482 Plus": MachineType.SM482_PLUS,
        }
        return machine_map.get(self.machine_combo.get(), MachineType.SM471_PLUS)
    
    def _run_optimization(self):
        """피더 최적화 실행"""
        if not self.bom_df_getter:
            messagebox.showinfo("알림", "BOM 데이터가 없습니다.")
            return
        
        df = self.bom_df_getter()
        if df is None or df.empty:
            messagebox.showinfo("알림", "BOM 데이터가 없습니다.\n먼저 BOM 파일을 처리하세요.")
            return
        
        # BOM 데이터를 리스트로 변환
        bom_data = df.to_dict('records')
        
        # 최적화기 초기화
        machine_type = self._get_machine_type()
        self.optimizer = FeederOptimizer(machine_type)
        
        # 부품 준비
        components = self.optimizer.prepare_components(bom_data)
        
        if not components:
            messagebox.showinfo("알림", "SMD 부품이 없습니다.")
            return
        
        # 최적화 실행
        strategy = self.strategy_combo.get()
        self.current_assignment = self.optimizer.optimize(components, strategy)
        
        # 결과 표시
        self._display_assignment(self.current_assignment)
    
    def _display_assignment(self, assignment: FeederAssignment):
        """피더 배치 결과 표시"""
        # 전면 트리 갱신
        self.front_tree.delete(*self.front_tree.get_children())
        for slot in self.optimizer.front_bank:
            if slot.component:
                self.front_tree.insert('', 'end', values=(
                    slot.slot_number,
                    slot.feeder_type.value if slot.feeder_type else '',
                    slot.component.mpn[:30],
                    slot.component.package,
                    slot.component.placement_count
                ))
        
        # 후면 트리 갱신
        self.rear_tree.delete(*self.rear_tree.get_children())
        for slot in self.optimizer.rear_bank:
            if slot.component:
                self.rear_tree.insert('', 'end', values=(
                    slot.slot_number,
                    slot.feeder_type.value if slot.feeder_type else '',
                    slot.component.mpn[:30],
                    slot.component.package,
                    slot.component.placement_count
                ))
        
        # 통계
        warnings = f" | ⚠️ {len(assignment.warnings)}개 경고" if assignment.warnings else ""
        self.feeder_stats_var.set(
            f"장비: {assignment.machine} | "
            f"슬롯: {assignment.used_slots}/{assignment.total_slots} ({assignment.slot_utilization*100:.1f}%) | "
            f"점수: {assignment.optimization_score:.1f}/100 | "
            f"예상 시간: {assignment.estimated_cycle_time_sec:.1f}초{warnings}"
        )
    
    def _export_csv(self):
        """CSV 내보내기"""
        if not self.current_assignment or not self.optimizer:
            messagebox.showinfo("알림", "먼저 최적화를 실행하세요.")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="피더 리스트 저장",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        
        if file_path:
            self.optimizer.export_to_csv(self.current_assignment, file_path)
            messagebox.showinfo("완료", f"CSV 파일이 저장되었습니다:\n{file_path}")
    
    def _show_text_report(self):
        """텍스트 보고서 표시"""
        if not self.current_assignment or not self.optimizer:
            messagebox.showinfo("알림", "먼저 최적화를 실행하세요.")
            return
        
        report = self.optimizer.generate_feeder_list(self.current_assignment)
        
        # 새 창에 표시
        dialog = tk.Toplevel(self)
        dialog.title("피더 배치 리스트")
        dialog.geometry("700x500")
        
        text = scrolledtext.ScrolledText(dialog, wrap='none', font=('Consolas', 9))
        text.pack(fill='both', expand=True)
        text.insert('1.0', report)
        text.config(state='disabled')


class PanelizationFrame(ttk.Frame):
    """패널라이제이션 프레임"""
    
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        
        self.panelizer: Optional[Panelizer] = None
        self.current_result: Optional[PanelResult] = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        # 상단: 보드 크기 입력
        board_frame = ttk.LabelFrame(self, text="PCB 크기", padding=10)
        board_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(board_frame, text="가로 (mm):").pack(side='left', padx=5)
        self.board_width_var = tk.StringVar(value="50")
        ttk.Entry(board_frame, textvariable=self.board_width_var, width=10).pack(side='left', padx=5)
        
        ttk.Label(board_frame, text="세로 (mm):").pack(side='left', padx=5)
        self.board_height_var = tk.StringVar(value="40")
        ttk.Entry(board_frame, textvariable=self.board_height_var, width=10).pack(side='left', padx=5)
        
        ttk.Label(board_frame, text="두께 (mm):").pack(side='left', padx=5)
        self.board_thick_var = tk.StringVar(value="1.6")
        ttk.Entry(board_frame, textvariable=self.board_thick_var, width=8).pack(side='left', padx=5)
        
        # 패널 설정
        panel_frame = ttk.LabelFrame(self, text="패널 설정", padding=10)
        panel_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(panel_frame, text="패널 크기:").pack(side='left', padx=5)
        self.panel_size_combo = ttk.Combobox(panel_frame, state='readonly', width=15, values=[
            "250 x 200", "300 x 250", "350 x 250", "400 x 300", 
            "450 x 350", "500 x 400", "600 x 500", "자동"
        ])
        self.panel_size_combo.current(7)  # 자동
        self.panel_size_combo.pack(side='left', padx=5)
        
        ttk.Label(panel_frame, text="분리 방식:").pack(side='left', padx=10)
        self.separation_combo = ttk.Combobox(panel_frame, state='readonly', width=12, values=[
            "V-Cut", "Tab Routing"
        ])
        self.separation_combo.current(0)
        self.separation_combo.pack(side='left', padx=5)
        
        ttk.Button(panel_frame, text="패널 계산", command=self._calculate_panel, width=12).pack(side='left', padx=20)
        
        # 중앙: 결과
        result_frame = ttk.LabelFrame(self, text="패널 결과", padding=10)
        result_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        # 요약
        summary_frame = ttk.Frame(result_frame)
        summary_frame.pack(fill='x', pady=5)
        
        self.panel_summary_var = tk.StringVar(value="보드 크기를 입력하고 패널 계산을 실행하세요")
        ttk.Label(summary_frame, textvariable=self.panel_summary_var, font=('맑은 고딕', 10, 'bold')).pack()
        
        # 결과 텍스트
        self.result_text = scrolledtext.ScrolledText(result_frame, height=15, wrap='word')
        self.result_text.pack(fill='both', expand=True)
        
        # 추천 패널
        recommend_frame = ttk.LabelFrame(result_frame, text="추천 패널 크기", padding=5)
        recommend_frame.pack(fill='x', pady=5)
        
        columns = ('panel', 'boards', 'layout', 'util', 'cost')
        self.recommend_tree = ttk.Treeview(recommend_frame, columns=columns, show='headings', height=4)
        
        self.recommend_tree.heading('panel', text='패널 크기')
        self.recommend_tree.heading('boards', text='보드수')
        self.recommend_tree.heading('layout', text='배열')
        self.recommend_tree.heading('util', text='활용률')
        self.recommend_tree.heading('cost', text='비용인자')
        
        for col, width in [('panel', 100), ('boards', 60), ('layout', 80), ('util', 80), ('cost', 80)]:
            self.recommend_tree.column(col, width=width)
        
        self.recommend_tree.pack(fill='x')
        
        # 하단: 내보내기
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill='x')
        
        ttk.Button(bottom_frame, text="보고서 저장", command=self._save_report, width=12).pack(side='right', padx=5)
        ttk.Button(bottom_frame, text="DXF 내보내기", command=self._export_dxf, width=12).pack(side='right', padx=5)
    
    def _calculate_panel(self):
        """패널 계산"""
        try:
            board_w = float(self.board_width_var.get())
            board_h = float(self.board_height_var.get())
            board_t = float(self.board_thick_var.get())
        except ValueError:
            messagebox.showwarning("오류", "올바른 숫자를 입력하세요.")
            return
        
        if board_w <= 0 or board_h <= 0:
            messagebox.showwarning("오류", "크기는 0보다 커야 합니다.")
            return
        
        board = BoardSize(board_w, board_h, board_t)
        
        # 패널 크기
        panel_str = self.panel_size_combo.get()
        if panel_str == "자동":
            panel_config = None
        else:
            parts = panel_str.split(' x ')
            panel_size = PanelSize(float(parts[0]), float(parts[1]))
            
            # 분리 방식
            from .panelization import SeparationType
            sep = self.separation_combo.get()
            if sep == "V-Cut":
                separation = SeparationType.V_CUT
                spacing = 0
            else:
                separation = SeparationType.TAB_ROUTING
                spacing = 2.0
            
            panel_config = PanelConfig(
                panel_size=panel_size,
                separation=separation,
                board_spacing=spacing
            )
        
        # 패널라이저 생성
        self.panelizer = Panelizer(board, panel_config)
        self.current_result = self.panelizer.panelize()
        
        # 결과 표시
        self._display_result(self.current_result)
        
        # 추천 패널
        recommendations = self.panelizer.optimize_panel_size()
        self._display_recommendations(recommendations)
    
    def _display_result(self, result: PanelResult):
        """결과 표시"""
        self.panel_summary_var.set(result.get_summary())
        
        # 상세 보고서
        report = self.panelizer.generate_report(result)
        self.result_text.delete('1.0', 'end')
        self.result_text.insert('1.0', report)
    
    def _display_recommendations(self, recommendations: List[Dict]):
        """추천 패널 표시"""
        self.recommend_tree.delete(*self.recommend_tree.get_children())
        
        for r in recommendations[:5]:
            self.recommend_tree.insert('', 'end', values=(
                r['panel_size'],
                r['boards'],
                r['layout'],
                f"{r['utilization']*100:.1f}%",
                f"{r['cost_factor']:.3f}"
            ))
    
    def _save_report(self):
        """보고서 저장"""
        if not self.current_result or not self.panelizer:
            messagebox.showinfo("알림", "먼저 패널 계산을 실행하세요.")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="보고서 저장",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        
        if file_path:
            report = self.panelizer.generate_report(self.current_result)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(report)
            messagebox.showinfo("완료", f"보고서가 저장되었습니다:\n{file_path}")
    
    def _export_dxf(self):
        """DXF 내보내기"""
        if not self.current_result or not self.panelizer:
            messagebox.showinfo("알림", "먼저 패널 계산을 실행하세요.")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="DXF 저장",
            defaultextension=".dxf",
            filetypes=[("DXF Files", "*.dxf"), ("All Files", "*.*")]
        )
        
        if file_path:
            if self.panelizer.export_to_dxf(self.current_result, file_path):
                messagebox.showinfo("완료", f"DXF 파일이 저장되었습니다:\n{file_path}")
            else:
                messagebox.showwarning("오류", "DXF 내보내기에 실패했습니다.")
