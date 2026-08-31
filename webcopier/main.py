#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebCopier 统一入口 v5.5

行为：
    python -m webcopier                → 启动 GUI
    python -m webcopier <命令> ...     → 命令行模式

命令详见：python -m webcopier --help
"""

import sys
import os

if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "webcopier"


def launch_gui():
    """启动 Tkinter 图形界面（惰性导入，保证 CLI 在无 GUI 环境可用）"""
    import tkinter as tk
    from .gui import WebCopierApp
    root = tk.Tk()
    app = WebCopierApp(root)
    root.mainloop()


def main():
    # 无参数 → GUI；有参数 → CLI
    if len(sys.argv) > 1:
        from .cli import main as cli_main
        return cli_main(sys.argv[1:])
    launch_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
