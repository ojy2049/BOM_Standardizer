#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
공급사 API 조회 모듈
- Digi-Key API (Product Information V4)
- Mouser API (Search API)
- MPN 정규화 및 별칭 관리
"""

import os
import re
import json
import time
import requests
from typing import Dict, Any, Optional, List, Tuple, Set
from datetime import datetime, timedelta
from pathlib import Path

from config import (
    APP_DIR, CACHE_FILE, SMD_KEYWORDS, DIP_KEYWORDS, TO_PACKAGE_SMD_VARIANTS,
    SMD_CRYSTAL_PACKAGES, THT_CRYSTAL_PACKAGES, SMD_METRIC_SIZES,
    ELECTROLYTIC_KEYWORDS, SMD_ELECTROLYTIC_KEYWORDS, UNCERTAIN_PART_KEYWORDS, REFDES_PREFIXES,
    load_config, save_config, get_env_or_config, load_components_db, get_mounting_type_from_package
)

# 별칭 사전 파일 경로
ALIASES_FILE = APP_DIR / "part_aliases.json"


class PartInfo:
    """부품 정보 데이터 클래스"""
    def __init__(self):
        self.official_name: str = ""  # 제조사 MPN (ManufacturerPartNumber)
        self.description: str = ""  # 제품 설명 (ProductDescription)
        self.package: str = ""
        self.mounting: str = ""  # "Surface Mount" / "Through Hole" / ""
        self.mounting_type: str = ""  # SMD / DIP / 미확정 / 확인필요
        self.classification_reason: str = ""  # 분류 판단 근거 (VBA 매크로의 "판단근거" 역할)
        self.datasheet_url: str = ""
        self.supplier: str = ""  # "Digi-Key" / "Mouser"
        self.supplier_pn: str = ""
        self.supplier_url: str = ""
        self.manufacturer: str = ""
        self.source: str = ""  # "api" / "cache" / "heuristic"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'official_name': self.official_name,
            'description': self.description,
            'package': self.package,
            'mounting': self.mounting,
            'mounting_type': self.mounting_type,
            'classification_reason': self.classification_reason,
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


class MPNNormalizer:
    """MPN 정규화 클래스 - 부품번호 표준화 및 비교"""
    
    # 정규화 시 제거되는 구분자
    SEPARATORS = r'[\s\-_./,()]'
    
    @staticmethod
    def normalize(mpn: str) -> Tuple[str, str]:
        """
        MPN 정규화
        
        Args:
            mpn: 원본 MPN
            
        Returns:
            (정규화된 MPN, 괄호 안 내용)
        """
        if not mpn:
            return "", ""
        
        original = mpn.strip()
        
        # 괄호 안 내용 추출 (종종 중요 정보 포함)
        parenthetical = re.findall(r'\(([^)]+)\)', original)
        parenthetical_info = ", ".join(parenthetical) if parenthetical else ""
        
        # 대문자 변환
        normalized = original.upper()
        
        # 구분자 제거
        normalized = re.sub(MPNNormalizer.SEPARATORS, '', normalized)
        
        return normalized, parenthetical_info
    
    @staticmethod
    def similarity(mpn1: str, mpn2: str) -> float:
        """
        두 MPN 간의 유사도 계산
        
        Returns:
            0.0 ~ 1.0 사이의 유사도 값
        """
        norm1, _ = MPNNormalizer.normalize(mpn1)
        norm2, _ = MPNNormalizer.normalize(mpn2)
        
        if not norm1 or not norm2:
            return 0.0
        
        if norm1 == norm2:
            return 1.0
        
        # Levenshtein 거리 기반 유사도
        max_len = max(len(norm1), len(norm2))
        distance = MPNNormalizer._levenshtein(norm1, norm2)
        
        return 1 - (distance / max_len)
    
    @staticmethod
    def are_same_part(mpn1: str, mpn2: str, threshold: float = 0.95) -> bool:
        """
        두 MPN이 같은 부품인지 판별
        
        Args:
            threshold: 유사도 임계값 (기본 0.95 = 95% 일치)
        """
        return MPNNormalizer.similarity(mpn1, mpn2) >= threshold
    
    @staticmethod
    def _levenshtein(s1: str, s2: str) -> int:
        """Levenshtein 편집 거리 계산"""
        if len(s1) < len(s2):
            return MPNNormalizer._levenshtein(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]


class AliasManager:
    """부품 별칭 관리자"""
    
    def __init__(self, aliases_file: Path = ALIASES_FILE):
        self.aliases_file = aliases_file
        self.data: Dict[str, Any] = {
            "aliases": {},
            "category_mappings": {},
            "ignore_patterns": []
        }
        self.load()
    
    def load(self) -> bool:
        """별칭 사전 로드"""
        if self.aliases_file.exists():
            try:
                with open(self.aliases_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
                return True
            except Exception as e:
                print(f"별칭 사전 로드 실패: {e}")
        return False
    
    def save(self) -> bool:
        """별칭 사전 저장"""
        try:
            self.data["_last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.aliases_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"별칭 사전 저장 실패: {e}")
            return False
    
    def get_canonical(self, mpn: str) -> Tuple[str, bool]:
        """
        정규 MPN 조회
        
        Args:
            mpn: 조회할 MPN
            
        Returns:
            (정규 MPN, 별칭에서 찾았는지 여부)
        """
        if not mpn:
            return "", False
        
        normalized, _ = MPNNormalizer.normalize(mpn)
        
        # 별칭 사전에서 검색
        aliases = self.data.get("aliases", {})
        
        for canonical, info in aliases.items():
            if normalized == canonical:
                return info.get("official_name", mpn), True
            
            variants = info.get("variants", [])
            for variant in variants:
                var_normalized, _ = MPNNormalizer.normalize(variant)
                if normalized == var_normalized:
                    return info.get("official_name", mpn), True
        
        return mpn, False
    
    def add_alias(self, canonical_mpn: str, variant: str, 
                  category: str = "", package: str = "", 
                  auto_generated: bool = False) -> bool:
        """
        별칭 추가
        
        Args:
            canonical_mpn: 정규 MPN (기준)
            variant: 변형 MPN
            category: 부품 카테고리
            package: 패키지 정보
            auto_generated: 자동 생성 여부
        """
        normalized_canonical, _ = MPNNormalizer.normalize(canonical_mpn)
        
        if not normalized_canonical:
            return False
        
        aliases = self.data.setdefault("aliases", {})
        
        if normalized_canonical not in aliases:
            aliases[normalized_canonical] = {
                "official_name": canonical_mpn,
                "variants": [],
                "category": category,
                "package": package,
                "auto_generated": auto_generated,
                "created_at": datetime.now().isoformat()
            }
        
        entry = aliases[normalized_canonical]
        
        # 변형 MPN 추가 (중복 방지)
        if variant and variant not in entry["variants"]:
            # 정규화했을 때 다른 경우에만 추가
            var_normalized, _ = MPNNormalizer.normalize(variant)
            if var_normalized != normalized_canonical:
                entry["variants"].append(variant)
        
        # 카테고리/패키지 업데이트 (비어있으면)
        if category and not entry.get("category"):
            entry["category"] = category
        if package and not entry.get("package"):
            entry["package"] = package
        
        return self.save()
    
    def remove_alias(self, canonical_mpn: str, variant: str = None) -> bool:
        """
        별칭 제거
        
        Args:
            canonical_mpn: 정규 MPN
            variant: 제거할 변형 (None이면 전체 삭제)
        """
        normalized_canonical, _ = MPNNormalizer.normalize(canonical_mpn)
        aliases = self.data.get("aliases", {})
        
        if normalized_canonical not in aliases:
            return False
        
        if variant is None:
            del aliases[normalized_canonical]
        else:
            entry = aliases[normalized_canonical]
            if variant in entry.get("variants", []):
                entry["variants"].remove(variant)
        
        return self.save()
    
    def search_aliases(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        별칭 검색
        
        Args:
            query: 검색어
            limit: 최대 결과 수
            
        Returns:
            매칭된 별칭 목록
        """
        results = []
        query_lower = query.lower()
        query_normalized, _ = MPNNormalizer.normalize(query)
        
        for canonical, info in self.data.get("aliases", {}).items():
            # 정규 MPN 매칭
            if query_lower in canonical.lower() or query_lower in info.get("official_name", "").lower():
                results.append({
                    "canonical": canonical,
                    "official_name": info.get("official_name", ""),
                    "variants": info.get("variants", []),
                    "category": info.get("category", ""),
                    "package": info.get("package", ""),
                    "match_type": "canonical"
                })
                continue
            
            # 변형 MPN 매칭
            for variant in info.get("variants", []):
                if query_lower in variant.lower():
                    results.append({
                        "canonical": canonical,
                        "official_name": info.get("official_name", ""),
                        "variants": info.get("variants", []),
                        "category": info.get("category", ""),
                        "package": info.get("package", ""),
                        "match_type": "variant",
                        "matched_variant": variant
                    })
                    break
            
            # 카테고리 매칭
            if query_lower in info.get("category", "").lower():
                results.append({
                    "canonical": canonical,
                    "official_name": info.get("official_name", ""),
                    "variants": info.get("variants", []),
                    "category": info.get("category", ""),
                    "package": info.get("package", ""),
                    "match_type": "category"
                })
            
            if len(results) >= limit:
                break
        
        return results
    
    def get_all_aliases(self) -> Dict[str, Any]:
        """모든 별칭 반환"""
        return self.data.get("aliases", {})
    
    def get_category_mapping(self, category: str) -> str:
        """카테고리 매핑 조회"""
        category_upper = category.upper().strip()
        mappings = self.data.get("category_mappings", {})
        
        for key, value in mappings.items():
            if key.upper() == category_upper:
                return value
        
        return category  # 매핑 없으면 원본 반환
    
    def add_category_mapping(self, from_category: str, to_category: str) -> bool:
        """카테고리 매핑 추가"""
        mappings = self.data.setdefault("category_mappings", {})
        mappings[from_category] = to_category
        return self.save()
    
    def get_stats(self) -> Dict[str, int]:
        """통계 반환"""
        aliases = self.data.get("aliases", {})
        total_variants = sum(len(info.get("variants", [])) for info in aliases.values())
        
        return {
            "total_entries": len(aliases),
            "total_variants": total_variants,
            "category_mappings": len(self.data.get("category_mappings", {}))
        }
    
    def export_data(self) -> Dict[str, Any]:
        """내보내기용 데이터 반환"""
        return self.data.copy()
    
    def import_data(self, data: Dict[str, Any], merge: bool = True) -> bool:
        """
        데이터 가져오기
        
        Args:
            data: 가져올 데이터
            merge: True면 병합, False면 교체
        """
        try:
            if merge:
                # 별칭 병합
                for canonical, info in data.get("aliases", {}).items():
                    if canonical in self.data.get("aliases", {}):
                        # 기존 항목에 변형 추가
                        existing = self.data["aliases"][canonical]
                        for variant in info.get("variants", []):
                            if variant not in existing.get("variants", []):
                                existing.setdefault("variants", []).append(variant)
                    else:
                        self.data.setdefault("aliases", {})[canonical] = info
                
                # 카테고리 매핑 병합
                self.data.setdefault("category_mappings", {}).update(
                    data.get("category_mappings", {})
                )
            else:
                self.data = data
            
            return self.save()
        except Exception as e:
            print(f"데이터 가져오기 실패: {e}")
            return False


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
            
            # API v4 필드명: ManufacturerProductNumber (not ManufacturerPartNumber)
            info.official_name = product.get('ManufacturerProductNumber', '')
            
            # Description은 중첩 딕셔너리
            desc_obj = product.get('Description', {})
            if isinstance(desc_obj, dict):
                info.description = desc_obj.get('ProductDescription', '') or desc_obj.get('DetailedDescription', '')
            else:
                info.description = str(desc_obj) if desc_obj else ''
            
            # Manufacturer도 중첩 딕셔너리
            info.manufacturer = product.get('Manufacturer', {}).get('Name', '')
            
            # DatasheetUrl (not PrimaryDatasheet)
            info.datasheet_url = product.get('DatasheetUrl', '')
            info.supplier_url = product.get('ProductUrl', '')
            
            # DigiKey PN은 ProductVariations에서 찾기
            variations = product.get('ProductVariations', [])
            if variations and len(variations) > 0:
                info.supplier_pn = variations[0].get('DigiKeyProductNumber', '') or variations[0].get('DigiKeyPartNumber', '')
            
            info.source = "api"
            
            # 파라미터에서 패키지/마운팅 추출 (API v4 필드명 확인)
            for param in product.get('Parameters', []):
                # v4에서는 'Parameter' 또는 'ParameterText' 키 사용
                param_name = (param.get('Parameter', '') or param.get('ParameterText', '')).lower()
                param_value = param.get('Value', '') or param.get('ValueText', '')
                
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
            info.official_name = part.get('ManufacturerPartNumber', '')  # 제조사 정식 MPN
            info.description = part.get('Description', '')  # 제품 설명
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


class WebSearchResolver:
    """DuckDuckGo 웹 검색 기반 부품 조회 (duckduckgo-search 라이브러리 사용)"""
    
    # 부품 정보 사이트들 (검색 결과 우선순위)
    TRUSTED_DOMAINS = [
        'digikey.com', 'digikey.kr', 'digikey.co.kr',
        'mouser.com', 'mouser.kr', 'mouser.co.kr',
        'octopart.com',
        'lcsc.com',
        'element14.com', 'newark.com',
        'arrow.com', 'avnet.com',
        'ti.com', 'st.com', 'microchip.com', 'nxp.com',  # 제조사 사이트
    ]
    
    # SMD/DIP 키워드 (검색 결과 분석용)
    SMD_INDICATORS = [
        'surface mount', 'smd', 'smt', 'chip', 'mlcc',
        'qfp', 'qfn', 'bga', 'soic', 'sop', 'sot', 'dfn', 'son',
        '0402', '0603', '0805', '1206', '1210',
    ]
    
    DIP_INDICATORS = [
        'through hole', 'through-hole', 'tht', 'dip', 'pdip',
        'axial', 'radial', 'leaded',
        'to-220', 'to-92', 'to-247',
    ]
    
    def __init__(self, enabled: bool = True, timeout: int = 10):
        self.enabled = enabled
        self.timeout = timeout
        self.ddgs = None
        
        # duckduckgo-search 라이브러리 초기화 시도
        if enabled:
            try:
                from duckduckgo_search import DDGS
                self.ddgs = DDGS()
            except ImportError:
                print("[WebSearch] duckduckgo-search 라이브러리가 설치되지 않음")
                self.enabled = False
            except Exception as e:
                print(f"[WebSearch] 초기화 오류: {e}")
                self.enabled = False
    
    def search_part(self, query: str, manufacturer: str = "") -> Optional[PartInfo]:
        """
        DuckDuckGo 검색으로 부품 정보 조회
        
        Args:
            query: 검색어 (스펙 또는 MPN)
            manufacturer: 제조사명 (선택)
            
        Returns:
            PartInfo 또는 None
        """
        if not self.enabled or not self.ddgs or not query or not query.strip():
            return None
        
        # 검색어 구성
        search_query = query.strip()
        if manufacturer and manufacturer.strip():
            search_query = f"{manufacturer.strip()} {search_query}"
        search_query += " datasheet"  # 데이터시트 페이지 우선
        
        try:
            # DuckDuckGo 검색 (최대 5개 결과)
            results = list(self.ddgs.text(search_query, max_results=5))
            
            if not results:
                return None
            
            # 결과 파싱
            return self._parse_ddgs_results(results, query)
            
        except Exception as e:
            print(f"[WebSearch] 검색 오류: {e}")
            return None
    
    def _parse_ddgs_results(self, results: list, original_query: str) -> Optional[PartInfo]:
        """duckduckgo-search 라이브러리 결과 파싱"""
        info = PartInfo()
        info.source = "web_search"
        
        # 결과에서 텍스트 추출
        titles = []
        snippets = []
        urls = []
        
        for r in results:
            if isinstance(r, dict):
                titles.append(r.get('title', ''))
                snippets.append(r.get('body', ''))
                urls.append(r.get('href', ''))
        
        all_text = " ".join(titles + snippets).lower()
        
        # 공식 부품명 추출 시도 (MPN 패턴)
        # 일반적인 MPN 패턴: 알파벳+숫자 조합, 하이픈 포함 가능
        mpn_patterns = [
            r'\b([A-Z]{2,}[0-9]{2,}[A-Z0-9\-]+)\b',  # RC0402FR-0710KL
            r'\b([A-Z][0-9]{4}[A-Z0-9\-]+)\b',  # C0402C104K4RACTU
            r'\b([A-Z]{3,}[0-9]+[A-Z]*)\b',  # STM32F103C8T6
        ]
        
        for pattern in mpn_patterns:
            matches = re.findall(pattern, " ".join(titles).upper())
            if matches:
                # 원래 쿼리와 유사한 것 우선
                query_upper = original_query.upper()
                for match in matches:
                    if query_upper in match or match in query_upper:
                        info.official_name = match
                        break
                if not info.official_name and matches:
                    info.official_name = matches[0]
                break
        
        # 제조사 추출
        known_manufacturers = [
            'SAMSUNG', 'MURATA', 'TDK', 'YAGEO', 'VISHAY', 'ROHM',
            'TEXAS INSTRUMENTS', 'TI', 'STM', 'STMICROELECTRONICS',
            'MICROCHIP', 'NXP', 'INFINEON', 'ON SEMI', 'ONSEMI',
            'ANALOG DEVICES', 'MAXIM', 'DIODES', 'NEXPERIA',
            'PANASONIC', 'NICHICON', 'KEMET', 'AVX', 'BOURNS',
        ]
        
        for mfr in known_manufacturers:
            if mfr.lower() in all_text:
                info.manufacturer = mfr
                break
        
        # 패키지 정보 추출
        package_patterns = [
            r'\b(0\d{3})\b',  # 0402, 0603, 0805
            r'\b(1\d{3})\b',  # 1206, 1210
            r'\b(SOT-\d+)\b', r'\b(SOD-\d+)\b',
            r'\b(SOIC-?\d+)\b', r'\b(SOP-?\d+)\b',
            r'\b(QFN-?\d+)\b', r'\b(QFP-?\d+)\b', r'\b(LQFP-?\d+)\b',
            r'\b(BGA-?\d+)\b',
            r'\b(DIP-?\d+)\b', r'\b(PDIP-?\d+)\b',
            r'\b(TO-\d+[A-Z]*)\b',
        ]
        
        for pattern in package_patterns:
            matches = re.findall(pattern, all_text.upper())
            if matches:
                info.package = matches[0]
                break
        
        # 마운팅 타입 분석
        smd_score = sum(1 for ind in self.SMD_INDICATORS if ind in all_text)
        dip_score = sum(1 for ind in self.DIP_INDICATORS if ind in all_text)
        
        if smd_score > dip_score:
            info.mounting = "Surface Mount"
        elif dip_score > smd_score:
            info.mounting = "Through Hole"
        
        # 데이터시트 URL 추출 (신뢰할 수 있는 도메인 우선)
        for url in urls:
            # PDF 링크 우선
            if '.pdf' in url.lower():
                info.datasheet_url = url
                break
            # 신뢰할 수 있는 도메인
            for domain in self.TRUSTED_DOMAINS:
                if domain in url:
                    info.supplier_url = url
                    break
            if info.supplier_url:
                break
        
        # Description 설정
        if snippets:
            info.description = snippets[0][:200] if len(snippets[0]) > 200 else snippets[0]
        
        # 유효한 결과인지 확인
        if info.official_name or info.package or info.mounting:
            return info
        
        return None
    
    def is_configured(self) -> bool:
        """항상 사용 가능"""
        return self.enabled


class MountingClassifier:
    """SMD/DIP 분류기 - VBA 매크로 로직 통합 버전"""
    
    # SMD로 분류할 부품 카테고리 (패키지 정보 없어도 대부분 SMD)
    SMD_CATEGORIES = [
        '칩저항', '칩콘덴서', '칩인덕터', '칩LED', '칩다이오드',
        'CHIP', 'MLCC',
    ]
    
    # DIP로 분류할 부품 카테고리
    DIP_CATEGORIES = [
        '전해콘덴서', '전해', 'ELECTROLYTIC', 'ELEC CAP',
    ]
    
    # IC는 현대적으로 대부분 SMD이므로, THT 키워드가 없으면 SMD 추정
    IC_KEYWORDS = [
        'IC', 'MCU', 'CPU', 'MPU', 'DSP', 'FPGA', 'CPLD', 'ASIC',
        'OPAMP', 'OP-AMP', 'COMPARATOR', 'ADC', 'DAC',
        'REGULATOR', 'LDO', 'DCDC', 'DC-DC', 'CONVERTER', 'DRIVER',
        'AMPLIFIER', 'MOSFET', 'TRANSISTOR', 'FET',
        'EEPROM', 'FLASH', 'SRAM', 'DRAM', 'MEMORY',
        'STM32', 'ATM', 'PIC', 'ESP', 'NRF', 'CC2', 'TL', 'LM', 'NE555',
    ]
    
    # RefDes 접두어별 기본 분류 (VBA 매크로에서 추가)
    REFDES_SMD_PREFIXES = ['R', 'C', 'L', 'D', 'Q', 'U', 'Z', 'FB', 'Y', 'LED']
    REFDES_UNCERTAIN_PREFIXES = ['J', 'P', 'CN', 'CON', 'S', 'SW', 'K']
    REFDES_DIP_PREFIXES = ['H', 'TP', 'M']  # Hole, Test Point, Mechanical
    
    _components_db = None

    @staticmethod
    def _ensure_db_loaded():
        if MountingClassifier._components_db is None:
            MountingClassifier._components_db = load_components_db()

    @staticmethod
    def _extract_refdes_prefix(refdes: str) -> str:
        """RefDes에서 접두어 추출 (예: R1 -> R, LED3 -> LED, CN5 -> CN)"""
        if not refdes:
            return ""
        
        refdes_upper = refdes.strip().upper()
        
        # 여러 RefDes가 있는 경우 첫 번째만 분석
        if ',' in refdes_upper:
            refdes_upper = refdes_upper.split(',')[0].strip()
        if '-' in refdes_upper:
            refdes_upper = refdes_upper.split('-')[0].strip()
        
        # 알파벳 접두어 추출
        prefix = ""
        for char in refdes_upper:
            if char.isalpha():
                prefix += char
            else:
                break
        
        return prefix
    
    @staticmethod
    def classify(spec: str = "", package: str = "", mounting: str = "", 
                 mpn: str = "", category: str = "", refdes: str = "") -> tuple:
        """
        장착방식 분류 (판단 근거 포함)
        
        Args:
            spec: 스펙 문자열
            package: 패키지 정보
            mounting: 공급사 제공 마운팅 정보
            mpn: 제조사 부품번호
            category: 부품 카테고리 (품목)
            refdes: Reference Designator (위치)
            
        Returns:
            (분류결과, 판단근거) 튜플
            분류결과: 'SMD' / 'DIP' / 'SMD(추정)' / '확인필요' / '미확정'
        """
        MountingClassifier._ensure_db_loaded()
        
        # 디버깅 로그
        
        # 모든 텍스트 결합 및 대문자 변환
        all_text = " ".join([spec or "", package or "", mounting or "", mpn or "", category or ""])
        text = all_text.upper()
        text = re.sub(r'[^A-Z0-9\\-\\s가-힣]', ' ', text)
        
        # === [Priority 0] DB MPN 패턴 매칭 (최우선) ===
        # MPN 또는 스펙에서 패턴 검색
        search_text = f"{mpn} {spec}".upper()
        
        if search_text.strip() and MountingClassifier._components_db:
            all_patterns = []  # (pattern, mounting, packages, original_pattern)
            components = MountingClassifier._components_db.get('components', {})
            
            for cat, items in components.items():
                for item_type, sub_items in items.items():
                    # 2단 구조 처리: sub_items가 바로 부품 정보인 경우 (예: IC -> LinearRegulator -> {...})
                    if isinstance(sub_items, dict) and ('mounting' in sub_items or 'packages' in sub_items):
                        mpn_patterns = sub_items.get('mpn_patterns', [])
                        mnt = sub_items.get('mounting', '확인필요')
                        pkgs = sub_items.get('packages', [])
                        for pattern in mpn_patterns:
                            all_patterns.append((pattern.upper(), mnt, pkgs, pattern))
                        continue

                    # 3단 구조 처리: sub_items가 하위 부품 딕셔너리인 경우 (예: 저항 -> 칩저항 -> {...})
                    if isinstance(sub_items, dict):
                        for part_name, part_info in sub_items.items():
                            if isinstance(part_info, dict):
                                mpn_patterns = part_info.get('mpn_patterns', [])
                                mnt = part_info.get('mounting', '확인필요')
                                pkgs = part_info.get('packages', [])
                                
                                for pattern in mpn_patterns:
                                    all_patterns.append((pattern.upper(), mnt, pkgs, pattern))
            
            # 긴 패턴 먼저 매칭
            all_patterns.sort(key=lambda x: len(x[0]), reverse=True)
            
            for pattern_upper, mnt, pkgs, original_pattern in all_patterns:
                if pattern_upper in search_text:
                    reason = f"DB Pattern({original_pattern})"
                    if mnt == 'SMD':
                        return "SMD", reason
                    elif mnt == 'DIP':
                        return "DIP", reason
                    
                    # SMD/DIP 혼용인 경우 패키지로 추가 판별
                    for pkg_name in pkgs:
                        # 유연한 비교를 위해 정규화 (공백, 하이픈 제거)
                        text_norm = text.replace(' ', '').replace('-', '')
                        pkg_norm = pkg_name.upper().replace(' ', '').replace('-', '')
                        
                        if pkg_norm in text_norm:
                            pkg_mnt = get_mounting_type_from_package(pkg_name)
                            if pkg_mnt != '확인필요':
                                return pkg_mnt, f"{reason} + Package({pkg_name})"
                    
                    # 패키지 판별 실패해도 패턴 매칭 성공이므로 확인필요 반환
                    return "확인필요", f"{reason} (SMD/DIP 혼용)"
        
        # === [로직 1] 절대적 키워드 우선 검색 (가장 강력함) ===
        
        # 1. 공급사 마운팅 정보 우선 확인 (가장 신뢰할 수 있음)
        if mounting:
            m_upper = mounting.upper()
            if any(kw in m_upper for kw in ['SURFACE', 'SMT', 'SMD']):
                return "SMD", f"API Mounting({mounting})"
            if any(kw in m_upper for kw in ['THROUGH', 'HOLE', 'THT']):
                return "DIP", f"API Mounting({mounting})"
        
        # === [로직 0] Buzzer 전용 처리 (최우선 순위) ===
        # BUZZER, TRANSDUCER, SOUNDER 키워드가 포함되면 전용 로직 수행
        BUZZER_TRIGGER_KEYWORDS = ['BUZZER', 'TRANSDUCER', 'SOUNDER']
        is_buzzer = any(kw in text for kw in BUZZER_TRIGGER_KEYWORDS)
        
        if is_buzzer:
            # (1) 특정 모델명 매칭 - DIP 확정 (Priority: High)
            buzzer_dip_models = ['BTH-', 'ALP', 'PKM', 'KPEG', 'PS1', 'PS2']
            for model in buzzer_dip_models:
                if model in text:
                    return "DIP", f"Buzzer 특정 모델({model})"
            
            # (2) PKLCS는 Murata SMD Buzzer 시리즈 - SMT 확정
            if 'PKLCS' in text:
                return "SMT", "Buzzer 특정 모델(PKLCS)"
            
            # (3) Buzzer 전용 SMT 키워드 (기존 알고리즘에 없는 것들)
            buzzer_smt_keywords = ['-TR', 'T/R', 'PAD', 'SDR']
            for kw in buzzer_smt_keywords:
                if kw in text:
                    return "SMT", f"Buzzer SMT Keyword({kw})"
            
            # (4) Fallback - DIP 추정 (부저는 통상적으로 핀 타입이 많음)
            return "확인필요(DIP추정)", "Buzzer Type Unsure"
        
        # 2. TO 패키지 특별 처리 (SMD 변형 먼저 체크)
        for smd_to in TO_PACKAGE_SMD_VARIANTS:
            if smd_to.upper() in text:
                return "SMD", f"Package({smd_to})"
        
        # 3. SMD 사이즈 코드 확인 (VBA: 우선순위 높음)
        # 인치 사이즈
        inch_sizes = ['01005', '0201', '0402', '0603', '0805', '1206', '1210', '1812', '2010', '2512']
        for size in inch_sizes:
            if re.search(r'\b' + size + r'\b', text):
                return "SMD", f"Size Code({size})"
        
        # 메트릭 사이즈 (VBA에서 추가)
        for size in SMD_METRIC_SIZES:
            if re.search(r'\b' + size + r'\b', text):
                return "SMD", f"Metric Size({size})"
        
        # 4. SMD 키워드 확인 (숫자/문자가 붙은 패키지도 인식)
        for kw in SMD_KEYWORDS:
            escaped_kw = re.escape(kw)
            pattern = r'\b' + escaped_kw + r'[A-Z0-9\\-]*\b'
            if re.search(pattern, text):
                return "SMD", f"Pkg Name({kw})"
        
        # 5. DIP 키워드 확인 (VBA: SMT보다 DIP 키워드가 있으면 DIP)
        for kw in DIP_KEYWORDS:
            escaped_kw = re.escape(kw)
            pattern = r'\b' + escaped_kw + r'[A-Z0-9\\-]*\b'
            if re.search(pattern, text):
                return "DIP", f"DIP Keyword({kw})"
        
        # 6. QFP/QFN/BGA + 숫자 패턴 (LQFP48, QFN32, BGA256 등)
        match = re.search(r'\b([TLMVPHC]?QF[NP][0-9]+)\b', text)
        if match:
            return "SMD", f"Package({match.group(1)})"
        match = re.search(r'\b([A-Z]*BGA[0-9]+)\b', text)
        if match:
            return "SMD", f"Package({match.group(1)})"
        
        # 7. SOT/SOD/SOP/SOIC + 숫자 패턴
        match = re.search(r'\b(SO[TDPIC]+[- ]?[0-9]+)\b', text)
        if match:
            return "SMD", f"Package({match.group(1)})"
        
        # 8. DO-214 계열 (SMD 다이오드)
        if re.search(r'\bDO-?21[489]\b', text):
            return "SMD", "Package(DO-214 Series)"
        
        # 9. 크리스탈 패키지 확인
        for pkg in THT_CRYSTAL_PACKAGES:
            if re.search(r'\b' + re.escape(pkg) + r'\b', text):
                return "DIP", f"Crystal Pkg({pkg})"
        for pkg in SMD_CRYSTAL_PACKAGES:
            if re.search(r'\b' + re.escape(pkg) + r'\b', text):
                return "SMD", f"Crystal Pkg({pkg})"
        
        # === [로직 2] 카테고리 기반 추론 ===
        
        # 10-a. SMD 전해콘덴서 확인 (SMD 버전은 SMD로 분류)
        for smd_elec_kw in SMD_ELECTROLYTIC_KEYWORDS:
            if smd_elec_kw.upper() in text:
                return "SMD", f"SMD 전해콘덴서({smd_elec_kw})"
        
        # 10-b. 일반 전해콘덴서 확인 (VBA: DIP로 분류)
        for elec_kw in ELECTROLYTIC_KEYWORDS:
            if elec_kw.upper() in text:
                return "DIP", f"전해콘덴서({elec_kw})"
        
        # 11. 확인필요 부품 키워드 (커넥터, 스위치, 세라믹 등) - passive 체크보다 먼저!
        for uncertain_kw in UNCERTAIN_PART_KEYWORDS:
            if uncertain_kw.upper() in text:
                return "확인필요", f"부품타입 확인필요({uncertain_kw})"
        
        # 12. 카테고리가 SMD 부품인 경우 (칩저항, 칩콘덴서 등 - 명시적인 것만)
        for smd_cat in MountingClassifier.SMD_CATEGORIES:
            if smd_cat.upper() in text:
                return "SMD", f"Category({smd_cat})"
        
        # 13. 카테고리가 DIP 부품인 경우
        for dip_cat in MountingClassifier.DIP_CATEGORIES:
            if dip_cat.upper() in text:
                return "DIP", f"Category({dip_cat})"
        
        # 14. IC 계열은 현대적으로 대부분 SMD
        for ic_kw in MountingClassifier.IC_KEYWORDS:
            if ic_kw.upper() in text:
                return "SMD", f"IC Type({ic_kw})"
        
        # 15. 저항/콘덴서/인덕터/LED/다이오드 - 패키지 정보 없으면 확인필요
        # (기존: 무조건 SMD -> 변경: 확인필요로 안내)
        passive_keywords_uncertain = ['콘덴서', '캐패시터', 'CAPACITOR', 'CAP']  # 세라믹/전해 불명확
        for pk in passive_keywords_uncertain:
            if pk.upper() in text:
                return "확인필요", f"패키지 확인필요({pk})"
        
        # 저항, 인덕터, LED, 다이오드는 SMD가 더 일반적
        passive_keywords_smd = ['저항', '인덕터', 'LED', '다이오드',
                               'RESISTOR', 'INDUCTOR', 'DIODE', 'RES', 'IND']
        for pk in passive_keywords_smd:
            if pk.upper() in text:
                return "SMD(추정)", f"Passive({pk}) - 일반적 SMD"
        
        # === [로직 3] RefDes 기반 추론 (VBA 매크로에서 추가) ===
        if refdes:
            prefix = MountingClassifier._extract_refdes_prefix(refdes)
            
            if prefix:
                # SMD 추정 부품
                if prefix in MountingClassifier.REFDES_SMD_PREFIXES:
                    return "SMD(추정)", f"RefDes({prefix}) - 일반적 칩부품"
                
                # 확인 필요 부품 (커넥터, 스위치 등)
                if prefix in MountingClassifier.REFDES_UNCERTAIN_PREFIXES:
                    return "확인필요", f"RefDes({prefix}) - 커넥터/스위치류"
                
                # DIP 추정 부품 (Hole, Mechanical)
                if prefix in MountingClassifier.REFDES_DIP_PREFIXES:
                    return "DIP", f"RefDes({prefix}) - 기계부품"
        
        return "미확정", "판단 근거 없음"
    
    @staticmethod
    def classify_simple(spec: str = "", package: str = "", mounting: str = "", 
                        mpn: str = "", category: str = "", refdes: str = "") -> str:
        """
        기존 호환용 간단 분류 (결과만 반환)
        """
        result, _ = MountingClassifier.classify(spec, package, mounting, mpn, category, refdes)
        return result


class PartResolver:
    """통합 부품 정보 조회기 - 웹 검색 우선"""
    
    def __init__(self, config: Dict[str, Any] = None):
        if config is None:
            config = load_config()
        
        self.config = config
        self.cache = CacheManager()
        self.classifier = MountingClassifier()
        
        # 웹 검색 클라이언트 (기본 활성화)
        use_web_search = config.get('use_web_search', True)
        self.web_search = WebSearchResolver(enabled=use_web_search)
        
        # API 클라이언트 (선택적 백업)
        self.digikey = DigiKeyAPI(
            get_env_or_config('digikey_client_id', config),
            get_env_or_config('digikey_client_secret', config)
        )
        self.mouser = MouserAPI(
            get_env_or_config('mouser_api_key', config)
        )
        
        self.api_delay = config.get('api_call_delay', 0.5)
        self.use_cache = False # config.get('use_cache', True)
        self.cache_ttl = config.get('cache_ttl_days', 30)
        self.use_api_fallback = config.get('use_api_fallback', False)  # API 폴백 비활성화 기본값
    
    def resolve(self, mpn: str = "", digi_pn: str = "", mouser_pn: str = "",
                spec: str = "", package: str = "", category: str = "",
                refdes: str = "", manufacturer: str = "") -> PartInfo:
        """
        부품 정보 조회 (웹 검색 우선)
        
        Args:
            mpn: 제조사 부품번호
            digi_pn: Digi-Key 부품번호
            mouser_pn: Mouser 부품번호
            spec: 스펙 (휴리스틱 분류용)
            package: 패키지 (휴리스틱 분류용)
            category: 부품 카테고리/품목 (휴리스틱 분류용)
            refdes: Reference Designator (위치, RefDes 기반 추론용)
            manufacturer: 제조사명 (웹 검색용)
            
        Returns:
            PartInfo 객체
        """
        # 캐시 확인
        cache_key = self.cache.make_key(mpn, digi_pn, mouser_pn)
        if cache_key and self.use_cache:
            cached = self.cache.get(cache_key, self.cache_ttl)
            if cached:
                cached.source = "cache"
                # 캐시에서도 mounting_type 항상 재분류 (DB 로직 등 최신 로직 반영을 위해)
                # 기존: if not cached.mounting_type or cached.mounting_type == "미확정":
                mounting_type, classification_reason = self.classifier.classify(
                    spec, cached.package or package, cached.mounting, mpn, category, refdes
                )
                cached.mounting_type = mounting_type
                cached.classification_reason = classification_reason
                
                return cached
        
        info = PartInfo()
        
        # 검색어 결정
        search_term = mpn or digi_pn or mouser_pn or ""
        
        # MPN이 없으면 스펙에서 추출 시도
        if not search_term and spec and spec.strip():
            potential_mpns = re.findall(r'[A-Z0-9][A-Z0-9\-_]{5,}[A-Z0-9]', spec.upper())
            if potential_mpns:
                search_term = potential_mpns[0]
            else:
                search_term = spec.strip()
        
        # === 1단계: 웹 검색 (DuckDuckGo) ===
        if self.web_search.is_configured() and search_term:
            result = self.web_search.search_part(search_term, manufacturer)
            if result:
                info = result
        
        # === 2단계: API 폴백 (선택적) ===
        if not info.official_name and self.use_api_fallback and search_term:
            for term in [mpn, digi_pn, mouser_pn]:
                if not term or not term.strip():
                    continue
                    
                # Digi-Key
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
        
        # === 3단계: 휴리스틱 처리 ===
        if not info.official_name:
            info.official_name = mpn or digi_pn or mouser_pn or ""
            if not info.source:
                info.source = "heuristic"
        
        if not info.supplier:
            if digi_pn:
                info.supplier = "Digi-Key"
                info.supplier_pn = digi_pn
            elif mouser_pn:
                info.supplier = "Mouser"
                info.supplier_pn = mouser_pn
        
        # 장착방식 분류 (웹 검색 결과의 mounting 정보 활용)
        mounting_type, classification_reason = self.classifier.classify(
            spec, info.package or package, info.mounting, mpn, category, refdes
        )
        info.mounting_type = mounting_type
        info.classification_reason = classification_reason
        
        # 캐시 저장
        if cache_key and self.use_cache:
            self.cache.set(cache_key, info)
        
        return info
    
    def get_api_status(self) -> Dict[str, bool]:
        """API/검색 설정 상태 확인"""
        return {
            'web_search': self.web_search.is_configured(),
            'digikey': self.digikey.is_configured(),
            'mouser': self.mouser.is_configured(),
        }
