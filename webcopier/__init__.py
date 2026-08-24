"""
webcopier - 网页正文抓取工具包 v5.4
模块化架构：爬虫引擎层 + 界面配置层 + 反爬增强层
v5.4 更新：
  - engine.py    新增 RateLimiter 并发限速器 + robots.txt Crawl-delay
  - engine.py    整站爬取断点续传（checkpoint/resume）
  - http_client  修复缓存过期时间单例 bug（线程安全）
  - writer.py    策略模式重构输出格式，新增 HTML 格式
  - writer.py    download_images 统一走 http_client
"""
__version__ = "5.4"
__author__ = "WebCopier"
