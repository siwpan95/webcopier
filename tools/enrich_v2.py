#!/usr/bin/env python3
"""identities.json enrichment from fake-useragent desktop pool."""
import json, re, os
from collections import defaultdict

# 原 D:\allin 外部数据源已失效；通过环境变量 FAU_JSONL 指定 browsers.jsonl 路径
FAU_JSONL = os.environ.get("FAU_JSONL", "")
# identities.json：环境变量 WEBCOPIER_IDENTITIES 覆盖，否则取仓内 webcopier/identities.json
# （去本地化，原桌面绝对路径已失效；tools/ 与 webcopier/ 同级，由 __file__ 推导）
OUTPUT = os.environ.get("WEBCOPIER_IDENTITIES") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webcopier", "identities.json"
)
_OUT_DIR = os.path.dirname(OUTPUT)
if _OUT_DIR:
    os.makedirs(_OUT_DIR, exist_ok=True)

BROWSER_TO_ENGINE = {
    "Chrome": "chrome", "Firefox": "firefox", "Safari": "safari",
    "Edge": "edge", "Opera": "opera",
}

CURL_MAP = {
    "chrome":  [(120,"chrome120"),(116,"chrome116"),(110,"chrome110"),(104,"chrome104"),(100,"chrome100"),(99,"chrome99")],
    "edge":    [(0,"edge101")],
    "firefox": [(0,"firefox116")],
    "safari":  [(17,"safari17_0"),(15,"safari15_5"),(0,"safari15_5")],
    "opera":   [(0,"chrome120")],
}

OS_MAP = {
    "Windows":   ("Windows NT 10.0; Win64; x64", "Windows"),
    "Mac OS X":  ("Macintosh; Intel Mac OS X 10_15_7", "macOS"),
    "Linux":     ("X11; Linux x86_64", "Linux"),
    "Chrome OS": ("X11; CrOS x86_64", "ChromeOS"),
}

BRAND = {"chrome": "Google Chrome", "edge": "Microsoft Edge", "opera": "Opera"}

def major_ver(v):
    m = re.match(r"(\d+)", v)
    return int(m.group(1)) if m else 0

def curl_imp(engine, maj):
    for min_v, imp in sorted(CURL_MAP.get(engine, []), key=lambda x: -x[0]):
        if maj >= min_v:
            return imp
    return "chrome120"

def sec_ch_ua(engine, maj):
    if engine not in BRAND:
        return {}
    brand = BRAND[engine]
    greasy = "Not?A_Brand" if maj >= 104 else " Not A;Brand"
    return {
        "sec-ch-ua": f'"{greasy}";v="99", "Chromium";v="{maj}", "{brand}";v="{maj}"',
        "sec-ch-ua-mobile": "?0",
    }

def main():
    if not os.path.isfile(FAU_JSONL):
        print("错误: 找不到 fake-useragent 数据源 browsers.jsonl")
        print("原 D:\\allin 路径已失效，请设置环境变量 FAU_JSONL 后重试")
        return
    # Load
    records = []
    for line in open(FAU_JSONL, encoding="utf-8"):
        rec = json.loads(line)
        if rec.get("type") == "desktop" and rec.get("browser") in BROWSER_TO_ENGINE:
            records.append(rec)
    print(f"Loaded {len(records)} desktop records", flush=True)

    # Generate
    identities = []
    seen = set()
    for rec in records:
        browser = rec["browser"]
        engine = BROWSER_TO_ENGINE[browser]
        fau_os = rec.get("os", "Windows")
        vs = rec.get("browser_version", "0.0")
        maj = major_ver(vs)
        os_str, platform = OS_MAP.get(fau_os, OS_MAP["Windows"])
        headers = sec_ch_ua(engine, maj)
        if platform:
            headers["sec-ch-ua-platform"] = f'"{platform}"'
        os_short = {"Windows":"win","Mac OS X":"mac","Linux":"linux","Chrome OS":"cros"}.get(fau_os, "unknown")
        base = f"{engine}-{os_short}-{maj}"
        uid = base
        c = 1
        while uid in seen:
            parts = vs.split(".")
            suffix = ".".join(parts[1:3]) if len(parts) >= 3 else f"v{c}"
            uid = f"{base}-{suffix}"
            c += 1
        seen.add(uid)
        identities.append({
            "id": uid, "engine": engine, "platform": "desktop",
            "os": os_str, "ua": rec["useragent"],
            "curl_impersonate": curl_imp(engine, maj), "headers": headers,
        })

    print(f"Generated {len(identities)} identities", flush=True)

    # Stats
    by_eng = defaultdict(int)
    for i in identities:
        by_eng[i["engine"]] += 1
    for eng, cnt in sorted(by_eng.items(), key=lambda x: -x[1]):
        print(f"  {eng}: {cnt}", flush=True)

    # Backup
    backup = OUTPUT.replace(".json", ".v5.2.backup.json")
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8") as s:
            with open(backup, "w", encoding="utf-8") as d:
                d.write(s.read())
        print(f"Backup: {backup}", flush=True)

    # Write
    out = {
        "version": "2.0",
        "description": f"WebCopier 5.3 — {len(identities)} desktop identities from fake-useragent/Intoli + dynamic sec-ch-ua + curl_cffi fingerprints",
        "source": "fake-useragent v2.2.0 / Intoli user-agents",
        "identities": identities,
    }
    json.dump(out, open(OUTPUT, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
    print(f"Written: {OUTPUT}", flush=True)

if __name__ == "__main__":
    main()
