#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP 客户端层 v5.1：请求发送、重试机制、代理支持、随机延迟
- 支持 requests + curl_cffi（TLS 指纹伪装）
- 代理认证、Cookie 注入、自适应重试
- 融合 crawlProject 反爬最佳实践
"""

import time
import random
import requests
from urllib.parse import urlparse
from .constants import DEFAULT_HEADERS, ANTICRAWL_STATUS_CODES

# ============================================================
#  可选依赖
# ============================================================
try:
    import requests_cache
    _HAS_REQUESTS_CACHE = True
except Exception:
    # v5.4 修复: requests_cache 导入时可能因环境内 bson 模块冲突抛出
    # AttributeError（非 ImportError），此处捕获一切异常实现优雅降级
    _HAS_REQUESTS_CACHE = False

# 模块级缓存 Session（惰性初始化，线程安全）
import threading
_cache_session = None
_cache_expire_after = 3600  # 默认 1 小时
_cache_lock = threading.Lock()


def _get_cache_session(expire_after=None):
    """惰性创建 requests-cache Session。

    v5.4 修复: 不同 cache_expire 参数会创建独立的缓存实例，
    避免第二次调用时被首次的过期时间覆盖。
    """
    global _cache_session, _cache_expire_after
    eff_expire = expire_after if expire_after is not None else _cache_expire_after
    with _cache_lock:
        # 已存在实例且过期时间匹配则复用，否则重建
        if _cache_session is not None and eff_expire == _cache_expire_after:
            return _cache_session
        _cache_expire_after = eff_expire
        _cache_session = requests_cache.CachedSession(
            "webcopier_cache",
            expire_after=eff_expire,
            allowable_methods=("GET",),
            allowable_codes=(200,),
        )
        return _cache_session

try:
    from curl_cffi import requests as curl_requests
    _HAS_CURL_CFFI = True
except ImportError:
    _HAS_CURL_CFFI = False


# ============================================================
#  代理解析
# ============================================================

def parse_proxy(proxy_str: str) -> dict:
    """
    解析代理字符串，支持多种格式：
      - http://host:port
      - http://user:pass@host:port
      - socks5://host:port
      - socks5://user:pass@host:port

    Returns:
        dict: {"http": ..., "https": ...} 可直接传给 requests
    """
    if not proxy_str or not proxy_str.strip():
        return None

    proxy_str = proxy_str.strip()

    # 判断协议
    proto = "http"
    for p in ["socks5", "https", "http"]:
        if proxy_str.startswith(f"{p}://"):
            proto = p
            break

    # 直接可以作为 http/https proxy 使用的字符串
    return {"http": proxy_str, "https": proxy_str}


# ============================================================
#  请求头构建
# ============================================================

def build_headers(identity=None, referer=None, cookie_str=None,
                  custom_ua=None, random_ua=False) -> dict:
    """
    构建请求头（v5.3 重构：接受 identity 字典作为唯一指纹来源）。

    Args:
        identity: 身份字典（来自 identity_manager），含 ua/headers/curl_impersonate
        referer: 可选 Referer URL
        cookie_str: 可选 Cookie 字符串
        custom_ua: 可选自定义 User-Agent 字符串（优先级高于 identity）
        random_ua: 是否使用随机 UA（预留接口，当前未启用随机池）

    Returns:
        完整请求头 dict
    """
    headers = dict(DEFAULT_HEADERS)

    # 从 identity 注入 UA 和指纹头
    if identity and isinstance(identity, dict):
        if identity.get("ua"):
            headers["User-Agent"] = identity["ua"]
        id_headers = identity.get("headers", {})
        if id_headers:
            for key in ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"):
                if key in id_headers:
                    headers[key] = id_headers[key]

    # custom_ua 优先级最高（覆盖 identity 和默认值）
    if custom_ua:
        headers["User-Agent"] = custom_ua

    # Referer
    if referer:
        headers["Referer"] = referer

    # Cookie
    if cookie_str:
        headers["Cookie"] = cookie_str

    return headers


def auto_referer(url) -> str:
    """根据 URL 自动生成 Referer（取域名根路径）"""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


# ============================================================
#  Cookie 工具
# ============================================================

def parse_cookie_string(cookie_str: str) -> dict:
    """
    将 Cookie 字符串解析为字典（参考 crawlProject 中间件）
    输入: "key1=val1; key2=val2"
    输出: {"key1": "val1", "key2": "val2"}
    """
    cookies = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


# ============================================================
#  HTTP 请求核心
# ============================================================

def http_get(url, headers=None, timeout=30, retries=1,
             proxies=None, random_delay=False, verify=True,
             use_curl_cffi=False, impersonate="chrome120",
             cookie_str=None, identity=None,
             use_cache=False, cache_expire=3600):
    """
    HTTP GET 请求（v5.3 重构：身份轮转由 engine 层管理，本函数最多重试 1 次连接错误）。

    Args:
        url: 目标 URL
        headers: 预构建请求头（None 则从 identity 构建）
        timeout: 超时秒数
        retries: 额外重试次数（引擎已管理主重试，此处仅处理瞬时连接错误，默认 1）
        proxies: 代理字典
        random_delay: 是否添加随机延迟
        verify: SSL 验证
        use_curl_cffi: 使用 curl_cffi TLS 指纹伪装
        impersonate: curl_cffi 指纹别名（如 identity 提供则优先使用其 curl_impersonate）
        cookie_str: Cookie 字符串
        identity: 身份字典（优先级最高）
        use_cache: 是否使用 requests-cache（同 URL 1 小时内不重复请求）
        cache_expire: 缓存过期秒数（默认 3600）

    Returns:
        requests.Response
    """
    # 从 identity 构建 headers（如果未提供预构建 headers）
    if headers is None and identity is not None:
        req_headers = build_headers(identity=identity, cookie_str=cookie_str)
    elif headers is not None:
        req_headers = dict(DEFAULT_HEADERS)
        req_headers.update(headers)
    else:
        req_headers = dict(DEFAULT_HEADERS)

    # identity 提供的 curl_cffi 指纹（引擎通过 headers["_curl_impersonate"] 透传）
    eff_impersonate = impersonate
    if "_curl_impersonate" in req_headers:
        val = req_headers.pop("_curl_impersonate")
        if val:
            eff_impersonate = val

    # 随机延迟
    if random_delay:
        jitter = random.uniform(0.5, 3.0)
        time.sleep(jitter)

    # Cookie 字符串注入
    if cookie_str:
        req_headers["Cookie"] = cookie_str

    # 选择后端
    if use_cache and _HAS_REQUESTS_CACHE:
        return _cached_get(url, req_headers, timeout,
                           proxies, random_delay, verify,
                           cache_expire)
    elif use_curl_cffi and _HAS_CURL_CFFI:
        return _curl_cffi_get(
            url, req_headers, timeout, retries,
            proxies, random_delay, verify, eff_impersonate, cookie_str)
    else:
        return _requests_get(
            url, req_headers, timeout, retries,
            proxies, random_delay, verify)


def _cached_get(url, headers, timeout, proxies,
                random_delay, verify, cache_expire):
    """使用 requests-cache 发送请求（同 URL 缓存期内直接返回）"""
    session = _get_cache_session(cache_expire)
    if random_delay:
        time.sleep(random.uniform(0.5, 3.0))
    resp = session.get(
        url, headers=headers, timeout=timeout,
        proxies=proxies, allow_redirects=True, verify=verify,
    )
    resp.raise_for_status()
    if resp.encoding is None or resp.encoding == "ISO-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp


def _requests_get(url, headers, timeout, retries, proxies,
                  random_delay, verify):
    """标准 requests 后端（含自适应重试和反爬处理）"""
    last_error = None
    for attempt in range(retries + 1):
        if attempt > 0:
            backoff = min(2 ** attempt, 60)
            time.sleep(backoff)
        try:
            resp = requests.get(
                url, headers=headers,
                timeout=timeout, proxies=proxies,
                allow_redirects=True, verify=verify,
            )
            resp.raise_for_status()
            # 自动检测编码（参考 crawlProject）
            if resp.encoding is None or resp.encoding == "ISO-8859-1":
                resp.encoding = resp.apparent_encoding or "utf-8"
            return resp
        except requests.exceptions.HTTPError as e:
            resp = e.response if hasattr(e, "response") else None
            # 反爬状态码：等待（身份轮换由 engine 层处理）
            if resp is not None and resp.status_code in ANTICRAWL_STATUS_CODES:
                wait_time = 10 * (attempt + 1)
                time.sleep(wait_time)
            last_error = e
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                ConnectionResetError,
                requests.exceptions.RequestException) as e:
            last_error = e
    raise last_error


def _curl_cffi_get(url, headers, timeout, retries, proxies,
                   random_delay, verify, impersonate, cookie_str):
    """
    使用 curl_cffi 发送请求，模拟真实浏览器的 TLS 指纹。
    参考 crawlProject 中「浏览器指纹检测 — 易九批」使用 curl_cffi 过 TLS 检测。
    """
    last_error = None
    for attempt in range(retries + 1):
        if attempt > 0:
            backoff = min(2 ** attempt, 60)
            time.sleep(backoff)
        try:
            resp = curl_requests.get(
                url, headers=headers,
                timeout=timeout, proxies=proxies,
                allow_redirects=True, verify=verify,
                impersonate=impersonate,
            )
            resp.raise_for_status()
            if resp.encoding is None or resp.encoding == "ISO-8859-1":
                resp.encoding = resp.apparent_encoding or "utf-8"
            return resp
        except Exception as e:
            if attempt < retries:
                pass  # 身份轮换由 engine 层管理
            last_error = e
    raise last_error


def http_post(url, headers=None, data=None, json=None,
              timeout=30, retries=3, proxies=None,
              random_delay=False, verify=True,
              use_curl_cffi=False, impersonate="chrome120",
              cookie_str=None):
    """
    HTTP POST 请求（v5.1 新增，用于登录等场景）。
    参数同 http_get，额外支持 data/json 负载。
    """
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)

    if cookie_str:
        req_headers["Cookie"] = cookie_str

    if random_delay:
        time.sleep(random.uniform(0.5, 2.0))

    if use_curl_cffi and _HAS_CURL_CFFI:
        client = curl_requests
    else:
        client = requests

    last_error = None
    for attempt in range(retries + 1):
        if attempt > 0:
            time.sleep(min(2 ** attempt, 60))
        try:
            resp = client.post(
                url, headers=req_headers,
                data=data, json=json,
                timeout=timeout, proxies=proxies,
                allow_redirects=True, verify=verify,
                **(dict(impersonate=impersonate) if use_curl_cffi and _HAS_CURL_CFFI else {}),
            )
            resp.raise_for_status()
            if resp.encoding is None or resp.encoding == "ISO-8859-1":
                resp.encoding = resp.apparent_encoding or "utf-8"
            return resp
        except Exception as e:
            last_error = e
    raise last_error
