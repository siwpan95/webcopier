#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试 extract_content"""
import sys
sys.path.insert(0, '.')
from crawl_studycpp import *
from bs4 import BeautifulSoup
import requests

url = 'https://www.studycpp.cn/basic/chapter0/introduction-to-site/'
headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, headers=headers, timeout=30)
resp.encoding = 'utf-8'

# 手动模拟 extract_content 的第一步
soup = BeautifulSoup(resp.text, 'html.parser')
content_area = soup.select_one('.col-md-8.card')
if not content_area:
    content_area = soup.select_one('.card')

print("=== Direct children before filtering ===")
for child in content_area.find_all(recursive=False):
    tag = child.name if hasattr(child, 'name') else 'TEXT'
    cls = child.get('class', []) if hasattr(child, 'get') else []
    text = child.get_text(strip=True)[:80]
    print(f"  <{tag}> class={cls} => {text}")

# Now run the actual extraction
md = extract_content(resp.text, "0.0 网站简介")
print("\n=== Extracted Markdown ===")
print(md[:2000])
