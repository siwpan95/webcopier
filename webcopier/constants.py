#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局常量：字体、UA 池、默认请求头、版本号
"""

# ============================================================
#  版本
# ============================================================
VERSION = "5.5"
APP_TITLE = f"网页正文抓取工具 v{VERSION}"

# ============================================================
#  全局字体（统一使用支持中文的 Microsoft YaHei）
# ============================================================
FONT_NORMAL   = ("Microsoft YaHei", 9)
FONT_BOLD     = ("Microsoft YaHei", 9, "bold")
FONT_TITLE    = ("Microsoft YaHei", 15, "bold")
FONT_SMALL    = ("Microsoft YaHei", 8)
FONT_MONO     = ("Microsoft YaHei", 9)
FONT_ENTRY    = ("Microsoft YaHei", 10)
FONT_BTN      = ("Microsoft YaHei", 9)

# ============================================================
#  默认 HTTP 请求头（不含 UA，由 identity_manager 注入）
# ============================================================
# 注: UA 池、浏览器指纹、curl_cffi 映射已迁移至 identities.json + identity_manager.py
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}

# ============================================================
#  反爬状态码分类
# ============================================================
ANTICRAWL_STATUS_CODES = {403, 429, 503, 418, 502, 999}

# ============================================================
#  支持的提取方法列表
# ============================================================
EXTRACT_METHODS = ["trafilatura", "lxml_xpath", "bs4", "readability", "newspaper", "playwright"]

# ============================================================
#  支持的输出格式列表
# ============================================================
OUTPUT_FORMATS = ["txt", "md", "json", "jsonl", "html"]

# ============================================================
#  提取方法中文名映射
# ============================================================
METHOD_LABELS = {
    "trafilatura": "trafilatura（智能提取）",
    "lxml_xpath": "lxml+XPath（结构化提取）",
    "bs4": "BeautifulSoup（结构提取）",
    "readability": "readability（新闻优化）",
    "newspaper": "newspaper3k（新闻提取）",
    "playwright": "Playwright（动态渲染）",
}

METHOD_SHORT = {
    "trafilatura": "trafilatura",
    "lxml_xpath": "lxml+XPath",
    "bs4": "BeautifulSoup",
    "readability": "readability",
    "newspaper": "newspaper3k",
    "playwright": "Playwright",
}

FORMAT_LABELS = {
    "txt": "纯文本 (.txt)",
    "md": "Markdown (.md)",
    "json": "JSON (.json)",
    "jsonl": "JSONL (.jsonl)",
    "html": "HTML (.html)",
}

FORMAT_SHORT = {
    "txt": ".txt",
    "md": ".md",
    "json": ".json",
    "jsonl": ".jsonl",
    "html": ".html",
}
