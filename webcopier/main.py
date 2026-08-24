#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebCopier 网页正文抓取工具 - 入口
"""

import sys
import os

# 使 main.py 既可单独运行也可作为包模块运行
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "webcopier"

import tkinter as tk
from .gui import WebCopierApp


def main():
    root = tk.Tk()
    app = WebCopierApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
