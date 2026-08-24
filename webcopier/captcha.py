#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证码识别模块 v5.1：图片验证码 / 滑块验证码 / 点选验证码
参考 crawlProject「验证码篇」的最佳实践：

- 图片验证码：使用 ddddocr 自动识别（参考 crawlProject 某诗文网案例）
- 滑块验证码：使用 ddddocr 识别缺口距离 + 轨迹生成（参考 JD 滑块案例）
- 点选验证码：坐标识别 + 轨迹生成（参考 极验三代点选案例）
"""

import os
import io
import time
import random
import base64
from typing import Optional, Tuple, List

import requests

try:
    import ddddocr
    _HAS_DDDDOCR = True
except ImportError:
    _HAS_DDDDOCR = False

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ============================================================
#  ddddocr 单例
# ============================================================

_OCR_INSTANCE = None


def _get_ocr():
    """获取 ddddocr 实例（懒加载单例）"""
    global _OCR_INSTANCE
    if not _HAS_DDDDOCR:
        raise ImportError(
            "请先安装 ddddocr：pip install ddddocr  或  pip install ddddocr -i https://pypi.tuna.tsinghua.edu.cn/simple")
    if _OCR_INSTANCE is None:
        _OCR_INSTANCE = ddddocr.DdddOcr(show_ad=False)
    return _OCR_INSTANCE


# ============================================================
#  图片验证码识别（参考 crawlProject 某诗文网案例）
# ============================================================

def recognize_image_captcha(image_data: bytes) -> str:
    """
    识别图片验证码（字母/数字）。
    参考 crawlProject 的 ddddocr 使用方法：
        ocr = ddddocr.DdddOcr()
        res = ocr.classification(img_bytes)

    Args:
        image_data: 图片二进制数据

    Returns:
        str: 识别结果（去空格后的字母数字串）
    """
    ocr = _get_ocr()
    result = ocr.classification(image_data)
    # 清洗结果：去除常见噪声字符
    result = result.replace(" ", "").replace("\n", "").replace("\t", "")
    return result


def download_and_recognize(img_url: str, headers: dict = None,
                           proxies: dict = None,
                           session: requests.Session = None) -> str:
    """
    下载验证码图片并识别。
    会尝试多种请求方式：直接 GET -> Session -> Referer 链

    Args:
        img_url: 验证码图片 URL
        headers: 自定义请求头
        proxies: 代理
        session: requests.Session（用于保持 Cookie）

    Returns:
        str: 识别结果
    """
    default_headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0.0.0 Safari/537.36"),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    if headers:
        default_headers.update(headers)

    last_error = None
    # 方式 1：使用 Session
    if session:
        try:
            resp = session.get(img_url, headers=default_headers,
                               timeout=15, proxies=proxies)
            resp.raise_for_status()
            return recognize_image_captcha(resp.content)
        except Exception as e:
            last_error = e

    # 方式 2：直接请求
    try:
        resp = requests.get(img_url, headers=default_headers,
                            timeout=15, proxies=proxies)
        resp.raise_for_status()
        return recognize_image_captcha(resp.content)
    except Exception as e:
        last_error = e

    raise last_error or RuntimeError("无法获取验证码图片")


def recognize_from_file(filepath: str) -> str:
    """从本地文件读取并识别验证码"""
    with open(filepath, "rb") as f:
        return recognize_image_captcha(f.read())


def recognize_base64(b64_str: str) -> str:
    """
    从 Base64 编码字符串识别验证码。
    常见场景：data:image/png;base64,iVBORw0KGgo...
    """
    if "," in b64_str:
        b64_str = b64_str.split(",", 1)[1]
    img_data = base64.b64decode(b64_str)
    return recognize_image_captcha(img_data)


# ============================================================
#  滑块验证码识别（参考 crawlProject JD 滑块案例）
# ============================================================

class SliderCaptchaSolver:
    """
    滑块验证码求解器（v5.1 新增）
    参考 crawlProject 的 JD 滑块方案：
    1. 使用 ddddocr 的 slide_match 识别缺口距离
    2. 生成拟人化滑动轨迹
    3. 发送验证请求

    用法:
        solver = SliderCaptchaSolver()
        distance = solver.get_gap_distance(bg_bytes, slider_bytes)
        track = solver.generate_track(distance)
        # ... 执行滑动 ...
    """

    def __init__(self):
        if not _HAS_DDDDOCR:
            raise ImportError("请先安装 ddddocr：pip install ddddocr")
        # 使用 ddddocr 的滑块检测
        self._det = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)

    def get_gap_distance(self,
                         background_bytes: bytes,
                         slider_bytes: bytes) -> int:
        """
        计算滑块缺口距离。
        使用 ddddocr 的 slide_match 功能（底层使用 OpenCV 模板匹配）。

        Args:
            background_bytes: 带缺口的背景图
            slider_bytes: 滑块小图

        Returns:
            int: 缺口 X 坐标（像素）
        """
        result = self._det.slide_match(slider_bytes, background_bytes)
        if result and "target" in result:
            return result["target"][0]  # x 坐标
        # 回退：尝试简单匹配
        return self._det.slide_match(target_bytes=slider_bytes,
                                      background_bytes=background_bytes)

    @staticmethod
    def generate_track(distance: int,
                       with_jitter: bool = True) -> List[Tuple[int, int, int]]:
        """
        生成拟人化滑动轨迹（参考 crawlProject JD 滑块轨迹生成）。
        轨迹由三部分组成：
        1. 加速段：从 0 匀加速到目标距离的 80%
        2. 减速段：缓慢滑到目标位置
        3. 抖动段：小幅回拉（模拟人类不精准操作）

        Returns:
            List[Tuple[int, int, int]]: [(x, y, delay_ms), ...]
        """
        track = []
        # 添加随机偏移（模拟真实操作，通常需要 -1~-5 像素偏移）
        offset = random.randint(-3, -1)
        target = max(0, distance + offset)

        # 1) 加速段 (0 -> 80%)
        current = 0
        mid = int(target * 0.8)
        t = random.uniform(0.2, 0.3)  # 加速参数
        while current < mid:
            move = int(t * (current + random.randint(1, 3)))
            if move <= 0:
                move = random.randint(2, 5)
            current += move
            y_jitter = random.randint(-1, 1)  # Y 轴微小抖动
            delay = random.randint(5, 15)  # ms
            track.append((min(current, target), y_jitter, delay))

        # 2) 减速段 (mid -> target)
        remaining = target - current
        while current < target:
            move = max(1, int(remaining * random.uniform(0.3, 0.6)))
            current += move
            y_jitter = random.randint(-1, 1)
            delay = random.randint(20, 60)
            track.append((min(current, target), y_jitter, delay))
            remaining = target - current

        # 确保达到目标
        if track and track[-1][0] != target:
            track.append((target, 0, random.randint(50, 100)))

        # 3) 抖动段（小幅来回，模拟人类不精准，参考 crawlProject）
        if with_jitter:
            for _ in range(random.randint(1, 3)):
                jitter_x = target + random.randint(-3, 2)
                track.append((max(0, jitter_x), 0, random.randint(30, 80)))

        return track


# ============================================================
#  带验证码的登录流程
# ============================================================

def login_with_captcha(session_manager,
                       login_url: str,
                       captcha_img_selector: str = None,
                       username: str = "",
                       password: str = "",
                       username_field: str = "username",
                       password_field: str = "password",
                       captcha_field: str = "captcha",
                       max_attempts: int = 5,
                       log=None) -> bool:
    """
    带验证码的自动登录流程（v5.1 新增）
    参考 crawlProject 某诗文网的「登录 + 图片验证码解决」方案。

    流程：
    1. GET 登录页面 -> 提取隐藏域 + 验证码图片 URL
    2. 下载验证码 -> ddddocr 识别
    3. POST 登录表单（含验证码）
    4. 如失败且验证码错误 -> 重试

    Args:
        session_manager: SessionManager 实例
        login_url: 登录页面 URL
        captcha_img_selector: 验证码图片的 CSS 选择器（如 "#captcha_img"）
                             None 则自动搜索常见选择器
        username / password: 登录凭证
        username_field / password_field / captcha_field: 表单字段名
        max_attempts: 最大重试次数
        log: 日志回调

    Returns:
        bool: 是否登录成功
    """
    _log = log or print
    from bs4 import BeautifulSoup
    from .http_client import build_headers

    domain = session_manager._extract_domain(login_url)
    session = session_manager.get_session(domain)

    for attempt in range(max_attempts):
        _log(f"[RETRY] 第 {attempt+1}/{max_attempts} 次登录尝试...")

        try:
            headers = build_headers(random_ua=True, referer=login_url)
            login_page = session.get(login_url, headers=headers, timeout=15)
            soup = BeautifulSoup(login_page.text, "lxml")

            # --- 提取隐藏域 ---
            form_data = {}
            for hidden in soup.find_all("input", type="hidden"):
                name = hidden.get("name")
                if name:
                    form_data[name] = hidden.get("value", "")

            # --- 找到验证码图片 ---
            captcha_url = None
            selectors_to_try = [
                captcha_img_selector,
                "img#captcha", "img#code_img", "img.captcha",
                "img[src*='captcha']", "img[src*='code']",
                "img[src*='verify']", "img[src*='check']",
            ]
            for sel in selectors_to_try:
                if not sel:
                    continue
                img = soup.select_one(sel) if sel else None
                if img and img.get("src"):
                    captcha_url = img["src"]
                    break

            if not captcha_url:
                # 可能是无验证码场景，直接提交
                _log("  ℹ️ 未检测到验证码，尝试直接登录")
                captcha_text = ""
            else:
                # 拼接完整 URL
                from urllib.parse import urljoin as _urljoin
                captcha_url = _urljoin(login_url, captcha_url)
                _log(f"  [SEARCH] 下载验证码: {captcha_url[:80]}...")

                # 下载并识别
                captcha_bytes = session.get(
                    captcha_url, headers=headers, timeout=10).content
                captcha_text = recognize_image_captcha(captcha_bytes)
                _log(f"  🤖 识别结果: [{captcha_text}]")

            # --- 构建登录表单 ---
            form_data[username_field] = username
            form_data[password_field] = password
            form_data[captcha_field] = captcha_text

            # --- 提交登录 ---
            post_headers = build_headers(random_ua=True, referer=login_url)
            post_headers["Origin"] = session_manager._extract_origin(login_url)
            post_headers["Content-Type"] = "application/x-www-form-urlencoded"

            resp = session.post(
                login_url, data=form_data, headers=post_headers,
                timeout=15, allow_redirects=True)

            # 检查是否登录成功
            if "captcha" not in resp.text.lower() and "验证码" not in resp.text:
                session_manager.save(domain)
                _log(f"  [OK] 登录成功！（第 {attempt+1} 次尝试）")
                return True
            else:
                _log(f"  [WARN] 验证码错误，重试...")

            time.sleep(random.uniform(1.0, 2.0))

        except Exception as e:
            _log(f"  [FAIL] 登录异常: {e}")
            time.sleep(random.uniform(2.0, 3.0))

    _log(f"  [FAIL] {max_attempts} 次尝试后登录失败")
    return False
