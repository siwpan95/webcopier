---
name: webcopier
description: Maintain WebCopier v5.5 (D:/webcopier). Web content extraction with anti-bot system and forum crawling.
agent_created: true
---

# WebCopier 维护

## 概述
网页正文抓取 v5.5：单页/批量/整站/论坛四模式；六种提取方式（trafilatura/lxml/BS4/readability/newspaper3k/Playwright）；反爬系统（身份池轮换、curl_cffi TLS、验证码识别、stealth.js、退避重试）。

## 入口
- `webcopier.bat`：命令提示符启动器（优先 .venv，回退系统 python）
- `python -m webcopier`：无参数启动 GUI，带参数进 CLI
- `WebCopier_GUI.py`：纯 GUI 入口
- CLI 子命令：`fetch` / `batch` / `crawl` / `forum` / `config`

## 结构（v5.5）
- `webcopier/cli.py`：argparse 命令行接口
- `webcopier/forum.py`：论坛抓取（列表翻页 → 主题二级页翻页 → 逐帖提取）
- `webcopier/http_client.py`：`strip_unsupported_encodings()` 剔除无法解码的压缩算法
- `config.json`：配置项

## 已知陷阱（重要）
- **Brotli 乱码**：`Accept-Encoding` 含 `br` 而本机无 brotli 时，requests 返回乱码正文，解析全部为空却不报错。
  v5.5 已在 `http_client` 自动剔除 `br`；建议 `pip install brotli` 并已写入 requirements.txt。
- **IPB 论坛列表页**：主题行与子版块行同构，必须排除含 `view=` 的 `showtopic` 链接，
  否则子版块的「最后回复」会被误判成主题。列表页还含侧栏「最近帖」，空页时会残留 3 条噪声。
- **`prune_day`**：trow.cc 除 `prune_day=100` 外其他值均返回空列表（100 即全量，非「近 100 天」）。
- **robots.txt 静默失效**：`engine.init_robots` 若拿不到基准 URL，`urljoin("", "/robots.txt")` 产出无协议地址 →
  RobotFileParser 抛 `unknown url type` → 被 except 吞掉并「默认允许抓取」。v5.5 已改为以首个 URL 为基准 + 空基准显式告警。
- **扩展名判断别复用渲染器表**：`forum.save_topic` 曾用 `fmt in _TOPIC_RENDERERS` 定扩展名，
  而渲染器表只含 md/txt，导致 json/jsonl 内容被写成 `.txt` 文件名。已改用 `_TOPIC_EXTS` 白名单。
  教训：**「支持哪些格式」和「有哪些渲染器」是两件事，不要共用一个集合**。
- **长任务别放前台**：单次 CLI 抓取超过 ~100 秒会被 Bash 工具超时 SIGTERM（残留半成品文件，
  曾导致 crawl 产物数对不上——按 session id 分组可辨）。用 `run_in_background` + 日志。
- **Windows .bat**：必须纯 ASCII + UTF-8 无 BOM + CRLF，否则 cmd 按 GBK 解读会乱码/截断。
- **控制台编码**：CLI 中 TTY 跟随代码页（GBK）、重定向用 UTF-8；`_safe_print` 兜底防 UnicodeEncodeError 中断抓取。
- 依赖重（Playwright/ddddocr），改动先 py_compile + 冒烟。
- 2026-08-23 从 notpython 误判区移回 tools\crawler（历史背景）。

## 论坛抓取要点（trow.cc / IPB 2.x）
- 版块列表：`showforum={fid}&is_digest=&prune_day=100&sort_by=Z-A&sort_key=last_post&topicfilter=all&st={0,30,60...}`，每页 30 条
- 主题详情：`showtopic={tid}&st={0,15,30...}`，每页 15 帖
- 帖子容器：`<td id="post-main-{pid}">`，正文在 `div.postcolor3 > div#post-{pid}`
- 作者/时间：同一 `<table>` 首行（`YYYY-MM-DD, HH:MM` + `Post #N`）
- 版块层级：137 幽暗之镜 → 150 异夜咏谣 → {177 蠕动意面, 171 马格努斯档案馆, 176 欢迎来到夜谷}；150 自身也有直接主题
- robots.txt：`Allow: /`，无 Crawl-delay；`Content-Signal: ai-train=no, use=reference`

## 谱系（crawler-kit，2026-08-27）
- identity_manager（身份池）已提炼为 crawl-hub/crawler_kit/identity.py（共享库规范）；本仓保留内联副本（复制优于共享），两侧改动需手工对照。
- B 模式插件：manifest.json 已接入 crawl-hub（plugin:true），harness plugin-audit 黄金值校验。
