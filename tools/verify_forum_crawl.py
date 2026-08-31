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
  4. 楼层数 > 0、字数 > 0
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

    # --- 4. 内容质量 ---
    zero_post = [r for r in records if int(r.get("posts", 0)) <= 0]
    zero_char = [r for r in records if int(r.get("chars", 0)) <= 0]
    check(not zero_post, f"所有主题楼层数 > 0 (异常 {len(zero_post)} 个)")
    check(not zero_char, f"所有主题字数 > 0 (异常 {len(zero_char)} 个)")

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
    print(f"  校验结果: {ok_count} 项通过, {fail_count} 项失败")
    print("=" * 56)
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
