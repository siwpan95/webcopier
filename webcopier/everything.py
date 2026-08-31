#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ES 包装层 v5.5 —— Everything 命令行搜索

将 voidtools 的 es.exe（MIT 许可，收录于 bin/）包装为 WebCopier 可用的
Python 接口，负责：
  - es.exe 定位（项目 bin/ → 环境变量 → Everything 安装目录）
  - 参数透传（保留 ES 全部搜索/排序/显示选项）
  - 结构化输出解析（-json / -csv / -tsv / 纯路径）
  - 编码适配与错误分类（未找到 ES / Everything 未运行 / 无结果）

es.exe 通过命名管道 \\\\.\\PIPE\\Everything IPC 与 Everything 通信，
因此运行时要求 Everything 主程序正在运行。

模块级函数可独立使用：
    from webcopier.everything import search, EverythingSearcher
    results = search("webcopier ext:md", count=10)
"""

import os
import csv
import json
import shutil
import subprocess
from dataclasses import dataclass, asdict
from typing import List, Optional, Sequence

from .constants import VERSION


# ============================================================
#  常量
# ============================================================

# es.exe 候选存放位置（相对项目根）
_BIN_SUBPATH = os.path.join("bin", "es.exe")

# Everything 常见安装目录（Windows），用于兜底查找
_EVERYTHING_DIR_CANDIDATES = (
    r"C:\Program Files\Everything",
    r"C:\Program Files (x86)\Everything",
    os.path.expandvars(r"%APPDATA%\Everything"),
)

# es.exe 输出的已知错误前缀 → 人类可读提示
_ERROR_HINTS = {
    "Error 1": "ES 参数错误，请检查搜索语法（可先运行 es.exe --help）。",
    "Error 3": "路径不存在或无法访问。",
    "Error 4": "ES 无法分配内存或参数过长。",
    "Error 5": "ES 操作被拒绝（可能是权限不足）。",
    "Error 8": "Everything 未运行，或 IPC 管道不可用。请先启动 Everything。",
    "Error 9": "Everything 数据库尚未就绪，请等待索引完成后重试。",
}


class EverythingError(RuntimeError):
    """ES / Everything 相关错误"""

    def __init__(self, message: str, hint: str = "", code: int = 0):
        full = f"{message}"
        if hint:
            full += f"\n  → {hint}"
        super().__init__(full)
        self.message = message
        self.hint = hint
        self.code = code


# ============================================================
#  数据
# ============================================================

@dataclass
class SearchResult:
    """一条 ESR 搜索结果"""
    path: str                       # 完整路径（目录以 \ 结尾）
    name: str = ""                  # 文件名
    size: Optional[int] = None
    date_modified: str = ""
    extension: str = ""

    @property
    def is_dir(self) -> bool:
        return self.path.endswith(("\\", "/"))

    def to_dict(self):
        return asdict(self)


# ============================================================
#  es.exe 定位
# ============================================================

def project_root() -> str:
    """返回项目根目录（webcopier 包的上一级）"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_es(explicit_path: str = "") -> Optional[str]:
    """定位 es.exe。

    查找顺序：
      1. 显式传入的路径
      2. 项目 bin/es.exe
      3. PATH 中的 es.exe
      4. Everything 常见安装目录下的 es.exe

    Returns:
        es.exe 绝对路径，找不到返回 None
    """
    if explicit_path:
        p = os.path.abspath(explicit_path)
        return p if os.path.isfile(p) else None

    candidate = os.path.join(project_root(), _BIN_SUBPATH)
    if os.path.isfile(candidate):
        return candidate

    which = shutil.which("es.exe") or shutil.which("es")
    if which:
        return which

    for base in _EVERYTHING_DIR_CANDIDATES:
        if not base or not os.path.isdir(base):
            continue
        p = os.path.join(base, "es.exe")
        if os.path.isfile(p):
            return p

    return None


# ============================================================
#  搜索器
# ============================================================

class EverythingSearcher:
    """ES 搜索器：调用 es.exe 并解析结果"""

    def __init__(self, es_path: str = "", timeout: int = 30,
                 instance: str = ""):
        """
        Args:
            es_path: es.exe 路径（留空则自动查找）
            timeout: 子进程超时（秒）
            instance: Everything 实例名（留空=默认实例）
        """
        self.es_path = find_es(es_path)
        self.timeout = timeout
        self.instance = instance
        if not self.es_path:
            raise EverythingError(
                "未找到 es.exe",
                "请将 es.exe 放到项目的 bin\\ 目录，或用 --es-path 指定路径。"
                "（es.exe 随 Everything 发行，MIT 许可）")

    # ---------------- 底层调用 ----------------
    def run_raw(self, args: Sequence[str]) -> str:
        """原样调用 es.exe，返回 stdout 文本（UTF-8 解码）。"""
        cmd = [self.es_path, *args]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.timeout,
                # 不在此处解码，统一按 UTF-8 处理，避免 GBK 代码页破坏中文路径
            )
        except subprocess.TimeoutExpired:
            raise EverythingError(
                f"ES 调用超时（>{self.timeout}s）",
                "Everything 可能正在重建索引，稍后重试或调大 --timeout。")
        except FileNotFoundError:
            raise EverythingError(f"es.exe 不存在: {self.es_path}")
        except OSError as e:
            raise EverythingError(f"无法执行 es.exe: {e}")

        out = self._decode(proc.stdout)
        err = self._decode(proc.stderr)

        # es.exe 把错误写到 stdout/stderr，需主动识别
        combined = (out + "\n" + err).strip()
        for prefix, hint in _ERROR_HINTS.items():
            if prefix in combined:
                raise EverythingError(combined.splitlines()[0], hint,
                                      code=proc.returncode)
        if proc.returncode != 0 and not out.strip():
            raise EverythingError(
                combined or f"ES 退出码 {proc.returncode}",
                code=proc.returncode)
        return out

    @staticmethod
    def _decode(data: bytes) -> str:
        if not data:
            return ""
        # 优先 UTF-8；ES 输出在部分代码页下可能是 GBK，做一次回退
        for enc in ("utf-8", "mbcs", "gbk"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    # ---------------- 诊断 ----------------
    def es_version(self) -> str:
        return self.run_raw(["-version"]).strip()

    def everything_version(self) -> str:
        return self.run_raw(["-get-everything-version"]).strip()

    def status(self) -> dict:
        """返回连通性诊断信息"""
        info = {"es_path": self.es_path, "ok": False}
        try:
            info["es_version"] = self.es_version()
            info["everything_version"] = self.everything_version()
            info["ok"] = True
        except EverythingError as e:
            info["error"] = str(e)
        return info

    # ---------------- 搜索 ----------------
    def search(self, query: str, count: int = 0,
               match_path: bool = False, match_case: bool = False,
               regex: bool = False, files_only: bool = False,
               folders_only: bool = False, sort: str = "",
               columns: Sequence[str] = (),
               path_filter: str = "",
               extra_args: Sequence[str] = (),
               ) -> List[SearchResult]:
        """执行搜索并解析为 SearchResult 列表。

        Args:
            query: Everything 搜索语法
            count: 结果上限（0 = ES 默认）
            match_path: -p 匹配完整路径
            match_case: -i 区分大小写
            regex: -r 正则
            files_only: /a-d 仅文件
            folders_only: /ad 仅目录
            sort: -sort 参数值（如 name / size / date-modified）
            columns: 附加显示列（size / dm / dc / da / ext / attribs ...）
            path_filter: -path 限定搜索目录
            extra_args: 其余原样透传给 es.exe 的参数
        """
        cols = list(columns)

        # 结构化输出：请求 JSON，ES 会输出 [{...}, ...] 形式
        args: List[str] = ["-json"]
        if cols:
            args += ["-add-columns", ";".join(cols)]
        if count and count > 0:
            args += ["-n", str(count)]
        if match_path:
            args.append("-p")
        if match_case:
            args.append("-i")
        if regex:
            args += ["-r", query]
        if files_only:
            args.append("/a-d")
        if folders_only:
            args.append("/ad")
        if sort:
            args += ["-sort", sort]
        if path_filter:
            args += ["-path", path_filter]
        if self.instance:
            args += ["-instance", self.instance]

        args += list(extra_args)

        # 非正则时查询串作为位置参数放在最后（与 ES 用法一致）
        if not regex:
            args.append(query)

        raw = self.run_raw(args)
        return self._parse_json(raw)

    # ---------------- 解析 ----------------
    @staticmethod
    def _parse_json(raw: str) -> List[SearchResult]:
        """解析 ES 的 -json 输出。

        ES 输出形如：
            [{"filename":"D:\\\\a\\\\"},
             {"filename":"D:\\\\a\\\\b.txt","size":"123"}]
        注意：ES 在每行末尾带逗号，最后一行没有，整体不是严格 JSON 数组，
        需要容错修复后再解析。
        """
        text = (raw or "").strip()
        if not text:
            return []

        # 容错：ES 的数组元素间有换行与逗号，末尾无逗号 → 直接解析通常可行；
        # 若失败，则逐行剥离后用 jsonlines 方式解析。
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = []
            for line in text.splitlines():
                line = line.strip().rstrip(",")
                if not line or line in ("[", "]"):
                    continue
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        results: List[SearchResult] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            path = item.get("filename") or item.get("path") or ""
            if not path:
                continue
            size = item.get("size")
            if size is not None:
                try:
                    size = int(str(size).replace(",", ""))
                except (ValueError, TypeError):
                    size = None
            results.append(SearchResult(
                path=path,
                name=item.get("name") or os.path.basename(
                    path.rstrip("\\/")) or path,
                size=size,
                date_modified=item.get("date_modified")
                or item.get("date-modified") or "",
                extension=item.get("extension") or item.get("ext") or "",
            ))
        return results


# ============================================================
#  便捷函数
# ============================================================

_DEFAULT_SEARCHER: Optional[EverythingSearcher] = None


def get_searcher(es_path: str = "", refresh: bool = False
                 ) -> EverythingSearcher:
    """获取（并缓存）默认搜索器"""
    global _DEFAULT_SEARCHER
    if refresh or _DEFAULT_SEARCHER is None or (
            es_path and _DEFAULT_SEARCHER.es_path != os.path.abspath(es_path)):
        _DEFAULT_SEARCHER = EverythingSearcher(es_path=es_path)
    return _DEFAULT_SEARCHER


def search(query: str, count: int = 20, **kwargs) -> List[SearchResult]:
    """模块级便捷搜索：search("foo ext:md") -> [SearchResult, ...]"""
    return get_searcher().search(query, count=count, **kwargs)


def to_file_url(path: str) -> str:
    """本地路径 → file:// URL（供 webcopier 提取器使用）。

    保留盘符冒号与路径分隔符，仅对空格、#、? 等真正需要转义的字符编码，
    以便输出形如 file:///D:/work/page.html 的可读 URL。
    """
    from urllib.parse import quote
    from pathlib import Path
    p = Path(path).resolve()
    as_posix = p.as_posix()
    if as_posix.startswith("//"):          # UNC: //host/share → file://host/share
        return "file:" + quote(as_posix, safe="/:")
    return "file:///" + quote(as_posix, safe="/:")


def is_probably_webpage(path: str) -> bool:
    """判断是否像网页文件（HTML/HTM），用于 --extract 过滤"""
    return os.path.splitext(path)[1].lower() in (".html", ".htm", ".mht")
