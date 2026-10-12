"""国标尺寸查表。图纸只写了标准号或规格（"键 16"、"4×M8 沉孔"、"M10 螺纹孔"）、没标具体尺寸时用。

用法（命令行）:
  python scripts/standards.py key 56              # 轴径 56 的平键和键槽 GB/T 1095
  python scripts/standards.py tap M8              # 攻丝底孔；细牙写 M10x1
  python scripts/standards.py clearance M8        # 螺钉通孔 GB/T 5277，默认中等装配
  python scripts/standards.py clearance M8 fine
  python scripts/standards.py counterbore M8      # 内六角圆柱头螺钉沉孔 GB/T 152.3
  python scripts/standards.py countersink M8      # 沉头螺钉沉孔 GB/T 152.2
  python scripts/standards.py list                # 有哪些表

在代码里:
  import standards; standards.key(56) -> {"b": 16, "h": 10, "t1": 6.0, "t2": 4.3, ...}

规则：
  * 图上标了具体尺寸时，一律以图纸为准。查表只补图上没写的数。
  * 用了查表结果的特征，evidence 里写清楚"按 GB/T xxxx 查表"，置信度不超过 0.9。
  * 表里 verified=false 的数值按常用手册整理，没逐条对照标准原文，结果会带提醒。
  * 只认 mm。英寸螺纹（1/4-20 UNC）不在这里，查不到就写进 open_questions 问用户。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "standards" / "gb.json"
_cache: dict | None = None


class NotFound(KeyError):
    pass


def _db() -> dict:
    global _cache
    if _cache is None:
        _cache = json.loads(DATA.read_text(encoding="utf-8"))
    return _cache


def _table(name: str) -> dict:
    return _db()[name]


def _result(name: str, row: dict) -> dict:
    t = _table(name)
    out = {**row, "standard": t["title"]}
    if not t.get("verified"):
        out["note"] = "此表数值未逐条对照标准原文，正式零件用前请核对；图上有标注以图纸为准"
    return out


def _size(s: str) -> str:
    """'m8' / 'M8x1.25' / 'M8-6H' -> 'M8'。"""
    m = re.match(r"\s*[Mm]\s*(\d+(?:\.\d+)?)", s)
    if not m:
        raise NotFound(f"看不懂螺纹规格 {s!r}，应该写成 M8 这样")
    v = m.group(1)
    return "M" + (v[:-2] if v.endswith(".0") else v)


def _by_size(name: str, size: str) -> dict:
    t = _table(name)
    key = _size(size)
    for r in t["rows"]:
        if r[0] == key:
            return dict(zip(t["columns"], r))
    have = ", ".join(r[0] for r in t["rows"])
    raise NotFound(f"{t['title']} 里没有 {key}。表里有：{have}")


def key(d: float) -> dict:
    """轴径 d (mm) -> 普通平键和键槽尺寸。"""
    t = _table("key_GB_T_1095")
    for r in t["rows"]:
        row = dict(zip(t["columns"], r))
        if row["d_min"] < d <= row["d_max"]:
            row["shaft_slot_bottom"] = round(d - row["t1"], 3)   # 轴图上常标 d − t1
            row["hub_slot_top"] = round(d + row["t2"], 3)        # 轮毂图上常标 d + t2
            return _result("key_GB_T_1095", row)
    raise NotFound(f"轴径 {d} 超出表的范围（6 < d ≤ 130）")


def tap(thread: str) -> dict:
    """攻丝底孔。粗牙查表；细牙（M10x1）按 d − P 算。"""
    m = re.match(r"\s*[Mm]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)", thread)
    coarse = _by_size("tap_drill_coarse", thread)
    if m and abs(float(m.group(2)) - coarse["pitch"]) > 1e-9:
        d, p = float(m.group(1)), float(m.group(2))
        return {"size": _size(thread), "pitch": p, "drill": round(d - p, 3),
                "standard": "细牙螺纹底孔 ≈ d − P", "note": "细牙按公式算，未查表"}
    return _result("tap_drill_coarse", coarse)


def clearance(size: str, fit: str = "medium") -> dict:
    """螺钉通孔。fit: fine / medium / coarse。"""
    row = _by_size("clearance_GB_T_5277", size)
    if fit not in ("fine", "medium", "coarse"):
        raise NotFound("fit 只能是 fine / medium / coarse")
    return _result("clearance_GB_T_5277", {"size": row["size"], "fit": fit, "diameter": row[fit]})


def counterbore(size: str) -> dict:
    """内六角圆柱头螺钉用沉孔：通孔 d1、沉孔直径 d2、深 t。"""
    return _result("counterbore_GB_T_152_3", _by_size("counterbore_GB_T_152_3", size))


def countersink(size: str) -> dict:
    """沉头螺钉用沉孔（90°）：通孔 d1、锥孔大端 D。"""
    return _result("countersink_GB_T_152_2", _by_size("countersink_GB_T_152_2", size))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = args[0], args[1:]
    try:
        if cmd == "list":
            for name, t in _db().items():
                if not name.startswith("_"):
                    print(f"{name:26s} {t['title']}{'' if t.get('verified') else '  [未核对]'}")
            return 0
        if cmd == "key":
            res = key(float(rest[0]))
        elif cmd == "tap":
            res = tap(rest[0])
        elif cmd == "clearance":
            res = clearance(rest[0], rest[1] if len(rest) > 1 else "medium")
        elif cmd == "counterbore":
            res = counterbore(rest[0])
        elif cmd == "countersink":
            res = countersink(rest[0])
        else:
            print(f"不认识的命令 {cmd}。可用：key tap clearance counterbore countersink list")
            return 2
    except (NotFound, IndexError, ValueError) as e:
        print(f"查不到：{e}")
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
