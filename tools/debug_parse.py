#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试页面解析"""
import requests
from bs4 import BeautifulSoup

url = 'https://www.studycpp.cn/basic/chapter0/introduction-to-site/'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
resp = requests.get(url, headers=headers, timeout=30)
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

# 找 .card
card = soup.select_one('.card')
if card:
    print("=== .card found ===")
    print(f"Classes: {card.get('class')}")
    # 查看直接子元素
    for child in card.find_all(recursive=False):
        if hasattr(child, 'name'):
            print(f"  {child.name}: class={child.get('class', [])}  text_preview={child.get_text(strip=True)[:80]}")
else:
    print(".card NOT found")

# 也看看 col-md-8
print("\n=== .col-md-8 ===")
col = soup.select_one('.col-md-8')
if col:
    for child in col.find_all(recursive=False):
        if hasattr(child, 'name'):
            text = child.get_text(strip=True)[:100]
            print(f"  {child.name}: class={child.get('class', [])}  text={text}")
