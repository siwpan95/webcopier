#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebCopier 命令行接口（CLI）v5.5

在命令提示符（cmd.exe）/ PowerShell / 终端中使用：

    webcopier fetch  <URL>              抓取单个页面
    webcopier batch  <文件>             批量抓取（每行一个 URL）
    webcopier crawl  <URL>              整站爬取
    webcopier forum  <版块ID...>        论坛抓取（列表翻页 + 主题二级页翻页）
    webcopier config [--show|--set k=v|--reset]

示例：
    webcopier fetch https://example.com/article -m trafilatura -o out -f md
    webcopier batch urls.txt --delay 2 --concurrency 4
    webcopier crawl https://example.com --depth 2 --sitemap
    webcopier forum 150 177 171 176 --preset trow -o output/trow --delay 2
"""

import os
import sys
import argparse
import json

from .constants import VERSION, EXTRACT_METHODS, OUTPUT_FORMATS, METHOD_SHORT
from .config import load_config, save_config, reset_config, DEFAULT_CONFIG
from .http_client import parse_proxy, build_headers
from .identity_manager import get_identity_manager


# ============================================================
#  控制台输出（Windows GBK 终端安全）
# ============================================================

def _safe_print(*args, **kwargs):
    """Windows 控制台安全输出。

    终端是 TTY 时用控制台代码页（GBK/936），重定向到文件/管道时用 UTF-8，
    遇到无法编码的字符降级为 '?'，绝不抛 UnicodeEncodeError 中断抓取。
    """
    sep = kwargs.pop("sep", " ")
    end = kwargs.pop("end", "\n")
    text = sep.join(str(a) for a in args) + end

    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        data = text.encode(enc, "replace")
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            try:
                buf.write(data)
            except Exception:
                sys.stdout.write(data.decode(enc, "replace"))
        else:
            sys.stdout.write(data.decode(enc, "replace"))
    except Exception:
        data = text.encode("ascii", "replace")
        sys.stdout.write(data.decode("ascii"))

    try:
        sys.stdout.flush()
    except Exception:
        pass


def configure_console():
    """按输出目标选择编码：TTY 跟随控制台代码页，重定向用 UTF-8。"""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            is_tty = stream.isatty()
        except Exception:
            is_tty = False
        try:
            if is_tty:
                # 保持控制台代码页（GBK），只放宽错误处理
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def make_logger(verbose: bool = True, quiet: bool = False):
    """构造日志函数"""
    def log(*args, **kwargs):
        if quiet:
            return
        _safe_print(*args, **kwargs)
        try:
            sys.stdout.flush()
        except Exception:
            pass
    return log


# ============================================================
#  通用参数装配
# ============================================================

def _build_headers(cfg: dict, args) -> dict:
    """根据配置 + 命令行参数构建请求头"""
    identity_mgr = get_identity_manager()
    identity = identity_mgr.get_identity(0)
    headers = identity_mgr.build_headers(identity)
    if getattr(args, "user_agent", ""):
        headers["User-Agent"] = args.user_agent
    elif cfg.get("user_agent"):
        headers["User-Agent"] = cfg["user_agent"]
    if getattr(args, "cookie", ""):
        headers["Cookie"] = args.cookie
    elif cfg.get("cookie_file") and os.path.exists(cfg["cookie_file"]):
        try:
            with open(cfg["cookie_file"], "r", encoding="utf-8") as f:
                headers["Cookie"] = f.read().strip()
        except Exception:
            pass
    return headers


def _get_proxies(cfg: dict, args):
    proxy = getattr(args, "proxy", "") or cfg.get("proxy", "")
    return parse_proxy(proxy) if proxy else None


# ============================================================
#  子命令：fetch
# ============================================================

def cmd_fetch(args, cfg, log):
    from .engine import CrawlerEngine
    from .writer import save_output, url_to_filename
    from .extractors import extract

    headers = _build_headers(cfg, args)
    proxies = _get_proxies(cfg, args)

    log(f"[单页] {args.url}")
    text = extract(args.url, args.method, headers, proxies=proxies,
                   random_delay=args.random_delay)
    if not text:
        log("[WARN] 未提取到正文")
        return 1

    os.makedirs(args.out, exist_ok=True)
    fname = url_to_filename(args.url, 1)
    path = save_output(text, args.url, fname, args.out, args.format)
    log(f"[OK] 已保存 {len(text)} 字符 -> {os.path.abspath(path)}")
    if args.stdout:
        _safe_print(text)
    return 0


# ============================================================
#  子命令：batch
# ============================================================

def cmd_batch(args, cfg, log):
    from .engine import CrawlerEngine

    if not os.path.exists(args.file):
        log(f"[ERROR] URL 列表文件不存在: {args.file}")
        return 2

    with open(args.file, "r", encoding="utf-8") as f:
        urls = [ln.strip() for ln in f
                if ln.strip() and not ln.strip().startswith("#")]
    if not urls:
        log("[ERROR] 列表文件中没有有效 URL")
        return 2

    headers = _build_headers(cfg, args)
    proxies = _get_proxies(cfg, args)

    engine = CrawlerEngine(
        log_callback=log,
        progress_callback=lambda c, t, m: log(f"  [进度] {c}/{t}"),
        status_callback=lambda m: log(f"[状态] {m}"))

    log(f"[批量] {len(urls)} 个网址 -> {os.path.abspath(args.out)}")
    engine.batch_fetch(
        urls, args.method, headers, args.delay, args.out,
        respect_robots=not args.ignore_robots,
        output_fmt=args.format, concurrency=args.concurrency,
        proxies=proxies, download_imgs=args.images,
        max_retries=args.retries, random_delay=args.random_delay)
    return 0


# ============================================================
#  子命令：crawl
# ============================================================

def cmd_crawl(args, cfg, log):
    from .engine import CrawlerEngine

    headers = _build_headers(cfg, args)
    proxies = _get_proxies(cfg, args)

    engine = CrawlerEngine(
        log_callback=log,
        progress_callback=lambda c, t, m: log(f"  [进度] {c}/{t}"),
        status_callback=lambda m: log(f"[状态] {m}"))

    log(f"[整站] {args.url} (深度={args.depth})")
    engine.site_crawl(
        args.url, args.method, headers, args.delay, args.out,
        respect_robots=not args.ignore_robots,
        output_fmt=args.format, max_depth=args.depth,
        use_sitemap=args.sitemap, proxies=proxies,
        download_images=args.images, max_retries=args.retries,
        random_delay=args.random_delay)
    return 0


# ============================================================
#  子命令：forum
# ============================================================

def cmd_forum(args, cfg, log):
    from .forum import crawl_forums

    proxies = _get_proxies(cfg, args)

    log("=" * 62)
    log(f"  WebCopier v{VERSION} — 论坛抓取")
    log(f"  版块: {', '.join(args.forum_ids)}")
    log(f"  输出: {os.path.abspath(args.out)}")
    log(f"  格式: {args.format}   延迟: {args.delay}s   并发: {args.workers}")
    log("=" * 62)

    crawler, state = crawl_forums(
        args.forum_ids, args.out,
        preset=args.preset, board_base=args.board_base or "",
        fmt=args.format, delay=args.delay, workers=args.workers,
        max_retries=args.retries,
        max_listing_pages=args.max_listing_pages,
        max_topics=args.max_topics,
        max_post_pages=args.max_post_pages,
        with_subforums=args.with_subforums,
        resume=not args.no_resume,
        proxies=proxies, use_curl_cffi=args.curl_cffi,
        log=log, user_agent=args.user_agent or "")

    s = crawler.stats
    log("")
    log("=" * 62)
    log("  抓取完成")
    log(f"  主题: {s.topics_done} 成功 / {s.topics_failed} 失败 / {s.topics_total} 总计")
    log(f"  楼层: {s.posts}   正文字数: {s.chars}")
    log(f"  请求: {crawler.request_count} 次（失败 {crawler.fail_count} 次）")
    log(f"  列表页: {s.listing_pages}   主题页: {s.topic_pages}")
    log(f"  耗时: {s.elapsed_sec}s")
    log(f"  输出目录: {os.path.abspath(args.out)}")
    log("  - index.json / index.csv / corpus.jsonl （索引）")
    log("  - checkpoint.json （断点，重跑同命令可续传）")
    log("=" * 62)
    return 0


# ============================================================
#  子命令：es（Everything 命令行搜索）
# ============================================================

def _fmt_size(n) -> str:
    if n is None:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def _render_es_table(results, log, show_size=False):
    """把结果渲染成对齐的表格"""
    if not results:
        return
    col_size = max((len(_fmt_size(r.size)) for r in results), default=0)
    col_size = max(col_size, 4)
    for r in results:
        if show_size:
            log(f"  {_fmt_size(r.size).rjust(col_size)}  {r.path}")
        else:
            log(f"  {r.path}")


def cmd_es(args, cfg, log):
    from .everything import (EverythingSearcher, EverythingError,
                             to_file_url, is_probably_webpage)

    try:
        searcher = EverythingSearcher(es_path=args.es_path or "",
                                      timeout=args.timeout,
                                      instance=args.instance or "")
    except EverythingError as e:
        log(f"[ERROR] {e}")
        return 2

    # ---------- 诊断模式 ----------
    if args.status:
        info = searcher.status()
        log(f"  es.exe           : {info.get('es_path')}")
        log(f"  ES 版本          : {info.get('es_version', '-')}")
        log(f"  Everything 版本  : {info.get('everything_version', '-')}")
        if info.get("ok"):
            log("  连通性           : [OK] Everything 正在运行，IPC 可用")
            return 0
        log(f"  连通性           : [FAIL] {info.get('error')}")
        log("  → 请先启动 Everything 后重试。")
        return 1

    if not args.query:
        log("[ERROR] 缺少搜索词。用法: webcopier es \"关键词\"")
        log("        诊断连通性: webcopier es --status")
        return 2

    # ---------- 执行搜索 ----------
    columns = [c.strip() for c in (args.columns or "").split(",") if c.strip()]
    if args.format == "table" and args.size:
        if "size" not in columns:
            columns.append("size")

    try:
        results = searcher.search(
            args.query,
            count=args.count,
            match_path=args.match_path,
            match_case=args.case,
            regex=args.regex,
            files_only=args.files_only,
            folders_only=args.folders_only,
            sort=args.sort or "",
            columns=columns,
            path_filter=args.path or "",
            extra_args=list(args.es_args or []),
        )
    except EverythingError as e:
        log(f"[ERROR] {e}")
        return 1

    if not results:
        log("[结果] 没有匹配项。")
        if not args.no_result_error:
            return 0
        return 3

    # ---------- 输出 ----------
    if args.format == "json":
        import json as _json
        log(_json.dumps([r.to_dict() for r in results],
                        ensure_ascii=False, indent=2))
    elif args.format == "csv":
        import csv as _csv
        import io
        buf = io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["path", "name", "size", "date_modified", "extension"])
        for r in results:
            w.writerow([r.path, r.name, r.size or "",
                        r.date_modified, r.extension])
        log(buf.getvalue().rstrip())
    elif args.format == "paths":
        for r in results:
            log(r.path)
    else:
        _render_es_table(results, log, show_size=args.size)

    log(f"\n[结果] 共 {len(results)} 项")

    # ---------- 落盘 ----------
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8", newline="") as f:
                for r in results:
                    f.write(r.path + "\n")
            log(f"[OK] 路径清单已写入: {os.path.abspath(args.out)}")
        except OSError as e:
            log(f"[ERROR] 写入失败: {e}")
            return 1

    # ---------- 资源管理器定位 ----------
    if args.open:
        idx = args.open - 1
        if 0 <= idx < len(results):
            target = results[idx].path
            try:
                subprocess.run(["explorer", "/select,", target], check=False)
                log(f"[OK] 已在资源管理器中定位: {target}")
            except Exception as e:
                log(f"[ERROR] 打开失败: {e}")
        else:
            log(f"[ERROR] 序号越界: {args.open}（共 {len(results)} 项）")

    # ---------- 整合：直接提取本地网页正文 ----------
    if args.extract:
        return _es_extract(args, results, log)

    return 0


def _es_extract(args, results, log):
    """把 ES 搜索结果中的本地网页送给 webcopier 提取器。"""
    from .extractors import extract
    from .writer import save_output, url_to_filename
    from .everything import to_file_url, is_probably_webpage

    targets = [r for r in results
               if (args.extract_all or is_probably_webpage(r.path))
               and not r.is_dir]

    if not targets:
        log("[整合] 结果中没有可提取的网页文件（.html/.htm/.mht）。")
        log("       如需对所有文件尝试提取，加 --extract-all。")
        return 0

    if not args.extract_dir:
        log("[ERROR] --extract 需要配合 --extract-dir 指定正文输出目录")
        return 2

    os.makedirs(args.extract_dir, exist_ok=True)
    log(f"\n[整合] 对 {len(targets)} 个本地网页执行正文提取 -> "
        f"{os.path.abspath(args.extract_dir)}")

    ok = fail = 0
    for i, r in enumerate(targets, 1):
        url = to_file_url(r.path)
        try:
            text = extract(url, args.extract_method, {},
                           random_delay=False)
            if not text:
                raise ValueError("未提取到正文")
            # 必须传 file:// URL 而非 Windows 路径：url_to_filename 按 "/" 切分，
            # 传裸路径会得到一整串被清洗过的路径（此前产出 Dwebcopier.debug... 这类怪名）
            fname = url_to_filename(url, i)
            path = save_output(text, url, fname, args.extract_dir,
                               args.extract_format)
            ok += 1
            log(f"  [OK] ({i}/{len(targets)}) {len(text)} 字符 -> "
                f"{os.path.basename(path)}")
        except Exception as e:
            fail += 1
            log(f"  [FAIL] ({i}/{len(targets)}) {r.name[:40]}: {e}")

    log(f"\n[整合] 提取完成：{ok} 成功 / {fail} 失败 / {len(targets)} 总计")
    return 0 if fail == 0 else 1


# ============================================================
#  子命令：config
# ============================================================

def cmd_config(args, cfg, log):
    if args.reset:
        reset_config()
        log("[OK] 配置已重置为默认值")
        return 0

    if args.set:
        changed = []
        for item in args.set:
            if "=" not in item:
                log(f"[WARN] 忽略无效赋值（需 k=v 格式）: {item}")
                continue
            k, v = item.split("=", 1)
            k, v = k.strip(), v.strip()
            if k not in DEFAULT_CONFIG:
                log(f"[WARN] 未知配置项，仍写入: {k}")
            # 尝试做类型转换
            old = cfg.get(k)
            if isinstance(old, bool):
                cfg[k] = v.lower() in ("1", "true", "yes", "on")
            elif isinstance(old, int):
                try:
                    cfg[k] = int(v)
                except ValueError:
                    cfg[k] = v
            elif isinstance(old, float):
                try:
                    cfg[k] = float(v)
                except ValueError:
                    cfg[k] = v
            else:
                cfg[k] = v
            changed.append(k)
        if changed and save_config(cfg):
            log(f"[OK] 已更新配置项: {', '.join(changed)}")
        return 0

    # 默认：显示配置
    log(f"WebCopier v{VERSION} 当前配置：")
    width = max(len(k) for k in cfg)
    for k in sorted(cfg):
        log(f"  {k.ljust(width)} = {cfg[k]}")
    return 0


# ============================================================
#  参数解析器
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    cfg = load_config()

    parser = argparse.ArgumentParser(
        prog="webcopier",
        description=f"WebCopier v{VERSION} — 网页正文抓取工具（命令行版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  webcopier fetch https://example.com/a -m trafilatura -o out -f md\n"
            "  webcopier batch urls.txt --delay 2 --concurrency 4\n"
            "  webcopier crawl https://example.com --depth 2 --sitemap\n"
            "  webcopier forum 150 177 171 176 --preset trow -o output/trow\n"
        ))

    parser.add_argument("--version", action="version",
                        version=f"WebCopier v{VERSION}")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="静默模式（不输出日志）")

    sub = parser.add_subparsers(dest="command", metavar="<命令>")

    # ---------- fetch ----------
    p = sub.add_parser("fetch", help="抓取单个页面",
                       description="抓取单个 URL 的正文并保存")
    p.add_argument("url", help="目标网址")
    p.add_argument("-m", "--method", default=cfg.get("method", "trafilatura"),
                   choices=EXTRACT_METHODS, help="提取方式（默认 trafilatura）")
    p.add_argument("-f", "--format", default=cfg.get("output_format", "txt"),
                   choices=OUTPUT_FORMATS, help="输出格式（默认 txt）")
    p.add_argument("-o", "--out", default=cfg.get("save_dir", "output"),
                   help="保存目录")
    p.add_argument("--stdout", action="store_true", help="同时把正文打印到控制台")
    p.add_argument("-p", "--proxy", default="", help="代理，如 http://127.0.0.1:7890")
    p.add_argument("--retries", type=int, default=cfg.get("max_retries", 3),
                   help="最大重试次数")
    p.add_argument("--random-delay", action="store_true", help="请求前随机延迟")
    p.add_argument("--user-agent", default="", help="自定义 User-Agent")
    p.add_argument("--cookie", default="", help="Cookie 字符串")
    p.add_argument("--curl-cffi", action="store_true", help="启用 curl_cffi TLS 伪装")
    p.set_defaults(func=cmd_fetch)

    # ---------- batch ----------
    p = sub.add_parser("batch", help="批量抓取（URL 列表文件）",
                       description="从文件读取 URL 列表批量抓取，每行一个 URL，# 开头为注释")
    p.add_argument("file", help="URL 列表文件路径")
    p.add_argument("-m", "--method", default=cfg.get("method", "trafilatura"),
                   choices=EXTRACT_METHODS)
    p.add_argument("-f", "--format", default=cfg.get("output_format", "txt"),
                   choices=OUTPUT_FORMATS)
    p.add_argument("-o", "--out", default=cfg.get("save_dir", "output"))
    p.add_argument("--delay", type=float, default=cfg.get("delay", 2.0),
                   help="请求间隔（秒）")
    p.add_argument("--concurrency", type=int, default=cfg.get("concurrency", 4),
                   help="并发线程数")
    p.add_argument("--retries", type=int, default=cfg.get("max_retries", 3))
    p.add_argument("--images", action="store_true", help="同时下载页面图片")
    p.add_argument("--ignore-robots", action="store_true", help="忽略 robots.txt")
    p.add_argument("--random-delay", action="store_true")
    p.add_argument("-p", "--proxy", default="")
    p.add_argument("--user-agent", default="")
    p.add_argument("--cookie", default="")
    p.add_argument("--curl-cffi", action="store_true")
    p.set_defaults(func=cmd_batch)

    # ---------- crawl ----------
    p = sub.add_parser("crawl", help="整站爬取",
                       description="从入口 URL 出发 BFS 或 sitemap 发现链接并抓取")
    p.add_argument("url", help="入口网址")
    p.add_argument("--depth", type=int, default=cfg.get("max_depth", 1),
                   help="爬取深度（默认 1）")
    p.add_argument("--sitemap", action="store_true", help="优先使用 sitemap.xml 发现链接")
    p.add_argument("-m", "--method", default=cfg.get("method", "trafilatura"),
                   choices=EXTRACT_METHODS)
    p.add_argument("-f", "--format", default=cfg.get("output_format", "txt"),
                   choices=OUTPUT_FORMATS)
    p.add_argument("-o", "--out", default=cfg.get("save_dir", "output"))
    p.add_argument("--delay", type=float, default=cfg.get("delay", 2.0))
    p.add_argument("--retries", type=int, default=cfg.get("max_retries", 3))
    p.add_argument("--images", action="store_true")
    p.add_argument("--ignore-robots", action="store_true")
    p.add_argument("--random-delay", action="store_true")
    p.add_argument("-p", "--proxy", default="")
    p.add_argument("--user-agent", default="")
    p.add_argument("--cookie", default="")
    p.add_argument("--curl-cffi", action="store_true")
    p.set_defaults(func=cmd_crawl)

    # ---------- forum ----------
    p = sub.add_parser(
        "forum", help="论坛抓取（列表翻页 + 主题二级页翻页）",
        description="按版块 ID 抓取论坛：自动翻页收集主题，再进入每个主题抓取全部楼层")
    p.add_argument("forum_ids", nargs="+", help="版块 ID，如 150 177 171 176")
    p.add_argument("--preset", default="trow",
                   choices=["trow", "ipb2"],
                   help="站点模板（默认 trow）")
    p.add_argument("--board-base", default="",
                   help="论坛 board 根地址，覆盖 preset（如 https://trow.cc/board/）")
    p.add_argument("-f", "--format", default="md",
                   choices=["md", "txt", "json", "jsonl"],
                   help="输出格式（默认 md）")
    p.add_argument("-o", "--out", default=os.path.join(cfg.get("save_dir", "output"), "trow"),
                   help="输出目录")
    p.add_argument("--delay", type=float, default=2.0,
                   help="请求基准间隔（秒，默认 2.0）")
    p.add_argument("--workers", type=int, default=2,
                   help="并发线程数（默认 2）")
    p.add_argument("--retries", type=int, default=3, help="单页最大尝试次数")
    p.add_argument("--with-subforums", action="store_true",
                   help="递归抓取子版块")
    p.add_argument("--no-resume", action="store_true",
                   help="忽略断点，从头重抓")
    p.add_argument("--max-listing-pages", type=int, default=None,
                   help="每个版块最多抓几页列表（调试用）")
    p.add_argument("--max-topics", type=int, default=None,
                   help="最多抓几个主题（调试用）")
    p.add_argument("--max-post-pages", type=int, default=None,
                   help="每个主题最多抓几页回帖（调试用）")
    p.add_argument("-p", "--proxy", default="")
    p.add_argument("--user-agent", default="")
    p.add_argument("--curl-cffi", action="store_true")
    p.set_defaults(func=cmd_forum)

    # ---------- es ----------
    p = sub.add_parser(
        "es", help="Everything 本地文件搜索（内置 ES）",
        description=(
            "调用内置的 ES（Everything 命令行接口）搜索本机文件。\n"
            "Everything 必须处于运行状态——ES 通过命名管道与其通信。\n"
            "搜索语法即 Everything 语法，例：\"foo ext:md\" \"bar path:C:\\\\work\""))
    p.add_argument("query", nargs="?", help="搜索词（Everything 语法）")
    p.add_argument("-n", "--count", type=int, default=20,
                   help="结果条数上限（默认 20）")
    p.add_argument("-f", "--format", default="table",
                   choices=["table", "json", "csv", "paths"],
                   help="输出格式（默认 table）")
    p.add_argument("--columns", default="",
                   help="附加显示列，逗号分隔（size / dm / dc / da / ext / attribs ...）")
    p.add_argument("--size", action="store_true", help="表格中显示文件大小")
    p.add_argument("--sort", default="",
                   help="排序，如 name / size / date-modified（加 -descending 降序）")
    p.add_argument("--path", default="", help="限定搜索目录（ES -path）")
    p.add_argument("-i", "--case", action="store_true", help="区分大小写")
    p.add_argument("-p", "--match-path", action="store_true",
                   help="匹配完整路径而非仅文件名")
    p.add_argument("-r", "--regex", action="store_true", help="正则表达式搜索")
    p.add_argument("--files-only", action="store_true", help="仅文件")
    p.add_argument("--folders-only", action="store_true", help="仅目录")
    p.add_argument("-o", "--out", default="", help="把结果路径写入文件（每行一条）")
    p.add_argument("--open", type=int, default=0, metavar="N",
                   help="在资源管理器中定位第 N 条结果")
    p.add_argument("--extract", action="store_true",
                   help="[整合] 对结果中的本地网页直接提取正文")
    p.add_argument("--extract-all", action="store_true",
                   help="配合 --extract：不限扩展名，对所有结果尝试提取")
    p.add_argument("--extract-dir", default="", help="配合 --extract：正文输出目录")
    p.add_argument("--extract-method", default=cfg.get("method", "trafilatura"),
                   choices=EXTRACT_METHODS, help="配合 --extract：提取方式")
    p.add_argument("--extract-format", default="txt",
                   choices=OUTPUT_FORMATS, help="配合 --extract：输出格式")
    p.add_argument("--es-path", default="", help="指定 es.exe 路径（默认用项目 bin\\es.exe）")
    p.add_argument("--instance", default="",
                   help="Everything 实例名（留空使用默认实例）")
    p.add_argument("--timeout", type=int, default=30, help="调用超时秒数")
    p.add_argument("--status", action="store_true",
                   help="只显示 Everything 连通性诊断")
    p.add_argument("--no-result-error", action="store_true",
                   help="无结果时返回非零退出码（便于脚本判断）")
    p.add_argument("--es-args", nargs=argparse.REMAINDER, default=[],
                   help="其余参数原样透传给 es.exe，如 --es-args -whole-word")
    p.set_defaults(func=cmd_es)

    # ---------- config ----------
    p = sub.add_parser("config", help="查看/修改配置")
    p.add_argument("--show", action="store_true", help="显示当前配置（默认行为）")
    p.add_argument("--set", nargs="+", metavar="K=V", help="设置配置项，可多个")
    p.add_argument("--reset", action="store_true", help="恢复默认配置")
    p.set_defaults(func=cmd_config)

    return parser


# ============================================================
#  入口
# ============================================================

def main(argv=None) -> int:
    """CLI 入口，返回退出码"""
    # Windows 控制台编码自适应（GBK 终端 / UTF-8 重定向）
    configure_console()

    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    log = make_logger(quiet=getattr(args, "quiet", False))
    cfg = load_config()

    try:
        return args.func(args, cfg, log) or 0
    except KeyboardInterrupt:
        log("\n[中断] 用户按下 Ctrl+C")
        return 130
    except Exception as e:
        log(f"[ERROR] {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
