#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会话管理模块 v5.1：Session 管理、Cookie 持久化、登录辅助
参考 crawlProject「模拟登录」与 Scrapy Cookie 中间件最佳实践：

- Session 池：维护带 Cookie 的 requests.Session，自动处理 Cookie 传递
- Cookie 持久化：CookieJar 的序列化与反序列化
- 登录辅助：自动检测登录表单 + 模拟提交
- 浏览器 Cookie 导入：从 Playwright/Chrome 导出 Cookie 到 requests
"""

import os
import json
import pickle
import time
from typing import Optional, Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .constants import VERSION
from .http_client import build_headers, parse_cookie_string


# ============================================================
#  Cookie 持久化工具
# ============================================================

def cookies_to_dict(session: requests.Session) -> dict:
    """
    将 Session 中的 Cookie 导出为字典。
    使用 requests 内置的 cookie jar 迭代器。
    """
    return requests.utils.dict_from_cookiejar(session.cookies)


def dict_to_cookies(session: requests.Session, cookie_dict: dict):
    """将 Cookie 字典加载到 Session 中"""
    for name, value in cookie_dict.items():
        session.cookies.set(name, value)


def save_cookies_to_file(session: requests.Session, filepath: str) -> bool:
    """
    保存 Session 的 Cookie 到 JSON 文件。
    参考 crawlProject：持久化登录状态，下次免登录。
    """
    try:
        cookies = cookies_to_dict(session)
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def load_cookies_from_file(session: requests.Session, filepath: str) -> bool:
    """
    从 JSON 文件加载 Cookie 到 Session。
    返回是否成功加载。
    """
    if not os.path.exists(filepath):
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        dict_to_cookies(session, cookies)
        return True
    except Exception:
        return False


# ============================================================
#  Cookie 字符串与 Session 互转
# ============================================================

def cookie_str_to_session(session: requests.Session,
                          cookie_str: str, domain: str = ""):
    """
    将浏览器导出的 Cookie 字符串注入到 Session。
    输入格式: "key1=val1; key2=val2; ..."（参考 crawlProject 中间件 Cookie 注入）
    """
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            session.cookies.set(k.strip(), v.strip(), domain=domain)


def session_to_cookie_str(session: requests.Session,
                          domain: Optional[str] = None) -> str:
    """将 Session Cookie 导出为请求头用的 Cookie 字符串"""
    if domain:
        cookies = session.cookies.get_dict(domain)
    else:
        cookies = cookies_to_dict(session)
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


# ============================================================
#  Session 管理器
# ============================================================

class SessionManager:
    """
    Session 管理器（v5.1 新增）
    管理带持久化 Cookie 的 requests.Session，支持多站点切换。

    用法:
        sm = SessionManager()
        sm.login_by_cookie_str("https://example.com", "sessionid=abc123; csrftoken=xyz")
        resp = sm.get("https://example.com/profile")
    """

    def __init__(self, cookie_dir: Optional[str] = None,
                 random_ua: bool = True,
                 proxy: Optional[str] = None,
                 log: Optional[callable] = None):
        """
        Args:
            cookie_dir: Cookie 文件存储目录
            random_ua: 是否默认随机 UA
            proxy: 代理地址
            log: 日志回调
        """
        self.cookie_dir = cookie_dir or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "session_cookies")
        os.makedirs(self.cookie_dir, exist_ok=True)

        self.random_ua = random_ua
        self.proxy = proxy
        self.log = log or print

        self._sessions: Dict[str, requests.Session] = {}
        self._active_domain: Optional[str] = None

    def _get_cookie_path(self, domain: str) -> str:
        safe = domain.replace(":", "_").replace("/", "_")
        return os.path.join(self.cookie_dir, f"session_{safe}.json")

    def get_session(self, domain: str) -> requests.Session:
        """获取或创建指定域名的 Session，自动恢复 Cookie"""
        if domain not in self._sessions:
            session = requests.Session()
            # 设置代理
            if self.proxy:
                session.proxies = {"http": self.proxy, "https": self.proxy}

            # 尝试恢复本地 Cookie
            cookie_path = self._get_cookie_path(domain)
            if os.path.exists(cookie_path):
                loaded = load_cookies_from_file(session, cookie_path)
                if loaded:
                    self.log(f"[COOKIE] 已恢复 {domain} 的 Cookie（{cookie_path}）")

            self._sessions[domain] = session

        self._active_domain = domain
        return self._sessions[domain]

    def switch(self, domain: str):
        """切换到指定域名的 Session"""
        self._active_domain = domain
        return self.get_session(domain)

    def active(self) -> Optional[requests.Session]:
        """获取当前活跃的 Session"""
        if self._active_domain:
            return self._sessions.get(self._active_domain)
        return None

    def save(self, domain: Optional[str] = None) -> bool:
        """保存指定域名（或当前活跃）的 Cookie 到文件"""
        domain = domain or self._active_domain
        if not domain or domain not in self._sessions:
            return False
        cookie_path = self._get_cookie_path(domain)
        result = save_cookies_to_file(self._sessions[domain], cookie_path)
        if result:
            self.log(f"[SAVE] 已保存 {domain} 的 Cookie")
        return result

    def save_all(self):
        """保存所有 Session 的 Cookie"""
        for domain in self._sessions:
            self.save(domain)

    def login_by_cookie_str(self, url_or_domain: str, cookie_str: str):
        """
        通过 Cookie 字符串登录（模拟已登录状态）
        参考 crawlProject Scrapy Cookie 中间件方案
        """
        domain = self._extract_domain(url_or_domain)
        session = self.get_session(domain)
        cookie_str_to_session(session, cookie_str, domain=domain)
        self.log(f"🔑 已注入 {domain} 的 Cookie（{len(cookie_str)} 字符）")

    def login_by_post(self, login_url: str,
                      username: str, password: str,
                      username_field: str = "username",
                      password_field: str = "password",
                      extra_data: Optional[dict] = None,
                      success_check: Optional[str] = None) -> bool:
        """
        通过 POST 表单模拟登录（自动检测隐藏域）

        Args:
            login_url: 登录接口 URL
            username: 用户名
            password: 密码
            username_field: 用户名字段名
            password_field: 密码字段名
            extra_data: 额外表单数据
            success_check: 成功标志文本（如"登录成功"），用于验证登录结果

        Returns:
            bool: 是否登录成功
        """
        domain = self._extract_domain(login_url)
        session = self.get_session(domain)

        # 1) 先 GET 登录页面，提取隐藏域（参考 crawlProject 模拟登录）
        headers = build_headers(random_ua=self.random_ua,
                                referer=login_url)
        try:
            login_page = session.get(login_url, headers=headers, timeout=15)
            login_page.raise_for_status()
            soup = BeautifulSoup(login_page.text, "lxml")

            # 提取隐藏域（如 __VIEWSTATE、csrfmiddlewaretoken 等）
            form_data = {}
            for hidden in soup.find_all("input", type="hidden"):
                name = hidden.get("name")
                value = hidden.get("value", "")
                if name:
                    form_data[name] = value

            # 提取 CSRF token（常见模式）
            meta_csrf = soup.find("meta", attrs={"name": "csrf-token"})
            if meta_csrf and meta_csrf.get("content"):
                form_data["csrf_token"] = meta_csrf["content"]
                form_data["_csrf"] = meta_csrf["content"]

            # 2) 填充用户名密码
            form_data[username_field] = username
            form_data[password_field] = password
            if extra_data:
                form_data.update(extra_data)

            # 3) 提交登录
            headers["Referer"] = login_url
            headers["Origin"] = self._extract_origin(login_url)
            headers["Content-Type"] = "application/x-www-form-urlencoded"

            resp = session.post(
                login_url, data=form_data, headers=headers,
                timeout=15, allow_redirects=True)
            resp.raise_for_status()

            # 4) 验证登录结果
            if success_check:
                logged_in = success_check.lower() in resp.text.lower()
            else:
                # 默认检查：Cookie 是否包含 session 相关字段
                cookies = cookies_to_dict(session)
                logged_in = any(
                    k.lower() in ["sessionid", "session", "token", "auth",
                                  "login", "userid", "uid", "sid"]
                    for k in cookies.keys()
                )

            if logged_in:
                self.save(domain)
                self.log(f"[OK] {domain} 登录成功！")
            else:
                self.log(f"[WARN] {domain} 可能登录失败，请检查参数")

            return logged_in

        except requests.exceptions.RequestException as e:
            self.log(f"[FAIL] {domain} 登录请求失败: {e}")
            return False

    def get(self, url: str, **kwargs) -> requests.Response:
        """通过活跃 Session 发起 GET 请求"""
        session = self.active()
        if not session:
            session = self.get_session(self._extract_domain(url))

        headers = build_headers(random_ua=self.random_ua,
                                referer=url)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        resp = session.get(url, headers=headers,
                           timeout=kwargs.pop("timeout", 30),
                           **kwargs)
        resp.raise_for_status()
        return resp

    def post(self, url: str, **kwargs) -> requests.Response:
        """通过活跃 Session 发起 POST 请求"""
        session = self.active()
        if not session:
            session = self.get_session(self._extract_domain(url))

        headers = build_headers(random_ua=self.random_ua,
                                referer=url)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        resp = session.post(url, headers=headers,
                            timeout=kwargs.pop("timeout", 30),
                            **kwargs)
        resp.raise_for_status()
        return resp

    # --------- helper ---------
    @staticmethod
    def _extract_domain(url: str) -> str:
        parsed = urlparse(url)
        return parsed.netloc or parsed.path.split("/")[0]

    @staticmethod
    def _extract_origin(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"


# ============================================================
#  浏览器 Cookie 导入工具
# ============================================================

def import_playwright_cookies(session: requests.Session,
                              pw_cookies: list):
    """
    将 Playwright 的 Cookie 列表导入 requests.Session。
    参考 crawlProject：用浏览器登录后再导出 Cookie 给 requests 使用。
    """
    for c in pw_cookies:
        session.cookies.set(
            name=c.get("name", ""),
            value=c.get("value", ""),
            domain=c.get("domain", ""),
            path=c.get("path", "/"),
            secure=c.get("secure", False),
        )
