---
name: webcopier
description: Maintain WebCopier v5.3 (本 SKILL.md 所在仓库根). Web content extraction with anti-bot system.
agent_created: true
---

# WebCopier 维护

## 概述
网页正文抓取 v5.3：单页/批量/整站三模式；六种提取方式（trafilatura/lxml/BS4/readability/newspaper3k/Playwright）；反爬系统（身份池轮换、curl_cffi TLS、验证码识别、stealth.js、退避重试）。

## 结构
- WebCopier_GUI.py：GUI 入口；python -m webcopier 模块入口
- config.json：12 项配置

## 已知陷阱
- 依赖重（Playwright/ddddocr），改动先 py_compile + 冒烟
- 2026-08-23 从 notpython 误判区移回 tools\crawler（历史背景）

## 谱系（crawler-kit，2026-08-27）
- identity_manager（身份池）已提炼为 crawl-hub/crawler_kit/identity.py（共享库规范）；本仓保留内联副本（复制优于共享），两侧改动需手工对照。
- B 模式插件：manifest.json 已接入 crawl-hub（plugin:true），harness plugin-audit 黄金值校验。
