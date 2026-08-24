#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度调试 extract_content"""
import sys
sys.path.insert(0, '.')
from crawl_studycpp import *
from bs4 import BeautifulSoup
import requests, re

url = 'https://www.studycpp.cn/basic/chapter0/introduction-to-site/'
headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, headers=headers, timeout=30)
resp.encoding = 'utf-8'
html = resp.text

# 完全模拟 extract_content
soup = BeautifulSoup(html, 'html.parser')
content_area = soup.select_one('.col-md-8.card')
if not content_area:
    content_area = soup.select_one('.card')

# Remove unwanted elements
for bad in content_area.find_all(['nav', 'footer', 'script', 'style', 'button', 'input']):
    bad.decompose()

# Remove 阅读量
for elem in content_area.find_all(string=re.compile(r'阅读量')):
    parent = elem.parent
    if parent:
        parent.decompose()

# Remove Waline
waline = content_area.find(id='waline')
if waline:
    waline.decompose()
    
# Remove wl-|waline|comment class elements  
print("=== Removing elements with waline/comment class ===")
for elem in content_area.find_all(class_=re.compile(r'wl-|waline|comment', re.I)):
    print(f"  Removing: {elem.name} class={elem.get('class', [])}")
    elem.decompose()

# Remove prev/next/pagination/navigation
print("=== Removing navigation elements ===")
for elem in content_area.find_all(class_=re.compile(r'prev|next|pagination|navigation', re.I)):
    print(f"  Removing: {elem.name} class={elem.get('class', [])}")
    elem.decompose()

# Remove h1
h1_tag = content_area.find('h1')
if h1_tag:
    title_text = h1_tag.get_text(strip=True)
    print(f"\nH1 title: {title_text}")
    h1_tag.decompose()

# Now list what's left
print("\n=== Remaining elements after cleanup ===")
for elem in content_area.find_all(recursive=False):
    tag = elem.name if hasattr(elem, 'name') else 'TEXT'
    cls = elem.get('class', []) if hasattr(elem, 'get') else []
    text = elem.get_text(strip=True)[:100]
    print(f"  <{tag}> class={cls} => {text}")

# Now try find_all
print("\n=== find_all results ===")
found = content_area.find_all(['h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'ul', 'ol', 'table', 'blockquote', 'div', 'hr'])
print(f"Found {len(found)} elements")
for elem in found:
    print(f"  <{elem.name}> parent={elem.parent.name if elem.parent else 'NONE'} text={elem.get_text(strip=True)[:100]}")
