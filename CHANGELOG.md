# Changelog

本项目所有值得注意的变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [5.5.0] - 2026-08-31

### Added

- **命令行接口 v5.5**：新增 `webcopier/cli.py` 与 `webcopier.bat` 启动器，子命令 `fetch` / `batch` / `crawl` / `forum` / `config`。
- **论坛抓取模块**：`webcopier/forum.py`，版块列表翻页 → 主题二级页翻页 → 逐帖（作者/时间/正文）提取，支持断点续传与索引导出（index.json/csv + corpus.jsonl）。
- **Everything / ES 整合**：收录官方 `bin/es.exe`（voidtools，MIT 许可）并提供 `webcopier/everything.py` Python 包装层，`es` 子命令支持搜索/排序/结构化输出（-json/-csv/-tsv）与诊断（`--status`）。
  - 额外打通 `file://` 本地文件读取管线（`http_client.file_get` + `FileResponse`），使 `webcopier es --extract` 能把 Everything 搜到的本地网页直接送入 6 种正文提取器 —— 这是与 WebCopier 既有 CLI 的**真整合**，而非两个并排命令。
- **完整性校验工具**：`tools/verify_forum_crawl.py`，21 项断言校验抓取产物一致性。

### Fixed

- 修复 `http_client` Brotli 解码缺失导致正文乱码（自动剔除不支持的 `br` 编码，缺库时明确报错）。
- 修复 `engine.batch_fetch` 中 `total` 未定义、`text` 未绑定的 NameError。
- 修复 `engine.init_robots` 基准 URL 缺失导致 robots.txt 检查被静默跳过（现以首个 URL 为基准）。
- 修复 `forum.save_topic` 扩展名判断错误：json/jsonl 内容被写成 `.txt` 文件名（改用 `_TOPIC_EXTS` 白名单）。
- 控制台编码自适应：TTY 跟随代码页（GBK），重定向用 UTF-8。

## [1.0.0] - 2026-08-27

### Added

- 首个发行版：Windows 单文件可执行程序（PyInstaller，Python 3.14）。
- 发布面：gitee [siwpan/webcopier](https://gitee.com/siwpan/webcopier) release `v1.0.0`（网页正文抓取工具 v1.0.0）。