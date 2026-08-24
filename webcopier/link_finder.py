#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
链接发现模块：sitemap 解析、页面链接提取
"""

from urllib.parse import urljoin, urlparse
import re
from bs4 import BeautifulSoup
from .http_client import http_get


# 已知的非内容资源扩展名（不应抓取）
_SKIP_EXTS = frozenset({
    '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',
    '.pdf', '.xml', '.rss', '.json', '.woff', '.woff2', '.ttf', '.eot',
    '.zip', '.mp4', '.mp3', '.webp', '.webm', '.avif', '.gz', '.bz2',
})

# 内容类路径标记关键词
_CONTENT_MARKERS = [
    'article', 'post', 'blog', 'news', 'topic',
    'read', 'story', 'page', 'detail', 'entry',
    'archives', 'note', 'essay', 'chapter',
]


def _is_content_url(full_url: str) -> bool:
    """判断 URL 是否为内容页（非资源文件）"""
    parsed = urlparse(full_url)
    path_lower = parsed.path.lower()

    # 排除已知资源扩展名
    for ext in _SKIP_EXTS:
        if path_lower.endswith(ext):
            return False

    # 明确的页面扩展名或目录
    if path_lower.endswith(('.html', '.htm', '.php', '.asp', '.jsp')) or path_lower.endswith('/'):
        return True

    # 包含内容关键词
    for marker in _CONTENT_MARKERS:
        if f'/{marker}' in path_lower or f'/{marker}/' in path_lower:
            return True

    # 年份类路径 /2024/03/15/slug
    if re.search(r'/\d{4}(?:/\d{2}(?:/\d{2})?)?/', path_lower):
        return True

    # 有 slug 风格路径段（至少包含字母，不纯数字）
    segments = [s for s in path_lower.strip('/').split('/') if s]
    if segments:
        last = segments[-1]
        if any(c.isalpha() for c in last):
            return True

    return False


def discover_sitemap(base_url, headers, proxies=None, max_recursion=3,
                     log=None):
    """
    尝试读取 /sitemap.xml 等路径，返回所有链接列表。
    支持 sitemap index 递归解析（最多 max_recursion 层）。

    Args:
        base_url: 网站根 URL
        headers: 请求头
        proxies: 代理
        max_recursion: 最大递归深度
        log: 日志回调函数

    Returns:
        list[str]: 发现的链接列表
    """
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [
        "/sitemap.xml", "/sitemap_index.xml", "/sitemap.txt",
        "/sitemap1.xml", "/post-sitemap.xml", "/page-sitemap.xml",
    ]
    found = []
    _log = log or print

    def _parse_sitemap_xml(xml_text, depth=0):
        if depth >= max_recursion:
            return
        soup = BeautifulSoup(xml_text, "lxml")
        # 直接链接
        for loc in soup.find_all("loc"):
            link = loc.get_text(strip=True)
            if link and link not in found:
                found.append(link)
        # 子 sitemap
        for sm in soup.find_all("sitemap"):
            sub = sm.find("loc")
            if sub:
                sub_url = sub.get_text(strip=True)
                try:
                    sr = http_get(sub_url, headers, timeout=15, proxies=proxies)
                    _parse_sitemap_xml(sr.text, depth + 1)
                except Exception:
                    pass

    for cand in candidates:
        url = base + cand
        try:
            resp = http_get(url, headers, timeout=15, proxies=proxies)
            _log(f"  [OK] 发现 sitemap: {url}")
            _parse_sitemap_xml(resp.text)
            if found:
                break
        except Exception as e:
            _log(f"  [WARN] sitemap 读取失败 ({cand}): {e}")
    return found


def extract_page_links(html, base_url, domain=None):
    """
    从 HTML 中提取同域名的页面链接。

    Args:
        html: HTML 文本
        base_url: 基准 URL（用于 urljoin）
        domain: 限制域名（None 则自动从 base_url 提取）

    Returns:
        list[str]: 去重后的链接列表
    """
    if domain is None:
        domain = urlparse(base_url).netloc
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if (parsed.netloc == domain
                and not parsed.fragment
                and _is_content_url(full_url)
                and full_url not in seen):
            seen.add(full_url)
            links.append(full_url)
    return links


def bfs_crawl(index_url, headers, proxies=None, max_depth=1,
              max_per_layer=200, log=None, cancel_check=None):
    """
    BFS 广度优先爬取页面链接。

    Args:
        index_url: 起始 URL
        headers: 请求头
        proxies: 代理
        max_depth: 最大爬取深度
        max_per_layer: 每层最多发现的链接数
        log: 日志回调
        cancel_check: 取消检查回调（返回 True 则停止）

    Returns:
        list[str]: 所有发现的链接（去重保序）
    """
    _log = log or print
    domain = urlparse(index_url).netloc

    resp = http_get(index_url, headers, timeout=30, proxies=proxies)
    links = extract_page_links(resp.text, index_url, domain)

    if max_depth <= 1:
        return links

    _log(f"  [STATS] BFS 深度爬取（最多 {max_depth} 层）...")
    crawled = set(links)
    frontier = list(links)
    for depth in range(1, max_depth):
        if cancel_check and cancel_check():
            break
        next_frontier = []
        for url in frontier:
            if cancel_check and cancel_check():
                break
            try:
                r = http_get(url, headers, timeout=15, proxies=proxies)
                new_links = extract_page_links(r.text, url, domain)
                for link in new_links:
                    if link not in crawled:
                        crawled.add(link)
                        next_frontier.append(link)
            except Exception:
                pass
        frontier = next_frontier[:max_per_layer]
        links.extend(frontier)
        _log(f"  [STATS] 第 {depth+1} 层发现 {len(frontier)} 个新链接")
        if not frontier:
            break

    # 去重保持顺序
    return list(dict.fromkeys(links))
