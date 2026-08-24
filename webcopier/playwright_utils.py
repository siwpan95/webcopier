#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 工具模块 v5.3：高级反检测、本地浏览器复用、Cookie 管理、资源路由拦截
参考 crawlProject「自动化篇/playwright」的最佳实践：
- 反检测浏览器（stealth.min.js 全量 evasion，来自 puppeteer-extra）
- 资源路由拦截（block image/media/font，提速 3-5x）
- 本地浏览器复用（保持登录状态）
- Cookie 持久化与恢复
"""

import os
import json
import time
import random
from typing import Optional, Callable

try:
    from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

# ============================================================
#  stealth.min.js 路径（puppeteer-extra 全量反检测库，27KB）
# ============================================================
_STEALTH_PATH = os.path.join(os.path.dirname(__file__), "stealth.min.js")

# ============================================================
#  资源路由拦截（A1：block 图片/媒体/字体，参考 crawlProject 采集资料/auto.py）
# ============================================================
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


def _block_route(route):
    """同步路由拦截器：阻止非内容资源加载"""
    if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
        route.abort()
    else:
        route.continue_()

# ============================================================
#  浏览器启动选项
# ============================================================

DEFAULT_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-browser-side-navigation",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-default-apps",
    "--hide-scrollbars",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-first-run",
    "--safebrowsing-disable-auto-update",
]

# 高风险启动参数（需用户显式开启，默认不启用）
_UNSAFE_LAUNCH_ARGS = [
    "--disable-web-security",
]

# ============================================================
#  高级反检测浏览器工厂
# ============================================================

class AntiDetectBrowser:
    """
    反检测浏览器封装（v5.1 新增）
    参考 crawlProject 的反检测浏览器 + 本地浏览器方案

    用法:
        with AntiDetectBrowser() as browser:
            page = browser.new_page()
            page.goto("https://example.com")
            html = page.content()
    """

    def __init__(self, headless: bool = True,
                 use_local_chrome: bool = False,
                 cookie_file: Optional[str] = None,
                 user_data_dir: Optional[str] = None,
                 proxy: Optional[str] = None,
                 viewport: Optional[dict] = None,
                 locale: str = "zh-CN",
                 timeout: int = 30000,
                 block_resources: bool = True,
                 unsafe_args: bool = False,
                 log: Optional[Callable] = None):
        """
        Args:
            headless: 是否无头模式
            use_local_chrome: 是否使用本地 Chrome（保持登录状态）
            cookie_file: Cookie 文件路径（JSON 格式）
            user_data_dir: Chrome 用户数据目录（持久化 Session）
            proxy: 代理地址（格式: http://ip:port 或 socks5://ip:port）
            viewport: 视口 {"width": 1920, "height": 1080}
            locale: 语言区域
            timeout: 默认超时(ms)
            block_resources: 是否拦截非内容资源（image/media/font），提速 3-5x
            unsafe_args: 是否启用高风险启动参数（如 --disable-web-security），默认 False
            log: 日志回调函数
        """
        if not _HAS_PLAYWRIGHT:
            raise ImportError(
                "请先安装 playwright：pip install playwright && playwright install chromium")

        self.headless = headless
        self.use_local_chrome = use_local_chrome
        self.cookie_file = cookie_file
        self.user_data_dir = user_data_dir
        self.proxy = proxy
        self.viewport = viewport or {"width": 1920, "height": 1080}
        self.locale = locale
        self.timeout = timeout
        self.block_resources = block_resources
        self.log = log or print

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    def __enter__(self):
        self.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def launch(self):
        """启动浏览器并创建上下文"""
        self._playwright = sync_playwright().start()

        launch_kwargs = {"args": list(DEFAULT_LAUNCH_ARGS)}

        # 仅在用户显式开启时追加高风险参数
        if self.unsafe_args:
            launch_kwargs["args"].extend(_UNSAFE_LAUNCH_ARGS)
            self.log("[WARN] 已启用高风险启动参数（--disable-web-security）")

        if self.use_local_chrome:
            launch_kwargs["channel"] = "chrome"
            launch_kwargs["headless"] = False
        else:
            launch_kwargs["headless"] = self.headless

        self.log(f"[LAUNCH] 启动浏览器: headless={launch_kwargs.get('headless', True)}, "
                  f"local_chrome={self.use_local_chrome}")

        self._browser = self._playwright.chromium.launch(**launch_kwargs)

        # 创建上下文
        context_kwargs = {
            "viewport": self.viewport,
            "locale": self.locale,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        }

        if self.proxy:
            context_kwargs["proxy"] = {"server": self.proxy}

        # 从文件恢复 Cookie/Session
        if self.cookie_file and os.path.exists(self.cookie_file):
            try:
                context_kwargs["storage_state"] = self.cookie_file
                self.log(f"[COOKIE] 已加载 Cookie 状态: {self.cookie_file}")
            except Exception as e:
                self.log(f"[WARN] 加载 Cookie 失败: {e}")

        self._context = self._browser.new_context(**context_kwargs)

        # 注入反检测脚本（v5.3: 使用 stealth.min.js 全量 evasion，替代内联脚本）
        self._context.add_init_script(path=_STEALTH_PATH)

        # 资源路由拦截：屏蔽图片/媒体/字体，提速 3-5x
        if self.block_resources:
            self._context.route("**/*", _block_route)

        self.log("[OK] 浏览器已启动（stealth.min.js + 资源拦截）")

    def close(self, save_cookies: bool = True):
        """关闭浏览器，可选保存 Cookie"""
        if save_cookies and self.cookie_file:
            try:
                if self._context:
                    cookies = self._context.cookies()
                    state = self._context.storage_state()
                    with open(self.cookie_file, "w", encoding="utf-8") as f:
                        json.dump(state, f, ensure_ascii=False, indent=2)
                    self.log(f"[SAVE] Cookie 状态已保存: {self.cookie_file}")
            except Exception as e:
                self.log(f"[WARN] 保存 Cookie 失败: {e}")

        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

        self.log("[CLOSED] 浏览器已关闭")

    def new_page(self,
                 wait_until: str = "domcontentloaded",
                 inject_stealth: bool = True) -> "Page":
        """创建新页面（已注入反检测脚本）"""
        page = self._context.new_page()
        page.set_default_timeout(self.timeout)

        # 额外注入反检测（页面级别）
        if inject_stealth:
            page.add_init_script("""
                // 额外的页面级反检测
                Object.defineProperty(document, 'hidden', { get: () => false });
                Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
                Object.defineProperty(document, 'webkitHidden', { get: () => false });
                Object.defineProperty(document, 'webkitVisibilityState', { get: () => 'visible' });
            """)

        return page

    def smart_goto(self, page, url: str,
                   wait_selector: Optional[str] = None,
                   scroll_down: bool = True,
                   wait_extra: float = 1.5) -> "Page":
        """
        智能页面导航（参考 crawlProject 的 playwright 等待策略）
        - 多重等待：domcontentloaded -> 选择器 -> 滚动 -> 额外延时
        """
        self.log(f"[PAGE] 导航至: {url}")
        page.goto(url, timeout=self.timeout, wait_until="domcontentloaded")

        # 多重选择器等待
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=15000)
            except Exception:
                pass
        else:
            # 默认等待常见内容容器
            for sel in ["article", ".content", ".post", "main", "p", "body"]:
                try:
                    page.wait_for_selector(sel, timeout=8000)
                    break
                except Exception:
                    continue

        # 模拟人类滚动（触发懒加载）
        if scroll_down:
            try:
                page.evaluate("""
                    async () => {
                        await new Promise((resolve) => {
                            let totalHeight = 0;
                            const distance = 300;
                            const timer = setInterval(() => {
                                window.scrollBy(0, distance);
                                totalHeight += distance;
                                if (totalHeight >= document.body.scrollHeight) {
                                    clearInterval(timer);
                                    resolve();
                                }
                            }, 100);
                        });
                    }
                """)
                # 滚回顶部
                page.evaluate("window.scrollTo(0, 0)")
            except Exception:
                pass

        # 额外等待 JS 渲染
        if wait_extra > 0:
            time.sleep(wait_extra)

        return page

    @property
    def browser(self) -> "Browser":
        return self._browser

    @property
    def context(self) -> "BrowserContext":
        return self._context


# ============================================================
#  Cookie 管理器
# ============================================================

class CookieManager:
    """
    Cookie 持久化管理器（v5.1 新增）
    保存/加载网站 Cookie 状态，实现免登录访问
    """

    def __init__(self, cookie_dir: Optional[str] = None):
        if cookie_dir is None:
            cookie_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "cookies")
        self.cookie_dir = cookie_dir
        os.makedirs(self.cookie_dir, exist_ok=True)

    def _get_path(self, domain: str) -> str:
        """根据域名生成 Cookie 文件路径"""
        safe_name = domain.replace(":", "_").replace("/", "_")
        return os.path.join(self.cookie_dir, f"{safe_name}.json")

    def save_cookies(self, domain: str, cookies: list) -> bool:
        """保存 Cookie 列表到文件"""
        try:
            with open(self._get_path(domain), "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def load_cookies(self, domain: str) -> Optional[list]:
        """加载 Cookie 列表"""
        path = self._get_path(domain)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def save_storage_state(self, domain: str, context) -> bool:
        """保存完整的浏览器存储状态（含 Cookie、localStorage 等）"""
        try:
            state = context.storage_state()
            with open(self._get_path(domain), "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def get_storage_path(self, domain: str) -> str:
        """获取存储状态的路径（可直接传给 Playwright 的 storage_state）"""
        return self._get_path(domain)


# ============================================================
#  快捷函数
# ============================================================

def fetch_rendered_html(url: str,
                        headless: bool = True,
                        anti_detect: bool = True,
                        scroll_after_load: bool = True,
                        wait_selector: Optional[str] = None,
                        timeout: int = 30000,
                        block_resources: bool = True,
                        cookie_file: Optional[str] = None) -> str:
    """
    快捷函数：使用反检测浏览器获取渲染后的 HTML。
    参考 crawlProject playwright 的「采集资料」案例。

    Args:
        block_resources: 拦截图片/媒体/字体资源，提速 3-5x（默认 True）
    """
    with AntiDetectBrowser(
        headless=headless,
        cookie_file=cookie_file,
        timeout=timeout,
        block_resources=block_resources,
        log=print,
    ) as browser:
        page = browser.new_page()
        if anti_detect:
            browser.smart_goto(page, url, wait_selector=wait_selector,
                               scroll_down=scroll_after_load)
        else:
            page.goto(url, timeout=timeout)
        html = page.content()
    return html
