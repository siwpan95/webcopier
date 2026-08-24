#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置持久化管理：加载、保存、导入、导出
配置文件存储在脚本同目录的 config.json
"""

import json
import shutil
from pathlib import Path
from .constants import VERSION

# ============================================================
#  配置文件路径
# ============================================================
_SCRIPT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = _SCRIPT_DIR / "config.json"

# 兼容旧版：自动迁移配置文件
_OLD_CONFIG = Path.home() / ".webcopier" / "config.json"
if _OLD_CONFIG.exists() and not CONFIG_FILE.exists():
    if not _OLD_CONFIG.parent.samefile(_SCRIPT_DIR):
        shutil.move(str(_OLD_CONFIG), str(CONFIG_FILE))
        try:
            shutil.rmtree(str(_OLD_CONFIG.parent))
        except Exception:
            pass


# ============================================================
#  默认配置
# ============================================================
DEFAULT_CONFIG = {
    "user_agent": "",
    "save_dir": str(_SCRIPT_DIR / "output"),
    "method": "trafilatura",
    "output_format": "txt",
    "delay": 2.0,
    "respect_robots": True,
    "concurrency": 4,
    "max_depth": 1,
    "max_retries": 3,
    "download_images": False,
    "proxy": "",
    "img_save_dir": "",
    "random_ua": True,
    "random_delay": True,
    "cache_enabled": False,
    "cache_expire": 3600,
    # --- v5.1 新增配置 ---
    "use_curl_cffi": False,
    "playwright_anti_detect": False,
    "playwright_local_browser": False,
    "cookie_file": "",
    "impersonate": "chrome120",
    "fingerprint_level": "standard",
    # --- v5.3 新增配置 ---
    "tk_theme": "clam",
}


def load_config() -> dict:
    """读取配置文件，不存在则返回默认配置"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> bool:
    """保存配置到文件，返回是否成功"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def export_config(cfg: dict, filepath: str) -> bool:
    """导出配置到指定文件（可用于备份或分享）"""
    try:
        data = {**cfg, "_version": VERSION, "_exported": True}
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def import_config(filepath: str) -> dict:
    """从指定文件导入配置，返回合并后的配置字典"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 移除导出标记字段
        data.pop("_version", None)
        data.pop("_exported", None)
        return {**DEFAULT_CONFIG, **data}
    except Exception:
        return dict(DEFAULT_CONFIG)


def reset_config() -> bool:
    """删除配置文件以恢复默认值"""
    if CONFIG_FILE.exists():
        try:
            CONFIG_FILE.unlink()
            return True
        except Exception:
            return False
    return True
