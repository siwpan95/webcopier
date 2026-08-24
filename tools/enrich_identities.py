#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
identities.json 混合增强脚本 v5.3

从 fake-useragent 的 browsers.jsonl 提取桌面 UA，
按浏览器引擎 + OS 匹配，为 identities.json 生成完整的身份条目。
保留 sec-ch-ua 模板、curl_impersonate 映射、平台头等反检测字段。
"""

import json
import os
import re
import sys
from collections import defaultdict

# ============================================================
#  配置
# ============================================================
# 原 D:\allin 外部数据源已失效；通过环境变量 FAU_JSONL 指定 browsers.jsonl 路径
FAU_JSONL = os.environ.get("FAU_JSONL", "")
CURRENT_IDENTITIES = r"C:\Users\13122\Desktop\txt\webcopier\identities.json"
OUTPUT = r"C:\Users\13122\Desktop\txt\webcopier\identities.json"

# 浏览器名 -> engine 内部名映射
BROWSER_TO_ENGINE = {
    "Chrome": "chrome",
    "Firefox": "firefox",
    "Safari": "safari",
    "Edge": "edge",
    "Opera": "opera",
}

# engine -> curl_impersonate 映射（按版本范围）
# 格式: [(min_version, impersonate), ...]
CURL_IMPERSONATE_MAP = {
    "chrome": [
        (120, "chrome120"),
        (116, "chrome116"),
        (110, "chrome110"),
        (104, "chrome104"),
        (100, "chrome100"),
        (99,  "chrome99"),
    ],
    "edge":  [(0, "edge101")],
    "firefox": [(0, "firefox116")],
    "safari": [
        (17, "safari17_0"),
        (15, "safari15_5"),
        (0,  "safari15_5"),
    ],
    "opera": [(0, "chrome120")],
}

# OS 标准化映射
OS_NORMALIZE = {
    "Windows":    ("Windows NT 10.0; Win64; x64", "Windows"),
    "Mac OS X":   ("Macintosh; Intel Mac OS X 10_15_7", "macOS"),
    "Linux":      ("X11; Linux x86_64", "Linux"),
    "Chrome OS":  ("X11; CrOS x86_64", "ChromeOS"),
}

# Chromium 系浏览器的 sec-ch-ua brand 名称
CHROMIUM_BRAND = {
    "chrome":  "Google Chrome",
    "edge":    "Microsoft Edge",
    "opera":   "Opera",
}


# ============================================================
#  辅助函数
# ============================================================
def extract_major(version_str: str) -> int:
    """从版本字符串提取主版本号。"""
    m = re.match(r"(\d+)", version_str)
    return int(m.group(1)) if m else 0


def get_curl_impersonate(engine: str, major: int) -> str:
    """根据引擎和主版本号返回 curl_impersonate 别名。"""
    rules = CURL_IMPERSONATE_MAP.get(engine, [])
    for min_v, imp in sorted(rules, key=lambda x: -x[0]):
        if major >= min_v:
            return imp
    return "chrome120"


def build_sec_ch_ua(engine: str, major: int) -> dict:
    """为 Chromium 系浏览器构建 sec-ch-ua 系列头。Firefox/Safari 返回空。"""
    if engine not in CHROMIUM_BRAND:
        return {}
    brand = CHROMIUM_BRAND[engine]
    # Chrome 104+ 使用新格式，旧版使用 " Not A;Brand" 格式
    if major >= 104:
        greasy = "Not?A_Brand"
    else:
        greasy = " Not A;Brand"
    return {
        "sec-ch-ua": f'"{greasy}";v="99", "Chromium";v="{major}", "{brand}";v="{major}"',
        "sec-ch-ua-mobile": "?0",
    }


def build_identity_id(engine: str, fau_os: str, major: int, sub: str = "") -> str:
    """生成 identity id，如 chrome-win-137 或 safari-mac-18_5。"""
    os_short = {"Windows": "win", "Mac OS X": "mac", "Linux": "linux",
                "Chrome OS": "cros"}.get(fau_os, "unknown")
    if sub:
        return f"{engine}-{os_short}-{major}.{sub}"
    return f"{engine}-{os_short}-{major}"


# ============================================================
#  加载 fake-useragent 桌面 UAs
# ============================================================
def load_fau_desktop(jsonl_path: str) -> list[dict]:
    """加载并过滤 fake-useragent 桌面端 UA 记录。"""
    records = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("type") != "desktop":
                continue
            browser = rec.get("browser")
            if browser not in BROWSER_TO_ENGINE:
                continue
            records.append(rec)
    print(f"[FAU] 加载 {len(records)} 条桌面 UA 记录")
    return records


# ============================================================
#  生成 enriched identities
# ============================================================
def generate_enriched(fau_records: list[dict]) -> list[dict]:
    """将 fake-useragent 记录转为 identity 格式。"""
    identities = []
    seen_ids = set()

    for rec in fau_records:
        browser = rec["browser"]
        engine = BROWSER_TO_ENGINE[browser]
        fau_os = rec.get("os", "Windows")
        version_str = rec.get("browser_version", "0.0")
        major = extract_major(version_str)

        # OS 标准化
        os_str, sec_ch_platform = OS_NORMALIZE.get(fau_os, OS_NORMALIZE["Windows"])

        # sec-ch-ua headers
        headers = build_sec_ch_ua(engine, major)
        if sec_ch_platform:
            headers["sec-ch-ua-platform"] = f'"{sec_ch_platform}"'

        # curl_impersonate
        curl_imp = get_curl_impersonate(engine, major)

        # identity id (处理重复)
        base_id = build_identity_id(engine, fau_os, major)
        unique_id = base_id
        counter = 1
        while unique_id in seen_ids:
            # 尝试用版本后缀区分
            sub_parts = version_str.split(".")
            suffix = ".".join(sub_parts[1:3]) if len(sub_parts) >= 3 else f"v{counter}"
            unique_id = f"{base_id}-{suffix}"
            counter += 1
        seen_ids.add(unique_id)

        identity = {
            "id": unique_id,
            "engine": engine,
            "platform": "desktop",
            "os": os_str,
            "ua": rec["useragent"],
            "curl_impersonate": curl_imp,
            "headers": headers,
        }
        identities.append(identity)

    return identities


# ============================================================
#  统计报告
# ============================================================
def report(identities: list[dict]):
    """输出增强后的统计信息。"""
    by_engine = defaultdict(int)
    by_os = defaultdict(int)
    for i in identities:
        by_engine[i["engine"]] += 1
        # 从 os 字段提取简名
        os_field = i["os"]
        if "Windows" in os_field:
            by_os["Windows"] += 1
        elif "Macintosh" in os_field:
            by_os["macOS"] += 1
        elif "Linux" in os_field or "CrOS" in os_field:
            by_os["Linux/ChromeOS"] += 1

    print(f"\n[生成] {len(identities)} 个增强身份（原 56 -> {len(identities)}）")
    print(f"\n  按引擎:")
    for eng, cnt in sorted(by_engine.items(), key=lambda x: -x[1]):
        print(f"    {eng}: {cnt}")
    print(f"\n  按 OS:")
    for osn, cnt in sorted(by_os.items(), key=lambda x: -x[1]):
        print(f"    {osn}: {cnt}")

    # 版本范围
    versions_by_engine = defaultdict(list)
    for i in identities:
        m = re.search(r"(\d+)(?:\.\d+)?$", i["id"])
        if m:
            versions_by_engine[i["engine"]].append(int(m.group(1)))
    print(f"\n  版本范围:")
    for eng in sorted(versions_by_engine):
        vs = sorted(versions_by_engine[eng])
        print(f"    {eng}: v{min(vs)} ~ v{max(vs)} ({len(vs)} 个主版本)")


# ============================================================
#  主流程
# ============================================================
def main():
    print("=" * 60)
    print("identities.json 混合增强 v5.3")
    print("  数据源: fake-useragent v2.2.0 (Intoli user-agents)")
    print("=" * 60)

    if not os.path.isfile(FAU_JSONL):
        print("错误: 找不到 fake-useragent 数据源 browsers.jsonl")
        print("原 D:\\allin 路径已失效，请设置环境变量 FAU_JSONL 后重试")
        return
    # 1) 加载 fake-useragent 桌面 UA
    fau_records = load_fau_desktop(FAU_JSONL)

    # 2) 生成 enriched identities
    identities = generate_enriched(fau_records)

    # 3) 报告
    report(identities)

    # 4) 备份旧文件
    if os.path.exists(CURRENT_IDENTITIES):
        backup = CURRENT_IDENTITIES.replace(".json", f".v5.2.backup.json")
        with open(CURRENT_IDENTITIES, "r", encoding="utf-8") as src:
            with open(backup, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        print(f"\n[备份] {backup}")

    # 5) 写入
    output = {
        "version": "2.0",
        "description": (
            "WebCopier 浏览器身份池 v5.3 — "
            "基于 fake-useragent (Intoli) 的 {} 条桌面 UA + "
            "动态 sec-ch-ua 头 + curl_cffi 指纹映射。"
            "身份数 = 最大重试次数。"
        ).format(len(identities)),
        "source": "fake-useragent v2.2.0 / Intoli user-agents",
        "identities": identities,
    }

    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[写入] {OUTPUT}")
    print("[完成]")

    # 额外: 写一份 Chrome-only 子集给用户参考
    chrome_only = [i for i in identities if i["engine"] == "chrome"]
    chrome_path = OUTPUT.replace(".json", ".chrome_only.json")
    chrome_output = {
        "version": "2.0-chrome",
        "description": "Chrome 桌面 UA 子集（用于测试对比）",
        "identities": chrome_only,
    }
    with open(chrome_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(chrome_output, f, ensure_ascii=False, indent=2)
    print(f"[子集] Chrome-only {len(chrome_only)} 条 -> {chrome_path}")


if __name__ == "__main__":
    main()
