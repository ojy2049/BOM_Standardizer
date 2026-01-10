#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
공급사 API 조회 모듈
- Digi-Key API (Product Information V4)
- Mouser API (Search API)
"""

import os
import re
import json
import time
import requests
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from config import (
    CACHE_FILE, SMD_KEYWORDS, DIP_KEYWORDS, TO_PACKAGE_SMD_VARIANTS,
    SMD_CRYSTAL_PACKAGES, THT_CRYSTAL_PACKAGES,
    load_config, save_config, get_env_or_config
)


class PartInfo:
    """부품 정보 데이터 클래스"""
    def __init__(self):
        self.official_name: str = ""
        self.package: str = ""
        self.mounting: str = ""  # "Surface Mount" / "Through Hole" / ""
        self.mounting_type: str = ""  # SMD / DIP / 미확정
        self.datasheet_url: str = ""
        self.supplier: str = ""  # "Digi-Key" / "Mouser"
        self.supplier_pn: str = ""
        self.supplier_url: str = ""
        self.manufacturer: str = ""
        self.source: str = ""  # "api" / "cache" / "heuristic"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'official_name': self.official_name,
            'package': self.package,
            'mounting': self.mounting,
            'mounting_type': self.mounting_type,
            'datasheet_url': self.datasheet_url,
            'supplier': self.supplier,
            'supplier_pn': self.supplier_pn,
            'supplier_url': self.supplier_url,
            'manufacturer': self.manufacturer,
            'source': self.source,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'PartInfo':
        info = cls()
        for k, v in d.items():
            if hasattr(info, k):
                setattr(info, k, v)
        return info


class CacheManager:
    """캐시 관리자"""
    
    def __init__(self, cache_file: Path = CACHE_FILE):
        self.cache_file = cache_file
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.load()
    
    def load(self):
        """캐시 파일 로드"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}
    
    def save(self):
        """캐시 파일 저장"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"캐시 저장 실패: {e}")
    
    def get(self, key: str, ttl_days: int = 30) -> Optional[PartInfo]:
        """캐시에서 조회"""
        if key in self.cache:
            entry = self.cache[key]
            # TTL 체크
            cached_time = entry.get('_cached_at', '')
            if cached_time:
                try:
                    cached_dt = datetime.fromisoformat(cached_time)
                    if datetime.now() - cached_dt < timedelta(days=ttl_days):
                        return PartInfo.from_dict(entry)
                except Exception:
                    pass
        return None
    
    def set(self, key: str, info: PartInfo):
        """캐시에 저장"""
        entry = info.to_dict()
        entry['_cached_at'] = datetime.now().isoformat()
        self.cache[key] = entry
        self.save()
    
    def make_key(self, mpn: str = "", digi_pn: str = "", mouser_pn: str = "") -> str:
        """캐시 키 생성"""
        parts = [p.strip().upper() for p in [mpn, digi_pn, mouser_pn] if p]
        return "|".join(sorted(parts)) if parts else ""


class DigiKeyAPI:
    """Digi-Key Product Information API V4"""
    
    BASE_URL = "https://api.digikey.com/products/v4"
    AUTH_URL = "https://api.digikey.com/v1/oauth2/token"
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = ""
        self.token_expires = 0
    
    def _get_access_token(self) -> bool:
        """OAuth 토큰 발급"""
        if not self.client_id or not self.client_secret:
            return False
        
        # 토큰이 유효하면 재사용
        if self.access_token and time.time() < self.token_expires - 60:
            return True
        
        try:
            response = requests.post(
                self.AUTH_URL,
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'grant_type': 'client_credentials',
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get('access_token', '')
                expires_in = data.get('expires_in', 3600)
                self.token_expires = time.time() + expires_in
                return True
            else:
                print(f"Digi-Key 인증 실패: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"Digi-Key 인증 오류: {e}")
            return False
    
    def search_part(self, keyword: str) -> Optional[PartInfo]:
        """부품 검색"""
        if not self._get_access_token():
            return None
        
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'X-DIGIKEY-Client-Id': self.client_id,
                'Content-Type': 'application/json',
            }
            
            # 키워드 검색
            response = requests.post(
                f"{self.BASE_URL}/search/keyword",
                headers=headers,
                json={
                    'Keywords': keyword,
                    'Limit': 1,
                    'Offset': 0,
                },
                timeout=30
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            products = data.get('Products', [])
            
            if not products:
                return None
            
            product = products[0]
            info = PartInfo()
            info.supplier = "Digi-Key"
            info.supplier_pn = product.get('DigiKeyPartNumber', '')
            info.official_name = product.get('ProductDescription', '') or product.get('ManufacturerPartNumber', '')
            info.manufacturer = product.get('Manufacturer', {}).get('Name', '')
            info.datasheet_url = product.get('PrimaryDatasheet', '')
            info.supplier_url = product.get('ProductUrl', '')
            info.source = "api"
            
            # 파라미터에서 패키지/마운팅 추출
            for param in product.get('Parameters', []):
                param_name = param.get('Parameter', '').lower()
                param_value = param.get('Value', '')
                
                if 'package' in param_name or 'case' in param_name:
                    info.package = param_value
                elif 'mount' in param_name:
                    info.mounting = param_value
            
            return info
            
        except Exception as e:
            print(f"Digi-Key 검색 오류: {e}")
            return None
    
    def is_configured(self) -> bool:
        """API 설정 여부 확인"""
        return bool(self.client_id and self.client_secret)


class MouserAPI:
    """Mouser Search API"""
    
    BASE_URL = "https://api.mouser.com/api/v1"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def search_part(self, keyword: str) -> Optional[PartInfo]:
        """부품 검색"""
        if not self.api_key:
            return None
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/search/partnumber",
                params={'apiKey': self.api_key},
                json={
                    'SearchByPartRequest': {
                        'mouserPartNumber': keyword,
                        'partSearchOptions': ''
                    }
                },
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code != 200:
                # 키워드 검색 시도
                response = requests.post(
                    f"{self.BASE_URL}/search/keyword",
                    params={'apiKey': self.api_key},
                    json={
                        'SearchByKeywordRequest': {
                            'keyword': keyword,
                            'records': 1,
                            'startingRecord': 0,
                            'searchOptions': '',
                            'searchWithYourSignUpLanguage': ''
                        }
                    },
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            parts = data.get('SearchResults', {}).get('Parts', [])
            
            if not parts:
                return None
            
            part = parts[0]
            info = PartInfo()
            info.supplier = "Mouser"
            info.supplier_pn = part.get('MouserPartNumber', '')
            info.official_name = part.get('Description', '') or part.get('ManufacturerPartNumber', '')
            info.manufacturer = part.get('Manufacturer', '')
            info.datasheet_url = part.get('DataSheetUrl', '')
            info.supplier_url = part.get('ProductDetailUrl', '')
            info.source = "api"
            
            # 속성에서 패키지/마운팅 추출
            for attr in part.get('ProductAttributes', []):
                attr_name = attr.get('AttributeName', '').lower()
                attr_value = attr.get('AttributeValue', '')
                
                if 'package' in attr_name or 'case' in attr_name:
                    info.package = attr_value
                elif 'mount' in attr_name:
                    info.mounting = attr_value
            
            return info
            
        except Exception as e:
            print(f"Mouser 검색 오류: {e}")
            return None
    
    def is_configured(self) -> bool:
        """API 설정 여부 확인"""
        return bool(self.api_key)


class MountingClassifier:
    """SMD/DIP 분류기"""
    
    @staticmethod
    def classify(spec: str = "", package: str = "", mounting: str = "", mpn: str = "") -> str:
        """
        장착방식 분류
        
        Args:
            spec: 스펙 문자열
            package: 패키지 정보
            mounting: 공급사 제공 마운팅 정보
            mpn: 제조사 부품번호
            
        Returns:
            'SMD' / 'DIP' / '미확정'
        """
        # 모든 텍스트 결합 및 대문자 변환
        text = " ".join([spec or "", package or "", mounting or "", mpn or ""]).upper()
        text = re.sub(r'[^A-Z0-9\-\s]', ' ', text)
        
        # 공급사 마운팅 정보 우선 확인
        if mounting:
            m_upper = mounting.upper()
            if any(kw in m_upper for kw in ['SURFACE', 'SMT', 'SMD']):
                return "SMD"
            if any(kw in m_upper for kw in ['THROUGH', 'HOLE', 'THT']):
                return "DIP"
        
        # TO 패키지 특별 처리 (SMD 변형 먼저 체크)
        for smd_to in TO_PACKAGE_SMD_VARIANTS:
            if smd_to.upper() in text:
                return "SMD"
        
        # SMD 키워드 확인 (숫자/문자가 붙은 패키지도 인식: LQFP48, SOD-323, DO-214AC 등)
        for kw in SMD_KEYWORDS:
            # 키워드 + 옵션 숫자/문자 패턴 (하이픈 제거 후 매칭)
            escaped_kw = re.escape(kw)
            # 정확한 키워드 매칭 또는 키워드 뒤에 숫자/문자가 붙는 경우
            pattern = r'\b' + escaped_kw + r'[A-Z0-9]*\b'
            if re.search(pattern, text):
                return "SMD"
        
        # DIP 키워드 확인
        for kw in DIP_KEYWORDS:
            escaped_kw = re.escape(kw)
            pattern = r'\b' + escaped_kw + r'[A-Z0-9]*\b'
            if re.search(pattern, text):
                return "DIP"
        
        # 숫자 패키지 패턴 (0402, 0603 등 - 4자리 칩 사이즈)
        if re.search(r'\b(0[1-6][0-3][0-9]|[0-2][0-9]{3})\b', text):
            # 대부분 칩 부품 = SMD
            return "SMD"
        
        # 추가: QFP/QFN + 숫자 패턴 (LQFP48, QFN32 등)
        if re.search(r'\b[TLMVPHC]?QF[NP][0-9]+\b', text):
            return "SMD"
        
        # 크리스탈 패키지 확인
        for pkg in THT_CRYSTAL_PACKAGES:
            if re.search(r'\b' + re.escape(pkg) + r'\b', text):
                return "DIP"
        for pkg in SMD_CRYSTAL_PACKAGES:
            if re.search(r'\b' + re.escape(pkg) + r'\b', text):
                return "SMD"
        
        return "미확정"


class PartResolver:
    """통합 부품 정보 조회기"""
    
    def __init__(self, config: Dict[str, Any] = None):
        if config is None:
            config = load_config()
        
        self.config = config
        self.cache = CacheManager()
        self.classifier = MountingClassifier()
        
        # API 클라이언트 초기화
        self.digikey = DigiKeyAPI(
            get_env_or_config('digikey_client_id', config),
            get_env_or_config('digikey_client_secret', config)
        )
        self.mouser = MouserAPI(
            get_env_or_config('mouser_api_key', config)
        )
        
        self.api_delay = config.get('api_call_delay', 0.5)
        self.use_cache = config.get('use_cache', True)
        self.cache_ttl = config.get('cache_ttl_days', 30)
    
    def resolve(self, mpn: str = "", digi_pn: str = "", mouser_pn: str = "",
                spec: str = "", package: str = "") -> PartInfo:
        """
        부품 정보 조회
        
        Args:
            mpn: 제조사 부품번호
            digi_pn: Digi-Key 부품번호
            mouser_pn: Mouser 부품번호
            spec: 스펙 (휴리스틱 분류용)
            package: 패키지 (휴리스틱 분류용)
            
        Returns:
            PartInfo 객체
        """
        # 캐시 확인
        cache_key = self.cache.make_key(mpn, digi_pn, mouser_pn)
        if cache_key and self.use_cache:
            cached = self.cache.get(cache_key, self.cache_ttl)
            if cached:
                cached.source = "cache"
                # 캐시에서도 mounting_type 재분류 (안전)
                if not cached.mounting_type or cached.mounting_type == "미확정":
                    cached.mounting_type = self.classifier.classify(
                        spec, cached.package or package, cached.mounting, mpn
                    )
                return cached
        
        info = PartInfo()
        
        # API 조회 시도
        search_terms = [t for t in [mpn, digi_pn, mouser_pn] if t and t.strip()]
        
        for term in search_terms:
            # Digi-Key 먼저
            if self.digikey.is_configured():
                result = self.digikey.search_part(term)
                if result:
                    info = result
                    break
                time.sleep(self.api_delay)
            
            # Mouser
            if self.mouser.is_configured():
                result = self.mouser.search_part(term)
                if result:
                    info = result
                    break
                time.sleep(self.api_delay)
        
        # API 결과가 없으면 기본값 설정
        if not info.official_name:
            info.official_name = mpn or digi_pn or mouser_pn or ""
            info.source = "heuristic"
        
        if not info.supplier:
            if digi_pn:
                info.supplier = "Digi-Key"
                info.supplier_pn = digi_pn
            elif mouser_pn:
                info.supplier = "Mouser"
                info.supplier_pn = mouser_pn
        
        # 장착방식 분류
        info.mounting_type = self.classifier.classify(
            spec, info.package or package, info.mounting, mpn
        )
        
        # 캐시 저장
        if cache_key and self.use_cache:
            self.cache.set(cache_key, info)
        
        return info
    
    def get_api_status(self) -> Dict[str, bool]:
        """API 설정 상태 확인"""
        return {
            'digikey': self.digikey.is_configured(),
            'mouser': self.mouser.is_configured(),
        }
