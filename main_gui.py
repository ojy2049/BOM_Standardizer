#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOM 정규화 도구 - GUI 메인 애플리케이션
tkinter 기반 GUI (Python 표준 라이브러리, 크로스 플랫폼)
"""

import sys
import os
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import pandas as pd

from config import load_config, save_config, COLUMN_MAP_CANDIDATES, STANDARD_OUTPUT_COLUMNS
from bom_parser import BOMParser
from api_resolver import PartResolver, PartInfo
from excel_writer import ExcelWriter


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
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                        background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                        font=("맑은 고딕", 9))
        label.pack()
    
    def hide(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class ColumnMappingFrame(ttk.LabelFrame):
    """컬럼 매핑 프레임"""
    
    STANDARD_KEYS = [
        ('no', '번호(NO)'),
        ('규격', '규격/부품종류'),
        ('스펙', '스펙/설명'),
        ('수량', '수량'),
        ('위치', '위치/RefDes'),
        ('mpn', '제조사 P/N'),
        ('manufacturer', '제조사'),
        ('digi_pn', 'Digi-Key P/N'),
        ('mouser_pn', 'Mouser P/N'),
        ('package', '패키지'),
    ]
    
    def __init__(self, parent):
        super().__init__(parent, text="컬럼 매핑 (자동 감지됨, 필요시 수정)", padding=10)
        self.combos: Dict[str, ttk.Combobox] = {}
        self._create_widgets()
    
    def _create_widgets(self):
        # 2열 레이아웃
        for idx, (key, label) in enumerate(self.STANDARD_KEYS):
            row = idx // 2
            col = (idx % 2) * 2
            
            ttk.Label(self, text=f"{label}:").grid(row=row, column=col, sticky='e', padx=5, pady=3)
            
            combo = ttk.Combobox(self, state='readonly', width=25)
            combo.grid(row=row, column=col+1, sticky='w', padx=5, pady=3)
            self.combos[key] = combo
    
    def set_columns(self, columns: list, auto_mapping: dict):
        """원본 컬럼 목록 및 자동 매핑 설정"""
        values = ["(자동/없음)"] + list(columns)
        
        for key, combo in self.combos.items():
            combo['values'] = values
            
            if key in auto_mapping:
                try:
                    idx = values.index(auto_mapping[key])
                    combo.current(idx)
                except ValueError:
                    combo.current(0)
            else:
                combo.current(0)
    
    def get_mapping(self) -> dict:
        """현재 매핑 반환"""
        mapping = {}
        for key, combo in self.combos.items():
            value = combo.get()
            if value and value != "(자동/없음)":
                mapping[key] = value
        return mapping


class SettingsFrame(ttk.Frame):
    """설정 프레임"""
    
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.config = load_config()
        self._create_widgets()
        self._load_settings()
    
    def _create_widgets(self):
        # Digi-Key 설정
        dk_frame = ttk.LabelFrame(self, text="Digi-Key API", padding=10)
        dk_frame.pack(fill='x', pady=5)
        
        ttk.Label(dk_frame, text="Client ID:").grid(row=0, column=0, sticky='e', padx=5, pady=3)
        self.dk_client_id = ttk.Entry(dk_frame, width=50)
        self.dk_client_id.grid(row=0, column=1, sticky='w', padx=5, pady=3)
        
        ttk.Label(dk_frame, text="Client Secret:").grid(row=1, column=0, sticky='e', padx=5, pady=3)
        self.dk_client_secret = ttk.Entry(dk_frame, width=50, show='*')
        self.dk_client_secret.grid(row=1, column=1, sticky='w', padx=5, pady=3)
        
        # Mouser 설정
        ms_frame = ttk.LabelFrame(self, text="Mouser API", padding=10)
        ms_frame.pack(fill='x', pady=5)
        
        ttk.Label(ms_frame, text="API Key:").grid(row=0, column=0, sticky='e', padx=5, pady=3)
        self.ms_api_key = ttk.Entry(ms_frame, width=50, show='*')
        self.ms_api_key.grid(row=0, column=1, sticky='w', padx=5, pady=3)
        
        # 일반 설정
        gen_frame = ttk.LabelFrame(self, text="일반 설정", padding=10)
        gen_frame.pack(fill='x', pady=5)
        
        self.use_cache_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(gen_frame, text="캐시 사용", variable=self.use_cache_var).grid(
            row=0, column=0, columnspan=2, sticky='w', pady=3)
        
        ttk.Label(gen_frame, text="캐시 유효기간(일):").grid(row=1, column=0, sticky='e', padx=5, pady=3)
        self.cache_ttl = ttk.Spinbox(gen_frame, from_=1, to=365, width=10)
        self.cache_ttl.grid(row=1, column=1, sticky='w', padx=5, pady=3)
        
        ttk.Label(gen_frame, text="API 호출 간격(초):").grid(row=2, column=0, sticky='e', padx=5, pady=3)
        self.api_delay = ttk.Spinbox(gen_frame, from_=0.1, to=5.0, increment=0.1, width=10)
        self.api_delay.grid(row=2, column=1, sticky='w', padx=5, pady=3)
        
        # 저장 버튼
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill='x', pady=10)
        
        ttk.Button(btn_frame, text="설정 저장", command=self._save_settings).pack(side='right')
    
    def _load_settings(self):
        """설정 로드"""
        self.dk_client_id.delete(0, tk.END)
        self.dk_client_id.insert(0, self.config.get('digikey_client_id', ''))
        
        self.dk_client_secret.delete(0, tk.END)
        self.dk_client_secret.insert(0, self.config.get('digikey_client_secret', ''))
        
        self.ms_api_key.delete(0, tk.END)
        self.ms_api_key.insert(0, self.config.get('mouser_api_key', ''))
        
        self.use_cache_var.set(self.config.get('use_cache', True))
        
        self.cache_ttl.delete(0, tk.END)
        self.cache_ttl.insert(0, str(self.config.get('cache_ttl_days', 30)))
        
        self.api_delay.delete(0, tk.END)
        self.api_delay.insert(0, str(self.config.get('api_call_delay', 0.5)))
    
    def _save_settings(self):
        """설정 저장"""
        self.config['digikey_client_id'] = self.dk_client_id.get()
        self.config['digikey_client_secret'] = self.dk_client_secret.get()
        self.config['mouser_api_key'] = self.ms_api_key.get()
        self.config['use_cache'] = self.use_cache_var.get()
        
        try:
            self.config['cache_ttl_days'] = int(self.cache_ttl.get())
        except ValueError:
            self.config['cache_ttl_days'] = 30
        
        try:
            self.config['api_call_delay'] = float(self.api_delay.get())
        except ValueError:
            self.config['api_call_delay'] = 0.5
        
        if save_config(self.config):
            messagebox.showinfo("설정", "설정이 저장되었습니다.")
        else:
            messagebox.showwarning("설정", "설정 저장에 실패했습니다.")
    
    def get_config(self) -> dict:
        """현재 설정 반환"""
        try:
            cache_ttl = int(self.cache_ttl.get())
        except ValueError:
            cache_ttl = 30
        
        try:
            api_delay = float(self.api_delay.get())
        except ValueError:
            api_delay = 0.5
        
        return {
            'digikey_client_id': self.dk_client_id.get(),
            'digikey_client_secret': self.dk_client_secret.get(),
            'mouser_api_key': self.ms_api_key.get(),
            'use_cache': self.use_cache_var.get(),
            'cache_ttl_days': cache_ttl,
            'api_call_delay': api_delay,
        }


class DataTableFrame(ttk.Frame):
    """데이터 테이블 프레임"""
    
    def __init__(self, parent, title="데이터"):
        super().__init__(parent)
        self.title = title
        self._create_widgets()
    
    def _create_widgets(self):
        # 테이블
        self.tree = ttk.Treeview(self, show='headings')
        
        # 스크롤바
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # 그리드 배치
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
    
    def display_dataframe(self, df: pd.DataFrame):
        """데이터프레임 표시"""
        # 기존 데이터 삭제
        self.tree.delete(*self.tree.get_children())
        
        if df.empty:
            self.tree['columns'] = []
            return
        
        # 컬럼 설정
        columns = list(df.columns)
        self.tree['columns'] = columns
        
        for col in columns:
            self.tree.heading(col, text=col)
            # 컬럼 너비 설정
            width = max(80, min(200, len(str(col)) * 12))
            self.tree.column(col, width=width, minwidth=50)
        
        # 데이터 추가
        for idx, row in df.iterrows():
            values = [str(v) if pd.notna(v) else "" for v in row]
            item_id = self.tree.insert('', 'end', values=values)
            
            # 장착방식 컬럼에 따른 색상 태그
            if '장착방식' in df.columns:
                mounting = row.get('장착방식', '')
                if mounting == 'SMD':
                    self.tree.item(item_id, tags=('smd',))
                elif mounting == 'DIP':
                    self.tree.item(item_id, tags=('dip',))
                elif mounting == '미확정':
                    self.tree.item(item_id, tags=('unknown',))
        
        # 태그 색상 설정
        self.tree.tag_configure('smd', background='#E2EFDA')
        self.tree.tag_configure('dip', background='#FCE4D6')
        self.tree.tag_configure('unknown', background='#FFF2CC')


class ProcessWorker:
    """백그라운드 처리 워커"""
    
    def __init__(self, parser: BOMParser, config: Dict[str, Any],
                 progress_callback: Callable, finished_callback: Callable):
        self.parser = parser
        self.config = config
        self.progress_callback = progress_callback
        self.finished_callback = finished_callback
        self._stop = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self):
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def stop(self):
        self._stop = True
    
    def _run(self):
        try:
            # 정규화
            self.progress_callback(5, "데이터 정규화 중...")
            success, msg = self.parser.normalize()
            if not success:
                self.finished_callback(False, msg, None)
                return
            
            df = self.parser.get_normalized_data()
            total_rows = len(df)
            
            if total_rows == 0:
                self.finished_callback(False, "처리할 데이터가 없습니다.", None)
                return
            
            # 공급사 조회 초기화
            self.progress_callback(10, "공급사 API 초기화...")
            resolver = PartResolver(self.config)
            
            api_status = resolver.get_api_status()
            if not any(api_status.values()):
                self.progress_callback(15, "API 미설정 - 휴리스틱 분류만 수행")
            else:
                apis = [k for k, v in api_status.items() if v]
                self.progress_callback(15, f"API 연결: {', '.join(apis)}")
            
            # 각 행 처리
            results = []
            for idx, row in df.iterrows():
                if self._stop:
                    self.finished_callback(False, "사용자에 의해 중단됨", None)
                    return
                
                progress = 15 + int((idx + 1) / total_rows * 80)
                self.progress_callback(progress, f"처리 중: {idx + 1}/{total_rows}")
                
                # 부품 정보 조회
                info = resolver.resolve(
                    mpn=str(row.get('mpn', '')),
                    digi_pn=str(row.get('digi_pn', '')),
                    mouser_pn=str(row.get('mouser_pn', '')),
                    spec=str(row.get('스펙', '')),
                    package=str(row.get('package', '')),
                )
                
                results.append({
                    'NO': row['NO'],
                    '규격': row['규격'],
                    '스펙': row['스펙'],
                    '수량': row['수량'],
                    '위치': row['위치'],
                    '장착방식': info.mounting_type,
                    '공식부품명': info.official_name,
                    '공급사': info.supplier,
                    '공급사부품번호': info.supplier_pn,
                    '데이터시트URL': info.datasheet_url,
                })
            
            result_df = pd.DataFrame(results)
            self.progress_callback(100, "처리 완료")
            self.finished_callback(True, f"처리 완료: {len(result_df)}개 항목", result_df)
            
        except Exception as e:
            self.finished_callback(False, f"처리 오류: {str(e)}", None)


class MainApplication(tk.Tk):
    """메인 애플리케이션"""
    
    def __init__(self):
        super().__init__()
        
        self.parser: Optional[BOMParser] = None
        self.result_df: Optional[pd.DataFrame] = None
        self.worker: Optional[ProcessWorker] = None
        
        self._init_ui()
    
    def _init_ui(self):
        self.title("BOM 정규화 도구 v1.0")
        self.geometry("1200x800")
        
        # 스타일 설정
        style = ttk.Style()
        style.theme_use('clam')
        
        # 메인 프레임
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill='both', expand=True)
        
        # 상단: 파일 선택
        file_frame = ttk.LabelFrame(main_frame, text="1. 입력 파일 선택", padding=10)
        file_frame.pack(fill='x', pady=(0, 10))
        
        self.file_path_var = tk.StringVar(value="파일을 선택하세요")
        ttk.Label(file_frame, textvariable=self.file_path_var, foreground='gray').pack(side='left', fill='x', expand=True)
        
        self.browse_btn = ttk.Button(file_frame, text="파일 찾기...", command=self._browse_file)
        self.browse_btn.pack(side='right')
        
        # 탭 노트북
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill='both', expand=True, pady=(0, 10))
        
        # 탭 1: 미리보기 & 매핑
        preview_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(preview_frame, text="데이터 & 매핑")
        
        # 미리보기 테이블
        preview_label_frame = ttk.LabelFrame(preview_frame, text="2. 데이터 미리보기 (상위 10행)", padding=5)
        preview_label_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        self.preview_table = DataTableFrame(preview_label_frame)
        self.preview_table.pack(fill='both', expand=True)
        
        # 컬럼 매핑
        self.mapping_frame = ColumnMappingFrame(preview_frame)
        self.mapping_frame.pack(fill='x')
        
        # 탭 2: 결과
        result_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(result_frame, text="결과")
        
        result_label_frame = ttk.LabelFrame(result_frame, text="처리 결과", padding=5)
        result_label_frame.pack(fill='both', expand=True)
        
        self.result_table = DataTableFrame(result_label_frame)
        self.result_table.pack(fill='both', expand=True)
        
        # 통계 레이블
        self.stats_var = tk.StringVar(value="")
        ttk.Label(result_label_frame, textvariable=self.stats_var, font=('맑은 고딕', 10, 'bold')).pack(pady=5)
        
        # 탭 3: 설정
        self.settings_frame = SettingsFrame(self.notebook)
        self.notebook.add(self.settings_frame, text="설정")
        
        # 하단: 진행률 & 버튼
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill='x')
        
        # 진행률
        progress_frame = ttk.Frame(bottom_frame)
        progress_frame.pack(fill='x', pady=(0, 10))
        
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side='left', fill='x', expand=True, padx=(0, 10))
        
        self.progress_label_var = tk.StringVar(value="준비")
        ttk.Label(progress_frame, textvariable=self.progress_label_var, width=30).pack(side='right')
        
        # 버튼
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(fill='x')
        
        self.save_btn = ttk.Button(btn_frame, text="엑셀 저장", command=self._save_excel, state='disabled')
        self.save_btn.pack(side='right', padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="중단", command=self._stop_process, state='disabled')
        self.stop_btn.pack(side='right', padx=5)
        
        self.process_btn = ttk.Button(btn_frame, text="처리 시작", command=self._start_process, state='disabled')
        self.process_btn.pack(side='right', padx=5)
    
    def _browse_file(self):
        """파일 선택 다이얼로그"""
        config = load_config()
        start_dir = config.get('last_input_dir', '')
        
        file_path = filedialog.askopenfilename(
            title="BOM 파일 선택",
            initialdir=start_dir if start_dir else None,
            filetypes=[
                ("BOM Files", "*.csv *.xlsx *.xls *.xlsm"),
                ("CSV Files", "*.csv"),
                ("Excel Files", "*.xlsx *.xls *.xlsm"),
                ("All Files", "*.*")
            ]
        )
        
        if file_path:
            self._load_file(file_path)
            
            # 마지막 디렉토리 저장
            config['last_input_dir'] = str(Path(file_path).parent)
            save_config(config)
    
    def _load_file(self, file_path: str):
        """파일 로드 및 미리보기"""
        self.parser = BOMParser()
        success, msg = self.parser.load_file(file_path)
        
        if not success:
            messagebox.showwarning("오류", msg)
            return
        
        self.file_path_var.set(file_path)
        self.progress_label_var.set(msg)
        
        # 미리보기 표시
        preview_df = self.parser.get_preview(10)
        self.preview_table.display_dataframe(preview_df)
        
        # 자동 매핑 감지
        auto_mapping = self.parser.auto_detect_mapping()
        columns = self.parser.get_columns()
        self.mapping_frame.set_columns(columns, auto_mapping)
        
        self.process_btn.config(state='normal')
        self.save_btn.config(state='disabled')
        self.result_df = None
        
        # 미리보기 탭으로 이동
        self.notebook.select(0)
    
    def _start_process(self):
        """처리 시작"""
        if not self.parser:
            return
        
        # 매핑 적용
        mapping = self.mapping_frame.get_mapping()
        if mapping:
            self.parser.set_mapping(mapping)
        
        # 설정 가져오기
        config = self.settings_frame.get_config()
        
        # UI 상태 변경
        self.process_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.save_btn.config(state='disabled')
        self.browse_btn.config(state='disabled')
        
        # 워커 시작
        self.worker = ProcessWorker(
            self.parser, config,
            self._on_progress,
            self._on_finished
        )
        self.worker.start()
    
    def _stop_process(self):
        """처리 중단"""
        if self.worker:
            self.worker.stop()
            self.stop_btn.config(state='disabled')
    
    def _on_progress(self, value: int, message: str):
        """진행률 업데이트 (스레드 안전)"""
        self.after(0, lambda: self._update_progress(value, message))
    
    def _update_progress(self, value: int, message: str):
        """실제 진행률 업데이트"""
        self.progress_var.set(value)
        self.progress_label_var.set(message)
    
    def _on_finished(self, success: bool, message: str, result_df):
        """처리 완료 (스레드 안전)"""
        self.after(0, lambda: self._handle_finished(success, message, result_df))
    
    def _handle_finished(self, success: bool, message: str, result_df):
        """실제 완료 처리"""
        self.process_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.browse_btn.config(state='normal')
        
        if success and result_df is not None:
            self.result_df = result_df
            self.result_table.display_dataframe(result_df)
            self.save_btn.config(state='normal')
            
            # 통계 표시
            stats = self._get_statistics(result_df)
            self.stats_var.set(
                f"총 {stats['total']}개  |  "
                f"SMD: {stats['smd']}개  |  "
                f"DIP: {stats['dip']}개  |  "
                f"미확정: {stats['unknown']}개"
            )
            
            # 결과 탭으로 이동
            self.notebook.select(1)
            
            messagebox.showinfo("완료", message)
        else:
            messagebox.showwarning("오류", message)
        
        self.progress_label_var.set(message)
    
    def _get_statistics(self, df: pd.DataFrame) -> dict:
        """통계 계산"""
        stats = {'total': len(df), 'smd': 0, 'dip': 0, 'unknown': 0}
        if '장착방식' in df.columns:
            stats['smd'] = len(df[df['장착방식'] == 'SMD'])
            stats['dip'] = len(df[df['장착방식'] == 'DIP'])
            stats['unknown'] = len(df[df['장착방식'] == '미확정'])
        return stats
    
    def _save_excel(self):
        """엑셀 저장"""
        if self.result_df is None:
            return
        
        config = load_config()
        start_dir = config.get('last_output_dir', '')
        
        # 기본 파일명 생성
        if self.parser and self.parser.file_path:
            default_name = Path(self.parser.file_path).stem + "_표준BOM.xlsx"
        else:
            default_name = "BOM_standardized.xlsx"
        
        file_path = filedialog.asksaveasfilename(
            title="엑셀 저장",
            initialdir=start_dir if start_dir else None,
            initialfile=default_name,
            defaultextension=".xlsx",
            filetypes=[
                ("Excel Files", "*.xlsx"),
                ("All Files", "*.*")
            ]
        )
        
        if file_path:
            writer = ExcelWriter()
            writer.prepare_data(self.result_df)
            success, msg = writer.write(file_path)
            
            if success:
                config['last_output_dir'] = str(Path(file_path).parent)
                save_config(config)
                
                # 파일 열기 제안
                result = messagebox.askyesno(
                    "저장 완료",
                    f"{msg}\n\n파일을 열어보시겠습니까?"
                )
                
                if result:
                    import subprocess
                    import platform
                    
                    try:
                        if platform.system() == 'Windows':
                            os.startfile(file_path)
                        elif platform.system() == 'Darwin':  # macOS
                            subprocess.run(['open', file_path])
                        else:  # Linux
                            subprocess.run(['xdg-open', file_path])
                    except Exception as e:
                        messagebox.showinfo("알림", f"파일 열기 실패: {e}\n\n파일 경로: {file_path}")
            else:
                messagebox.showwarning("저장 실패", msg)


def main():
    app = MainApplication()
    app.mainloop()


if __name__ == "__main__":
    main()
