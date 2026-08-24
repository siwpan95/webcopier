#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深入查看页面结构"""
import requests
from bs4 import BeautifulSoup

url = 'https://www.studycpp.cn/basic/chapter0/introduction-to-site/'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
resp = requests.get(url, headers=headers, timeout=30)
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

# 进入 main-container
main_container = soup.select_one('#main-container')
if main_container:
    # 看看里面有什么
    children = main_container.find_all(recursive=False)[:10]
    for child in children:
        print(f"Tag: {child.name}, class={child.get('class', [])}, id={child.get('id', '')}")
        # 获取里面的文本开头
        text = child.get_text(strip=True)[:100] if child.get_text(strip=True) else ''
        if text:
            print(f"  Text: {text}")
        print()

# 也查看是否有 row/col 布局
print("--- Checking .row > .col structure ---")
for row in soup.select('.row')[:3]:
    cols = row.select('.col, .col-md, .col-lg, [class*="col-"]')
    for col in cols:
        text = col.get_text(strip=True)[:150]
        if text:
            print(f"Col class={col.get('class', [])}: {text}")
            print()

# 看看文章标题在哪里
print("--- Looking for article title ---")
for tag in soup.find_all(['h1', 'h2', 'h3'])[:5]:
    print(f"{tag.name}: {tag.get_text(strip=True)[:100]}")

# 查找页面上所有文本段落（p标签内容）
print("\n--- First few paragraphs ---")
for p in soup.find_all('p')[:5]:
    text = p.get_text(strip=True)
    if len(text) > 20:
        print(f"P: {text[:200]}")
