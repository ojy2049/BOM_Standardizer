#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
웹 스크래핑을 통한 전자부품 정보 수집
requests + BeautifulSoup 기반 단순 스크래핑
"""

import re
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False
    print("[WebScraper] requests 또는 beautifulsoup4 설치 필요")


@dataclass
class ScrapedPartInfo:
    """스크래핑된 부품 정보"""
    mpn: str = ""
    manufacturer: str = ""
    description: str = ""
    package: str = ""
    mounting_type: str = ""  # SMD, Through Hole
    category: str = ""
    datasheet_url: str = ""
    source: str = ""  # octopart, lcsc, etc.
    
    def is_valid(self) -> bool:
        """유효한 결과인지 확인"""
        return bool(self.mpn or self.manufacturer or self.description)


class PartScraper:
    """전자부품 사이트 스크래핑"""
    
    # 제조사 정규화
    MANUFACTURER_ALIASES = {
        'yeonho electronics': 'Yeonho',
        'yeonho': 'Yeonho',
        '연호': 'Yeonho',
        'samsung electro-mechanics': 'Samsung',
        'samsung': 'Samsung',
        'murata manufacturing': 'Murata',
        'murata': 'Murata',
        'texas instruments': 'Texas Instruments',
        'stmicroelectronics': 'STMicroelectronics',
    }
    
    # 신뢰할 수 있는 제조사 목록
    KNOWN_MANUFACTURERS = [
        'Yeonho', 'Samsung', 'Murata', 'TDK', 'Vishay', 'Rohm',
        'Texas Instruments', 'STMicroelectronics', 'Microchip', 'NXP',
        'Infineon', 'ON Semiconductor', 'Analog Devices', 'Maxim',
        'Panasonic', 'Nichicon', 'Kemet', 'AVX', 'Bourns',
        'Amphenol', 'TE Connectivity', 'Molex', 'Hirose', 'JST', 'JAE',
        'Omron', 'Alps', 'Kyocera', 'Taiyo Yuden', 'Yageo',
    ]
    
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session() if SCRAPER_AVAILABLE else None
        if self.session:
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/json',
                'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
            })
    
    def search_lcsc_api(self, mpn: str) -> Optional[ScrapedPartInfo]:
        """
        LCSC API를 통한 부품 검색
        
        Args:
            mpn: 부품번호
            
        Returns:
            ScrapedPartInfo 또는 None
        """
        if not self.session:
            return None
        
        try:
            # LCSC 검색 API
            url = "https://wmsc.lcsc.com/ftps/wm/product/search/global"
            params = {
                'keyword': mpn,
                'pageNumber': 1,
                'pageSize': 10,
            }
            
            resp = self.session.get(url, params=params, timeout=self.timeout)
            
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            
            # 결과 파싱
            products = data.get('result', {}).get('productList', [])
            if not products:
                return None
            
            # 첫 번째 결과 사용
            prod = products[0]
            
            info = ScrapedPartInfo(source='lcsc')
            info.mpn = prod.get('productCode', '') or prod.get('productModel', '') or mpn
            info.manufacturer = self._normalize_manufacturer(prod.get('brandNameEn', ''))
            info.description = prod.get('productDescEn', '')[:500]
            info.package = prod.get('encapStandard', '')
            info.category = prod.get('parentCatalogName', '')
            
            # 마운팅 타입 추론
            package_lower = info.package.lower()
            desc_lower = info.description.lower()
            if any(kw in package_lower + desc_lower for kw in ['smd', 'smt', 'surface']):
                info.mounting_type = 'SMD'
            elif any(kw in package_lower + desc_lower for kw in ['dip', 'through hole', 'tht']):
                info.mounting_type = 'Through Hole'
            
            # 데이터시트 URL
            datasheet = prod.get('pdfUrl', '')
            if datasheet:
                info.datasheet_url = datasheet if datasheet.startswith('http') else f"https://datasheet.lcsc.com{datasheet}"
            
            return info if info.is_valid() else None
            
        except Exception as e:
            print(f"[WebScraper] LCSC API 오류: {e}")
            return None
    
    def search_octopart_html(self, mpn: str) -> Optional[ScrapedPartInfo]:
        """
        Octopart HTML 페이지 분석
        
        Args:
            mpn: 부품번호
            
        Returns:
            ScrapedPartInfo 또는 None
        """
        if not self.session:
            return None
        
        try:
            url = f"https://octopart.com/search?q={mpn}"
            resp = self.session.get(url, timeout=self.timeout)
            
            if resp.status_code != 200:
                return None
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            info = ScrapedPartInfo(source='octopart')
            
            # 검색 결과에서 정보 추출
            # Octopart는 JavaScript 렌더링이 필요할 수 있음
            # 기본 HTML에서 추출 가능한 정보만
            
            # 제조사 찾기
            mfr_patterns = [
                r'manufacturer["\s:]+([A-Za-z\s]+)',
                r'"brand"["\s:]+([A-Za-z\s]+)',
            ]
            
            page_text = resp.text
            for pattern in mfr_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    mfr = match.group(1).strip()
                    if mfr and len(mfr) > 2:
                        info.manufacturer = self._normalize_manufacturer(mfr)
                        break
            
            # MPN 찾기
            if mpn.upper() in page_text.upper():
                info.mpn = mpn
            
            # 설명 찾기 (메타 태그에서)
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                info.description = meta_desc.get('content', '')[:200]
            
            return info if info.is_valid() else None
            
        except Exception as e:
            print(f"[WebScraper] Octopart 오류: {e}")
            return None
    
    def search_alldatasheet(self, mpn: str) -> Optional[ScrapedPartInfo]:
        """
        AllDatasheet에서 부품 검색
        
        Args:
            mpn: 부품번호
            
        Returns:
            ScrapedPartInfo 또는 None
        """
        if not self.session:
            return None
        
        try:
            url = f"https://www.alldatasheet.com/view.jsp?Searchword={mpn}"
            resp = self.session.get(url, timeout=self.timeout)
            
            if resp.status_code != 200:
                return None
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            info = ScrapedPartInfo(source='alldatasheet')
            
            # 검색 결과 테이블에서 첫 번째 결과
            result_table = soup.find('table', class_='main')
            if result_table:
                first_row = result_table.find('tr', {'bgcolor': True})
                if first_row:
                    cells = first_row.find_all('td')
                    if len(cells) >= 3:
                        # MPN
                        mpn_cell = cells[0].find('a')
                        if mpn_cell:
                            info.mpn = mpn_cell.get_text(strip=True)
                        
                        # 제조사
                        info.manufacturer = self._normalize_manufacturer(cells[1].get_text(strip=True))
                        
                        # 설명
                        info.description = cells[2].get_text(strip=True)[:500]
                        
                        # 데이터시트 링크
                        link = cells[0].find('a', href=True)
                        if link:
                            href = link['href']
                            if not href.startswith('http'):
                                href = f"https://www.alldatasheet.com{href}"
                            info.datasheet_url = href
            
            return info if info.is_valid() else None
            
        except Exception as e:
            print(f"[WebScraper] AllDatasheet 오류: {e}")
            return None
    
    def search_all(self, mpn: str) -> Optional[ScrapedPartInfo]:
        """
        여러 사이트에서 순차 검색
        
        Args:
            mpn: 부품번호
            
        Returns:
            ScrapedPartInfo 또는 None
        """
        if not SCRAPER_AVAILABLE:
            print("[WebScraper] requests/beautifulsoup4 설치 필요")
            return None
        
        # 검색 순서: LCSC API (가장 안정적) -> AllDatasheet -> Octopart
        sources = [
            ('lcsc', self.search_lcsc_api),
            ('alldatasheet', self.search_alldatasheet),
            ('octopart', self.search_octopart_html),
        ]
        
        for name, search_func in sources:
            try:
                result = search_func(mpn)
                if result and result.is_valid():
                    print(f"[WebScraper] {name}에서 '{mpn}' 정보 발견")
                    return result
            except Exception as e:
                print(f"[WebScraper] {name} 검색 실패: {e}")
                continue
            
            time.sleep(0.5)  # 요청 간 딜레이
        
        return None
    
    def _normalize_manufacturer(self, name: str) -> str:
        """제조사명 정규화"""
        if not name:
            return ""
        
        name_lower = name.lower().strip()
        
        # 별칭 확인
        for alias, normalized in self.MANUFACTURER_ALIASES.items():
            if alias in name_lower:
                return normalized
        
        # 알려진 제조사 확인
        for known in self.KNOWN_MANUFACTURERS:
            if known.lower() in name_lower:
                return known
        
        # 첫 글자 대문자화
        return name.strip().title()


def is_scraper_available() -> bool:
    """스크래퍼 사용 가능 여부"""
    return SCRAPER_AVAILABLE


# 테스트용
if __name__ == '__main__':
    if not SCRAPER_AVAILABLE:
        print("pip install requests beautifulsoup4")
        exit(1)
    
    scraper = PartScraper()
    
    test_mpns = ['YDW200-16P', 'GRM155R71C104KA88D', 'STM32F103C8T6']
    
    for mpn in test_mpns:
        print(f"\n=== {mpn} 검색 ===")
        result = scraper.search_all(mpn)
        if result:
            print(f"  MPN: {result.mpn}")
            print(f"  제조사: {result.manufacturer}")
            print(f"  패키지: {result.package}")
            print(f"  마운팅: {result.mounting_type}")
            print(f"  설명: {result.description[:100]}...")
            print(f"  출처: {result.source}")
        else:
            print("  결과 없음")
