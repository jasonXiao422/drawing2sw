# -*- coding: utf-8 -*-
r"""
drawing2sw 知识库检索：问题 → 向量 → 从 Chroma 取最相关的切片。

用法：
    .venv\Scripts\python.exe dev\rag\search_kb.py "R6 圆角比槽角大为什么失败" -k 3

先运行 build_kb.py 建库，否则这里会报"集合不存在"。
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

# 国内下载 HuggingFace 模型走镜像，必须在 import fastembed 之前设置
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from fastembed import TextEmbedding  # noqa: E402
import chromadb  # noqa: E402

PERSIST_DIR = Path(__file__).resolve().parent / "kb"
MODEL = "BAAI/bge-small-zh-v1.5"
COLLECTION = "drawing2sw_kb"
# bge 系列官方建议查询时加指令前缀，提升检索效果
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


def main() -> None:
    ap = argparse.ArgumentParser(description="检索 drawing2sw 知识库")
    ap.add_argument("query", help="要查的问题")
    ap.add_argument("-k", type=int, default=3, help="返回条数")
    args = ap.parse_args()

    if not PERSIST_DIR.exists():
        print(f"错误：向量库不存在（{PERSIST_DIR}）。先运行 build_kb.py 建库。")
        raise SystemExit(1)

    print(f"加载模型 {MODEL}（首次约 95MB）...")
    model = TextEmbedding(model_name=MODEL)
    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    try:
        col = client.get_collection(COLLECTION)
    except Exception:  # noqa: BLE001
        print("错误：集合不存在。先运行 build_kb.py 建库。")
        raise SystemExit(1)

    try:
        qv = list(model.query_embed(QUERY_PREFIX + args.query))
    except AttributeError:  # 旧版 fastembed 没有 query_embed
        qv = list(model.embed(QUERY_PREFIX + args.query))

    hits = col.query(query_embeddings=qv, n_results=args.k)

    print(f"问题：{args.query}\n")
    for i, (doc, meta, dist) in enumerate(
        zip(hits["documents"][0], hits["metadatas"][0], hits["distances"][0]), 1
    ):
        print(f"--- 第 {i} 条 [{meta['source']} > {meta['title']}] 距离 {dist:.3f} ---")
        print(doc[:600])
        print()


if __name__ == "__main__":
    main()
