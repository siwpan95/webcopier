# ES (Everything Command-line Interface) — 收录说明

## 来源

| 项目 | 值 |
|---|---|
| 组件 | ES — Everything 命令行搜索接口 |
| 版本 | 1.1.0.37 |
| 作者 | voidtools / David Carpenter |
| 许可 | **MIT**（见同目录 `ES-LICENSE.txt`） |
| 上游 | https://www.voidtools.com/ |
| 收录时间 | 2026-08-31 |

本目录下的 `es.exe` 是从 `C:\Users\13122\Desktop\Everything-1.5.0.1418b.x64\` 原样复制的
预编译二进制，未经任何修改。其完整 C 源码可从同目录的 `ES-1.1.0.37.src.zip` 获取
（同为 MIT 许可），如需自行编译或修改，源码是可用的。

## 许可合规

MIT 许可允许「使用、复制、修改、合并、发布、分发、再许可和/或销售」，
唯一条件是**保留版权声明和许可声明**。因此：

- 随附 `ES-LICENSE.txt`（含 "Copyright (c) 2025 voidtools"）
- 本文件即为归属标注
- 若本项目整体再分发，这两个文件必须一并携带

## 为什么不直接用源码改？

ES 源码是 **27,172 行纯 Win32 C**（约 40 个文件），Python 项目无法直接「复制粘贴」
运行——它需要 C 工具链编译成 exe。因此采取的策略是：

**收录官方预编译二进制 + 编写 Python 包装层**（`webcopier/everything.py`），
包装层负责参数透传、结构化输出解析、错误处理与编码适配。

这样既满足「内置到本项目」，又保留 ES 全部功能（IPC v1/v2/v3 自动协商、
全部搜索/排序/显示选项），且上游由 voidtools 维护，无需我们自己跟进
Everything 的 IPC 协议变更。

## 运行时依赖

`es.exe` 通过命名管道 `\\.\PIPE\Everything IPC` 与 Everything 主程序通信，
因此**必须运行 Everything**（1.5 或 1.4）才能工作。

若 Everything 未运行，`es.exe` 会返回 `Error 8: Everything IPC not found`，
webcopier 包装层会把这条信息转成明确的可读提示。

## 手动调用

```bat
bin\es.exe --help
bin\es.exe -json -n 10 "webcopier ext:md"
bin\es.exe -get-everything-version
```

正常情况下无需手动调用，请用 `webcopier es ...`。
