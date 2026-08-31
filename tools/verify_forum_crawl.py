#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
论坛抓取产物完整性校验

用法:
    python tools/verify_forum_crawl.py [输出目录]

默认输出目录: output/trow

校验项:
  1. checkpoint 中版块列表主题数 vs 已完成主题数
  2. index.csv / index.json / corpus.jsonl 记录数一致
  3. 每条记录对应的文件真实存在且非空
  4. 内容非空（图片帖/密码帖等「合法空主题」逐条判定，避免误判为失败）
  5. 失败清单（failed.json）为空
  6. 抽查若干文件的正文结构（标题行 + 楼层标题）
"""

import os
import sys
import json
import csv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAVE_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join("output", "trow")

ok_count = 0
fail_count = 0
warn_count = 0


def check(cond, msg):
    global ok_count, fail_count
    if cond:
        ok_count += 1
        print(f"  [PASS] {msg}")
    else:
        fail_count += 1
        print(f"  [FAIL] {msg}")
    return cond


def main():
    global ok_count, fail_count, warn_count
    print(f"校验目录: {os.path.abspath(SAVE_DIR)}\n")

    if not os.path.isdir(SAVE_DIR):
        print(f"[FAIL] 输出目录不存在: {SAVE_DIR}")
        return 1

    # --- 1. checkpoint ---
    ckpt_path = os.path.join(SAVE_DIR, "checkpoint.json")
    if not check(os.path.exists(ckpt_path), "checkpoint.json 存在"):
        return 1
    with open(ckpt_path, encoding="utf-8") as f:
        ckpt = json.load(f)

    listing = ckpt.get("listing", {})
    done = ckpt.get("done", {})
    failed = ckpt.get("failed", {})

    listed_total = sum(len(v) for v in listing.values())
    print(f"  版块数: {len(listing)}  列表主题数: {listed_total}  "
          f"已完成: {len(done)}  失败: {len(failed)}")
    for fid in sorted(listing, key=lambda x: int(x) if x.isdigit() else 0):
        n_list = len(listing[fid])
        n_done = sum(1 for r in done.values() if str(r.get("forum_id")) == fid)
        print(f"    版块 {fid}: 列表 {n_list} 条，已完成 {n_done} 条")
        check(n_done == n_list, f"版块 {fid} 完成数 == 列表数 ({n_done}/{n_list})")

    check(len(failed) == 0, f"失败清单为空 (当前 {len(failed)} 条)")

    # --- 2. 索引一致性 ---
    idx_json = os.path.join(SAVE_DIR, "index.json")
    idx_csv = os.path.join(SAVE_DIR, "index.csv")
    corpus = os.path.join(SAVE_DIR, "corpus.jsonl")
    for p in (idx_json, idx_csv, corpus):
        check(os.path.exists(p), f"{os.path.basename(p)} 存在")

    with open(idx_json, encoding="utf-8") as f:
        index = json.load(f)
    records = index.get("topics", [])

    with open(idx_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    with open(corpus, encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]

    check(len(records) == len(done), f"index.json 记录数 == checkpoint 完成数 ({len(records)}/{len(done)})")
    check(len(rows) == len(records), f"index.csv 行数 == index.json 记录数 ({len(rows)}/{len(records)})")
    check(len(lines) == len(records), f"corpus.jsonl 行数 == index.json 记录数 ({len(lines)}/{len(records)})")

    # --- 3. 文件存在且非空 ---
    missing, empty = [], []
    for r in records:
        fp = os.path.join(SAVE_DIR, r["file"].replace("/", os.sep))
        if not os.path.exists(fp):
            missing.append(r["file"])
        elif os.path.getsize(fp) == 0:
            empty.append(r["file"])
    check(not missing, f"所有记录的文件均存在 (缺失 {len(missing)} 个)")
    if missing:
        for m in missing[:10]:
            print(f"        缺失: {m}")
    check(not empty, f"所有文件非空 (空文件 {len(empty)} 个)")

    # --- 4. 内容质量（区分「合法空主题」与「解析遗漏」）---
    # 图片帖（仅含附件/图片，0 文本）、密码保护主题（游客不可见）、
    # 列表本身 0 回复的主题，其 posts/chars 为 0 属预期，不应判失败；
    # 但若列表显示有回复却解析到 0 帖，则疑似解析遗漏，需人工复核。
    zero_recs = [r for r in records
                 if int(r.get("posts", 0)) <= 0 or int(r.get("chars", 0)) <= 0]
    seen = set()
    for r in zero_recs:
        key = r.get("tid") or r.get("file")
        if key in seen:
            continue
        seen.add(key)
        fp = os.path.join(SAVE_DIR, r["file"].replace("/", os.sep))
        try:
            txt = open(fp, encoding="utf-8").read()
        except OSError:
            fail_count += 1
            print(f"  [FAIL] 主题 {r.get('tid')} 文件无法读取: {r.get('file')}")
            continue
        if not txt.startswith("# "):
            fail_count += 1
            print(f"  [FAIL] 主题 {r.get('tid')} 文件结构损坏（缺少标题行）")
            continue
        replies = int(r.get("replies", r.get("reply_count", 0)) or 0)
        label = f"{r.get('tid')} ({r.get('file')})"
        if int(r.get("posts", 0)) <= 0 and replies > 0:
            low = txt.lower()
            if "密码" in txt or "password" in low or "protected" in low:
                print(f"  [INFO] 合法空主题 {label}: 密码保护（游客不可见，0 帖为预期）")
            else:
                warn_count += 1
                print(f"  [WARN] 主题 {label}: 列表回复数={replies} 但解析到 0 帖，疑似解析遗漏，需人工复核")
        else:
            print(f"  [INFO] 合法空主题 {label}: 图片帖/空主题（0 字为预期）")

    check(fail_count == 0, f"所有主题内容有效（空主题已逐条判定，失败 {fail_count} 个，告警 {warn_count} 个）")

    total_posts = sum(int(r.get("posts", 0)) for r in records)
    total_chars = sum(int(r.get("chars", 0)) for r in records)
    print(f"\n  累计楼层: {total_posts}   累计字数: {total_chars}")

    # --- 5. 抽查文件结构 ---
    print("\n  抽查文件结构:")
    sample = records[:3] + records[len(records) // 2:len(records) // 2 + 2]
    for r in sample:
        fp = os.path.join(SAVE_DIR, r["file"].replace("/", os.sep))
        if not os.path.exists(fp):
            continue
        with open(fp, encoding="utf-8") as f:
            head = f.read(400)
        has_title = head.startswith("# ")
        has_floor = "## #" in head
        print(f"    {os.path.basename(fp)[:50]:52s} 标题={has_title} 楼层={has_floor}")
        check(has_title and has_floor, f"  结构正确: {os.path.basename(fp)[:40]}")

    # --- 汇总 ---
    print("\n" + "=" * 56)
    print(f"  校验结果: {ok_count} 项通过, {fail_count} 项失败, {warn_count} 项告警")
    print("=" * 56)
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
