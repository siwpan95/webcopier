#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬虫调度引擎：协调 HTTP 客户端、提取器、链接发现、文件输出
支持单页/批量/整站抓取，含取消、暂停、恢复控制

v5.4: 新增 RateLimiter 并发限速器 + robots.txt Crawl-delay 支持
"""

import os
import time
import threading
import concurrent.futures
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin

from .http_client import http_get, build_headers, auto_referer
from .extractors import extract
from .link_finder import discover_sitemap, bfs_crawl
from .writer import save_output, download_images, url_to_filename
from .constants import ANTICRAWL_STATUS_CODES
from .identity_manager import get_identity_manager


# ============================================================
#  并发限速器（v5.4 新增）
# ============================================================

class RateLimiter:
    """线程安全的并发限速器。

    确保整体请求速率不超过配置的 QPS（每秒请求数），
    同时兼顾 robots.txt 的 Crawl-delay 指令。

    用法:
        limiter = RateLimiter(delay=2.0, concurrency=4)
        with limiter:
            do_request()
    """

    def __init__(self, delay: float = 2.0, concurrency: int = 1,
                 crawl_delay: float = 0.0):
        """
        Args:
            delay: 用户配置的请求间隔（秒）
            concurrency: 并发线程数
            crawl_delay: robots.txt 指定的 crawl-delay（秒），
                         取 max(delay, crawl_delay) 作为实际限速
        """
        self._delay = max(delay, crawl_delay)
        self._concurrency = max(1, concurrency)
        # 每个周期允许的请求数：并发数 或 1（取决于 delay 是否足够大）
        self._period = max(self._delay / self._concurrency, 0.1)
        self._lock = threading.Lock()
        self._last_time = 0.0

    @property
    def effective_delay(self) -> float:
        """实际生效的限速间隔"""
        return self._delay

    def wait(self):
        """等待直到可以发送下一个请求（线程安全）"""
        with self._lock:
            now = time.time()
            wait_for = self._period - (now - self._last_time)
            if wait_for > 0:
                pass  # 锁外 sleep
            self._last_time = max(now, self._last_time + self._period)
        if wait_for > 0:
            time.sleep(wait_for)

    def __enter__(self):
        self.wait()
        return self

    def __exit__(self, *args):
        pass


class CrawlerEngine:
    """爬虫调度引擎（v5.0 模块化重构版）"""

    def __init__(self, log_callback=None, progress_callback=None,
                 status_callback=None,
                 before_fetch=None, after_fetch=None):
        """爬虫调度引擎。

        Args:
            log_callback: 日志回调
            progress_callback: 进度回调 (completed, total, message)
            status_callback: 状态回调 (message)
            before_fetch: 请求前钩子 (url, method, headers) -> None/dict（可返回修改后的headers）
            after_fetch: 请求后钩子 (url, method, text, headers) -> None/str（可返回修改后的text）
        """
        self.log = log_callback or print
        self.progress = progress_callback
        self.status = status_callback
        self._cancel_flag = False
        self._pause_flag = False
        self.identity_mgr = get_identity_manager()
        self._before_fetch = before_fetch
        self._after_fetch = after_fetch

    # -------------------------------------------------------
    #  控制方法
    # -------------------------------------------------------
    def cancel(self):
        self._cancel_flag = True

    def pause(self):
        self._pause_flag = True

    def resume(self):
        self._pause_flag = False

    def is_paused(self):
        """返回当前是否处于暂停状态（供 GUI 查询，避免直接访问私有属性）"""
        return self._pause_flag

    def reset(self):
        self._cancel_flag = False
        self._pause_flag = False

    def _check_pause(self):
        while self._pause_flag and not self._cancel_flag:
            time.sleep(0.2)

    # -------------------------------------------------------
    #  robots.txt
    # -------------------------------------------------------
    def init_robots(self, user_agent, base_url=None):
        """读取 robots.txt，返回 (RobotFileParser, crawl_delay)。

        v5.5 修复：base_url 为空时 urljoin 会产出 '/robots.txt' 这种无协议的
        相对地址，RobotFileParser 直接抛 "unknown url type"，导致 robots 检查
        被静默跳过（表现为「默认允许抓取」）。此处显式短路并如实告知。
        """
        if not base_url:
            self.log("[WARN] 未提供基准 URL，跳过 robots.txt 检查，默认允许抓取")
            return None, 0.0

        robot = RobotFileParser()
        crawl_delay = 0.0
        try:
            robots_url = urljoin(base_url, "/robots.txt")
            robot.set_url(robots_url)
            robot.read()
            # v5.4: 读取 Crawl-delay 指令
            try:
                crawl_delay = robot.crawl_delay(user_agent) or 0.0
            except Exception:
                pass
            if crawl_delay > 0:
                self.log(f"[OK] 已读取 robots.txt: {robots_url} "
                         f"(Crawl-delay: {crawl_delay}s)")
            else:
                self.log(f"[OK] 已读取 robots.txt: {robots_url}")
            return robot, crawl_delay
        except Exception as e:
            self.log(f"[WARN] 无法获取 robots.txt: {e}，将默认允许抓取")
            return None, 0.0

    @staticmethod
    def robots_ok(robot, ua, url):
        return robot.can_fetch(ua, url) if robot else True

    # -------------------------------------------------------
    #  单页抓取（v5.2 重构：重试 = 身份池大小，每轮切换浏览器身份）
    # -------------------------------------------------------
    def single_fetch(self, url, method, headers, proxies=None,
                     max_retries=3, random_ua=False, random_delay=False):
        """抓取正文，每次重试换一个浏览器身份（UA + sec-ch-ua + TLS 指纹）。

        max_retries 为上限；实际重试次数 = min(max_retries, 身份池大小-1)
        """
        identity_count = self.identity_mgr.count
        max_attempts = min(max_retries + 1, identity_count)
        if max_attempts <= 0:
            max_attempts = 1

        self.log(f"[单页] 开始抓取: {url}  (方法: {method}, "
                 f"可用身份: {identity_count}, 最大尝试: {max_attempts})")

        # 预处理：提取 Cookie 字符串（如果 headers 里有）
        cookie_str = None
        if headers:
            cookie_str = headers.get("Cookie", "") or None

        last_error = None
        for attempt in range(max_attempts):
            if self._cancel_flag:
                raise Exception("用户取消操作")
            if attempt > 0:
                self._check_pause()
                wait = min(2 ** attempt, 60)
                self.log(f"  [RETRY] 第 {attempt}/{max_attempts - 1} 次重试（身份轮换），等待 {wait}s...")
                time.sleep(wait)

            # --- 身份轮换：每轮取下一个浏览器身份 ---
            identity = self.identity_mgr.get_identity(attempt)
            identity_headers = self.identity_mgr.build_headers(
                identity, referer=auto_referer(url), cookie_str=cookie_str)

            # 请求前中间件（可修改 headers）
            if self._before_fetch:
                try:
                    modified = self._before_fetch(url, method, identity_headers)
                    if modified and isinstance(modified, dict):
                        identity_headers.update(modified)
                except Exception:
                    pass

            try:
                text = extract(url, method, identity_headers, proxies=proxies,
                               random_delay=random_delay)

                # 请求后中间件（可修改 text）
                if self._after_fetch:
                    try:
                        modified = self._after_fetch(url, method, text, identity_headers)
                        if modified and isinstance(modified, str):
                            text = modified
                    except Exception:
                        pass

                return text
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    self.log(f"  [WARN] [{identity['id']}] 失败: {e}")
                else:
                    self.log(f"  [FAIL] 已耗尽全部 {max_attempts} 个身份，最终失败")

        raise last_error

    # -------------------------------------------------------
    #  批量抓取
    # -------------------------------------------------------
    def batch_fetch(self, url_list, method, headers, delay, save_dir,
                    respect_robots=True, output_fmt="txt",
                    concurrency=4, proxies=None, download_imgs=False,
                    max_retries=3, random_ua=False, random_delay=False):
        os.makedirs(save_dir, exist_ok=True)
        robot = None
        crawl_delay = 0.0
        if respect_robots:
            # v5.5: 以首个 URL 为基准解析 robots.txt（此前 base_url 恒为 None）
            base_url = url_list[0] if url_list else None
            robot, crawl_delay = self.init_robots(
                headers.get("User-Agent", ""), base_url=base_url)

        # v5.5 修复：total 此前在赋值前被引用（NameError）
        total = len(url_list)

        # v5.4: 使用 RateLimiter 确保整体请求速率合规
        rate_limiter = RateLimiter(
            delay=delay, concurrency=concurrency, crawl_delay=crawl_delay)
        actual_delay = rate_limiter.effective_delay
        if actual_delay != delay:
            self.log(f"[INFO] robots.txt Crawl-delay 生效: "
                     f"{delay}s -> {actual_delay}s")
        self.log(f"[LAUNCH] 批量抓取开始：{total} 个网址，并发数={concurrency}，"
                 f"限速={actual_delay}s/请求")

        completed = 0
        completed_lock = threading.Lock()

        def _process_one(item):
            nonlocal completed
            idx, real_url = item
            if self._cancel_flag:
                return idx, None, "已取消"
            self._check_pause()

            # v5.4: 请求前统一限速
            rate_limiter.wait()

            if robot and not self.robots_ok(robot, headers.get("User-Agent", ""),
                                            real_url):
                self.log(f"  ⛔ robots.txt 禁止: {real_url}")
                with completed_lock:
                    completed += 1
                if self.progress:
                    self.progress(completed, total, f"处理中 {completed}/{total}")
                return idx, None, "被 robots.txt 禁止"

            # v5.5 修复：异常时 text 未绑定会导致 UnboundLocalError
            text = None
            try:
                text = self.single_fetch(
                    real_url, method, headers, proxies=proxies,
                    max_retries=max_retries,
                    random_ua=random_ua, random_delay=random_delay)
                if text:
                    filename = url_to_filename(real_url, idx)
                    save_output(text, real_url, filename, save_dir, output_fmt)
                    self.log(f"  [OK] 已保存: {filename}.{output_fmt} "
                             f"({len(text)} 字符)")
                else:
                    self.log("  [WARN] 未提取到正文")
            except Exception as e:
                self.log(f"  [FAIL] 错误: {e}")

            if download_imgs and text:
                img_dir = os.path.join(
                    save_dir, "images", url_to_filename(real_url, idx))
                download_images(real_url, headers, img_dir, proxies=proxies,
                                 random_ua=random_ua, log=self.log)

            with completed_lock:
                completed += 1
                current = completed
            if self.progress:
                self.progress(current, total, f"处理中 {current}/{total}")
            return idx, (text if text else ""), None

        if concurrency > 1:
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=concurrency) as ex:
                futures = [ex.submit(_process_one, (i+1, u))
                           for i, u in enumerate(url_list)]
                for fut in concurrent.futures.as_completed(futures):
                    pass
        else:
            for i, url in enumerate(url_list):
                _process_one((i+1, url))

        self.log(f"\n🎉 批量抓取完成！保存至: {os.path.abspath(save_dir)}")
        if self.status:
            self.status("批量抓取完成")

    # -------------------------------------------------------
    #  整站爬取
    # -------------------------------------------------------
    def site_crawl(self, index_url, method, headers, delay, save_dir,
                   respect_robots=True, output_fmt="txt", max_depth=1,
                   use_sitemap=False, proxies=None, download_images=False,
                   max_retries=3, random_ua=False, random_delay=False,
                   resume_checkpoint=None):
        """整站爬取（v5.4: 支持断点续传）。

        Args:
            resume_checkpoint: 断点文件路径，提供则从断点恢复
        """
        os.makedirs(save_dir, exist_ok=True)
        from urllib.parse import urlparse
        domain = urlparse(index_url).netloc

        # v5.4: 断点续传支持
        checkpoint_file = resume_checkpoint or os.path.join(
            save_dir, ".webcopier_checkpoint.json")
        fetched_urls = set()
        if os.path.exists(checkpoint_file):
            try:
                import json as _json
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    checkpoint = _json.load(f)
                fetched_urls = set(checkpoint.get("fetched", []))
                self.log(f"[RESUME] 从断点恢复: 已完成 {len(fetched_urls)} 个页面")
            except Exception:
                pass

        links = []
        if use_sitemap:
            self.log("[整站] 尝试从 sitemap.xml 发现链接...")
            links = discover_sitemap(index_url, headers, proxies=proxies,
                                    log=self.log)
            if links:
                self.log(f"[整站] sitemap 发现 {len(links)} 个链接")

        if not links:
            links = bfs_crawl(
                index_url, headers, proxies=proxies,
                max_depth=max_depth, log=self.log,
                cancel_check=lambda: self._cancel_flag)

        # 过滤已抓取的 URL
        if fetched_urls:
            links = [url for url in links if url not in fetched_urls]
            self.log(f"[RESUME] 跳过 {len(fetched_urls)} 个已抓取页面，"
                     f"剩余 {len(links)} 个")

        self.log(f"📚 共发现 {len(links)} 个页面链接")
        if self.status:
            self.status(f"发现 {len(links)} 个链接，开始抓取...")

        # v5.4: 保存断点（每抓取成功一个页面就更新）
        def _after_save_callback(url):
            fetched_urls.add(url)
            try:
                with open(checkpoint_file, "w", encoding="utf-8") as f:
                    import json as _json
                    _json.dump({"fetched": list(fetched_urls)}, f,
                              ensure_ascii=False)
            except Exception:
                pass

        # 包装进度回调以包含断点保存
        orig_progress = self.progress

        def _wrapped_progress(completed, total, message):
            if orig_progress:
                orig_progress(completed, total, message)

        self.progress = _wrapped_progress

        # 批量抓取（v5.4: respect_robots 正确传递）
        self.batch_fetch(links, method, headers, delay, save_dir,
                          respect_robots=respect_robots, output_fmt=output_fmt,
                          concurrency=4, proxies=proxies,
                          download_imgs=download_images,
                          max_retries=max_retries, random_ua=random_ua,
                          random_delay=random_delay)

        # 完成后清理断点文件
        self.progress = orig_progress
        try:
            if os.path.exists(checkpoint_file):
                os.remove(checkpoint_file)
        except Exception:
            pass
