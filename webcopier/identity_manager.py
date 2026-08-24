#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
浏览器身份管理器 v5.2
从 identities.json 加载浏览器身份池，提供索引轮换和请求头构建。
身份数 = 重试次数上限。
"""

import json
import os
import random

from .constants import DEFAULT_HEADERS

# ============================================================
#  内置最小回退池（JSON 文件缺失时使用）
# ============================================================
_FALLBACK_IDENTITIES = [
    {
        "id": "chrome-win-130",
        "engine": "chrome", "platform": "desktop",
        "os": "Windows NT 10.0; Win64; x64",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "curl_impersonate": "chrome120",
        "headers": {
            "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
    },
    {
        "id": "firefox-win-133",
        "engine": "firefox", "platform": "desktop",
        "os": "Windows NT 10.0; Win64; x64; rv:133.0",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
              "Gecko/20100101 Firefox/133.0",
        "curl_impersonate": "firefox116",
        "headers": {},
    },
    {
        "id": "safari-mac-18_3",
        "engine": "safari", "platform": "desktop",
        "os": "Macintosh; Intel Mac OS X 10_15_7",
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
              "(KHTML, like Gecko) Version/18.3 Safari/605.1.15",
        "curl_impersonate": "safari17_0",
        "headers": {},
    },
    {
        "id": "edge-win-130",
        "engine": "edge", "platform": "desktop",
        "os": "Windows NT 10.0; Win64; x64",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
        "curl_impersonate": "edge101",
        "headers": {
            "sec-ch-ua": '"Chromium";v="130", "Microsoft Edge";v="130", "Not?A_Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
    },
    {
        "id": "chrome-android-130",
        "engine": "chrome", "platform": "mobile",
        "os": "Linux; Android 14; Pixel 8 Pro",
        "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
        "curl_impersonate": "chrome120",
        "headers": {
            "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
        },
    },
]


class BrowserIdentityManager:
    """浏览器身份池管理器。

    从 identities.json 加载身份列表，提供:
    - count: 身份总数（= 建议最大重试次数）
    - get_identity(index): 按索引取身份（支持轮转，索引取模）
    - get_random_identity(): 随机取一个身份
    - build_headers(identity, referer, cookie_str): 构建完整 HTTP 请求头
    """

    def __init__(self, identities_path=None):
        if identities_path is None:
            identities_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "identities.json")
        self._path = identities_path
        self._identities = []
        self._load()

    # -------------------------------------------------------
    #  加载
    # -------------------------------------------------------
    def _load(self):
        """从 JSON 文件加载身份池，缺失则用内置回退池。"""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded = data.get("identities", [])
            if loaded:
                self._identities = loaded
                return
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        # 回退
        self._identities = list(_FALLBACK_IDENTITIES)

    # -------------------------------------------------------
    #  属性
    # -------------------------------------------------------
    @property
    def count(self) -> int:
        """身份总数。"""
        return len(self._identities)

    @property
    def identities(self):
        """返回身份列表副本。"""
        return list(self._identities)

    # -------------------------------------------------------
    #  身份获取
    # -------------------------------------------------------
    def get_identity(self, index: int) -> dict:
        """按索引获取身份。超出范围自动取模（轮转）。"""
        if not self._identities:
            raise RuntimeError("身份池为空，无法获取身份")
        return self._identities[index % len(self._identities)]

    def get_random_identity(self) -> dict:
        """随机获取一个身份。"""
        if not self._identities:
            raise RuntimeError("身份池为空")
        return random.choice(self._identities)

    # -------------------------------------------------------
    #  UA 获取
    # -------------------------------------------------------
    def get_ua(self, identity: dict) -> str:
        """从身份字典中提取 User-Agent 字符串。"""
        return identity.get("ua", "")

    def get_random_ua(self) -> str:
        """随机获取一条 User-Agent。"""
        return self.get_ua(self.get_random_identity())

    # -------------------------------------------------------
    #  curl_cffi 指纹
    # -------------------------------------------------------
    def get_curl_impersonate(self, identity: dict) -> str:
        """获取 identity 对应的 curl_cffi 指纹别名。"""
        return identity.get("curl_impersonate", "chrome120")

    # -------------------------------------------------------
    #  请求头构建
    # -------------------------------------------------------
    def build_headers(self, identity: dict, referer=None,
                      cookie_str=None) -> dict:
        """基于 identity 构建完整 HTTP 请求头。

        Args:
            identity: 身份字典
            referer: 可选 Referer URL
            cookie_str: 可选 Cookie 字符串

        Returns:
            完整的请求头 dict（包含 _curl_impersonate 内部透传键，http_get 会 pop 掉）
        """
        headers = dict(DEFAULT_HEADERS)

        # UA
        headers["User-Agent"] = identity.get("ua", DEFAULT_HEADERS["User-Agent"])

        # 浏览器指纹头（sec-ch-ua / sec-ch-ua-mobile / sec-ch-ua-platform）
        id_headers = identity.get("headers", {})
        if id_headers:
            for key in ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"):
                if key in id_headers:
                    headers[key] = id_headers[key]
                else:
                    headers.pop(key, None)

        # Referer
        if referer:
            headers["Referer"] = referer

        # Cookie
        if cookie_str:
            headers["Cookie"] = cookie_str

        # curl_cffi 指纹透传（http_get 会在请求前 pop 掉，不会发送到服务器）
        headers["_curl_impersonate"] = identity.get("curl_impersonate", "")

        return headers


# ============================================================
#  模块级单例（方便跨模块复用，避免重复加载 JSON）
# ============================================================
_default_manager = None


def get_identity_manager() -> BrowserIdentityManager:
    """获取模块级单例 BrowserIdentityManager。"""
    global _default_manager
    if _default_manager is None:
        _default_manager = BrowserIdentityManager()
    return _default_manager
