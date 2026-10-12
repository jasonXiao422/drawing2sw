"""在 skill 的文档里按关键词搜索，零依赖（只用 Python 标准库）。

用法:
  python scripts/search_refs.py "R6 圆角 失败"
  python scripts/search_refs.py "切除 方向 反了" -k 5
  python scripts/search_refs.py "沉孔" --full        # 输出整段，不截断

搜索范围：references/*.md、SKILL.md（skill 本体，不搜开发文档）。
按 ## / ### 标题切段，中文按两字一组、英文和数字按单词打分，标题里命中加倍。

什么时候用：读图或建模时拿不准某个符号、某种报错、某种画法，先搜一下有没有记录。
注意：搜索只是补充。SKILL.md 里写明"必读"的文件照样要读，reading-rules.md 第 3 步之前照样要扫一遍。
AI 最容易错的地方往往是它没意识到要搜的地方（见 reading-rules R8 R9）。

想用向量语义搜索的，见 dev/rag/README.md（可选模块，依赖较重）。
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ["references/*.md", "SKILL.md"]
_CJK = re.compile(r"[一-鿿]+")
_WORD = re.compile(r"[A-Za-zØΦφ⌀]*\d+(?:\.\d+)?[A-Za-z]*|[A-Za-z_][A-Za-z_0-9]+|#\d+")


def tokens(text: str) -> list[str]:
    """中文两字一组（单字也算），英文、数字、R6、M8、#15 这类按整体。"""
    out = []
    for run in _CJK.findall(text):
        out += list(run) if len(run) == 1 else [run[i:i + 2] for i in range(len(run) - 1)]
    out += [w.lower() for w in _WORD.findall(text)]
    return out


def chunks():
    """按 ## / ### 标题切段，返回 (文件, 标题路径, 正文)。"""
    for pat in SOURCES:
        for f in sorted(ROOT.glob(pat)):
            rel = f.relative_to(ROOT).as_posix()
            h2 = h3 = ""
            buf: list[str] = []

            def emit():
                body = "\n".join(buf).strip()
                if body:
                    yield rel, " > ".join(x for x in (h2, h3) if x), body

            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith("## ") or line.startswith("### "):
                    yield from emit()
                    buf = [line]
                    if line.startswith("## "):
                        h2, h3 = line[3:].strip(), ""
                    else:
                        h3 = line[4:].strip()
                else:
                    buf.append(line)
            yield from emit()


def search(query: str, k: int = 3) -> list[dict]:
    docs = list(chunks())
    q = tokens(query)
    if not q or not docs:
        return []
    tfs = [Counter(tokens(t + "\n" + b)) for _, t, b in docs]
    title_tfs = [Counter(tokens(t)) for _, t, _ in docs]
    n = len(docs)
    df = Counter(tok for tf in tfs for tok in set(tf))
    scored = []
    for i, (f, t, b) in enumerate(docs):
        s = 0.0
        hit = set()
        for tok in set(q):
            if tfs[i][tok]:
                idf = math.log(1 + n / df[tok])
                s += idf * (1 + math.log(tfs[i][tok])) * (2 if title_tfs[i][tok] else 1)
                hit.add(tok)
        if s:
            s *= len(hit) / len(set(q))  # 命中的查询词越全越靠前
            scored.append({"score": round(s, 2), "file": f, "title": t, "text": b})
    scored.sort(key=lambda d: -d["score"])
    return scored[:k]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 终端中文不乱码
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=3, help="返回几段（默认 3）")
    ap.add_argument("--full", action="store_true", help="输出整段")
    args = ap.parse_args()
    res = search(args.query, args.k)
    if not res:
        print("没有找到相关记录。可以换个说法再搜，或者直接读 references/reading-rules.md。")
        return 1
    for r in res:
        print(f"=== {r['file']}  {r['title']}   (得分 {r['score']})")
        lines = r["text"].splitlines()
        print("\n".join(lines if args.full else lines[:14]))
        if not args.full and len(lines) > 14:
            print(f"... 还有 {len(lines) - 14} 行，加 --full 看全文")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
