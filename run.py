#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOM 정규화 도구 실행 스크립트
"""

import sys
import os

# 현재 디렉토리를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main_gui import main

if __name__ == "__main__":
    main()
