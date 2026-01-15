#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
부품 라이브러리 GUI 프레임
- 부품 DB 관리
- AVL 관리
- 위험도 분석
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional, Dict, Any, List
import pandas as pd

try:
    from parts_library import (
        PartsLibrary, PartLibraryEntry, AVLEntry, RiskAssessment,
        get_parts_library, RiskLevel, LifecycleStatus
    )
    PARTS_LIBRARY_AVAILABLE = True
except ImportError:
    PARTS_LIBRARY_AVAILABLE = False


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
        
        columns = ('MPN', '제조사', '카테고리', '패키지', '상태', '리드타임')
        self.parts_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        
        for col in columns:
            self.parts_tree.heading(col, text=col)
            width = 150 if col in ['MPN', '제조사'] else 100
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
        ttk.Button(btn_frame, text="내보내기", command=self._export_library).pack(side='right', padx=2)
        ttk.Button(btn_frame, text="가져오기", command=self._import_library).pack(side='right', padx=2)
        
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
        
        for part in parts:
            self.parts_tree.insert('', 'end', values=(
                part.mpn,
                part.manufacturer,
                part.category,
                part.package,
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


class PartEditDialog(tk.Toplevel):
    """부품 편집 다이얼로그"""
    
    def __init__(self, parent, library: PartsLibrary, 
                 part: PartLibraryEntry = None, on_save=None):
        super().__init__(parent)
        self.library = library
        self.part = part
        self.on_save = on_save
        self.is_edit = part is not None
        
        self.title("부품 편집" if self.is_edit else "부품 추가")
        self.geometry("450x500")
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
        
        # 버튼
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=20)
        
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


def add_library_tab(notebook: ttk.Notebook, get_bom_data_callback=None) -> None:
    """노트북에 부품 라이브러리 탭 추가"""
    if not PARTS_LIBRARY_AVAILABLE:
        return
    
    library_frame = PartsLibraryFrame(notebook, get_bom_data_callback)
    notebook.add(library_frame, text="부품 라이브러리")
