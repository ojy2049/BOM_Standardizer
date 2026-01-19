#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
부품 라이브러리 GUI 프레임
- 부품 DB 관리
- AVL 관리
- 위험도 분석
- 웹 검색을 통한 부품 정보 수집
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional, Dict, Any, List, Callable
import pandas as pd
import threading
import json

try:
    from parts_library import (
        PartsLibrary, PartLibraryEntry, AVLEntry, RiskAssessment,
        get_parts_library, RiskLevel, LifecycleStatus
    )
    PARTS_LIBRARY_AVAILABLE = True
except ImportError:
    PARTS_LIBRARY_AVAILABLE = False

try:
    from bom_parser import AliasManager
    ALIAS_MANAGER_AVAILABLE = True
except ImportError:
    ALIAS_MANAGER_AVAILABLE = False


class PartsLibraryFrame(ttk.Frame):
    """부품 라이브러리 관리 프레임"""
    
    def __init__(self, parent, get_bom_data_callback=None):
        super().__init__(parent, padding=10)
        self.get_bom_data = get_bom_data_callback
        self.library: Optional[PartsLibrary] = None
        
        if PARTS_LIBRARY_AVAILABLE:
            self.library = get_parts_library()
        
        self._create_widgets()
    
    def _create_widgets(self):
        if not PARTS_LIBRARY_AVAILABLE:
            ttk.Label(self, text="부품 라이브러리 모듈을 로드할 수 없습니다.", 
                     foreground='red').pack(pady=50)
            return
        
        # 상단: 탭 노트북
        self.sub_notebook = ttk.Notebook(self)
        self.sub_notebook.pack(fill='both', expand=True)
        
        # 탭 1: 부품 라이브러리
        self._create_parts_tab()
        
        # 탭 2: AVL 관리
        self._create_avl_tab()
        
        # 탭 3: 위험도 분석
        self._create_risk_tab()
        
        # 탭 4: 부품 별칭
        if ALIAS_MANAGER_AVAILABLE:
            self._create_alias_tab()
    
    def _create_parts_tab(self):
        """부품 라이브러리 탭"""
        frame = ttk.Frame(self.sub_notebook, padding=10)
        self.sub_notebook.add(frame, text="부품 라이브러리")
        
        # 검색
        search_frame = ttk.Frame(frame)
        search_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(search_frame, text="검색:").pack(side='left')
        self.parts_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.parts_search_var, width=30)
        search_entry.pack(side='left', padx=5)
        search_entry.bind('<Return>', lambda e: self._search_parts())
        ttk.Button(search_frame, text="검색", command=self._search_parts).pack(side='left')
        ttk.Button(search_frame, text="전체 보기", command=self._show_all_parts).pack(side='left', padx=5)
        
        # 통계
        self.parts_stats_var = tk.StringVar(value="")
        ttk.Label(search_frame, textvariable=self.parts_stats_var).pack(side='right')
        
        # 테이블
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill='both', expand=True)
        
        columns = ('MPN', '제조사', '카테고리', '패키지', '별칭', '상태', '리드타임')
        self.parts_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        
        for col in columns:
            self.parts_tree.heading(col, text=col)
            if col in ['MPN', '제조사']:
                width = 150
            elif col == '별칭':
                width = 200
            else:
                width = 100
            self.parts_tree.column(col, width=width)
        
        vsb = ttk.Scrollbar(table_frame, orient='vertical', command=self.parts_tree.yview)
        self.parts_tree.configure(yscrollcommand=vsb.set)
        
        self.parts_tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        
        # 버튼
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x', pady=(10, 0))
        
        ttk.Button(btn_frame, text="추가", command=self._add_part).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="편집", command=self._edit_part).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="삭제", command=self._delete_part).pack(side='left', padx=2)
        
        # 웹 검색 수집 버튼
        ttk.Separator(btn_frame, orient='vertical').pack(side='left', fill='y', padx=10)
        ttk.Button(btn_frame, text="🔍 웹 검색 추가", command=self._web_search_add).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="📥 BOM에서 수집", command=self._collect_from_bom).pack(side='left', padx=2)
        
        ttk.Button(btn_frame, text="내보내기", command=self._export_library).pack(side='right', padx=2)
        ttk.Button(btn_frame, text="가져오기", command=self._import_library).pack(side='right', padx=2)
        
        # 진행 상황 프레임 (숨김)
        self.progress_frame = ttk.LabelFrame(frame, text="수집 진행 상황", padding=5)
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(self.progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill='x', padx=5, pady=2)
        self.progress_label_var = tk.StringVar(value="")
        ttk.Label(self.progress_frame, textvariable=self.progress_label_var).pack(pady=2)
        
        self._update_parts_stats()
    
    def _create_avl_tab(self):
        """AVL 관리 탭"""
        frame = ttk.Frame(self.sub_notebook, padding=10)
        self.sub_notebook.add(frame, text="AVL 관리")
        
        # 필터
        filter_frame = ttk.Frame(frame)
        filter_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(filter_frame, text="상태:").pack(side='left')
        self.avl_status_var = tk.StringVar(value="all")
        status_combo = ttk.Combobox(filter_frame, textvariable=self.avl_status_var,
                                     values=['all', 'approved', 'preferred', 'restricted', 'banned'],
                                     width=12, state='readonly')
        status_combo.pack(side='left', padx=5)
        status_combo.bind('<<ComboboxSelected>>', lambda e: self._refresh_avl())
        ttk.Button(filter_frame, text="새로고침", command=self._refresh_avl).pack(side='left')
        
        # 테이블
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill='both', expand=True)
        
        columns = ('MPN', '제조사', '공급업체', '공급업체 P/N', '상태', '승인일')
        self.avl_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        
        for col in columns:
            self.avl_tree.heading(col, text=col)
            self.avl_tree.column(col, width=120)
        
        vsb = ttk.Scrollbar(table_frame, orient='vertical', command=self.avl_tree.yview)
        self.avl_tree.configure(yscrollcommand=vsb.set)
        
        self.avl_tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        
        # 상태별 색상
        self.avl_tree.tag_configure('approved', background='#E2EFDA')
        self.avl_tree.tag_configure('preferred', background='#BDD7EE')
        self.avl_tree.tag_configure('restricted', background='#FFF2CC')
        self.avl_tree.tag_configure('banned', background='#F8CBAD')
        
        # 버튼
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x', pady=(10, 0))
        
        ttk.Button(btn_frame, text="AVL 추가", command=self._add_avl).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="상태 변경", command=self._change_avl_status).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="BOM에서 가져오기", command=self._import_from_bom).pack(side='left', padx=2)
    
    def _create_risk_tab(self):
        """위험도 분석 탭"""
        frame = ttk.Frame(self.sub_notebook, padding=10)
        self.sub_notebook.add(frame, text="위험도 분석")
        
        # 상단: 분석 옵션
        option_frame = ttk.LabelFrame(frame, text="분석 옵션", padding=10)
        option_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Button(option_frame, text="BOM 전체 분석", 
                   command=self._analyze_bom_risk).pack(side='left', padx=5)
        ttk.Button(option_frame, text="단일 부품 분석", 
                   command=self._analyze_single_part).pack(side='left', padx=5)
        
        # 위험 등급 범례
        legend_frame = ttk.Frame(option_frame)
        legend_frame.pack(side='right')
        
        for level, color in [('낮음', '#C6EFCE'), ('보통', '#FFEB9C'), 
                             ('높음', '#FFC7CE'), ('매우높음', '#FF6B6B')]:
            lbl = ttk.Label(legend_frame, text=f" {level} ", background=color)
            lbl.pack(side='left', padx=2)
        
        # 결과 테이블
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill='both', expand=True)
        
        columns = ('MPN', '위험등급', '점수', '권장사항')
        self.risk_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=10)
        
        self.risk_tree.heading('MPN', text='MPN')
        self.risk_tree.heading('위험등급', text='위험등급')
        self.risk_tree.heading('점수', text='점수')
        self.risk_tree.heading('권장사항', text='권장사항')
        
        self.risk_tree.column('MPN', width=200)
        self.risk_tree.column('위험등급', width=80)
        self.risk_tree.column('점수', width=60)
        self.risk_tree.column('권장사항', width=400)
        
        vsb = ttk.Scrollbar(table_frame, orient='vertical', command=self.risk_tree.yview)
        self.risk_tree.configure(yscrollcommand=vsb.set)
        
        self.risk_tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        
        # 색상 태그
        self.risk_tree.tag_configure('low', background='#C6EFCE')
        self.risk_tree.tag_configure('medium', background='#FFEB9C')
        self.risk_tree.tag_configure('high', background='#FFC7CE')
        self.risk_tree.tag_configure('critical', background='#FF6B6B')
        
        # 상세 정보
        detail_frame = ttk.LabelFrame(frame, text="상세 분석", padding=5)
        detail_frame.pack(fill='x', pady=(10, 0))
        
        self.risk_detail_text = scrolledtext.ScrolledText(detail_frame, height=6)
        self.risk_detail_text.pack(fill='x')
        
        self.risk_tree.bind('<<TreeviewSelect>>', self._on_risk_select)
    
    # ===== 부품 라이브러리 기능 =====
    
    def _search_parts(self):
        """부품 검색"""
        query = self.parts_search_var.get().strip()
        if not query:
            return
        
        parts = self.library.search_parts(query)
        self._display_parts(parts)
    
    def _show_all_parts(self):
        """전체 부품 표시"""
        parts = self.library.get_all_parts(limit=500)
        self._display_parts(parts)
    
    def _display_parts(self, parts: List[PartLibraryEntry]):
        """부품 목록 표시"""
        self.parts_tree.delete(*self.parts_tree.get_children())
        
        # 별칭 데이터 로드
        alias_data = {}
        if ALIAS_MANAGER_AVAILABLE:
            try:
                alias_mgr = AliasManager()
                alias_data = alias_mgr.get_all_aliases()
            except:
                pass
        
        for part in parts:
            # 별칭 가져오기
            aliases_str = ""
            if part.mpn in alias_data:
                info = alias_data[part.mpn]
                variants = info.get('variants', [])
                if variants:
                    aliases_str = ', '.join(variants[:3])
                    if len(variants) > 3:
                        aliases_str += f' (+{len(variants) - 3})'
            
            self.parts_tree.insert('', 'end', values=(
                part.mpn,
                part.manufacturer,
                part.category,
                part.package,
                aliases_str,
                part.lifecycle,
                f"{part.lead_time_days}일" if part.lead_time_days else '-'
            ))
        
        self._update_parts_stats()
    
    def _update_parts_stats(self):
        """통계 업데이트"""
        stats = self.library.get_stats()
        self.parts_stats_var.set(
            f"총 {stats.get('total_parts', 0)}개 부품 | AVL {stats.get('total_avl', 0)}개"
        )
    
    def _add_part(self):
        """부품 추가 다이얼로그"""
        PartEditDialog(self, self.library, on_save=self._show_all_parts)
    
    def _edit_part(self):
        """부품 편집"""
        selection = self.parts_tree.selection()
        if not selection:
            messagebox.showinfo("알림", "편집할 부품을 선택하세요.")
            return
        
        mpn = self.parts_tree.item(selection[0])['values'][0]
        part = self.library.get_part(mpn)
        if part:
            PartEditDialog(self, self.library, part=part, on_save=self._show_all_parts)
    
    def _delete_part(self):
        """부품 삭제"""
        selection = self.parts_tree.selection()
        if not selection:
            return
        
        mpn = self.parts_tree.item(selection[0])['values'][0]
        if messagebox.askyesno("확인", f"'{mpn}'을(를) 삭제하시겠습니까?"):
            if self.library.delete_part(mpn):
                self._show_all_parts()
    
    def _export_library(self):
        """라이브러리 내보내기"""
        file_path = filedialog.asksaveasfilename(
            title="라이브러리 내보내기",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")]
        )
        if file_path:
            success, msg = self.library.export_to_json(file_path)
            messagebox.showinfo("결과", msg)
    
    def _import_library(self):
        """라이브러리 가져오기"""
        file_path = filedialog.askopenfilename(
            title="라이브러리 가져오기",
            filetypes=[("JSON Files", "*.json")]
        )
        if file_path:
            success, msg = self.library.import_from_json(file_path)
            messagebox.showinfo("결과", msg)
            self._show_all_parts()
    
    # ===== 웹 검색 수집 기능 =====
    
    def _web_search_add(self):
        """MPN 입력하여 웹 검색으로 부품 추가"""
        WebSearchDialog(self, self.library, on_complete=self._on_web_search_complete)
    
    def _on_web_search_complete(self, results: Dict[str, Any]):
        """웹 검색 완료 콜백"""
        success = results.get('success', 0)
        failed = results.get('failed', 0)
        
        messagebox.showinfo(
            "수집 완료",
            f"성공: {success}개\n실패: {failed}개"
        )
        self._show_all_parts()
        self._update_parts_stats()
    
    def _collect_from_bom(self):
        """BOM에서 부품 정보 수집"""
        if not self.get_bom_data:
            messagebox.showinfo("안내", "BOM 데이터 콜백이 없습니다.")
            return
        
        bom_df = self.get_bom_data()
        if bom_df is None or bom_df.empty:
            messagebox.showinfo("안내", "먼저 BOM을 처리해주세요.")
            return
        
        # MPN 추출
        mpn_list = []
        for _, row in bom_df.iterrows():
            mpn = str(row.get('공식부품명', '')).strip()
            if mpn and mpn.lower() not in ['nan', '', 'none']:
                mpn_list.append(mpn)
        
        mpn_list = list(set(mpn_list))  # 중복 제거
        
        if not mpn_list:
            messagebox.showinfo("안내", "수집할 부품이 없습니다.")
            return
        
        # 확인
        if not messagebox.askyesno(
            "확인",
            f"{len(mpn_list)}개 부품을 웹 검색으로 수집하시겠습니까?\n"
            f"(이미 라이브러리에 있는 부품은 건너뜁니다)"
        ):
            return
        
        # 진행 상황 표시
        self.progress_frame.pack(fill='x', pady=(10, 0))
        self.progress_var.set(0)
        self.progress_label_var.set("수집 준비 중...")
        self.update_idletasks()
        
        # 백그라운드 스레드에서 실행
        def run_collection():
            def on_progress(current, total, mpn, status):
                progress = int(current / total * 100)
                self.after(0, lambda: self._update_progress(progress, f"{current}/{total}: {mpn} - {status}"))
            
            results = self.library.batch_enrich_from_web(mpn_list, on_progress)
            self.after(0, lambda: self._on_collection_complete(results))
        
        thread = threading.Thread(target=run_collection, daemon=True)
        thread.start()
    
    def _update_progress(self, progress: int, message: str):
        """진행 상황 업데이트 (메인 스레드)"""
        self.progress_var.set(progress)
        self.progress_label_var.set(message)
        self.update_idletasks()
    
    def _on_collection_complete(self, results: Dict[str, Any]):
        """수집 완료 처리"""
        # 진행 상황 숨기기
        self.progress_frame.pack_forget()
        
        success = results.get('success', 0)
        failed = results.get('failed', 0)
        skipped = results.get('skipped', 0)
        
        messagebox.showinfo(
            "수집 완료",
            f"성공: {success}개\n실패: {failed}개\n건너뜀: {skipped}개"
        )
        
        self._show_all_parts()
        self._update_parts_stats()
    
    # ===== AVL 기능 =====
    
    def _refresh_avl(self):
        """AVL 목록 새로고침"""
        status = self.avl_status_var.get()
        status_filter = None if status == 'all' else status
        
        avl_list = self.library.get_all_avl(status_filter)
        
        self.avl_tree.delete(*self.avl_tree.get_children())
        for avl in avl_list:
            item = self.avl_tree.insert('', 'end', values=(
                avl.mpn, avl.manufacturer, avl.vendor, avl.vendor_pn,
                avl.status, avl.approved_date[:10] if avl.approved_date else '-'
            ), tags=(avl.status,))
    
    def _add_avl(self):
        """AVL 추가"""
        AVLEditDialog(self, self.library, on_save=self._refresh_avl)
    
    def _change_avl_status(self):
        """AVL 상태 변경"""
        selection = self.avl_tree.selection()
        if not selection:
            messagebox.showinfo("알림", "변경할 항목을 선택하세요.")
            return
        # TODO: 상태 변경 다이얼로그
        messagebox.showinfo("안내", "상태 변경 기능은 추후 구현 예정입니다.")
    
    def _import_from_bom(self):
        """BOM에서 AVL 가져오기"""
        if not self.get_bom_data:
            messagebox.showinfo("안내", "BOM 데이터가 없습니다.")
            return
        
        bom_df = self.get_bom_data()
        if bom_df is None or bom_df.empty:
            messagebox.showinfo("안내", "먼저 BOM을 처리해주세요.")
            return
        
        # 부품번호와 제조사 정보 추출
        count = 0
        for _, row in bom_df.iterrows():
            mpn = str(row.get('공식부품명', '')).strip()
            manufacturer = str(row.get('제조사', '')).strip()
            
            if mpn and mpn.lower() not in ['nan', '']:
                entry = AVLEntry(
                    mpn=mpn,
                    manufacturer=manufacturer if manufacturer.lower() not in ['nan', ''] else 'Unknown',
                    vendor='BOM Import',
                    status='approved'
                )
                if self.library.add_avl_entry(entry):
                    count += 1
        
        messagebox.showinfo("완료", f"{count}개 항목을 AVL에 추가했습니다.")
        self._refresh_avl()
    
    # ===== 위험도 분석 =====
    
    def _analyze_bom_risk(self):
        """BOM 전체 위험도 분석"""
        if not self.get_bom_data:
            messagebox.showinfo("안내", "BOM 데이터가 없습니다.")
            return
        
        bom_df = self.get_bom_data()
        if bom_df is None or bom_df.empty:
            messagebox.showinfo("안내", "먼저 BOM을 처리해주세요.")
            return
        
        # 부품 목록 추출
        parts_list = []
        for _, row in bom_df.iterrows():
            mpn = str(row.get('공식부품명', '')).strip()
            qty = int(row.get('수량', 1)) if pd.notna(row.get('수량')) else 1
            
            if mpn and mpn.lower() not in ['nan', '']:
                parts_list.append({'mpn': mpn, 'qty': qty})
        
        if not parts_list:
            messagebox.showinfo("안내", "분석할 부품이 없습니다.")
            return
        
        # 분석 실행
        results = self.library.batch_assess_risk(parts_list)
        self._display_risk_results(results)
    
    def _analyze_single_part(self):
        """단일 부품 분석"""
        # 간단한 입력 다이얼로그
        mpn = tk.simpledialog.askstring("부품 분석", "부품번호(MPN)를 입력하세요:")
        if mpn:
            result = self.library.assess_risk(mpn)
            self._display_risk_results([result])
    
    def _display_risk_results(self, results: List[RiskAssessment]):
        """위험도 분석 결과 표시"""
        self.risk_tree.delete(*self.risk_tree.get_children())
        
        for r in results:
            # 태그 결정
            tag = {
                RiskLevel.LOW: 'low',
                RiskLevel.MEDIUM: 'medium',
                RiskLevel.HIGH: 'high',
                RiskLevel.CRITICAL: 'critical',
            }.get(r.risk_level, 'low')
            
            self.risk_tree.insert('', 'end', values=(
                r.mpn,
                r.risk_level.value,
                f"{r.risk_score:.0f}",
                r.recommendation
            ), tags=(tag,))
        
        # 요약
        high_risk = sum(1 for r in results if r.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL])
        self.risk_detail_text.delete('1.0', 'end')
        self.risk_detail_text.insert('end', f"총 {len(results)}개 부품 분석 완료\n")
        self.risk_detail_text.insert('end', f"고위험 부품: {high_risk}개\n\n")
        self.risk_detail_text.insert('end', "부품을 선택하면 상세 정보가 표시됩니다.")
    
    def _on_risk_select(self, event):
        """위험도 항목 선택 시"""
        selection = self.risk_tree.selection()
        if not selection:
            return
        
        mpn = self.risk_tree.item(selection[0])['values'][0]
        # 가장 최근 분석 결과 표시 (현재는 간략 정보만)
        self.risk_detail_text.delete('1.0', 'end')
        self.risk_detail_text.insert('end', f"MPN: {mpn}\n\n")
        self.risk_detail_text.insert('end', "상세 분석 결과는 DB에 저장됩니다.")
    
    # ===== 부품 별칭 관리 =====
    
    def _create_alias_tab(self):
        """부품 별칭 탭"""
        frame = ttk.Frame(self.sub_notebook, padding=10)
        self.sub_notebook.add(frame, text="부품 별칭")
        
        self.alias_manager = AliasManager()
        
        # 상단: 검색 및 통계
        top_frame = ttk.Frame(frame)
        top_frame.pack(fill='x', pady=(0, 10))
        
        # 검색
        search_frame = ttk.LabelFrame(top_frame, text="검색", padding=5)
        search_frame.pack(side='left', fill='x', expand=True, padx=(0, 10))
        
        self.alias_search_var = tk.StringVar()
        self.alias_search_var.trace('w', lambda *args: self._on_alias_search())
        
        search_entry = ttk.Entry(search_frame, textvariable=self.alias_search_var, width=40)
        search_entry.pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        ttk.Button(search_frame, text="초기화", command=self._clear_alias_search, width=8).pack(side='left')
        
        # 통계
        stats_frame = ttk.LabelFrame(top_frame, text="통계", padding=5)
        stats_frame.pack(side='right')
        
        self.alias_stats_var = tk.StringVar(value="항목: 0 | 변형: 0")
        ttk.Label(stats_frame, textvariable=self.alias_stats_var).pack()
        
        # 중앙: 별칭 목록
        list_frame = ttk.LabelFrame(frame, text="별칭 목록", padding=5)
        list_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        # 트리뷰
        columns = ('official_name', 'variants', 'category', 'package')
        self.alias_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=12)
        
        self.alias_tree.heading('official_name', text='공식 부품명')
        self.alias_tree.heading('variants', text='변형 (별칭)')
        self.alias_tree.heading('category', text='카테고리')
        self.alias_tree.heading('package', text='패키지')
        
        self.alias_tree.column('official_name', width=200, minwidth=100)
        self.alias_tree.column('variants', width=250, minwidth=100)
        self.alias_tree.column('category', width=100, minwidth=60)
        self.alias_tree.column('package', width=80, minwidth=50)
        
        # 스크롤바
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.alias_tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.alias_tree.xview)
        self.alias_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.alias_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # 더블클릭으로 편집
        self.alias_tree.bind('<Double-1>', self._on_alias_double_click)
        
        # 하단: 버튼
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x')
        
        # 왼쪽 버튼 (추가/편집/삭제)
        left_btns = ttk.Frame(btn_frame)
        left_btns.pack(side='left')
        
        ttk.Button(left_btns, text="추가", command=self._add_alias, width=10).pack(side='left', padx=2)
        ttk.Button(left_btns, text="편집", command=self._edit_alias, width=10).pack(side='left', padx=2)
        ttk.Button(left_btns, text="삭제", command=self._delete_alias, width=10).pack(side='left', padx=2)
        
        # 오른쪽 버튼 (가져오기/내보내기)
        right_btns = ttk.Frame(btn_frame)
        right_btns.pack(side='right')
        
        ttk.Button(right_btns, text="새로고침", command=self._refresh_alias_list, width=10).pack(side='left', padx=2)
        ttk.Button(right_btns, text="가져오기", command=self._import_aliases, width=10).pack(side='left', padx=2)
        ttk.Button(right_btns, text="내보내기", command=self._export_aliases, width=10).pack(side='left', padx=2)
        
        # 초기 로드
        self._refresh_alias_list()
    
    def _refresh_alias_list(self, filter_query: str = ""):
        """별칭 목록 새로고침"""
        self.alias_tree.delete(*self.alias_tree.get_children())
        
        self.alias_manager.load()
        
        if filter_query:
            aliases = self.alias_manager.search_aliases(filter_query, limit=200)
            items = [(a['canonical'], a) for a in aliases]
        else:
            items = list(self.alias_manager.get_all_aliases().items())
        
        for canonical, info in items:
            if isinstance(info, dict):
                official_name = info.get('official_name', canonical)
                variants = info.get('variants', [])
                category = info.get('category', '')
                package = info.get('package', '')
            else:
                official_name = canonical
                variants = []
                category = ''
                package = ''
            
            variants_str = ', '.join(variants[:3])
            if len(variants) > 3:
                variants_str += f' (+{len(variants) - 3}개)'
            
            self.alias_tree.insert('', 'end', iid=canonical, values=(
                official_name, variants_str, category, package
            ))
        
        stats = self.alias_manager.get_stats()
        self.alias_stats_var.set(f"항목: {stats['total_entries']} | 변형: {stats['total_variants']}")
    
    def _on_alias_search(self):
        """별칭 검색"""
        query = self.alias_search_var.get().strip()
        self._refresh_alias_list(query)
    
    def _clear_alias_search(self):
        """검색 초기화"""
        self.alias_search_var.set("")
        self._refresh_alias_list()
    
    def _on_alias_double_click(self, event):
        """더블클릭으로 편집"""
        self._edit_alias()
    
    def _add_alias(self):
        """별칭 추가"""
        AliasEditDialog(self, "별칭 추가", self.alias_manager, on_save=self._refresh_alias_list)
    
    def _edit_alias(self):
        """별칭 편집"""
        selected = self.alias_tree.selection()
        if not selected:
            messagebox.showinfo("알림", "편집할 항목을 선택하세요.")
            return
        
        canonical = selected[0]
        aliases = self.alias_manager.get_all_aliases()
        info = aliases.get(canonical, {})
        
        AliasEditDialog(self, "별칭 편집", self.alias_manager, canonical, info, on_save=self._refresh_alias_list)
    
    def _delete_alias(self):
        """별칭 삭제"""
        selected = self.alias_tree.selection()
        if not selected:
            messagebox.showinfo("알림", "삭제할 항목을 선택하세요.")
            return
        
        canonical = selected[0]
        
        if messagebox.askyesno("확인", f"'{canonical}' 항목을 삭제하시겠습니까?"):
            if self.alias_manager.remove_alias(canonical):
                self._refresh_alias_list()
                messagebox.showinfo("완료", "항목이 삭제되었습니다.")
            else:
                messagebox.showwarning("오류", "삭제에 실패했습니다.")
    
    def _import_aliases(self):
        """별칭 가져오기"""
        file_path = filedialog.askopenfilename(
            title="별칭 파일 가져오기",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if self.alias_manager.import_data(data, merge=True):
                    self._refresh_alias_list()
                    messagebox.showinfo("완료", "별칭을 가져왔습니다.")
                else:
                    messagebox.showwarning("오류", "가져오기에 실패했습니다.")
            except Exception as e:
                messagebox.showerror("오류", f"파일 읽기 실패: {e}")
    
    def _export_aliases(self):
        """별칭 내보내기"""
        file_path = filedialog.asksaveasfilename(
            title="별칭 파일 내보내기",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if file_path:
            try:
                data = self.alias_manager.export_data()
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                messagebox.showinfo("완료", f"별칭을 내보냈습니다:\n{file_path}")
            except Exception as e:
                messagebox.showerror("오류", f"파일 저장 실패: {e}")


class PartEditDialog(tk.Toplevel):
    """부품 편집 다이얼로그"""
    
    def __init__(self, parent, library: PartsLibrary, 
                 part: PartLibraryEntry = None, on_save=None):
        super().__init__(parent)
        self.library = library
        self.part = part
        self.on_save = on_save
        self.is_edit = part is not None
        
        # AliasManager 초기화
        if ALIAS_MANAGER_AVAILABLE:
            self.alias_manager = AliasManager()
        else:
            self.alias_manager = None
        
        self.title("부품 편집" if self.is_edit else "부품 추가")
        self.geometry("500x600")
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
        if self.is_edit:
            self._load_data()
    
    def _create_widgets(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill='both', expand=True)
        
        # 필드들
        fields = [
            ('MPN:', 'mpn'),
            ('제조사:', 'manufacturer'),
            ('설명:', 'description'),
            ('카테고리:', 'category'),
            ('패키지:', 'package'),
            ('장착방식:', 'mounting_type'),
            ('생산상태:', 'lifecycle'),
            ('리드타임(일):', 'lead_time_days'),
            ('단가(원):', 'unit_price_krw'),
            ('대체품 (쉼표구분):', 'alternates'),
            ('데이터시트 URL:', 'datasheet_url'),
        ]
        
        self.vars = {}
        for i, (label, key) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky='e', pady=3)
            var = tk.StringVar()
            self.vars[key] = var
            
            if key == 'lifecycle':
                entry = ttk.Combobox(frame, textvariable=var, 
                                     values=[s.value for s in LifecycleStatus], width=35)
            elif key == 'mounting_type':
                entry = ttk.Combobox(frame, textvariable=var, 
                                     values=['SMD', 'DIP', '확인필요'], width=35)
            else:
                entry = ttk.Entry(frame, textvariable=var, width=38)
            
            entry.grid(row=i, column=1, sticky='w', pady=3)
        
        # 별칭 필드 (여러 줄 입력)
        alias_row = len(fields)
        ttk.Label(frame, text="별칭 (한 줄에 하나씩):").grid(row=alias_row, column=0, sticky='ne', pady=3)
        
        alias_frame = ttk.Frame(frame)
        alias_frame.grid(row=alias_row, column=1, sticky='w', pady=3)
        
        self.aliases_text = scrolledtext.ScrolledText(alias_frame, width=35, height=5)
        self.aliases_text.pack(side='left')
        ttk.Label(alias_frame, text="여러 개 가능", foreground='gray').pack(side='left', padx=5)
        
        # 버튼
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=alias_row + 1, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="저장", command=self._save).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="취소", command=self.destroy).pack(side='left')
    
    def _load_data(self):
        """기존 데이터 로드"""
        self.vars['mpn'].set(self.part.mpn)
        self.vars['manufacturer'].set(self.part.manufacturer)
        self.vars['description'].set(self.part.description)
        self.vars['category'].set(self.part.category)
        self.vars['package'].set(self.part.package)
        self.vars['mounting_type'].set(self.part.mounting_type)
        self.vars['lifecycle'].set(self.part.lifecycle)
        self.vars['lead_time_days'].set(str(self.part.lead_time_days))
        self.vars['unit_price_krw'].set(str(self.part.unit_price_krw))
        self.vars['alternates'].set(', '.join(self.part.alternates))
        self.vars['datasheet_url'].set(self.part.datasheet_url)
        
        # 별칭 로드
        if self.alias_manager:
            aliases = self.alias_manager.get_all_aliases()
            mpn = self.part.mpn
            if mpn in aliases:
                info = aliases[mpn]
                variants = info.get('variants', [])
                self.aliases_text.insert('1.0', '\n'.join(variants))
    
    def _save(self):
        """저장"""
        mpn = self.vars['mpn'].get().strip()
        if not mpn:
            messagebox.showwarning("오류", "MPN을 입력하세요.")
            return
        
        alternates_str = self.vars['alternates'].get().strip()
        alternates = [a.strip() for a in alternates_str.split(',') if a.strip()]
        
        try:
            lead_time = int(self.vars['lead_time_days'].get() or 0)
        except ValueError:
            lead_time = 0
        
        try:
            unit_price = float(self.vars['unit_price_krw'].get() or 0)
        except ValueError:
            unit_price = 0
        
        entry = PartLibraryEntry(
            mpn=mpn,
            manufacturer=self.vars['manufacturer'].get().strip(),
            description=self.vars['description'].get().strip(),
            category=self.vars['category'].get().strip(),
            package=self.vars['package'].get().strip(),
            mounting_type=self.vars['mounting_type'].get().strip(),
            lifecycle=self.vars['lifecycle'].get().strip(),
            lead_time_days=lead_time,
            unit_price_krw=unit_price,
            alternates=alternates,
            datasheet_url=self.vars['datasheet_url'].get().strip(),
            source='manual'
        )
        
        if self.library.add_part(entry):
            # 별칭 저장
            if self.alias_manager:
                aliases_text = self.aliases_text.get('1.0', 'end').strip()
                aliases = [a.strip() for a in aliases_text.split('\n') if a.strip()]
                
                # 기존 별칭 삭제 후 새로 추가
                self.alias_manager.remove_alias(mpn)
                
                if aliases:
                    # 먼저 공식 부품명 등록
                    self.alias_manager.add_alias(
                        canonical_mpn=mpn,
                        variant="",
                        category=entry.category,
                        package=entry.package,
                        auto_generated=False
                    )
                    # 변형(별칭) 추가
                    for alias in aliases:
                        self.alias_manager.add_alias(
                            canonical_mpn=mpn,
                            variant=alias,
                            category=entry.category,
                            package=entry.package
                        )
            
            if self.on_save:
                self.on_save()
            self.destroy()
        else:
            messagebox.showerror("오류", "저장 실패")


class AVLEditDialog(tk.Toplevel):
    """AVL 편집 다이얼로그"""
    
    def __init__(self, parent, library: PartsLibrary, on_save=None):
        super().__init__(parent)
        self.library = library
        self.on_save = on_save
        
        self.title("AVL 추가")
        self.geometry("400x300")
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
    
    def _create_widgets(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill='both', expand=True)
        
        fields = [
            ('MPN:', 'mpn'),
            ('제조사:', 'manufacturer'),
            ('공급업체:', 'vendor'),
            ('공급업체 P/N:', 'vendor_pn'),
            ('비고:', 'notes'),
        ]
        
        self.vars = {}
        for i, (label, key) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky='e', pady=5)
            var = tk.StringVar()
            self.vars[key] = var
            ttk.Entry(frame, textvariable=var, width=30).grid(row=i, column=1, pady=5)
        
        # 상태
        ttk.Label(frame, text="상태:").grid(row=len(fields), column=0, sticky='e', pady=5)
        self.status_var = tk.StringVar(value='approved')
        status_combo = ttk.Combobox(frame, textvariable=self.status_var,
                                     values=['approved', 'preferred', 'restricted', 'banned'],
                                     width=27, state='readonly')
        status_combo.grid(row=len(fields), column=1, pady=5)
        
        # 버튼
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(fields)+1, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="저장", command=self._save).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="취소", command=self.destroy).pack(side='left')
    
    def _save(self):
        mpn = self.vars['mpn'].get().strip()
        manufacturer = self.vars['manufacturer'].get().strip()
        vendor = self.vars['vendor'].get().strip()
        
        if not all([mpn, manufacturer, vendor]):
            messagebox.showwarning("오류", "필수 항목을 입력하세요.")
            return
        
        entry = AVLEntry(
            mpn=mpn,
            manufacturer=manufacturer,
            vendor=vendor,
            vendor_pn=self.vars['vendor_pn'].get().strip(),
            status=self.status_var.get(),
            notes=self.vars['notes'].get().strip()
        )
        
        if self.library.add_avl_entry(entry):
            if self.on_save:
                self.on_save()
            self.destroy()
        else:
            messagebox.showerror("오류", "저장 실패")


class WebSearchDialog(tk.Toplevel):
    """웹 검색으로 부품 추가 다이얼로그"""
    
    def __init__(self, parent, library: PartsLibrary, on_complete=None):
        super().__init__(parent)
        self.library = library
        self.on_complete = on_complete
        
        self.title("🔍 웹 검색으로 부품 추가")
        self.geometry("500x400")
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
    
    def _create_widgets(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill='both', expand=True)
        
        # 설명
        desc_label = ttk.Label(
            frame, 
            text="부품명(스펙, 규격, 제조사 등)을 입력하면 웹 검색을 통해\n제조사, 카테고리, 패키지 정보를 자동으로 수집합니다.",
            justify='center'
        )
        desc_label.pack(pady=(0, 15))
        
        # 입력 필드
        input_frame = ttk.LabelFrame(frame, text="부품 정보 입력", padding=10)
        input_frame.pack(fill='x', pady=(0, 10))
        
        # 규격
        ttk.Label(input_frame, text="규격:").grid(row=0, column=0, sticky='e', padx=5, pady=3)
        self.standard_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.standard_var, width=40).grid(row=0, column=1, sticky='w', padx=5)
        ttk.Label(input_frame, text="예: 0603, SOT-23", foreground='gray').grid(row=0, column=2, sticky='w')
        
        # 스펙
        ttk.Label(input_frame, text="스펙:").grid(row=1, column=0, sticky='e', padx=5, pady=3)
        self.spec_var = tk.StringVar()
        spec_entry = ttk.Entry(input_frame, textvariable=self.spec_var, width=40)
        spec_entry.grid(row=1, column=1, sticky='w', padx=5)
        spec_entry.bind('<Return>', lambda e: self._search())
        spec_entry.focus()
        ttk.Label(input_frame, text="예: 100nF, 10K, 1uH", foreground='gray').grid(row=1, column=2, sticky='w')
        
        # 제조사
        ttk.Label(input_frame, text="제조사:").grid(row=2, column=0, sticky='e', padx=5, pady=3)
        self.manufacturer_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.manufacturer_var, width=40).grid(row=2, column=1, sticky='w', padx=5)
        ttk.Label(input_frame, text="예: Samsung, Murata", foreground='gray').grid(row=2, column=2, sticky='w')
        
        # MPN (선택)
        ttk.Label(input_frame, text="MPN (선택):").grid(row=3, column=0, sticky='e', padx=5, pady=3)
        self.mpn_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.mpn_var, width=40).grid(row=3, column=1, sticky='w', padx=5)
        ttk.Label(input_frame, text="예: GRM155R71C104KA88D", foreground='gray').grid(row=3, column=2, sticky='w')
        
        # 버튼
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="검색 및 추가", command=self._search).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="닫기", command=self._close).pack(side='left', padx=5)
        
        # 결과 표시
        result_frame = ttk.LabelFrame(frame, text="수집 결과", padding=5)
        result_frame.pack(fill='both', expand=True)
        
        self.result_text = scrolledtext.ScrolledText(result_frame, height=8, wrap='word')
        self.result_text.pack(fill='both', expand=True)
        
        # 상태
        self.status_var = tk.StringVar(value="스펙/규격/제조사를 입력하고 '검색 및 추가' 버튼을 클릭하세요.")
        ttk.Label(frame, textvariable=self.status_var, foreground='gray').pack(pady=5)
        
        # 수집 결과 집계
        self.results = {'success': 0, 'failed': 0}
    
    def _search(self):
        """웹 검색 실행"""
        spec = self.spec_var.get().strip()
        standard = self.standard_var.get().strip()
        manufacturer = self.manufacturer_var.get().strip()
        mpn = self.mpn_var.get().strip()
        
        # 검색어 조합 (표시용)
        search_parts = [p for p in [standard, spec, manufacturer, mpn] if p]
        search_display = ' '.join(search_parts)
        
        if not search_display:
            messagebox.showwarning("입력 오류", "스펙, 규격, 제조사, MPN 중 하나 이상을 입력하세요.")
            return
        
        self.status_var.set(f"'{search_display[:30]}...' 검색 중...")
        self.update_idletasks()
        
        # 백그라운드에서 검색
        def do_search():
            success, message = self.library.enrich_part_from_web(
                mpn=mpn, 
                manufacturer=manufacturer,
                spec=spec,
                standard=standard
            )
            self.after(0, lambda: self._show_result(search_display, success, message))
        
        thread = threading.Thread(target=do_search, daemon=True)
        thread.start()
    
    def _show_result(self, mpn: str, success: bool, message: str):
        """검색 결과 표시"""
        if success:
            self.results['success'] += 1
            result_text = f"✅ {mpn}: {message}\n"
        else:
            self.results['failed'] += 1
            result_text = f"❌ {mpn}: {message}\n"
        
        self.result_text.insert('end', result_text)
        self.result_text.see('end')
        
        self.status_var.set(f"완료. 성공: {self.results['success']}, 실패: {self.results['failed']}")
        
        # 입력 필드 초기화
        self.mpn_var.set("")
    
    def _close(self):
        """다이얼로그 닫기"""
        if self.on_complete:
            self.on_complete(self.results)
        self.destroy()


def add_library_tab(notebook: ttk.Notebook, get_bom_data_callback=None) -> None:
    """노트북에 부품 라이브러리 탭 추가"""
    if not PARTS_LIBRARY_AVAILABLE:
        return
    
    library_frame = PartsLibraryFrame(notebook, get_bom_data_callback)
    notebook.add(library_frame, text="부품 라이브러리")


class AliasEditDialog(tk.Toplevel):
    """별칭 편집 다이얼로그"""
    
    def __init__(self, parent, title: str, alias_manager,
                 canonical: str = "", info: dict = None, on_save=None):
        super().__init__(parent)
        
        self.alias_manager = alias_manager
        self.canonical = canonical
        self.info = info or {}
        self.is_edit = bool(canonical)
        self.on_save = on_save
        
        self.title(title)
        self.geometry("500x400")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
        self._load_data()
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill='both', expand=True)
        
        # 공식 부품명
        ttk.Label(main_frame, text="공식 부품명 (MPN):").grid(row=0, column=0, sticky='e', pady=5)
        self.official_name_var = tk.StringVar()
        self.official_name_entry = ttk.Entry(main_frame, textvariable=self.official_name_var, width=40)
        self.official_name_entry.grid(row=0, column=1, sticky='w', pady=5)
        
        # 카테고리
        ttk.Label(main_frame, text="카테고리:").grid(row=1, column=0, sticky='e', pady=5)
        self.category_var = tk.StringVar()
        self.category_entry = ttk.Entry(main_frame, textvariable=self.category_var, width=40)
        self.category_entry.grid(row=1, column=1, sticky='w', pady=5)
        
        # 패키지
        ttk.Label(main_frame, text="패키지:").grid(row=2, column=0, sticky='e', pady=5)
        self.package_var = tk.StringVar()
        self.package_entry = ttk.Entry(main_frame, textvariable=self.package_var, width=40)
        self.package_entry.grid(row=2, column=1, sticky='w', pady=5)
        
        # 변형 (별칭) 목록
        ttk.Label(main_frame, text="변형 (별칭):").grid(row=3, column=0, sticky='ne', pady=5)
        
        variants_frame = ttk.Frame(main_frame)
        variants_frame.grid(row=3, column=1, sticky='w', pady=5)
        
        self.variants_text = scrolledtext.ScrolledText(variants_frame, width=35, height=8)
        self.variants_text.pack(side='left')
        
        ttk.Label(variants_frame, text="(한 줄에 하나씩)", foreground='gray').pack(side='left', padx=5)
        
        # 버튼
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="저장", command=self._save, width=12).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="취소", command=self.destroy, width=12).pack(side='left', padx=5)
    
    def _load_data(self):
        """기존 데이터 로드"""
        if self.is_edit:
            self.official_name_var.set(self.info.get('official_name', ''))
            self.category_var.set(self.info.get('category', ''))
            self.package_var.set(self.info.get('package', ''))
            
            variants = self.info.get('variants', [])
            self.variants_text.insert('1.0', '\n'.join(variants))
    
    def _save(self):
        """저장"""
        official_name = self.official_name_var.get().strip()
        
        if not official_name:
            messagebox.showwarning("오류", "공식 부품명을 입력하세요.")
            return
        
        category = self.category_var.get().strip()
        package = self.package_var.get().strip()
        
        # 변형 목록 파싱
        variants_text = self.variants_text.get('1.0', 'end').strip()
        variants = [v.strip() for v in variants_text.split('\n') if v.strip()]
        
        # 저장
        if self.is_edit:
            # 기존 항목 삭제 후 다시 추가
            self.alias_manager.remove_alias(self.canonical)
        
        # 새 항목 추가
        self.alias_manager.add_alias(
            canonical_mpn=official_name,
            variant="",
            category=category,
            package=package,
            auto_generated=False
        )
        
        # 변형 추가
        for variant in variants:
            self.alias_manager.add_alias(
                canonical_mpn=official_name,
                variant=variant,
                category=category,
                package=package
            )
        
        if self.on_save:
            self.on_save()
        
        self.destroy()
