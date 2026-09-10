#!/usr/bin/env python3
"""Herdr 插件入口；运行时仅依赖 Python 标准库。"""
import sys

if sys.version_info < (3, 11):
    sys.exit("快捷键提示插件需要 Python 3.11 或更高版本。")

from key_hints.runtime import main

if __name__ == "__main__":
    raise SystemExit(main())
