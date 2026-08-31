"""
webcopier - 网页正文抓取工具包 v5.5
模块化架构：爬虫引擎层 + 界面配置层 + 反爬增强层
v5.4 更新：
  - engine.py    新增 RateLimiter 并发限速器 + robots.txt Crawl-delay
  - engine.py    整站爬取断点续传（checkpoint/resume）
  - http_client  修复缓存过期时间单例 bug（线程安全）
  - writer.py    策略模式重构输出格式，新增 HTML 格式
  - writer.py    download_images 统一走 http_client
v5.5 更新：
  - cli.py       新增命令行接口（fetch / batch / crawl / forum / config）
  - main.py      统一入口：无参数启动 GUI，带参数进入 CLI
  - __main__.py  支持 python -m webcopier
  - forum.py     新增论坛抓取模块（列表翻页 + 主题二级页翻页 + 断点续传）
  - engine.py    修复 batch_fetch 中 total 未定义 / text 未绑定的 NameError
"""
__version__ = "5.5"
__author__ = "WebCopier"
