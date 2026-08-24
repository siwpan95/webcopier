#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试页面解析"""
import requests
from bs4 import BeautifulSoup

url = 'https://www.studycpp.cn/basic/chapter0/introduction-to-site/'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
resp = requests.get(url, headers=headers, timeout=30)
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

print('Title:', soup.title.string if soup.title else 'N/A')
print()

# 查找主要内容区域
for selector in ['article', '.page-content', '.content', '.post-content', 'main', '.markdown-body', '[role=main]']:
    el = soup.select_one(selector)
    if el:
        print(f'Found selector: {selector}')
        print(f'Tag: {el.name}, Classes: {el.get("class", [])}')
        children = [c.name for c in el.find_all(recursive=False) if c.name]
        print(f'Direct children tags (first 20): {children[:20]}')
        text = el.get_text(strip=True)
        print(f'Text length: {len(text)} chars')
        print(f'First 300 chars: {text[:300]}')
        print()
        break
else:
    print('No common content selector found. Looking at body structure...')
    for div in soup.body.find_all('div', recursive=False)[:10]:
        cls = div.get('class', [])
        div_id = div.get('id', '')
        if cls or div_id:
            print(f'Body > div: class={cls}, id={div_id}')

# 也看看是否有特定结构的页面
print('\n--- Checking for .theme-default-content or similar ---')
for cls in ['.theme-default-content', '.page', '.doc-content', '.article-content']:
    el = soup.select_one(cls)
    if el:
        print(f'Found: {cls}')
        print(f'Text preview: {el.get_text(strip=True)[:200]}')
