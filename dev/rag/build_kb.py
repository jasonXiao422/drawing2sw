# -*- coding: utf-8 -*-
r"""
drawing2sw 知识库构建：把 references/*.md 切片、向量化，存入本地 Chroma。

用法：
    .venv\Scripts\python.exe dev\rag\build_kb.py

首次运行会从 HuggingFace 镜像（hf-mirror.com）下载 bge-small-zh-v1.5 模型，
约 95 MB，之后离线可用。向量库落在 dev\rag\kb\ 目录。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 国内下载 HuggingFace 模型走镜像，必须在 import fastembed 之前设置
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from fastembed import TextEmbedding  # noqa: E402
import chromadb  # noqa: E402

PROJECT = Path(__file__).resolve().parents[2]         # drawing2sw 根目录
REFERENCES = PROJECT / "references"                  # 知识库源文件
PERSIST_DIR = Path(__file__).resolve().parent / "kb"  # 向量库落盘位置
MODEL = "BAAI/bge-small-zh-v1.5"
COLLECTION = "drawing2sw_kb"


def split_markdown(text: str) -> list[tuple[str, str]]:
    """按 ## / ### 标题切块，返回 [(标题, 块正文)]。"""
    lines = text.splitlines()
    chunks: list[tuple[str, str]] = []
    cur_title = "（文件头）"
    buf: list[str] = []

    def flush():
        nonlocal buf
        body = "\n".join(buf).strip()
        if body:
            chunks.append((cur_title, body))
        buf = []

    for line in lines:
        if line.startswith("### "):
            flush()
            cur_title = line[4:].strip()
            buf = [line]
        elif line.startswith("## "):
            flush()
            cur_title = line[3:].strip()
            buf = [line]
        else:
            buf.append(line)
    flush()
    return chunks


def main() -> None:
    files = sorted(REFERENCES.glob("*.md"))
    if not files:
        print(f"错误：{REFERENCES} 下没有 md 文件")
        sys.exit(1)

    print(f"加载模型 {MODEL}（首次会下载约 95MB，走 hf-mirror）...")
    model = TextEmbedding(model_name=MODEL)

    print("切片 + 向量化...")
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    for f in files:
        for title, body in split_markdown(f.read_text(encoding="utf-8")):
            ids.append(f"{f.stem}::{title}")
            docs.append(body)
            metas.append({"source": f.name, "title": title})
    print(f"共 {len(docs)} 个切片，来源 {len(files)} 个文件")

    embeddings = list(model.embed(docs))

    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    # 重建，避免旧数据残留
    try:
        client.delete_collection(COLLECTION)
    except Exception:  # noqa: BLE001  集合不存在时忽略
        pass
    col = client.get_or_create_collection(COLLECTION)
    col.add(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)
    print(f"写入 {PERSIST_DIR}，共 {col.count()} 条。完成。")


if __name__ == "__main__":
    main()
