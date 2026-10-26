#!/usr/bin/env python3
"""无头自检：五种输出格式写入读回、页面链接提取/过滤、配置持久化与导出导入。

只 import writer / link_finder / config 等纯逻辑模块，不启动 Tkinter、不联网。
运行：python selfcheck.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def fail(msg):
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        import webcopier
        from webcopier import config, link_finder, writer
    except Exception as exc:  # pragma: no cover
        fail(f"导入项目模块失败: {exc}")

    text = "第一段正文。\n\n第二段正文。"
    url = "https://example.com/article/42"

    # ---------- 1. 五种输出格式：写入 → 读回校验 ----------
    with tempfile.TemporaryDirectory() as tmp:
        for fmt in ("txt", "md", "json", "jsonl", "html"):
            path = Path(writer.save_output(text, url, "page", tmp, fmt))
            if not path.is_file() or path.stat().st_size == 0:
                fail(f"{fmt} 输出未生成")
            if path.suffix != writer._FORMAT_EXT[fmt]:
                fail(f"{fmt} 扩展名不符: {path.suffix}")
            raw = path.read_text(encoding="utf-8")
            if fmt == "txt":
                if url not in raw or text not in raw or f"v{webcopier.__version__}" not in raw:
                    fail("txt 输出缺少 URL/正文/版本头")
            elif fmt == "md":
                if not raw.startswith(f"# 来源: {url}") or text not in raw:
                    fail("md 输出结构错误")
            elif fmt == "json":
                data = json.loads(raw)
                if data["网址"] != url or data["内容"] != text or data["字符数"] != len(text):
                    fail("json 输出字段/字符数错误")
            elif fmt == "jsonl":
                lines = raw.strip().splitlines()
                if len(lines) != 1:
                    fail("jsonl 输出应为单行 JSON")
                data = json.loads(lines[0])
                if data["url"] != url or data["content"] != text:
                    fail("jsonl 输出字段错误")
            elif fmt == "html":
                if not raw.startswith("<!DOCTYPE html>") or url not in raw or "第二段正文" not in raw:
                    fail("html 输出结构错误")
        unknown = Path(writer.save_output(text, url, "page", tmp, "unknown-format"))
        if unknown.suffix != ".txt":
            fail("未知格式未回退为 .txt")

    # ---------- 2. 链接提取：同域、去重、过滤资源文件 ----------
    html = (
        '<html><body>'
        '<a href="/post/1">相对链接</a>'
        '<a href="/post/1#section">同页锚点重复</a>'
        '<a href="https://example.com/2024/03/hello-world">年份路径</a>'
        '<a href="https://example.com/banner.jpg">图片资源</a>'
        '<a href="https://other.example.net/post/2">外站链接</a>'
        '</body></html>'
    )
    links = link_finder.extract_page_links(html, "https://example.com/")
    if links != [
        "https://example.com/post/1",
        "https://example.com/2024/03/hello-world",
    ]:
        fail(f"链接提取结果错误: {links}")
    content_cases = [
        ("https://x.com/a.css", False),
        ("https://x.com/post/1", True),
        ("https://x.com/2024/06/01/slug", True),
        ("https://x.com/", True),
        ("https://x.com/data.json", False),
    ]
    for sample, expected in content_cases:
        if link_finder._is_content_url(sample) != expected:
            fail(f"_is_content_url 判定错误: {sample}")

    # ---------- 3. 配置：默认合并、持久化、导出/导入 ----------
    original_config_file = config.CONFIG_FILE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config.CONFIG_FILE = Path(tmp) / "config.json"
            if not config.save_config({"delay": 1.5, "output_format": "md"}):
                fail("save_config 返回 False")
            loaded = config.load_config()
            if loaded["delay"] != 1.5 or loaded["output_format"] != "md":
                fail("配置持久化往返失败")
            if loaded["method"] != config.DEFAULT_CONFIG["method"]:
                fail("缺失配置项未回退默认值")

            export_path = Path(tmp) / "exported.json"
            if not config.export_config(loaded, str(export_path)):
                fail("export_config 返回 False")
            exported = json.loads(export_path.read_text(encoding="utf-8"))
            if exported.get("_version") != webcopier.__version__ or not exported.get("_exported"):
                fail("导出文件缺少版本/标记字段")
            imported = config.import_config(str(export_path))
            if "_version" in imported or "_exported" in imported:
                fail("导入配置未剔除导出标记字段")
            if imported["delay"] != 1.5:
                fail("导入配置内容丢失")

            if not config.reset_config() or config.CONFIG_FILE.exists():
                fail("reset_config 未删除配置文件")
            if config.load_config()["method"] != config.DEFAULT_CONFIG["method"]:
                fail("重置后未回退默认配置")
    finally:
        config.CONFIG_FILE = original_config_file

    print(
        "selfcheck ok: txt/md/json/jsonl/html 五种输出写入读回、"
        "同域链接提取与资源过滤去重、配置持久化及导出导入（剔除 _version/_exported）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
