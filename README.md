# WebCopier — 网页正文抓取工具 v5.5

全功能网页正文抓取程序，支持多种提取方式、论坛抓取和完善的反爬系统。

## 功能

- **四种模式** — 单页抓取 / 批量抓取 / 整站爬取 / **论坛抓取**
- **六种提取方式** — trafilatura / lxml+XPath / BeautifulSoup / readability / newspaper3k / Playwright
- **论坛抓取** — 版块列表翻页 → 主题二级页翻页 → 逐帖（作者/时间/正文）提取，支持断点续传与索引导出
- **反爬系统** — 浏览器身份池轮换、curl_cffi TLS 伪装、验证码识别 (ddddocr)、Session/Cookie 管理、stealth.js 注入、请求延迟 + 退避重试
- **批量处理** — 从文件读取 URL 列表，多线程并发抓取
- **GUI 界面** — Tkinter 可视化操作，支持实时进度和日志

## 快速开始

```bat
REM 安装依赖
pip install -r requirements.txt

REM 启动 GUI（无参数）
webcopier.bat

REM 命令行帮助
webcopier.bat --help
```

## 命令行接口（cmd / PowerShell / 终端）

`webcopier.bat` 是命令提示符启动器（自动使用项目 `.venv`，缺失时回退系统 `python`）。
也可直接用 `python -m webcopier <命令>`。

### fetch — 抓取单个页面

```bat
webcopier fetch https://example.com/article -m trafilatura -o out -f md
webcopier fetch https://example.com/article --stdout          :: 正文同时打印到控制台
```

| 参数 | 说明 |
|---|---|
| `-m/--method` | 提取方式，默认 trafilatura |
| `-f/--format` | 输出格式 txt/md/json/jsonl/html，默认 txt |
| `-o/--out` | 保存目录 |
| `--stdout` | 同时把正文打印到控制台 |
| `--cookie` / `--user-agent` / `-p/--proxy` | 请求定制 |
| `--retries` / `--random-delay` / `--curl-cffi` | 反爬与重试 |

### batch — 批量抓取

```bat
webcopier batch urls.txt --delay 2 --concurrency 4 -o out -f md
```

`urls.txt` 每行一个 URL，`#` 开头为注释。

### crawl — 整站爬取

```bat
webcopier crawl https://example.com --depth 2 --sitemap -o out
```

### forum — 论坛抓取（列表翻页 + 主题二级页翻页）

```bat
REM 抓取 trow.cc 四个版块的全部文章
webcopier forum 150 177 171 176 --preset trow -o output\trow

REM 递归抓取子版块
webcopier forum 150 --with-subforums -o output\trow

REM 中断后继续（重跑同一条命令即可）
webcopier forum 150 177 171 176 -o output\trow

REM 调试：只抓 1 页列表、3 个主题
webcopier forum 150 -o output\_smoke --max-listing-pages 1 --max-topics 3
```

| 参数 | 说明 |
|---|---|
| `forum_ids` | 版块 ID，可多个 |
| `--preset` | 站点模板：`trow` / `ipb2`，默认 trow |
| `--board-base` | 自定义 board 根地址，覆盖 preset |
| `-f/--format` | md（默认）/ txt / json / jsonl |
| `-o/--out` | 输出目录 |
| `--delay` | 请求基准间隔（秒），默认 2.0 |
| `--workers` | 并发线程数，默认 2 |
| `--with-subforums` | 递归抓取子版块 |
| `--no-resume` | 忽略断点，从头重抓 |
| `--max-listing-pages` / `--max-topics` / `--max-post-pages` | 调试用限量 |

输出结构：

```
output/trow/
├── forum_150/              每个版块一个目录
│   └── 150_54123_标题.md   每条主题一个文件
├── forum_177/
├── forum_171/
├── forum_176/
├── index.json              完整索引（含统计）
├── index.csv               表格索引（Excel 可直接打开）
├── corpus.jsonl            语料行索引
├── checkpoint.json         断点，重跑自动续传
└── failed.json             失败清单（如有）
```

### config — 查看/修改配置

```bat
webcopier config                       :: 显示全部配置
webcopier config --set delay=3 concurrency=8
webcopier config --reset
```

### es — Everything 搜索（本地文件索引）

把 [voidtools Everything](https://www.voidtools.com/) 的官方命令行接口 `es.exe`（MIT 许可，收录于 `bin/`）接入 WebCopier。需先运行 Everything 主程序（ES 通过命名管道 `\\.\PIPE\Everything IPC` 通信）。

```bat
REM 诊断连通性（Everything 是否在运行）
webcopier es --status

REM 搜索并表格展示（带大小）
webcopier es "webcopier ext:md" --size

REM 仅输出路径清单并落盘
webcopier es "D:\webcopier\*.html" -f paths -o hits.txt

REM 限定目录 + 正则 + 结构化 JSON
webcopier es "\.md$" -r -p -path D:\docs\ -f json

REM 整合：把搜到的本地网页直接送入正文提取器
webcopier es "ext:html" --extract --extract-dir output\_es_extract -f paths
```

| 参数 | 说明 |
|---|---|
| `--status` | 诊断 ES/Everything 连通性（版本 + 管道可用性） |
| `-f/--format` | `table`（默认）/ `paths` / `json` / `csv` |
| `--size` | 表格模式追加文件大小列 |
| `--columns` | 附加显示列（size/dm/dc/da/ext/attribs…） |
| `-o/--out` | 把路径清单写入文件（UTF-8） |
| `-p/--match-path` / `-i/--case` / `-r/--regex` | 匹配完整路径 / 区分大小写 / 正则 |
| `--path` | 限定搜索目录（目录尾部反斜杠 `D:\dir\`） |
| `-n/--count` | 结果上限 |
| `--open N` | 在资源管理器中定位第 N 项 |
| `--extract` | 把结果中的本地网页 `.html/.htm/.mht` 送入正文提取器 |
| `--extract-all` | 对所有结果（不限于网页）尝试提取 |
| `--extract-dir` / `--extract-method` / `--extract-format` | 正文输出目录 / 提取方式 / 输出格式 |
| `--es-path` / `--instance` / `--timeout` | 指定 es.exe 路径 / Everything 实例 / 超时秒 |
| `--es-args` | 其余参数**原样透传**给 es.exe（`REMAINDER`，写在所有参数之后） |

**整合要点**：`--extract` 借助 `http_client.file_get` 把本地文件路径转成 `file://` URL，从而复用 WebCopier 既有的 6 种正文提取器与噪声过滤，无需把 Everything 重写为 Python。

## 配置

编辑 `config.json` 调整配置参数（超时、并发数、提取方式等），也可用 `webcopier config --set` 修改。

## 项目结构

```
webcopier/
├── webcopier.bat        # 命令提示符启动器
├── WebCopier_GUI.py     # GUI 入口
├── bin/                 # 第三方命令行工具（含 es.exe，MIT 许可）
│   ├── es.exe           # Everything 命令行搜索（voidtools，MIT）
│   ├── ES-LICENSE.txt   # ES 许可文件
│   └── ES-README.md     # ES 用途与合规说明
├── webcopier/           # 核心包
│   ├── main.py          # 统一入口（无参数 GUI / 有参数 CLI）
│   ├── __main__.py      # python -m webcopier
│   ├── cli.py           # 命令行接口（v5.5 新增）
│   ├── forum.py         # 论坛抓取模块（v5.5 新增）
│   ├── everything.py    # Everything/ES 包装层（v5.5 新增）
│   ├── gui.py           # GUI 界面
│   ├── engine.py        # 抓取引擎
│   ├── extractors.py    # 6 种正文提取方式
│   ├── http_client.py   # HTTP 客户端（v5.5 增加 file:// 支持）
│   ├── playwright_utils.py
│   ├── link_finder.py   # 链接发现
│   ├── session.py       # Session 管理
│   ├── captcha.py       # 验证码识别
│   ├── writer.py        # 输出写入
│   └── identity_manager.py  # 身份轮换
├── tools/               # 辅助脚本
├── output/              # 抓取输出
└── config.json          # 配置文件
```

## 版本历史

### v5.5

- 新增命令行接口 `cli.py`（fetch / batch / crawl / forum / config / **es**）与 `webcopier.bat` 启动器
- 新增论坛抓取模块 `forum.py`：列表翻页 + 主题二级页翻页 + 断点续传 + 索引导出
- 新增 Everything/ES 整合：`bin/es.exe`（MIT）+ `everything.py` 包装层，`es` 子命令搜索/诊断；`http_client.file_get` 打通 `file://` 管线使 ES 结果可送入正文提取器
- 修复 `http_client` Brotli 解码缺失导致正文乱码（自动剔除不支持的 `br` 编码，缺库时明确报错）
- 修复 `engine.batch_fetch` 中 `total` 未定义、`text` 未绑定的 NameError
- 修复 `engine.init_robots` 基准 URL 缺失导致 robots.txt 检查被静默跳过（现以首个 URL 为基准）
- 修复 `forum.save_topic` 扩展名判断错误：json/jsonl 内容被写成 `.txt` 文件名
- 控制台编码自适应：TTY 跟随代码页，重定向用 UTF-8

### v5.4

- RateLimiter 并发限速器 + robots.txt Crawl-delay
- 整站爬取断点续传、HTML 输出格式、缓存过期单例修复

## 许可

内部项目，全哥创建。
