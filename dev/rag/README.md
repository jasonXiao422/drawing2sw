# rag：向量检索（可选模块）

**不装也完全不影响 skill。** 默认用零依赖的关键词搜索：

```
.venv\Scripts\python.exe scripts\search_refs.py "R6 圆角 失败"
```

## 什么时候才值得用这个

现在 `references/` 只有几十 KB，AI 能整份读完，关键词搜索也足够准（2026-10-10 用 6 个真实问题测过，第一条全部命中）。
向量检索适合知识库大到读不完、而且问题的说法和记录的说法差别很大的时候，例如：

- 接入几百页的 SolidWorks API 文档、国标原文
- 测试题积累到几百道，要按"像不像"找相似的历史题

工程数据（键槽、沉孔、螺纹底孔）不要用向量检索，用 `scripts/standards.py` 查表，结果是精确的。

## 安装（单独的环境，不碰主环境）

主环境里的 cadquery、numba 对 numpy 版本敏感，向量检索的依赖可能会改动 numpy，所以装在 `dev\rag\.venv` 里。

1. 建一个单独的环境：
```
py -3.12 -m venv dev\rag\.venv
```

2. 装依赖（清华镜像）：
```
dev\rag\.venv\Scripts\python.exe -m pip install -r dev\rag\requirements-rag.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

3. 建库（第一次会从 hf-mirror.com 下载约 95 MB 的 bge-small-zh-v1.5 模型）：
```
dev\rag\.venv\Scripts\python.exe dev\rag\build_kb.py
```

4. 检索：
```
dev\rag\.venv\Scripts\python.exe dev\rag\search_kb.py "R6 圆角比槽角大为什么失败" -k 3
```

## 状态

| 文件 | 作者 | 测试情况 |
|---|---|---|
| build_kb.py | 豆包 2026-10-10 | 只做过语法检查，没跑过（依赖没装） |
| search_kb.py | 豆包 2026-10-10 | 同上 |

`references/` 改了以后要重新跑 build_kb.py，否则检索的是旧内容。关键词搜索没有这个问题。
