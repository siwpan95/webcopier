#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI 主窗口：WebCopierApp
整合所有界面逻辑：四个 Tab、进度条、日志区、状态栏
"""

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, scrolledtext

# 脚本根目录（WebCopier_GUI.py 所在目录）
_SCRIPT_DIR = Path(__file__).resolve().parent.parent

from .constants import (
    VERSION, APP_TITLE, FONT_NORMAL, FONT_BOLD, FONT_TITLE, FONT_SMALL,
    FONT_MONO, FONT_ENTRY,
    METHOD_LABELS, METHOD_SHORT, FORMAT_LABELS, FORMAT_SHORT,
    EXTRACT_METHODS,
)
from .config import load_config, save_config, reset_config, export_config, import_config, CONFIG_FILE
from .engine import CrawlerEngine
from .writer import save_output, url_to_filename


class WebCopierApp:
    """WebCopier GUI 主窗口"""

    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("960x820")
        self.root.minsize(800, 650)

        self.cfg = load_config()
        self.engine = CrawlerEngine(
            log_callback=self._append_log,
            progress_callback=self._on_progress,
            status_callback=self._on_status,
        )
        self._thread = None

        self.style = ttk.Style()
        _theme = self.cfg.get("tk_theme", "clam")
        try:
            self.style.theme_use(_theme)
        except Exception:
            self.style.theme_use("clam")  # 回退到默认
        self.style.configure("Green.Horizontal.TProgressbar",
                             background="#27ae60", troughcolor="#ecf0f1")

        self._build_ui()
        self._load_cfg_to_ui()

    # ==========================================================
    #  界面构建
    # ==========================================================
    def _build_ui(self):
        # 顶部标题栏
        header = tk.Frame(self.root, bg="#2c3e50", height=52)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text=f"[CLIPBOARD] {APP_TITLE}",
                 bg="#2c3e50", fg="white",
                 font=FONT_TITLE).pack(side=tk.LEFT, padx=18, pady=10)
        info = tk.Label(header,
                        text="v5.4  集成 6 种提取引擎 - 并发限速 - 断点续传 - HTML输出 - curl_cffi TLS指纹",
                        bg="#2c3e50", fg="#bdc3c7", font=FONT_SMALL)
        info.pack(side=tk.RIGHT, padx=18, pady=14)

        # Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        self._tab_single()
        self._tab_batch()
        self._tab_site()
        self._tab_settings()

        # 底部：进度条 + 状态栏
        bottom = ttk.Frame(self.root)
        bottom.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.progress_bar = ttk.Progressbar(
            bottom, mode="determinate",
            style="Green.Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X, pady=(0, 3))

        status_frame = tk.Frame(bottom, bg="#ecf0f1")
        status_frame.pack(fill=tk.X)
        self.status_label = tk.Label(
            status_frame, text="🟢 就绪", bg="#ecf0f1", fg="#2c3e50",
            font=FONT_NORMAL, anchor=tk.W)
        self.status_label.pack(fill=tk.X, padx=5, pady=2)

        # 日志区
        log_frame = ttk.LabelFrame(self.root, text="  运行日志  ", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.log_area = scrolledtext.ScrolledText(
            log_frame, height=10, wrap=tk.WORD,
            font=FONT_MONO, bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white")
        self.log_area.pack(fill=tk.BOTH, expand=True)

    # ==========================================================
    #  单页抓取 Tab
    # ==========================================================
    def _tab_single(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="  单页抓取  ")
        row = 0

        ttk.Label(tab, text="目标网址：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=5)
        self.single_url = ttk.Entry(tab, width=72, font=FONT_ENTRY)
        self.single_url.grid(row=row, column=1, columnspan=3,
                              sticky=tk.EW, pady=5)
        self.single_url.insert(0, "https://example.com/article")

        row += 1
        ttk.Label(tab, text="提取方式：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=8)
        self.single_method = tk.StringVar(value="trafilatura")
        mf = ttk.Frame(tab)
        mf.grid(row=row, column=1, columnspan=3, sticky=tk.W, pady=8)
        for v, lbl in METHOD_LABELS.items():
            ttk.Radiobutton(mf, text=lbl, variable=self.single_method,
                             value=v).pack(side=tk.LEFT, padx=(0, 12))

        row += 1
        ttk.Label(tab, text="输出格式：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=5)
        self.single_fmt = tk.StringVar(value="txt")
        ff = ttk.Frame(tab)
        ff.grid(row=row, column=1, columnspan=3, sticky=tk.W, pady=5)
        for v, lbl in FORMAT_LABELS.items():
            ttk.Radiobutton(ff, text=lbl, variable=self.single_fmt,
                             value=v).pack(side=tk.LEFT, padx=(0, 12))

        row += 1
        ttk.Label(tab, text="浏览器标识 (UA)：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=5)
        self.single_ua = ttk.Entry(tab, width=72, font=FONT_ENTRY)
        self.single_ua.grid(row=row, column=1, columnspan=3,
                              sticky=tk.EW, pady=5)

        row += 1
        self.single_random_ua = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="🎲 随机更换 User-Agent（反爬推荐）",
                         variable=self.single_random_ua).grid(
            row=row, column=1, columnspan=3, sticky=tk.W, pady=3)

        row += 1
        ttk.Label(tab, text="最大重试次数：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=5)
        self.single_max_retries = ttk.Entry(tab, width=6, font=FONT_ENTRY)
        self.single_max_retries.grid(row=row, column=1, sticky=tk.W, pady=5)
        self.single_max_retries.insert(0, "3")
        ttk.Label(tab, text="（失败后自动重试，含指数退避等待）",
                   font=FONT_SMALL, foreground="#888").grid(
            row=row, column=2, columnspan=2, sticky=tk.W, pady=5)

        row += 1
        ttk.Label(tab, text="保存目录：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=5)
        self.single_dir = ttk.Entry(tab, width=56, font=FONT_ENTRY)
        self.single_dir.grid(row=row, column=1, columnspan=2,
                              sticky=tk.EW, pady=5)
        ttk.Button(tab, text="浏览...",
                   command=self._browse_single_dir).grid(
            row=row, column=3, padx=(5, 0))

        row += 1
        ttk.Label(tab, text="提取预览：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.NW, pady=5)
        self.single_preview = scrolledtext.ScrolledText(
            tab, height=14, wrap=tk.WORD, font=FONT_NORMAL)
        self.single_preview.grid(row=row, column=1, columnspan=3,
                                  sticky=tk.NSEW, pady=5)

        row += 1
        bf = ttk.Frame(tab)
        bf.grid(row=row, column=1, columnspan=3, sticky=tk.E, pady=(5, 0))
        ttk.Button(bf, text="[SEARCH] 提取正文",
                   command=self._do_single).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(bf, text="[SAVE] 保存到文件",
                   command=self._save_single).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(bf, text="🗑 清空",
                   command=lambda: self.single_preview.delete(
                       1.0, tk.END)).pack(side=tk.RIGHT)

        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(row, weight=1)

    # ==========================================================
    #  批量抓取 Tab
    # ==========================================================
    def _tab_batch(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="  批量抓取  ")
        row = 0

        ttk.Label(tab, text="网址列表（每行一个）：", font=FONT_NORMAL).grid(
            row=row, column=0, columnspan=5, sticky=tk.W, pady=(5, 3))
        row += 1
        self.batch_urls = scrolledtext.ScrolledText(
            tab, height=7, wrap=tk.WORD, font=FONT_NORMAL)
        self.batch_urls.grid(row=row, column=0, columnspan=5,
                              sticky=tk.NSEW, pady=(0, 8))
        self.batch_urls.insert(
            tk.END, "https://example.com/article/1\nhttps://example.com/article/2")

        row += 1
        ttk.Label(tab, text="提取方式：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.batch_method = tk.StringVar(value="trafilatura")
        bf = ttk.Frame(tab)
        bf.grid(row=row, column=1, columnspan=4, sticky=tk.W, pady=4)
        for v, lbl in METHOD_SHORT.items():
            ttk.Radiobutton(bf, text=lbl, variable=self.batch_method,
                             value=v).pack(side=tk.LEFT, padx=(0, 10))

        row += 1
        ttk.Label(tab, text="输出格式：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.batch_fmt = tk.StringVar(value="txt")
        for i, (v, lbl) in enumerate(FORMAT_SHORT.items()):
            ttk.Radiobutton(tab, text=lbl, variable=self.batch_fmt,
                             value=v).grid(row=row, column=1+i,
                                            sticky=tk.W, pady=4)

        row += 1
        ttk.Label(tab, text="请求间隔（秒）：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.batch_delay = ttk.Entry(tab, width=8, font=FONT_ENTRY)
        self.batch_delay.grid(row=row, column=1, sticky=tk.W, pady=4)

        self.batch_robots = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="遵守 robots.txt 协议",
                         variable=self.batch_robots).grid(
            row=row, column=2, sticky=tk.W, padx=(10, 0))

        ttk.Label(tab, text="并发数：", font=FONT_NORMAL).grid(
            row=row, column=3, sticky=tk.W, padx=(20, 0), pady=4)
        self.batch_concurrency = ttk.Entry(tab, width=5, font=FONT_ENTRY)
        self.batch_concurrency.grid(row=row, column=4, sticky=tk.W, pady=4)

        row += 1
        self.batch_random_ua = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="🎲 随机更换 User-Agent",
                         variable=self.batch_random_ua).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=3)
        self.batch_random_delay = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="⏱ 随机请求延迟",
                         variable=self.batch_random_delay).grid(
            row=row, column=2, columnspan=3, sticky=tk.W, pady=3)

        row += 1
        ttk.Label(tab, text="最大重试次数：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.batch_max_retries = ttk.Entry(tab, width=5, font=FONT_ENTRY)
        self.batch_max_retries.grid(row=row, column=1, sticky=tk.W, pady=4)
        self.batch_max_retries.insert(0, "3")
        ttk.Label(tab, text="（指数退避等待）",
                   font=FONT_SMALL, foreground="#888").grid(
            row=row, column=2, columnspan=3, sticky=tk.W, pady=4)

        row += 1
        ttk.Label(tab, text="浏览器标识 (UA)：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.batch_ua = ttk.Entry(tab, width=72, font=FONT_ENTRY)
        self.batch_ua.grid(row=row, column=1, columnspan=4,
                            sticky=tk.EW, pady=4)

        row += 1
        ttk.Label(tab, text="保存目录：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.batch_dir = ttk.Entry(tab, width=56, font=FONT_ENTRY)
        self.batch_dir.grid(row=row, column=1, columnspan=2,
                             sticky=tk.EW, pady=4)
        ttk.Button(tab, text="浏览...",
                   command=self._browse_batch_dir).grid(
            row=row, column=3, padx=(5, 0))
        self.batch_img_dl = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab, text="下载页面图片",
                         variable=self.batch_img_dl).grid(
            row=row, column=4, sticky=tk.W, padx=(10, 0))

        row += 1
        btn_f = ttk.Frame(tab)
        btn_f.grid(row=row, column=1, columnspan=4, sticky=tk.E, pady=(8, 0))
        self.batch_btn = ttk.Button(btn_f, text="▶ 开始批量抓取",
                                     command=self._do_batch)
        self.batch_btn.pack(side=tk.RIGHT, padx=(5, 0))
        self.batch_pause_btn = ttk.Button(btn_f, text="⏸ 暂停",
                                           command=self._toggle_pause)
        self.batch_pause_btn.pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_f, text="⏹ 取消",
                   command=self._cancel).pack(side=tk.RIGHT)

        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

    # ==========================================================
    #  整站爬取 Tab
    # ==========================================================
    def _tab_site(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="  整站爬取  ")
        row = 0

        ttk.Label(tab, text="索引页 / 网站首页网址：", font=FONT_NORMAL).grid(
            row=row, column=0, columnspan=5, sticky=tk.W, pady=(5, 3))
        row += 1
        self.site_url = ttk.Entry(tab, width=72, font=FONT_ENTRY)
        self.site_url.grid(row=row, column=0, columnspan=5,
                            sticky=tk.EW, pady=(0, 8))
        self.site_url.insert(0, "https://example.com/")

        row += 1
        ttk.Label(tab, text="提取方式：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.site_method = tk.StringVar(value="trafilatura")
        sf = ttk.Frame(tab)
        sf.grid(row=row, column=1, columnspan=4, sticky=tk.W, pady=4)
        for v, lbl in METHOD_SHORT.items():
            ttk.Radiobutton(sf, text=lbl, variable=self.site_method,
                             value=v).pack(side=tk.LEFT, padx=(0, 10))

        row += 1
        ttk.Label(tab, text="输出格式：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.site_fmt = tk.StringVar(value="txt")
        for i, (v, lbl) in enumerate(FORMAT_SHORT.items()):
            ttk.Radiobutton(tab, text=lbl, variable=self.site_fmt,
                             value=v).grid(row=row, column=1+i,
                                            sticky=tk.W, pady=4)

        row += 1
        ttk.Label(tab, text="请求间隔（秒）：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.site_delay = ttk.Entry(tab, width=8, font=FONT_ENTRY)
        self.site_delay.grid(row=row, column=1, sticky=tk.W, pady=4)

        self.site_robots = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="遵守 robots.txt",
                         variable=self.site_robots).grid(
            row=row, column=2, sticky=tk.W, padx=(10, 0))

        ttk.Label(tab, text="最大深度：", font=FONT_NORMAL).grid(
            row=row, column=3, sticky=tk.W, padx=(20, 0), pady=4)
        self.site_depth = ttk.Entry(tab, width=5, font=FONT_ENTRY)
        self.site_depth.grid(row=row, column=4, sticky=tk.W, pady=4)

        row += 1
        self.site_random_ua = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="🎲 随机更换 User-Agent",
                         variable=self.site_random_ua).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=3)
        self.site_random_delay = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="⏱ 随机请求延迟",
                         variable=self.site_random_delay).grid(
            row=row, column=2, columnspan=3, sticky=tk.W, pady=3)

        row += 1
        ttk.Label(tab, text="最大重试次数：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.site_max_retries = ttk.Entry(tab, width=5, font=FONT_ENTRY)
        self.site_max_retries.grid(row=row, column=1, sticky=tk.W, pady=4)
        self.site_max_retries.insert(0, "3")
        ttk.Label(tab, text="（指数退避等待）",
                   font=FONT_SMALL, foreground="#888").grid(
            row=row, column=2, columnspan=3, sticky=tk.W, pady=4)

        row += 1
        self.site_sitemap = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab, text="🗺 从 sitemap.xml 发现链接（推荐）",
                         variable=self.site_sitemap).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=4)
        self.site_img_dl = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab, text="下载页面图片",
                         variable=self.site_img_dl).grid(
            row=row, column=2, columnspan=3, sticky=tk.W, pady=4)

        row += 1
        ttk.Label(tab, text="浏览器标识 (UA)：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.site_ua = ttk.Entry(tab, width=72, font=FONT_ENTRY)
        self.site_ua.grid(row=row, column=1, columnspan=4,
                           sticky=tk.EW, pady=4)

        row += 1
        ttk.Label(tab, text="保存目录：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=4)
        self.site_dir = ttk.Entry(tab, width=56, font=FONT_ENTRY)
        self.site_dir.grid(row=row, column=1, columnspan=2,
                            sticky=tk.EW, pady=4)
        ttk.Button(tab, text="浏览...",
                   command=self._browse_site_dir).grid(
            row=row, column=3, padx=(5, 0))

        row += 1
        btn_f = ttk.Frame(tab)
        btn_f.grid(row=row, column=1, columnspan=4, sticky=tk.E, pady=(8, 0))
        self.site_btn = ttk.Button(btn_f, text="▶ 开始整站爬取",
                                    command=self._do_site)
        self.site_btn.pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_f, text="⏹ 取消",
                   command=self._cancel).pack(side=tk.RIGHT)

        tab.columnconfigure(1, weight=1)

    # ==========================================================
    #  设置 Tab
    # ==========================================================
    def _tab_settings(self):
        tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(tab, text="  设置  ")
        row = 0

        ttk.Label(tab, text="⚙️ 全局设置",
                   font=(FONT_TITLE[0], 13, "bold")).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 12))

        row += 1
        ttk.Label(tab, text="默认浏览器标识 (UA)：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=6)
        self.setting_ua = ttk.Entry(tab, width=70, font=FONT_ENTRY)
        self.setting_ua.grid(row=row, column=1, columnspan=2,
                              sticky=tk.EW, pady=6)

        row += 1
        self.setting_random_ua = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="🎲 默认启用随机 User-Agent 更换",
                         variable=self.setting_random_ua).grid(
            row=row, column=1, columnspan=2, sticky=tk.W, pady=3)

        row += 1
        ttk.Label(tab, text="HTTP/SOCKS5 代理服务器：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=6)
        self.setting_proxy = ttk.Entry(tab, width=70, font=FONT_ENTRY)
        self.setting_proxy.grid(row=row, column=1, columnspan=2,
                                sticky=tk.EW, pady=6)
        ttk.Label(tab, text="格式：http://ip:port  或  socks5://ip:port",
                   font=FONT_SMALL, foreground="#888").grid(
            row=row+1, column=1, columnspan=2, sticky=tk.W)

        row += 2
        ttk.Label(tab, text="默认保存目录：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=6)
        self.setting_dir = ttk.Entry(tab, width=70, font=FONT_ENTRY)
        self.setting_dir.grid(row=row, column=1, columnspan=2,
                               sticky=tk.EW, pady=6)

        row += 1
        ttk.Label(tab, text="默认提取方式：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=6)
        self.setting_method = tk.StringVar(value="trafilatura")
        mf = ttk.Frame(tab)
        mf.grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=6)
        for v, lbl in METHOD_SHORT.items():
            ttk.Radiobutton(mf, text=lbl, variable=self.setting_method,
                             value=v).pack(side=tk.LEFT, padx=(0, 10))

        row += 1
        ttk.Label(tab, text="默认输出格式：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=6)
        self.setting_fmt = tk.StringVar(value="txt")
        ff = ttk.Frame(tab)
        ff.grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=6)
        for v, lbl in FORMAT_SHORT.items():
            ttk.Radiobutton(ff, text=lbl, variable=self.setting_fmt,
                             value=v).pack(side=tk.LEFT, padx=(0, 10))

        row += 1
        ttk.Label(tab, text="默认请求间隔（秒）：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=6)
        self.setting_delay = ttk.Entry(tab, width=8, font=FONT_ENTRY)
        self.setting_delay.grid(row=row, column=1, sticky=tk.W, pady=6)

        row += 1
        ttk.Label(tab, text="批量默认并发数：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=6)
        self.setting_concurrency = ttk.Entry(tab, width=8, font=FONT_ENTRY)
        self.setting_concurrency.grid(row=row, column=1, sticky=tk.W, pady=6)

        row += 1
        ttk.Label(tab, text="默认最大重试次数：", font=FONT_NORMAL).grid(
            row=row, column=0, sticky=tk.W, pady=6)
        self.setting_max_retries = ttk.Entry(tab, width=8, font=FONT_ENTRY)
        self.setting_max_retries.grid(row=row, column=1, sticky=tk.W, pady=6)
        ttk.Label(tab, text="（0 表示不重试）",
                   font=FONT_SMALL, foreground="#888").grid(
            row=row, column=2, sticky=tk.W, pady=6)

        row += 1
        self.setting_cache = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab, text="[SAVE] 启用 HTTP 请求缓存（需安装 requests-cache）",
                         variable=self.setting_cache).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=6)

        row += 1
        btn_f = ttk.Frame(tab)
        btn_f.grid(row=row, column=0, columnspan=3, pady=(18, 0))
        ttk.Button(btn_f, text="[SAVE] 保存配置",
                   command=self._save_settings).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_f, text="[RETRY] 恢复默认",
                   command=self._reset_settings).pack(side=tk.LEFT)
        ttk.Button(btn_f, text="📤 导出配置",
                   command=self._export_settings).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(btn_f, text="📥 导入配置",
                   command=self._import_settings).pack(side=tk.LEFT)
        ttk.Label(btn_f, text=f"配置文件：{CONFIG_FILE}",
                   font=FONT_SMALL, foreground="#888").pack(
            side=tk.LEFT, padx=(10, 0))

        tab.columnconfigure(1, weight=1)

    # ==========================================================
    #  配置加载 / 保存
    # ==========================================================
    def _load_cfg_to_ui(self):
        cfg = self.cfg
        ua = cfg.get("user_agent", "")
        mr = str(cfg.get("max_retries", 3))

        # 单页
        self.single_ua.insert(0, ua)
        self.single_dir.insert(0, cfg.get("save_dir", ""))
        self.single_method.set(cfg.get("method", "trafilatura"))
        self.single_fmt.set(cfg.get("output_format", "txt"))
        self.single_random_ua.set(cfg.get("random_ua", True))
        self.single_max_retries.insert(0, mr)

        # 批量
        self.batch_ua.insert(0, ua)
        self.batch_dir.insert(0, cfg.get("save_dir", ""))
        self.batch_delay.insert(0, str(cfg.get("delay", 2.0)))
        self.batch_method.set(cfg.get("method", "trafilatura"))
        self.batch_fmt.set(cfg.get("output_format", "txt"))
        self.batch_concurrency.insert(0, str(cfg.get("concurrency", 4)))
        self.batch_robots.set(cfg.get("respect_robots", True))
        self.batch_random_ua.set(cfg.get("random_ua", True))
        self.batch_random_delay.set(cfg.get("random_delay", True))
        self.batch_max_retries.insert(0, mr)

        # 整站
        self.site_ua.insert(0, ua)
        self.site_dir.insert(0, cfg.get("save_dir", ""))
        self.site_delay.insert(0, str(cfg.get("delay", 2.0)))
        self.site_method.set(cfg.get("method", "trafilatura"))
        self.site_fmt.set(cfg.get("output_format", "txt"))
        self.site_depth.insert(0, str(cfg.get("max_depth", 1)))
        self.site_img_dl.set(cfg.get("download_images", False))
        self.site_random_ua.set(cfg.get("random_ua", True))
        self.site_random_delay.set(cfg.get("random_delay", True))
        self.site_max_retries.insert(0, mr)

        # 设置
        self.setting_ua.insert(0, ua)
        self.setting_proxy.insert(0, cfg.get("proxy", ""))
        self.setting_dir.insert(0, cfg.get("save_dir", ""))
        self.setting_method.set(cfg.get("method", "trafilatura"))
        self.setting_fmt.set(cfg.get("output_format", "txt"))
        self.setting_delay.insert(0, str(cfg.get("delay", 2.0)))
        self.setting_concurrency.insert(0, str(cfg.get("concurrency", 4)))
        self.setting_random_ua.set(cfg.get("random_ua", True))
        self.setting_cache.set(cfg.get("cache_enabled", False))
        self.setting_max_retries.insert(0, mr)

    def _collect_cfg(self):
        ua = self.setting_ua.get().strip() or self.batch_ua.get().strip()
        return {
            "user_agent": ua,
            "save_dir": self.setting_dir.get().strip() or self.batch_dir.get().strip(),
            "method": self.setting_method.get(),
            "output_format": self.setting_fmt.get(),
            "delay": float(self.setting_delay.get().strip() or 2.0),
            "respect_robots": self.batch_robots.get(),
            "concurrency": int(self.setting_concurrency.get().strip() or 4),
            "max_depth": int(self.site_depth.get().strip() or 1),
            "download_images": self.site_img_dl.get(),
            "max_retries": int(self.setting_max_retries.get().strip() or 3),
            "proxy": self.setting_proxy.get().strip(),
            "random_ua": self.setting_random_ua.get(),
            "random_delay": self.site_random_delay.get(),
            "cache_enabled": self.setting_cache.get(),
            "cache_expire": 3600,
        }

    def _save_settings(self):
        cfg = self._collect_cfg()
        save_config(cfg)
        self.cfg = cfg
        messagebox.showinfo("配置已保存", f"配置已保存至：\n{CONFIG_FILE}")
        self._append_log("[SAVE] 配置已保存")

    def _reset_settings(self):
        reset_config()
        self.cfg = load_config()
        messagebox.showinfo("已恢复默认", "配置已恢复为默认值，重启程序后生效")
        self._append_log("[RETRY] 配置已恢复默认")

    def _export_settings(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
            title="导出配置")
        if filepath:
            if export_config(self._collect_cfg(), filepath):
                messagebox.showinfo("导出成功", f"配置已导出至：\n{filepath}")
                self._append_log(f"📤 配置已导出至 {filepath}")

    def _import_settings(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("JSON 文件", "*.json")],
            title="导入配置")
        if filepath:
            new_cfg = import_config(filepath)
            self.cfg = new_cfg
            save_config(new_cfg)
            messagebox.showinfo("导入成功", "配置已导入并保存")
            self._append_log(f"📥 配置已从 {filepath} 导入")

    # ==========================================================
    #  工具方法
    # ==========================================================
    def _get_proxies(self):
        proxy_str = self.setting_proxy.get().strip() or self.cfg.get("proxy", "")
        if not proxy_str:
            return None
        return {"http": proxy_str, "https": proxy_str}

    @staticmethod
    def _get_float(entry, default=2.0):
        try:
            return max(0.0, float(entry.get().strip()))
        except ValueError:
            return default

    @staticmethod
    def _get_int(entry, default=3):
        try:
            return max(1, int(entry.get().strip()))
        except ValueError:
            return default

    def _browse_single_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.single_dir.delete(0, tk.END)
            self.single_dir.insert(0, d)

    def _browse_batch_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.batch_dir.delete(0, tk.END)
            self.batch_dir.insert(0, d)

    def _browse_site_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.site_dir.delete(0, tk.END)
            self.site_dir.insert(0, d)

    def _append_log(self, msg):
        self.log_area.after(0, lambda: (
            self.log_area.insert(tk.END, msg + "\n"),
            self.log_area.see(tk.END)
        ))

    def _on_progress(self, current, total, msg=""):
        self.progress_bar.after(0, lambda: self.progress_bar.config(
            maximum=total, value=current))
        if msg:
            self._on_status(msg)

    def _on_status(self, msg):
        self.status_label.after(0, lambda: self.status_label.config(
            text=f"[WAIT] {msg}"))

    def _cancel(self):
        self.engine.cancel()
        self._on_status("已发送取消信号，等待当前任务结束...")
        self._append_log("⏹ 已发送取消信号")

    def _toggle_pause(self):
        if self.engine.is_paused():
            self.engine.resume()
            self.batch_pause_btn.config(text="⏸ 暂停")
            self._on_status("已恢复")
        else:
            self.engine.pause()
            self.batch_pause_btn.config(text="▶ 继续")
            self._on_status("已暂停")

    # ==========================================================
    #  单页操作
    # ==========================================================
    def _do_single(self):
        url = self.single_url.get().strip()
        method = self.single_method.get()
        ua = self.single_ua.get().strip()
        retries = self._get_int(self.single_max_retries, 3)
        random_ua = self.single_random_ua.get()
        if not url:
            messagebox.showwarning("提示", "请输入目标网址")
            return

        self._append_log(f"\n{'='*50}")
        self._append_log(f"单页抓取：{url}")
        self._on_status(f"正在抓取：{url[:50]}...")

        try:
            headers = {"User-Agent": ua} if ua else {}
            proxies = self._get_proxies()
            text = self.engine.single_fetch(
                url, method, headers, proxies=proxies,
                max_retries=retries, random_ua=random_ua, random_delay=True)
            if text:
                self.single_preview.after(0, lambda: (
                    self.single_preview.delete(1.0, tk.END),
                    self.single_preview.insert(tk.END, text)
                ))
                self._append_log(f"[OK] 提取成功，共 {len(text)} 个字符")
                self._on_status(f"提取成功，{len(text)} 字符")
            else:
                self._append_log("[WARN] 未提取到正文内容")
                self._on_status("未提取到正文")
        except Exception as e:
            self._append_log(f"[FAIL] 错误：{e}")
            messagebox.showerror("错误", str(e))
            self._on_status("抓取失败")

    def _save_single(self):
        text = self.single_preview.get(1.0, tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "没有可保存的内容，请先提取正文")
            return
        save_dir = self.single_dir.get().strip() or str(_SCRIPT_DIR / "output")
        os.makedirs(save_dir, exist_ok=True)
        url = self.single_url.get().strip()
        fmt = self.single_fmt.get()
        fname = url_to_filename(url, 1)
        fpath = save_output(text, url, fname, save_dir, fmt)
        self._append_log(f"[SAVE] 已保存：{fpath}")
        messagebox.showinfo("保存成功", f"文件已保存至：\n{fpath}")
        self._on_status(f"已保存：{fname}.{fmt}")

    # ==========================================================
    #  批量操作
    # ==========================================================
    def _do_batch(self):
        urls_text = self.batch_urls.get(1.0, tk.END).strip()
        urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning("提示", "请输入至少一个网址")
            return

        method = self.batch_method.get()
        fmt = self.batch_fmt.get()
        ua = self.batch_ua.get().strip()
        delay = self._get_float(self.batch_delay, 2.0)
        save_dir = self.batch_dir.get().strip() or str(_SCRIPT_DIR / "batch_output")
        robots = self.batch_robots.get()
        concur = self._get_int(self.batch_concurrency, 4)
        retries = self._get_int(self.batch_max_retries, 3)
        proxies = self._get_proxies()
        dl_img = self.batch_img_dl.get()
        random_ua = self.batch_random_ua.get()
        random_delay = self.batch_random_delay.get()

        self.engine.reset()
        self.batch_btn.config(state=tk.DISABLED)
        self.batch_pause_btn.config(state=tk.NORMAL)
        self.progress_bar.config(maximum=len(urls), value=0)
        self._append_log(f"\n{'='*50}")
        self._append_log(f"批量抓取开始：{len(urls)} 个网址，并发数={concur}，重试次数={retries}")

        def worker():
            try:
                self.engine.batch_fetch(
                    urls, method, {"User-Agent": ua} if ua else {},
                    delay, save_dir, respect_robots=robots, output_fmt=fmt,
                    concurrency=concur, proxies=proxies,
                    download_imgs=dl_img, max_retries=retries,
                    random_ua=random_ua, random_delay=random_delay)
            except Exception as e:
                self._append_log(f"[FAIL] 批量抓取出错：{e}")
            finally:
                self.batch_btn.after(0, lambda: self.batch_btn.config(
                    state=tk.NORMAL))
                self.batch_pause_btn.after(0, lambda: self.batch_pause_btn.config(
                    text="⏸ 暂停", state=tk.NORMAL))
                self.progress_bar.after(0, lambda: self._on_status("批量抓取完成"))

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    # ==========================================================
    #  整站操作
    # ==========================================================
    def _do_site(self):
        url = self.site_url.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入索引页网址")
            return

        method = self.site_method.get()
        fmt = self.site_fmt.get()
        ua = self.site_ua.get().strip()
        delay = self._get_float(self.site_delay, 2.0)
        save_dir = self.site_dir.get().strip() or str(_SCRIPT_DIR / "site_output")
        robots = self.site_robots.get()
        max_depth = self._get_int(self.site_depth, 1)
        retries = self._get_int(self.site_max_retries, 3)
        use_sitemap = self.site_sitemap.get()
        dl_img = self.site_img_dl.get()
        proxies = self._get_proxies()
        random_ua = self.site_random_ua.get()
        random_delay = self.site_random_delay.get()

        self.engine.reset()
        self.site_btn.config(state=tk.DISABLED)
        self._append_log(f"\n{'='*50}")
        self._append_log(f"整站爬取开始：{url}")

        def worker():
            try:
                self.engine.site_crawl(
                    url, method, {"User-Agent": ua} if ua else {},
                    delay, save_dir, respect_robots=robots, output_fmt=fmt,
                    max_depth=max_depth, use_sitemap=use_sitemap,
                    proxies=proxies, download_images=dl_img,
                    max_retries=retries, random_ua=random_ua,
                    random_delay=random_delay)
            except Exception as e:
                self._append_log(f"[FAIL] 整站爬取出错：{e}")
            finally:
                self.site_btn.after(0, lambda: self.site_btn.config(
                    state=tk.NORMAL))
                self.progress_bar.after(0, lambda: self._on_status("整站爬取完成"))

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
