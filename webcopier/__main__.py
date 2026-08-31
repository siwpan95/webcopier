#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""python -m webcopier 入口"""

import sys
import os

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "webcopier"

from .main import main

if __name__ == "__main__":
    sys.exit(main())
