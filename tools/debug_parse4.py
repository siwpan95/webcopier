#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐步调试 - 不清理直接解析"""
from bs4 import BeautifulSoup
import requests, re

url = 'https://www.studycpp.cn/basic/chapter0/introduction-to-site/'
headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, headers=headers, timeout=30)
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

card = soup.select_one('.col-md-8.card')

print("=== Direct children count:", len(list(card.find_all(recursive=False))), "===")
for child in card.find_all(recursive=False):
    tag = child.name if hasattr(child, 'name') else 'TEXT'
    cls = child.get('class', []) if hasattr(child, 'get') else []
    print(f"  <{tag}> class={cls} id={child.get('id','')}")

print()

# 测试: 不清理直接 find_all
found = card.find_all(['h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'ul', 'ol', 'table', 'blockquote', 'div', 'hr'])
print(f"=== Without cleanup: find_all found {len(found)} elements ===")
for elem in found[:20]:
    print(f"  <{elem.name}> {elem.get_text(strip=True)[:80]}")

# 测试: 逐步清理
print("\n=== Step by step cleanup ===")

# Step 1: remove nav, footer, etc
card2 = soup.select_one('.col-md-8.card')  # fresh copy ... wait no this is same soup
# Let me just clone explicitly
soup2 = BeautifulSoup(resp.text, 'html.parser')
card2 = soup2.select_one('.col-md-8.card')

# Only remove the h1
h1 = card2.find('h1')
if h1:
    print(f"Removing h1: {h1.get_text(strip=True)}")
    h1.decompose()

found2 = card2.find_all(['h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'ul', 'ol', 'table', 'blockquote', 'div', 'hr'])
print(f"After removing h1 only: find_all found {len(found2)} elements")
for elem in found2[:10]:
    print(f"  <{elem.name}> {elem.get_text(strip=True)[:80]}")
