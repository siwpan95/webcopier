#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容提取器：六种正文提取方法
trafilatura / lxml+xpath / bs4 / readability / newspaper / Playwright

v5.1 增强版：融合 crawlProject 的 lxml+xpath 解析技巧、
中文编码自动检测、更多内容容器选择器
"""

import re

from bs4 import BeautifulSoup
from lxml import etree

# ============================================================
#  可选依赖
# ============================================================
try:
    from readability import Document as ReadabilityDoc
    _HAS_READABILITY = True
except ImportError:
    _HAS_READABILITY = False

try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

try:
    from newspaper import Article as NewsArticle
    _HAS_NEWSPAPER = True
except ImportError:
    _HAS_NEWSPAPER = False

import trafilatura
from .http_client import http_get


# ============================================================
#  通用工具函数
# ============================================================

def _clean_text(text: str) -> str:
    """统一文本清洗：多余空行、首尾空白"""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _auto_detect_encoding(resp):
    """自动检测编码（参考 crawlProject 的 encoding 处理）"""
    if resp.encoding is None or resp.encoding == "ISO-8859-1":
        # 优先使用 apparent_encoding，再回退 utf-8
        enc = getattr(resp, 'apparent_encoding', None)
        resp.encoding = enc if enc else "utf-8"
    return resp


# ============================================================
#  提取方法实现
# ============================================================

def extract_trafilatura(url, headers, proxies=None, random_delay=False):
    """使用 trafilatura 智能提取正文（推荐首选）"""
    resp = http_get(url, headers, timeout=30, proxies=proxies,
                    random_delay=random_delay)
    _auto_detect_encoding(resp)
    result = trafilatura.extract(
        resp.text,
        output_format='txt',
        include_comments=False,
        include_tables=True,
        with_metadata=True,
    )
    # with_metadata=True 返回 (text, metadata) 元组；需判断类型
    if isinstance(result, (list, tuple)):
        text = result[0] if result else ""
    else:
        text = result
    if not text:
        raise ValueError("trafilatura 未能提取到正文")
    return _clean_text(text)


def extract_lxml_xpath(url, headers, proxies=None, random_delay=False):
    """
    使用 lxml + XPath 结构化提取正文（v5.1 新增）
    融合 crawlProject 的 lxml/etree 最佳实践：
    - 树形解析 + 多级选择器回退
    - 移除 script/style/nav/footer 等噪声标签
    - 保留 p/div/li/h1~h6 段落结构
    """
    resp = http_get(url, headers, timeout=30, proxies=proxies,
                    random_delay=random_delay)
    _auto_detect_encoding(resp)

    html = resp.text
    tree = etree.HTML(html)

    # 1) 移除噪声标签（脚本、样式、导航、页脚、侧边栏、广告）
    noise_xpath = (
        '//script | //style | //noscript | //nav | //footer | '
        '//aside | //header | //form | //select | //button | '
        '//div[contains(@class,"sidebar")] | '
        '//div[contains(@class,"comment")] | '
        '//div[contains(@class,"ad")] | '
        '//div[contains(@class,"nav")] | '
        '//div[contains(@id,"sidebar")] | '
        '//div[contains(@id,"comment")] | '
        '//div[contains(@id,"footer")] | '
        '//div[contains(@id,"header")] '
    )
    for node in tree.xpath(noise_xpath):
        node.getparent().remove(node) if node.getparent() is not None else None

    # 2) 提取正文：多级选择器回退（参考 crawlProject 的 58 同城案例）
    content_selectors = [
        '//article',
        '//div[contains(@class,"content")]',
        '//div[contains(@class,"post")]',
        '//div[contains(@class,"article")]',
        '//div[contains(@class,"entry")]',
        '//div[contains(@id,"content")]',
        '//div[contains(@id,"post")]',
        '//div[contains(@id,"article")]',
        '//main',
        '//div[@class="detail"]',
        '//div[@class="text"]',
        '//body',
    ]

    text_parts = []
    for selector in content_selectors:
        nodes = tree.xpath(selector)
        if nodes:
            for node in nodes:
                # 提取所有文本段落（保留结构）
                parts = node.xpath(
                    './/p//text() | .//li//text() | '
                    './/h1//text() | .//h2//text() | .//h3//text() | '
                    './/h4//text() | .//h5//text() | .//h6//text() | '
                    './/span[not(ancestor::a)]//text() | '
                    './/div[not(.//div)]//text() | '
                    './/pre//text() | .//blockquote//text()'
                )
                for p in parts:
                    p = p.strip()
                    if p and len(p) > 1:
                        text_parts.append(p)
            if text_parts:
                break

    if not text_parts:
        # 最后回退：提取 body 中所有可见文本
        text_nodes = tree.xpath('//body//text()')
        text_parts = [t.strip() for t in text_nodes
                      if t.strip() and len(t.strip()) > 1]

    text = "\n".join(text_parts)
    return _clean_text(text)


def extract_bs4(url, headers, proxies=None, random_delay=False):
    """使用 BeautifulSoup 结构化提取正文（v5.1 增强版）"""
    resp = http_get(url, headers, timeout=30, proxies=proxies,
                    random_delay=random_delay)
    _auto_detect_encoding(resp)
    soup = BeautifulSoup(resp.text, "lxml")

    # 先清除噪声标签
    for tag in soup.find_all(['script', 'style', 'nav', 'footer',
                               'aside', 'header', 'noscript',
                               'form', 'select', 'button']):
        tag.decompose()
    for cls in ['sidebar', 'comment', 'ad', 'nav-bar', 'footer-nav']:
        for tag in soup.find_all(class_=re.compile(cls, re.I)):
            tag.decompose()

    # 多级内容容器选择器（扩展自 crawlProject 的 bs4 案例）
    article = (
        soup.find("article") or
        soup.find("div", class_=re.compile(r"content|post|article|entry|detail|text-body|main-body", re.I)) or
        soup.find("main") or
        soup.find("div", id=re.compile(r"content|post|article|entry|detail|main", re.I)) or
        soup.find("div", class_="detail") or
        soup.find("div", class_="text") or
        soup.find("body")
    )

    if article:
        # 保留段落语义
        for br in article.find_all("br"):
            br.replace_with("\n")
        for el in article.find_all(["p", "div", "li", "h1", "h2",
                                     "h3", "h4", "h5", "h6",
                                     "pre", "blockquote"]):
            el.append("\n")
        text = article.get_text("\n", strip=True)
        return _clean_text(text)
    return ""


def extract_readability(url, headers, proxies=None, random_delay=False):
    """使用 readability-lxml 新闻优化提取"""
    if not _HAS_READABILITY:
        raise ImportError("请先安装 readability-lxml：pip install readability-lxml")
    resp = http_get(url, headers, timeout=30, proxies=proxies,
                    random_delay=random_delay)
    _auto_detect_encoding(resp)
    doc = ReadabilityDoc(resp.text)
    title = doc.short_title()
    content = doc.summary()
    soup = BeautifulSoup(content, "lxml")
    text = soup.get_text("\n", strip=True)
    return f"【{title}】\n\n{_clean_text(text)}"


def extract_newspaper(url, headers, proxies=None, random_delay=False):
    """
    使用 newspaper3k 提取正文（v5.1 新增）
    擅长新闻、博客类网站的多语言提取
    """
    if not _HAS_NEWSPAPER:
        raise ImportError("请先安装 newspaper3k：pip install newspaper3k")
    resp = http_get(url, headers, timeout=30, proxies=proxies,
                    random_delay=random_delay)
    _auto_detect_encoding(resp)
    article = NewsArticle(url, language='zh')
    article.download(input_html=resp.text)
    article.parse()
    if article.text:
        return f"【{article.title}】\n\n{_clean_text(article.text)}"
    raise ValueError("newspaper3k 未能提取到正文")


def extract_playwright(url, headers=None, proxies=None, wait_selector="article",
                       timeout=30000, random_delay=False,
                       use_local_browser=False, anti_detect=False,
                       cookie_file=None):
    """
    使用 Playwright 动态渲染后提取正文（v5.3 重构）
    复用 playwright_utils.AntiDetectBrowser，消除与 playwright_utils 的功能重叠。

    参数透传说明：
    - anti_detect 控制是否注入 stealth.min.js（通过 AntiDetectBrowser 实现）
    - cookie_file 透传给 AntiDetectBrowser，自动恢复/保存 storage_state
    - use_local_browser 透传给 AntiDetectBrowser(use_local_chrome=...)
    - headers/proxies 仅为对齐统一入口 extract() 的兼容参数：
      Playwright 走自身网络栈，proxies 不生效（忽略）；headers 中
      User-Agent/Cookie 由 AntiDetectBrowser 身份池接管，同样忽略。
    """
    if not _HAS_PLAYWRIGHT:
        raise ImportError(
            "请先安装 playwright：pip install playwright && playwright install chromium")

    import time as _time
    import random as _r

    if random_delay:
        _time.sleep(_r.uniform(1.0, 3.0))
    else:
        _time.sleep(_r.uniform(0.5, 1.5))

    from .playwright_utils import AntiDetectBrowser

    with AntiDetectBrowser(
        headless=True,
        use_local_chrome=use_local_browser,
        cookie_file=cookie_file,
        timeout=timeout,
        block_resources=True,
        log=print,
    ) as browser:

        page = browser.new_page(inject_stealth=anti_detect)

        # smart_goto 已内置：domcontentloaded -> 选择器等待 -> 滚动 -> 额外延时
        browser.smart_goto(
            page, url,
            wait_selector=wait_selector,
            scroll_down=True,
            wait_extra=1.5,
        )

        html = page.content()

    # 渲染完成后用 trafilatura 提取正文
    text = trafilatura.extract(
        html,
        output_format='txt',
        include_comments=False,
        include_tables=True,
    )
    if not text:
        raise ValueError("Playwright 渲染后 trafilatura 仍无法提取正文")
    return _clean_text(text)


# ============================================================
#  提取方法注册表（v5.1 扩展为六种方法）
# ============================================================
EXTRACTOR_MAP = {
    "trafilatura": extract_trafilatura,
    "lxml_xpath": extract_lxml_xpath,
    "bs4": extract_bs4,
    "readability": extract_readability,
    "newspaper": extract_newspaper,
    "playwright": extract_playwright,
}

# 各方法的详细参数说明
EXTRACTOR_PARAMS = {
    "trafilatura": {},
    "lxml_xpath": {},
    "bs4": {},
    "readability": {},
    "newspaper": {},
    "playwright": {
        "wait_selector": ("等待渲染的CSS选择器", "article"),
        "timeout": ("页面加载超时(ms)", 30000),
        "use_local_browser": ("使用本地浏览器(保持登录状态)", False),
        "anti_detect": ("启用反检测脚本", False),
        "cookie_file": ("Cookie持久化文件路径", None),
    },
}


def extract(url, method, headers, proxies=None, random_delay=False,
            **kwargs):
    """
    统一提取入口，根据方法名分发到对应提取器。

    支持关键字参数透传（如 Playwright 的 anti_detect、cookie_file 等）
    """
    if method not in EXTRACTOR_MAP:
        raise ValueError(f"未知提取方法: {method}，可选: {list(EXTRACTOR_MAP.keys())}")
    return EXTRACTOR_MAP[method](url, headers, proxies=proxies,
                                  random_delay=random_delay, **kwargs)
