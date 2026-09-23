# WebCopier — 网页正文抓取工具 v5.3

> 仓库：<https://gitee.com/siwpan/webcopier> ｜ 许可：MIT（见 [LICENSE](LICENSE)）

全功能网页正文抓取程序，支持多种提取方式和完善的反爬系统。

## 功能

- **三种模式** — 单页抓取 / 批量抓取 / 整站爬取
- **六种提取方式** — trafilatura / lxml+XPath / BeautifulSoup / readability / newspaper3k / Playwright
- **反爬系统** — 浏览器身份池轮换、curl_cffi TLS 伪装、验证码识别 (ddddocr)、Session/Cookie 管理、stealth.js 注入、请求延迟 + 退避重试
- **批量处理** — 从文件读取 URL 列表，多线程并发抓取
- **GUI 界面** — Tkinter 可视化操作，支持实时进度和日志

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 GUI
python WebCopier_GUI.py

# 或作为模块
python -m webcopier
```

## 配置

编辑 `config.json` 调整 12 项配置参数（超时、并发数、提取方式等）。

## 项目结构

```
txt/
├── WebCopier_GUI.py     # GUI 入口
├── webcopier/           # 核心包
│   ├── main.py          # 程序入口
│   ├── gui.py           # GUI 界面
│   ├── engine.py        # 抓取引擎
│   ├── extractors.py    # 6 种正文提取方式
│   ├── http_client.py   # HTTP 客户端
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

## 许可

内部项目，全哥创建。
