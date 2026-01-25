#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NPI 프레임 - GUI 확장
Pick & Place 생성, DFM 분석, 프로젝트 관리 GUI
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd

# NPI 모듈 임포트
try:
    from centroid_parser import CentroidParser, match_bom_centroid
    from pnp_generator import SamsungSMGenerator, generate_pnp_files
    from dfm_analyzer import DFMAnalyzer, analyze_dfm, Severity
    from project_manager import ProjectManager, Project, ProcessingResult
    NPI_MODULES_AVAILABLE = True
except ImportError:
    NPI_MODULES_AVAILABLE = False


class NPIFrame(ttk.Frame):
    """NPI 기능 프레임"""
    
    SUPPORTED_MACHINES = ['SM421', 'SM411', 'SM471', 'SM471 PLUS', 'SM482', 'SM482 PLUS']
    
    def __init__(self, parent, get_bom_data_callback):
        """
        Args:
            parent: 부모 위젯
            get_bom_data_callback: BOM 데이터 가져오기 콜백 (DataFrame 반환)
        """
        super().__init__(parent, padding=10)
        self.get_bom_data = get_bom_data_callback
        
        self.centroid_parser: Optional[CentroidParser] = None
        self.merged_df: Optional[pd.DataFrame] = None
        self.dfm_issues = []
        
        self._create_widgets()
    
    def _create_widgets(self):
        if not NPI_MODULES_AVAILABLE:
            ttk.Label(self, text="NPI 모듈이 설치되지 않았습니다.", 
                     foreground='red', font=('맑은 고딕', 12)).pack(pady=50)
            return
        
        # 상단: 파일 섹션
        file_frame = ttk.LabelFrame(self, text="1. 파일 설정", padding=10)
        file_frame.pack(fill='x', pady=(0, 10))
        
        # Centroid 파일
        centroid_frame = ttk.Frame(file_frame)
        centroid_frame.pack(fill='x', pady=2)
        
        ttk.Label(centroid_frame, text="Centroid 파일:", width=15).pack(side='left')
        self.centroid_path_var = tk.StringVar(value="선택하세요...")
        ttk.Entry(centroid_frame, textvariable=self.centroid_path_var, width=50, 
                  state='readonly').pack(side='left', padx=5)
        ttk.Button(centroid_frame, text="찾기...", 
                   command=self._browse_centroid).pack(side='left')
        
        # 장비 선택
        machine_frame = ttk.Frame(file_frame)
        machine_frame.pack(fill='x', pady=2)
        
        ttk.Label(machine_frame, text="SMT 장비:", width=15).pack(side='left')
        self.machine_var = tk.StringVar(value="SM471")
        machine_combo = ttk.Combobox(machine_frame, textvariable=self.machine_var,
                                      values=self.SUPPORTED_MACHINES, width=15, state='readonly')
        machine_combo.pack(side='left', padx=5)
        
        # 출력 포맷 선택
        format_frame = ttk.Frame(file_frame)
        format_frame.pack(fill='x', pady=2)
        
        ttk.Label(format_frame, text="출력 포맷:", width=15).pack(side='left')
        
        self.format_ssa_var = tk.BooleanVar(value=True)
        self.format_csv_var = tk.BooleanVar(value=True)
        self.format_txt_var = tk.BooleanVar(value=True)
        self.format_mounter_var = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(format_frame, text="SSA", variable=self.format_ssa_var).pack(side='left', padx=3)
        ttk.Checkbutton(format_frame, text="CSV", variable=self.format_csv_var).pack(side='left', padx=3)
        ttk.Checkbutton(format_frame, text="TXT", variable=self.format_txt_var).pack(side='left', padx=3)
        ttk.Checkbutton(format_frame, text="Mounter CSV", variable=self.format_mounter_var).pack(side='left', padx=3)
        
        # 출력 폴더
        output_frame = ttk.Frame(file_frame)
        output_frame.pack(fill='x', pady=2)
        
        ttk.Label(output_frame, text="출력 폴더:", width=15).pack(side='left')
        self.output_path_var = tk.StringVar(value="")
        ttk.Entry(output_frame, textvariable=self.output_path_var, width=50).pack(side='left', padx=5)
        ttk.Button(output_frame, text="찾기...", 
                   command=self._browse_output).pack(side='left')
        
        # 중간: 상태 및 액션
        action_frame = ttk.LabelFrame(self, text="2. 작업", padding=10)
        action_frame.pack(fill='x', pady=(0, 10))
        
        btn_row = ttk.Frame(action_frame)
        btn_row.pack(fill='x')
        
        ttk.Button(btn_row, text="데이터 매칭", 
                   command=self._match_data, width=15).pack(side='left', padx=5)
        ttk.Button(btn_row, text="매칭 결과 저장", 
                   command=self._save_matched_data, width=15).pack(side='left', padx=5)
        ttk.Button(btn_row, text="DFM 분석", 
                   command=self._run_dfm, width=15).pack(side='left', padx=5)
        ttk.Button(btn_row, text="P&P 파일 생성", 
                   command=self._generate_pnp, width=15).pack(side='left', padx=5)
        ttk.Button(btn_row, text="전체 실행", 
                   command=self._run_all, width=15).pack(side='left', padx=5)
        
        # 상태 표시
        self.status_var = tk.StringVar(value="준비")
        ttk.Label(action_frame, textvariable=self.status_var, 
                  foreground='blue').pack(pady=5)
        
        # 하단: 결과 노트북
        result_notebook = ttk.Notebook(self)
        result_notebook.pack(fill='both', expand=True)
        
        # 매칭 결과 탭
        match_frame = ttk.Frame(result_notebook, padding=5)
        result_notebook.add(match_frame, text="매칭 결과")
        
        self.match_text = scrolledtext.ScrolledText(match_frame, height=15)
        self.match_text.pack(fill='both', expand=True)
        
        # DFM 결과 탭
        dfm_frame = ttk.Frame(result_notebook, padding=5)
        result_notebook.add(dfm_frame, text="DFM 분석")
        
        self.dfm_text = scrolledtext.ScrolledText(dfm_frame, height=15)
        self.dfm_text.pack(fill='both', expand=True)
        
        # 생성 파일 탭
        files_frame = ttk.Frame(result_notebook, padding=5)
        result_notebook.add(files_frame, text="생성된 파일")
        
        self.files_list = tk.Listbox(files_frame, height=10)
        self.files_list.pack(fill='both', expand=True)
        self.files_list.bind('<Double-1>', self._open_file)
        
        ttk.Label(files_frame, text="더블클릭하여 파일 열기", 
                  foreground='gray').pack()
    
    def _browse_centroid(self):
        """Centroid 파일 선택"""
        file_path = filedialog.askopenfilename(
            title="Centroid (XY 좌표) 파일 선택",
            filetypes=[
                ("Centroid Files", "*.csv *.txt *.pos *.xy *.xlsx"),
                ("CSV Files", "*.csv"),
                ("Text Files", "*.txt *.pos *.xy"),
                ("Excel Files", "*.xlsx"),
                ("All Files", "*.*")
            ]
        )
        
        if file_path:
            self.centroid_path_var.set(file_path)
            self._load_centroid(file_path)
    
    def _browse_output(self):
        """출력 폴더 선택"""
        folder = filedialog.askdirectory(title="출력 폴더 선택")
        if folder:
            self.output_path_var.set(folder)
    
    def _load_centroid(self, file_path: str):
        """Centroid 파일 로드"""
        self.status_var.set("Centroid 파일 로드 중...")
        self.update_idletasks()
        
        self.centroid_parser = CentroidParser()
        success, msg = self.centroid_parser.load_file(file_path)
        
        if success:
            summary = self.centroid_parser.get_summary()
            self.status_var.set(f"Centroid 로드 완료: {summary['total']}개 부품")
            
            self.match_text.delete('1.0', 'end')
            self.match_text.insert('end', f"Centroid 파일 로드 완료\n")
            self.match_text.insert('end', f"- 총 부품: {summary['total']}개\n")
            self.match_text.insert('end', f"- Top: {summary['top_count']}개\n")
            self.match_text.insert('end', f"- Bottom: {summary['bottom_count']}개\n")
            self.match_text.insert('end', f"- 단위: {summary['unit']}\n")
        else:
            self.status_var.set(f"로드 실패: {msg}")
            messagebox.showwarning("오류", msg)
    
    def _match_data(self):
        """BOM과 Centroid 데이터 매칭"""
        bom_df = self.get_bom_data()
        
        if bom_df is None or bom_df.empty:
            messagebox.showwarning("오류", "BOM 데이터가 없습니다. 먼저 BOM을 처리해주세요.")
            return
        
        if self.centroid_parser is None:
            messagebox.showwarning("오류", "Centroid 파일을 로드해주세요.")
            return
        
        self.status_var.set("데이터 매칭 중...")
        self.update_idletasks()
        
        try:
            self.merged_df, stats = match_bom_centroid(bom_df, self.centroid_parser)
            
            self.match_text.delete('1.0', 'end')
            self.match_text.insert('end', "=== BOM + Centroid 매칭 결과 ===\n\n")
            self.match_text.insert('end', f"BOM 항목: {stats['bom_total']}개\n")
            self.match_text.insert('end', f"Centroid 항목: {stats['centroid_total']}개\n")
            self.match_text.insert('end', f"매칭됨: {stats['matched']}개\n\n")
            
            if stats['bom_only']:
                self.match_text.insert('end', f"BOM에만 있음 ({len(stats['bom_only'])}개):\n")
                self.match_text.insert('end', f"  {', '.join(stats['bom_only'][:20])}")
                if len(stats['bom_only']) > 20:
                    self.match_text.insert('end', f"... (+{len(stats['bom_only'])-20}개)")
                self.match_text.insert('end', "\n\n")
            
            if stats['centroid_only']:
                self.match_text.insert('end', f"Centroid에만 있음 ({len(stats['centroid_only'])}개):\n")
                self.match_text.insert('end', f"  {', '.join(stats['centroid_only'][:20])}")
                if len(stats['centroid_only']) > 20:
                    self.match_text.insert('end', f"... (+{len(stats['centroid_only'])-20}개)")
                self.match_text.insert('end', "\n")
            
            self.status_var.set(f"매칭 완료: {stats['matched']}개 항목")
            
        except Exception as e:
            self.status_var.set(f"매칭 오류: {str(e)}")
            messagebox.showerror("오류", f"데이터 매칭 실패: {str(e)}")
    
    def _save_matched_data(self):
        """매칭된 BOM+Centroid 데이터를 파일로 저장"""
        if self.merged_df is None or self.merged_df.empty:
            messagebox.showwarning("오류", 
                "저장할 매칭 데이터가 없습니다.\n"
                "먼저 '데이터 매칭'을 실행해주세요.")
            return
        
        # 저장 파일 경로 선택
        file_path = filedialog.asksaveasfilename(
            title="매칭 결과 저장",
            defaultextension=".xlsx",
            filetypes=[
                ("Excel Files", "*.xlsx"),
                ("CSV Files", "*.csv"),
                ("All Files", "*.*")
            ],
            initialfile="BOM_Centroid_Matched"
        )
        
        if not file_path:
            return
        
        try:
            self.status_var.set("매칭 결과 저장 중...")
            self.update_idletasks()
            
            if file_path.endswith('.csv'):
                self.merged_df.to_csv(file_path, index=False, encoding='utf-8-sig')
            else:
                self.merged_df.to_excel(file_path, index=False, engine='openpyxl')
            
            self.status_var.set(f"저장 완료: {Path(file_path).name}")
            
            # 생성된 파일 목록에 추가
            self.files_list.insert('end', file_path)
            
            messagebox.showinfo("완료", f"매칭 결과가 저장되었습니다:\n{file_path}")
            
        except Exception as e:
            self.status_var.set(f"저장 오류: {str(e)}")
            messagebox.showerror("오류", f"파일 저장 실패: {str(e)}")
    
    def _run_dfm(self):
        """DFM 분석 실행"""
        if self.merged_df is None:
            # 매칭 안됐으면 BOM만으로 분석
            bom_df = self.get_bom_data()
            if bom_df is None or bom_df.empty:
                messagebox.showwarning("오류", "분석할 데이터가 없습니다.")
                return
            df_to_analyze = bom_df
        else:
            df_to_analyze = self.merged_df
        
        self.status_var.set("DFM 분석 중...")
        self.update_idletasks()
        
        try:
            issues, summary, report = analyze_dfm(df_to_analyze)
            self.dfm_issues = issues
            
            self.dfm_text.delete('1.0', 'end')
            self.dfm_text.insert('end', report)
            
            # 심각도별 색상 태깅 (간략화)
            critical_count = summary['by_severity'].get('치명', 0)
            error_count = summary['by_severity'].get('오류', 0)
            warning_count = summary['by_severity'].get('주의', 0)
            
            status_msg = f"DFM 완료: {summary['total_issues']}개 이슈"
            if critical_count > 0:
                status_msg += f" (치명: {critical_count})"
            self.status_var.set(status_msg)
            
        except Exception as e:
            self.status_var.set(f"DFM 오류: {str(e)}")
            messagebox.showerror("오류", f"DFM 분석 실패: {str(e)}")
    
    def _generate_pnp(self):
        """Pick & Place 파일 생성"""
        if self.merged_df is None:
            # 좌표 없이 BOM만으로는 생성 불가
            messagebox.showwarning("오류", 
                "Centroid 데이터가 필요합니다.\n"
                "Centroid 파일을 로드하고 '데이터 매칭'을 먼저 실행해주세요.")
            return
        
        output_dir = self.output_path_var.get()
        if not output_dir:
            # 기본 출력 폴더: 사용자 문서
            output_dir = str(Path.home() / "Documents" / "PnP_Output")
        
        machine = self.machine_var.get().replace(' ', '')
        
        self.status_var.set("P&P 파일 생성 중...")
        self.update_idletasks()
        
        try:
            # 선택된 출력 포맷 수집
            output_formats = []
            if self.format_ssa_var.get():
                output_formats.append('ssa')
            if self.format_csv_var.get():
                output_formats.append('csv')
            if self.format_txt_var.get():
                output_formats.append('txt')
            if self.format_mounter_var.get():
                output_formats.append('mounter')
            
            if not output_formats:
                output_formats = ['ssa', 'csv', 'txt']  # 기본값
            
            success, msg, files = generate_pnp_files(
                self.merged_df, 
                output_dir,
                board_name="PCB",
                machine_type=machine,
                output_formats=output_formats
            )
            
            self.files_list.delete(0, 'end')
            for f in files:
                self.files_list.insert('end', f)
            
            if success:
                self.status_var.set(f"P&P 생성 완료: {len(files)}개 파일")
                messagebox.showinfo("완료", msg)
            else:
                self.status_var.set(f"생성 실패: {msg}")
                messagebox.showwarning("오류", msg)
                
        except Exception as e:
            self.status_var.set(f"생성 오류: {str(e)}")
            messagebox.showerror("오류", f"P&P 생성 실패: {str(e)}")
    
    def _run_all(self):
        """전체 프로세스 실행"""
        # 1. 데이터 매칭 (Centroid 있는 경우)
        if self.centroid_parser is not None:
            self._match_data()
        
        # 2. DFM 분석
        self._run_dfm()
        
        # 3. P&P 생성 (좌표 있는 경우)
        if self.merged_df is not None:
            self._generate_pnp()
    
    def _open_file(self, event):
        """생성된 파일 열기"""
        selection = self.files_list.curselection()
        if not selection:
            return
        
        file_path = self.files_list.get(selection[0])
        
        try:
            import subprocess
            import platform
            
            if platform.system() == 'Windows':
                os.startfile(file_path)
            elif platform.system() == 'Darwin':
                subprocess.run(['open', file_path])
            else:
                subprocess.run(['xdg-open', file_path])
        except Exception as e:
            messagebox.showerror("오류", f"파일 열기 실패: {e}")


def add_npi_tab(notebook: ttk.Notebook, get_bom_data_callback) -> None:
    """
    기존 노트북에 NPI 탭 추가
    
    Args:
        notebook: ttk.Notebook 인스턴스
        get_bom_data_callback: BOM 데이터 반환 콜백 함수
    """
    if not NPI_MODULES_AVAILABLE:
        return
    
    npi_frame = NPIFrame(notebook, get_bom_data_callback)
    notebook.add(npi_frame, text="NPI / P&P")
