#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
论坛抓取模块 v5.5

针对 IPB（Invision Power Board）风格论坛设计，支持：
  - 版块列表页翻页（showforum=FID&...&st=0/30/60...）
  - 主题详情页（二级页面）翻页（showtopic=TID&st=0/15/30...）
  - 逐帖提取：楼层号 / 作者 / 时间 / 正文
  - 断点续传（checkpoint.json）+ 索引输出（index.json / index.csv）
  - 身份池轮换 + 限速（复用 WebCopier 反爬体系）

已验证站点：trow.cc（The Ring of Wonder，IPB 2.x skin）
"""

import os
import re
import csv
import json
import time
import random
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

from .http_client import http_get, build_headers, auto_referer
from .identity_manager import get_identity_manager
from .constants import VERSION


# ============================================================
#  站点模板
# ============================================================

SITE_PRESETS = {
    # trow.cc（The Ring of Wonder）—— IPB 2.x
    "trow": {
        "board_base": "https://trow.cc/board/",
        "forum_url": "{base}showforum={fid}&is_digest=&prune_day=100"
                     "&sort_by=Z-A&sort_key=last_post&topicfilter=all&st={st}",
        "topic_url": "{base}showtopic={tid}&st={st}",
        "forum_step": 30,
        "topic_step": 15,
        "title_suffix": " - The Ring of Wonder",
    },
    # 通用 IPB 2.x：需自行确认每页条数
    "ipb2": {
        "board_base": "",
        "forum_url": "{base}showforum={fid}&prune_day=100&st={st}",
        "topic_url": "{base}showtopic={tid}&st={st}",
        "forum_step": 30,
        "topic_step": 15,
        "title_suffix": "",
    },
}


# ============================================================
#  数据结构
# ============================================================

@dataclass
class ForumPost:
    """单条回帖"""
    index: int          # 楼层号（Post #N）
    pid: str            # 帖子 ID
    author: str
    time: str
    body: str
    chars: int = 0

    def __post_init__(self):
        self.chars = len(self.body)


@dataclass
class ForumTopic:
    """列表页中的一条主题"""
    tid: str
    title: str
    url: str
    replies: str = ""
    views: str = ""
    author: str = ""
    last_post: str = ""
    forum_id: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class CrawlStats:
    """抓取统计"""
    forums: int = 0
    listing_pages: int = 0
    topics_total: int = 0
    topics_done: int = 0
    topics_failed: int = 0
    topic_pages: int = 0
    posts: int = 0
    chars: int = 0
    started_at: str = ""
    finished_at: str = ""
    elapsed_sec: float = 0.0

    def to_dict(self):
        return asdict(self)


# ============================================================
#  HTML → 纯文本
# ============================================================

_BLOCK_TAGS = {
    "p", "div", "li", "tr", "br", "blockquote", "table",
    "h1", "h2", "h3", "h4", "h5", "h6", "pre", "ul", "ol", "dl",
}

# 需要整块剔除的噪声（编辑记录、签名档分隔等）
_NOISE_SELECTORS = [
    ("span", "edit"),
    ("div", "edit"),
    ("span", "signature"),
]


def _strip_noise(node):
    """剔除编辑记录等噪声节点"""
    for tag_name, cls in _NOISE_SELECTORS:
        for el in node.find_all(tag_name, class_=cls):
            el.decompose()
    return node


def node_to_text(node) -> str:
    """把 HTML 节点转为保留段落结构的纯文本。

    - <br> → 换行
    - 块级标签 → 末尾补换行
    - 连续空行折叠为 1 行
    """
    for br in node.find_all("br"):
        br.replace_with("\n")
    for tag in node.find_all(_BLOCK_TAGS):
        if tag.name == "br":
            continue
        tag.append("\n")

    text = node.get_text()

    lines = []
    blank = 0
    for raw in text.split("\n"):
        line = re.sub(r"[ \t\u3000\r]+", " ", raw).strip()
        if line:
            lines.append(line)
            blank = 0
        else:
            blank += 1
            if blank <= 1:
                lines.append("")
    # 去掉尾部空行
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


# ============================================================
#  页面解析
# ============================================================

_TOPIC_RE = re.compile(r"showtopic=(\d+)")
_FORUM_RE = re.compile(r"showforum=(\d+)")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2},\s*\d{2}:\d{2}")


def _clean_last_post(text: str) -> str:
    """去掉 IPB 列表页「Last post by: xxx」尾巴，只保留时间"""
    text = re.sub(r"Last post by:.*$", "", text, flags=re.I | re.S)
    return text.strip()


def parse_forum_page(html: str, fid: str, base_url: str = ""):
    """解析版块列表页。

    Returns:
        (topics, subforums)
        topics:    list[ForumTopic] —— 本页主题行（已排除子版块行）
        subforums: list[(fid, name)] —— 子版块（仅首页有意义）
    """
    soup = BeautifulSoup(html, "lxml")
    wrap = soup.find("div", id="ipbwrapper") or soup

    topics = []
    seen_tids = set()

    for tr in wrap.select("table.ipbtable tr"):
        link = None
        for cand in tr.find_all("a", href=True):
            href = cand["href"]
            # 关键：排除 &view=getlastpost/getnewpost 等跳转链接，
            # 否则子版块行的「最后回复」也会被误判为主题
            if "view=" in href:
                continue
            m = _TOPIC_RE.search(href)
            if m and cand.get_text(strip=True):
                link = (cand, m.group(1))
                break
        if not link:
            continue

        a_tag, tid = link
        if tid in seen_tids:
            continue
        seen_tids.add(tid)

        tds = tr.find_all("td", recursive=False)
        topic = ForumTopic(
            tid=tid,
            title=a_tag.get_text(strip=True),
            url=urljoin(base_url, f"showtopic={tid}") if base_url else a_tag["href"],
            forum_id=str(fid),
        )
        # 常规列布局: [图标, (可选)图标2, 标题, 回复, 作者, 浏览, 最后回复]
        if len(tds) >= 7:
            topic.replies = tds[3].get_text(" ", strip=True)
            topic.author = tds[4].get_text(" ", strip=True)
            topic.views = tds[5].get_text(" ", strip=True)
            topic.last_post = _clean_last_post(tds[6].get_text(" ", strip=True))
        elif len(tds) >= 5:
            topic.replies = tds[2].get_text(" ", strip=True)
            topic.author = tds[3].get_text(" ", strip=True)
            topic.views = tds[4].get_text(" ", strip=True)
        topics.append(topic)

    # 子版块（用于 --with-subforums）
    subforums = []
    seen_fids = set()
    for tr in wrap.select("table.ipbtable tr"):
        for cand in tr.find_all("a", href=True):
            m = _FORUM_RE.search(cand["href"])
            if not m:
                continue
            sub_id = m.group(1)
            name = cand.get_text(strip=True)
            if not name or sub_id in seen_fids or sub_id == str(fid):
                continue
            # 排除分页链接（文本为纯数字或符号）
            if re.fullmatch(r"[\d›»«\.\s]+", name):
                continue
            seen_fids.add(sub_id)
            subforums.append((sub_id, name))
            break

    return topics, subforums


def parse_topic_page(html: str, tid: str = ""):
    """解析主题详情页（单页）。

    Returns:
        (title, posts)  posts 为 list[ForumPost]
    """
    soup = BeautifulSoup(html, "lxml")

    # 标题：优先 <title>，去掉站点后缀
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    title = re.sub(r"\s*-\s*The Ring of Wonder\s*$", "", title).strip()

    posts = []
    for main_td in soup.find_all("td", id=lambda v: v and v.startswith("post-main-")):
        pid = main_td["id"].split("post-main-")[-1]

        # 正文
        body_node = main_td.find("div", class_="postcolor3") or main_td
        inner = body_node.find("div", id=f"post-{pid}") or body_node
        inner = _strip_noise(inner)
        body = node_to_text(inner)

        # 作者 / 时间：位于同一 <table> 的首行
        author, post_time, floor = "", "", 0
        table = main_td.find_parent("table")
        if table:
            for tr in table.find_all("tr"):
                head = tr.get_text(" ", strip=True)
                m_date = _DATE_RE.search(head)
                if m_date:
                    post_time = m_date.group(0).replace(", ", " ")
                    a_tag = tr.find("a")
                    if a_tag:
                        author = a_tag.get_text(strip=True)
                    m_floor = re.search(r"Post\s*#(\d+)", head)
                    if m_floor:
                        floor = int(m_floor.group(1))
                    break

        posts.append(ForumPost(
            index=floor or len(posts) + 1,
            pid=pid,
            author=author,
            time=post_time,
            body=body,
        ))

    posts.sort(key=lambda p: p.index)
    return title, posts


# ============================================================
#  文件名安全化
# ============================================================

def safe_filename(name: str, maxlen: int = 60) -> str:
    """把标题转为合法文件名（保留中日韩字符）"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "", name).strip()
    name = re.sub(r"\s+", " ", name)
    name = name.strip(". ")
    if len(name) > maxlen:
        name = name[:maxlen].rstrip()
    return name or "untitled"


# ============================================================
#  论坛爬虫
# ============================================================

class ForumCrawler:
    """论坛爬虫：版块翻页 → 主题二级页翻页 → 逐帖提取"""

    def __init__(self, preset: str = "trow", board_base: str = "",
                 log=print, progress=None,
                 delay: float = 2.0, max_retries: int = 3,
                 workers: int = 1, proxies=None,
                 use_curl_cffi: bool = False,
                 random_delay: bool = True,
                 user_agent: str = ""):
        cfg = dict(SITE_PRESETS.get(preset, SITE_PRESETS["ipb2"]))
        if board_base:
            cfg["board_base"] = board_base if board_base.endswith("/") else board_base + "/"

        self.preset = preset
        self.cfg = cfg
        self.base = cfg["board_base"]
        self.forum_step = cfg["forum_step"]
        self.topic_step = cfg["topic_step"]

        self.log = log or (lambda *a, **k: None)
        self.progress = progress
        self.delay = max(0.0, delay)
        self.max_retries = max(1, max_retries)
        self.workers = max(1, workers)
        self.proxies = proxies
        self.use_curl_cffi = use_curl_cffi
        self.random_delay = random_delay
        self.user_agent = user_agent

        self.identity_mgr = get_identity_manager()
        self.stats = CrawlStats()

        self._cancel = False
        self._lock = threading.Lock()
        self._last_request = 0.0

        # 统计
        self.request_count = 0
        self.fail_count = 0

    # ---------------- 控制 ----------------
    def cancel(self):
        self._cancel = True

    # ---------------- HTTP ----------------
    def _throttle(self):
        """全局限速（并发下按 workers 摊薄）"""
        period = max(self.delay / self.workers, 0.05) if self.workers > 1 else self.delay
        with self._lock:
            now = time.time()
            wait = period - (now - self._last_request)
            self._last_request = max(now, self._last_request + period)
        if wait > 0:
            time.sleep(wait)
        if self.random_delay:
            time.sleep(random.uniform(0.0, 0.6))

    def fetch(self, url: str) -> str:
        """带身份轮换与重试的 GET，返回 HTML 文本"""
        last_error = None
        attempts = min(self.max_retries, max(1, self.identity_mgr.count))

        for attempt in range(attempts):
            if self._cancel:
                raise RuntimeError("用户取消")
            if attempt > 0:
                backoff = min(2 ** attempt, 60)
                self.log(f"    [RETRY] {attempt}/{attempts - 1} 等待 {backoff}s: {url}")
                time.sleep(backoff)

            identity = self.identity_mgr.get_identity(attempt)
            headers = self.identity_mgr.build_headers(
                identity, referer=auto_referer(url))
            if self.user_agent:
                headers["User-Agent"] = self.user_agent

            self._throttle()
            try:
                resp = http_get(url, headers=headers, timeout=30,
                                proxies=self.proxies,
                                use_curl_cffi=self.use_curl_cffi)
                self.request_count += 1
                return resp.text
            except Exception as e:
                last_error = e
                self.fail_count += 1

        raise last_error

    # ---------------- URL 构造 ----------------
    def forum_url(self, fid, st=0) -> str:
        return self.cfg["forum_url"].format(base=self.base, fid=fid, st=st)

    def topic_url(self, tid, st=0) -> str:
        return self.cfg["topic_url"].format(base=self.base, tid=tid, st=st)

    # ---------------- 列表页翻页 ----------------
    def crawl_forum_listing(self, fid, max_pages=None, with_subforums=False):
        """遍历版块所有列表页，返回主题列表（含子版块主题）。"""
        fid = str(fid)
        all_topics = {}
        seen_sub = set()
        pending_fids = [fid]
        page_no = 0

        while pending_fids:
            cur = pending_fids.pop(0)
            st = 0
            local_pages = 0
            while True:
                if self._cancel:
                    return list(all_topics.values())
                if max_pages and local_pages >= max_pages:
                    break

                url = self.forum_url(cur, st)
                self.log(f"[列表] forum={cur} st={st} -> {url}")
                try:
                    html = self.fetch(url)
                except Exception as e:
                    self.log(f"  [FAIL] 列表页获取失败: {e}")
                    break

                self.stats.listing_pages += 1
                local_pages += 1
                page_no += 1

                topics, subs = parse_forum_page(html, cur, self.base)
                new_cnt = 0
                for t in topics:
                    if t.tid not in all_topics:
                        all_topics[t.tid] = t
                        new_cnt += 1
                self.log(f"  发现 {len(topics)} 条主题（新增 {new_cnt}，累计 {len(all_topics)}）")

                if with_subforums:
                    for sub_id, sub_name in subs:
                        if sub_id not in seen_sub and sub_id != fid:
                            seen_sub.add(sub_id)
                            pending_fids.append(sub_id)
                            self.log(f"  [子版块] {sub_id} {sub_name}")

                # 翻页终止条件：本页无主题，或主题数不足一页
                if not topics or len(topics) < self.forum_step:
                    break
                st += self.forum_step

                if self.progress:
                    self.progress(len(all_topics), 0, f"列表页 {page_no}")

        return list(all_topics.values())

    # ---------------- 主题页翻页 ----------------
    def crawl_topic(self, tid, forum_id="", max_pages=None):
        """抓取单个主题的所有楼层，返回 dict。"""
        tid = str(tid)
        posts = []
        seen_pids = set()
        title = ""
        st = 0
        pages = 0

        while True:
            if self._cancel:
                break
            if max_pages and pages >= max_pages:
                break

            url = self.topic_url(tid, st)
            html = self.fetch(url)
            self.stats.topic_pages += 1
            pages += 1

            page_title, page_posts = parse_topic_page(html, tid)
            if page_title and not title:
                title = page_title

            new_cnt = 0
            for p in page_posts:
                if p.pid and p.pid in seen_pids:
                    continue
                seen_pids.add(p.pid)
                posts.append(p)
                new_cnt += 1

            if not page_posts or new_cnt == 0:
                break
            if len(page_posts) < self.topic_step:
                break
            st += self.topic_step

        posts.sort(key=lambda p: p.index)
        return {
            "tid": tid,
            "forum_id": str(forum_id),
            "title": title,
            "url": self.topic_url(tid, 0),
            "post_count": len(posts),
            "char_count": sum(p.chars for p in posts),
            "posts": [asdict(p) for p in posts],
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "engine": f"WebCopier v{VERSION}",
        }


# ============================================================
#  输出
# ============================================================

def _render_topic_md(data: dict) -> str:
    lines = [
        f"# {data['title'] or '(无标题)'}",
        "",
        f"- 主题 ID: {data['tid']}",
        f"- 版块 ID: {data['forum_id']}",
        f"- 链接: {data['url']}",
        f"- 楼层数: {data['post_count']}",
        f"- 字数: {data['char_count']}",
        f"- 抓取时间: {data['crawled_at']}",
        f"- 引擎: {data['engine']}",
        "",
        "---",
        "",
    ]
    for p in data["posts"]:
        lines.append(f"## #{p['index']} · {p['author'] or '匿名'} · {p['time'] or ''}")
        lines.append("")
        lines.append(p["body"] or "(空)")
        lines.append("")
    return "\n".join(lines)


def _render_topic_txt(data: dict) -> str:
    lines = [
        f"标题: {data['title'] or '(无标题)'}",
        f"主题ID: {data['tid']}   版块ID: {data['forum_id']}",
        f"链接: {data['url']}",
        f"楼层数: {data['post_count']}   字数: {data['char_count']}",
        f"抓取时间: {data['crawled_at']}  引擎: {data['engine']}",
        "=" * 60,
        "",
    ]
    for p in data["posts"]:
        lines.append(f"[#{p['index']}] {p['author'] or '匿名'} @ {p['time'] or ''}")
        lines.append("-" * 40)
        lines.append(p["body"] or "(空)")
        lines.append("")
    return "\n".join(lines)


_TOPIC_RENDERERS = {
    "md": _render_topic_md,
    "txt": _render_topic_txt,
}


# 论坛主题输出支持的所有扩展名
_TOPIC_EXTS = ("md", "txt", "json", "jsonl")


def save_topic(data: dict, save_dir: str, fmt: str = "md") -> str:
    """保存单个主题，返回文件路径"""
    os.makedirs(save_dir, exist_ok=True)
    name = f"{data['forum_id']}_{data['tid']}_{safe_filename(data['title'])}"
    # v5.5 修复：此前扩展名用 `fmt in _TOPIC_RENDERERS` 判断，
    # 而该表只含 md/txt，导致 json/jsonl 的内容被写成 .txt 文件名。
    ext = fmt if fmt in _TOPIC_EXTS else "txt"
    fname = f"{name}.{ext}"
    fpath = os.path.join(save_dir, fname)

    if fmt == "json":
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    elif fmt == "jsonl":
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    else:
        render = _TOPIC_RENDERERS.get(fmt, _render_topic_txt)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(render(data))
    return fpath


# ============================================================
#  断点续传状态
# ============================================================

class CrawlState:
    """断点续传状态（checkpoint.json）"""

    def __init__(self, path: str):
        self.path = path
        self.listing = {}   # fid -> [topic dict, ...]
        self.done = {}      # tid -> {file, title, posts, chars, forum_id}
        self.failed = {}    # tid -> error
        self._lock = threading.Lock()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.listing = data.get("listing", {})
                self.done = data.get("done", {})
                self.failed = data.get("failed", {})
                return True
            except Exception:
                return False
        return False

    def save(self):
        with self._lock:
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "listing": self.listing,
                            "done": self.done,
                            "failed": self.failed,
                        },
                        f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
            except Exception:
                pass


# ============================================================
#  高层入口：抓取多个版块
# ============================================================

def crawl_forums(fids, save_dir, preset="trow", board_base="",
                 fmt="md", delay=2.0, workers=1, max_retries=3,
                 max_listing_pages=None, max_topics=None,
                 max_post_pages=None, with_subforums=False,
                 resume=True, proxies=None, use_curl_cffi=False,
                 log=print, progress=None, user_agent=""):
    """抓取一个或多个版块的全部主题。

    Args:
        fids: 版块 ID 列表
        save_dir: 输出根目录
        fmt: md / txt / json / jsonl
        with_subforums: 是否递归抓取子版块
        resume: 是否断点续传
        max_listing_pages: 每个版块最多抓几页列表（调试用）
        max_topics: 最多抓几个主题（调试用）
        max_post_pages: 每个主题最多抓几页回帖（调试用）

    Returns:
        (crawler, state)
    """
    os.makedirs(save_dir, exist_ok=True)
    state = CrawlState(os.path.join(save_dir, "checkpoint.json"))

    crawler = ForumCrawler(preset=preset, board_base=board_base, log=log,
                           progress=progress, delay=delay, max_retries=max_retries,
                           workers=workers, proxies=proxies,
                           use_curl_cffi=use_curl_cffi, user_agent=user_agent)
    crawler.stats.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()

    if resume:
        if state.load():
            log(f"[续传] 已加载断点：列表 {len(state.listing)} 个版块，"
                f"已完成 {len(state.done)} 个主题，失败 {len(state.failed)} 个")

    # ---------- 1. 收集主题列表 ----------
    all_topics = []
    for fid in fids:
        fid = str(fid)
        if resume and fid in state.listing:
            cached = [ForumTopic(**t) for t in state.listing[fid]]
            log(f"[列表] forum={fid} 使用缓存：{len(cached)} 条主题")
        else:
            cached = crawler.crawl_forum_listing(
                fid, max_pages=max_listing_pages,
                with_subforums=with_subforums)
            state.listing[fid] = [t.to_dict() for t in cached]
            state.save()
        all_topics.extend(cached)

    # 去重（tid 唯一）
    uniq = {}
    for t in all_topics:
        uniq.setdefault(t.tid, t)
    all_topics = list(uniq.values())
    all_topics.sort(key=lambda t: (-int(t.tid) if t.tid.isdigit() else 0))

    crawler.stats.forums = len(fids)
    crawler.stats.topics_total = len(all_topics)

    if max_topics:
        all_topics = all_topics[:max_topics]

    pending = [t for t in all_topics if t.tid not in state.done]
    log(f"\n[计划] 共 {len(all_topics)} 个主题，"
        f"跳过已完成 {len(all_topics) - len(pending)} 个，待抓 {len(pending)} 个\n")

    # ---------- 2. 逐个主题抓取 ----------
    total = len(pending)
    finished = 0

    def _work(topic):
        nonlocal finished
        per_dir = os.path.join(save_dir, f"forum_{topic.forum_id}")
        try:
            data = crawler.crawl_topic(topic.tid, topic.forum_id,
                                       max_pages=max_post_pages)
            if not data["title"]:
                data["title"] = topic.title
            fpath = save_topic(data, per_dir, fmt)
            record = {
                "file": os.path.relpath(fpath, save_dir).replace("\\", "/"),
                "title": data["title"],
                "posts": data["post_count"],
                "chars": data["char_count"],
                "forum_id": topic.forum_id,
                "tid": topic.tid,
                "url": data["url"],
                "replies": topic.replies,
                "views": topic.views,
                "author": topic.author,
                "last_post": topic.last_post,
            }
            state.done[topic.tid] = record
            state.failed.pop(topic.tid, None)
            return topic.tid, record, None
        except Exception as e:
            state.failed[topic.tid] = str(e)
            return topic.tid, None, e

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_work, t): t for t in pending}
            for fut in as_completed(futures):
                tid, rec, err = fut.result()
                finished += 1
                if err:
                    crawler.stats.topics_failed += 1
                    log(f"  [FAIL] ({finished}/{total}) tid={tid}: {err}")
                else:
                    crawler.stats.topics_done += 1
                    crawler.stats.posts += rec["posts"]
                    crawler.stats.chars += rec["chars"]
                    log(f"  [OK] ({finished}/{total}) tid={tid} "
                        f"{rec['posts']}帖/{rec['chars']}字 | {rec['title'][:40]}")
                if progress:
                    progress(finished, total, f"{finished}/{total}")
                if finished % 5 == 0:
                    state.save()
    else:
        for topic in pending:
            tid, rec, err = _work(topic)
            finished += 1
            if err:
                crawler.stats.topics_failed += 1
                log(f"  [FAIL] ({finished}/{total}) tid={tid}: {err}")
            else:
                crawler.stats.topics_done += 1
                crawler.stats.posts += rec["posts"]
                crawler.stats.chars += rec["chars"]
                log(f"  [OK] ({finished}/{total}) tid={tid} "
                    f"{rec['posts']}帖/{rec['chars']}字 | {rec['title'][:40]}")
            if progress:
                progress(finished, total, f"{finished}/{total}")
            if finished % 5 == 0:
                state.save()

    state.save()

    # ---------- 3. 索引输出 ----------
    # 先收尾统计，再写索引，否则 finished_at / elapsed_sec 会为空
    # 汇总按累积状态计算，断点续传时索引仍反映完整语料而非仅本次增量
    crawler.stats.topics_total = len(all_topics)
    crawler.stats.topics_done = len(state.done)
    crawler.stats.topics_failed = len(state.failed)
    crawler.stats.posts = sum(int(r.get("posts", 0)) for r in state.done.values())
    crawler.stats.chars = sum(int(r.get("chars", 0)) for r in state.done.values())
    crawler.stats.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    crawler.stats.elapsed_sec = round(time.time() - t0, 1)

    records = list(state.done.values())
    records.sort(key=lambda r: (str(r.get("forum_id", "")),
                                -int(r["tid"]) if str(r["tid"]).isdigit() else 0))

    index_json = os.path.join(save_dir, "index.json")
    with open(index_json, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "engine": f"WebCopier v{VERSION}",
            "site": crawler.base,
            "forums": [str(f) for f in fids],
            "stats": crawler.stats.to_dict(),
            "topics": records,
        }, f, ensure_ascii=False, indent=2)

    index_csv = os.path.join(save_dir, "index.csv")
    with open(index_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["forum_id", "tid", "title", "author", "replies",
                    "views", "last_post", "posts", "chars", "file", "url"])
        for r in records:
            w.writerow([r.get("forum_id", ""), r.get("tid", ""), r.get("title", ""),
                        r.get("author", ""), r.get("replies", ""), r.get("views", ""),
                        r.get("last_post", ""), r.get("posts", 0), r.get("chars", 0),
                        r.get("file", ""), r.get("url", "")])

    jsonl_path = os.path.join(save_dir, "corpus.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({
                "tid": r.get("tid"), "forum_id": r.get("forum_id"),
                "title": r.get("title"), "url": r.get("url"),
                "author": r.get("author"), "posts": r.get("posts"),
                "chars": r.get("chars"), "file": r.get("file"),
            }, ensure_ascii=False) + "\n")

    if state.failed:
        failed_path = os.path.join(save_dir, "failed.json")
        with open(failed_path, "w", encoding="utf-8") as f:
            json.dump(state.failed, f, ensure_ascii=False, indent=2)

    return crawler, state
