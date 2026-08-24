#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速测试爬取前几页"""
import sys
sys.path.insert(0, '.')
from crawl_studycpp import *

# 只测试序章
test_chapters = {
    "chapter0": CHAPTERS["chapter0"]
}

original = CHAPTERS.copy()
CHAPTERS.clear()
CHAPTERS.update(test_chapters)

crawl_all()

# 恢复
CHAPTERS.clear()
CHAPTERS.update(original)
