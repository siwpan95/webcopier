#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件输出模块 v5.4：保存 txt/md/json/jsonl/html，图片下载
- v5.4: 策略模式重构输出格式，新增 HTML 格式
- v5.4: download_images 统一走 http_client
"""

import os
import re
import json
import time
import threading
from datetime import datetime
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from .http_client import http_get, build_headers
from .constants import VERSION

# 文件写入锁（并发安全）
_write_lock = threading.Lock()


def url_to_filename(url, fallback_id):
    """将 URL 转换为安全的文件名"""
    name = url.rstrip("/").split("/")[-1] or f"page_{fallback_id}"
    name = re.sub(r'\?.*$', '', name)
    return re.sub(r'[\\/*?:"<>|]', "", name)[:80]


# ============================================================
#  输出格式注册表（策略模式，v5.4 重构）
# ============================================================

def _write_txt(fpath, text, url, timestamp):
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(f"来源: {url}\n")
        f.write(f"抓取时间: {timestamp}\n")
        f.write(f"引擎版本: WebCopier v{VERSION}\n")
        f.write(f"{'='*50}\n\n")
        f.write(text)


def _write_md(fpath, text, url, timestamp):
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(f"# 来源: {url}\n\n")
        f.write(f"> 抓取时间: {timestamp}  \n")
        f.write(f"> 引擎版本: WebCopier v{VERSION}\n\n")
        f.write("---\n\n")
        f.write(f"{text}\n")


def _write_json(fpath, text, url, timestamp):
    data = {
        "网址": url,
        "内容": text,
        "字符数": len(text),
        "抓取时间": timestamp,
        "提取引擎": f"WebCopier v{VERSION}",
    }
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _write_jsonl(fpath, text, url, timestamp):
    data = {
        "url": url,
        "content": text,
        "char_count": len(text),
        "timestamp": timestamp,
        "engine": f"WebCopier v{VERSION}",
    }
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def _write_html(fpath, text, url, timestamp):
    """v5.4 新增: HTML 格式输出，将纯文本包装为结构化的 HTML 文档"""
    escaped_url = url.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    paragraphs = text.split("\n\n")
    html_body = "\n".join(
        f"  <p>{p.replace(chr(10), '<br>')}</p>"
        for p in paragraphs if p.strip()
    )
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="generator" content="WebCopier v{VERSION}">
  <title>{url_to_filename(url, 0)}</title>
  <style>
    body {{ font-family: "Microsoft YaHei", sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.8; }}
    .meta {{ color: #666; font-size: 0.9em; border-bottom: 1px solid #ddd; padding-bottom: 10px; margin-bottom: 20px; }}
    p {{ margin: 1em 0; }}
  </style>
</head>
<body>
  <div class="meta">
    <p>来源: <a href="{escaped_url}">{escaped_url}</a></p>
    <p>抓取时间: {timestamp} | 引擎: WebCopier v{VERSION}</p>
  </div>
{html_body}
</body>
</html>
"""
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(html)


# 格式到写入函数的映射（策略模式）
_FORMAT_WRITERS = {
    "txt": _write_txt,
    "md": _write_md,
    "json": _write_json,
    "jsonl": _write_jsonl,
    "html": _write_html,
}

# 格式到扩展名的映射
_FORMAT_EXT = {
    "txt": ".txt",
    "md": ".md",
    "json": ".json",
    "jsonl": ".jsonl",
    "html": ".html",
}


def save_output(text, url, filename, save_dir, fmt):
    """
    根据格式保存内容到文件（v5.4 重构为策略模式）。

    Args:
        text: 正文内容
        url: 来源 URL
        filename: 文件名（不含扩展名）
        save_dir: 保存目录
        fmt: 格式（txt/md/json/jsonl/html）

    Returns:
        str: 保存的文件绝对路径
    """
    os.makedirs(save_dir, exist_ok=True)
    safe_name = re.sub(r'[\\/*?:"<>|]', "", filename)[:80]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ext = _FORMAT_EXT.get(fmt, ".txt")
    fpath = os.path.join(save_dir, f"{safe_name}{ext}")

    writer = _FORMAT_WRITERS.get(fmt)
    if writer is None:
        # 未知格式，默认纯文本
        fpath = os.path.join(save_dir, f"{safe_name}.txt")
        writer = _write_txt

    with _write_lock:
        writer(fpath, text, url, timestamp)

    return fpath


def download_images(url, headers, save_subdir, proxies=None,
                    limit=20, min_size_kb=1, random_ua=False,
                    log=None):
    """
    下载页面中的所有 <img> 到 save_subdir（v5.4: 统一走 http_client）。

    Args:
        url: 页面 URL
        headers: 请求头
        save_subdir: 图片保存目录
        proxies: 代理
        limit: 最多下载图片数
        min_size_kb: 最小文件大小（KB）
        random_ua: 是否使用随机 UA
        log: 日志回调

    Returns:
        int: 成功下载的图片数
    """
    _log = log or print
    os.makedirs(save_subdir, exist_ok=True)

    req_headers = build_headers(
        custom_ua=headers.get("User-Agent", "") if headers else None,
        random_ua=random_ua
    )
    try:
        resp = http_get(url, req_headers, timeout=30, proxies=proxies)
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        _log(f"  [WARN] 获取页面失败，跳过图片下载: {e}")
        return 0

    img_tags = soup.find_all("img", src=True, limit=limit)
    count = 0
    downloaded = set()
    for img in img_tags:
        img_url = urljoin(url, img["src"])
        if img_url in downloaded:
            continue
        try:
            # v5.4: 使用 http_client 替代裸 requests.get，享受重试+UA轮换
            r = http_get(img_url, req_headers, timeout=15, proxies=proxies)
            content_len = len(r.content)
            if content_len < min_size_kb * 1024:
                continue
            # 生成安全文件名
            parsed_url = urlparse(img_url)
            fname = os.path.basename(parsed_url.path) or f"img_{count+1}.jpg"
            fname = re.sub(r'[\\/*?:"<>|]', "_", fname)[:100]
            if "." not in fname:
                ct = r.headers.get("Content-Type", "")
                ext = ct.split("/")[-1].split(";")[0].strip() if "/" in ct else "jpg"
                fname += f".{ext}"
            # 去重：如果文件已存在则编号
            fpath = os.path.join(save_subdir, fname)
            if os.path.exists(fpath):
                base, ext = os.path.splitext(fname)
                fname = f"{base}_{count+1}{ext}"
                fpath = os.path.join(save_subdir, fname)
            with open(fpath, "wb") as f:
                f.write(r.content)
            downloaded.add(img_url)
            count += 1
        except Exception as e:
            _log(f"  [WARN] 图片下载失败 ({img_url[:60]}...): {e}")
    _log(f"  [IMG] 共下载 {count} 张图片 -> {save_subdir}")
    return count
