"""把图上的标注文字解析成结构化规格：孔、螺纹孔、沉孔、沉头孔、锪平、分布圆、槽、倒角、圆角、形位公差。

用法:
  python scripts/callouts.py "2X ⌀4.5 THRU ⌴⌀7 ↧3.5"
  python scripts/callouts.py "4×Φ9 沉孔Φ15深5" "M8x1.25 ↧12" "flatness|0.2"

只做文字解析，不判断它标在哪个结构上。输出里的 feature_hint 是写进特征表 hole 特征的字段
（diameter、depth、cbore、csink、bolt_circle），长度单位和图纸一致，不换算。
认不出的写法返回 kind = "unknown"，不要硬凑。

支持的写法（ASME Y14.5 / ISO 129 / GB/T 4458.4 常见形式）:
  数量      4X  4×  4x                     通孔      THRU  通孔  通
  直径      ⌀ Ø Φ φ %%c                    深度      ↧3.5  DEEP  深5  ▽5
  沉孔      ⌴⌀7 ↧3.5   沉孔Φ15深5           锪平      ⌴⌀68 SF ↧1  锪平Φ20
  沉头      ⌵⌀10 X 90°  沉头Φ10×90°         分布圆    EQ SP ON ⌀60 B.C.  均布  PCD80
  螺纹      M8  M8x1.25  M6-6H              槽        7 X 29 X 2.5 DEEP
  倒角      C0.5  0.5 X 45°                 圆角      R5  3X R1.5
  公差      ±0.05  +0.1/-0.05  H7           形位公差  flatness|0.2   parallelism|0.2|B
  小数逗号  4,5 → 4.5
"""
from __future__ import annotations

import json
import re
import sys

_NUM = r"(\d+(?:\.\d+)?|\.\d+)"
_GDT = {"flatness", "straightness", "circularity", "roundness", "cylindricity", "parallelism",
        "perpendicularity", "angularity", "position", "concentricity", "coaxiality", "symmetry",
        "runout", "circular runout", "total runout", "profile", "profile of a line",
        "profile of a surface", "平面度", "直线度", "圆度", "圆柱度", "平行度", "垂直度", "倾斜度",
        "位置度", "同轴度", "对称度", "圆跳动", "全跳动", "线轮廓度", "面轮廓度"}


def normalize(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)                     # 小数逗号
    t = re.sub(r"%%[cC]|[ØΦφ⌀]", "⌀", t)
    t = t.replace("×", "X").replace("＊", "X")
    t = re.sub(r"(?<=\d)\s*[xX]\s*(?=[⌀M\d.])", " X ", t)        # 4x⌀9 / 7x29
    t = re.sub(r"^(\d+)\s*X\s*", r"\1X ", t)
    t = t.replace("深度", "↧").replace("深", "↧").replace("DEEP", "↧D")
    t = re.sub(r"[▽▼↓⊽]", "↧", t)                                  # 深度符号的各种字形
    t = re.sub(r"L_J|└┘|⊔|⌴", "⌴", t)                               # 沉孔 / 锪平
    t = re.sub(r"[∨]|(?<![A-Z])V(?=\s*⌀)", "⌵", t)                 # 沉头
    t = re.sub(r"\bC'?BORE\b", "⌴", t, flags=re.I)
    t = re.sub(r"\bSPOT\s*FACE\b|\bSPOTFACE\b", "⌴SF", t, flags=re.I)
    t = re.sub(r"\bC'?SINK\b|\bCSK\b", "⌵", t, flags=re.I)
    t = t.replace("沉孔", "⌴").replace("锪平", "⌴SF").replace("沉头", "⌵")
    t = t.replace("通孔", "THRU").replace("通", "THRU")
    t = re.sub(r"EQUALLY SPACED|EQ\.? SP\.?|均布", "EQS", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def _tol(rest: str) -> tuple[dict | None, str]:
    m = re.match(r"\s*±\s*" + _NUM, rest)
    if m:
        return {"plus_minus": float(m.group(1))}, rest[m.end():]
    m = re.match(r"\s*\+\s*" + _NUM + r"\s*/?\s*-\s*" + _NUM, rest)
    if m:
        return {"upper": float(m.group(1)), "lower": -float(m.group(2))}, rest[m.end():]
    m = re.match(r"\s*([A-Za-z]{1,2}\d{1,2})(?![\d.])", rest)
    if m and not m.group(1).upper().startswith(("THRU", "SF", "EQ", "BC", "PCD")):
        return {"fit": m.group(1)}, rest[m.end():]
    return None, rest


def parse(text: str) -> dict:
    raw = text
    t = normalize(text)
    out: dict = {"text": raw, "kind": "unknown"}
    if not t:
        return out
    m = re.fullmatch(r"\((.+)\)", t)          # (35)：参考尺寸
    if m:
        inner = parse(m.group(1))
        if inner["kind"] != "unknown":
            return {**inner, "text": raw, "reference": True,
                    "note": "括号里是参考尺寸，不是建模依据，通常可以由别的尺寸推出"}

    # 形位公差框：flatness|0.2|B，可能多行
    if "|" in t:
        rows = []
        for line in re.sub(r"(?<=\d),(?=\d)", ".", raw).splitlines():
            parts = [p.strip() for p in line.split("|")]
            if parts and parts[0].lower() in _GDT:
                val = re.search(_NUM, parts[1]) if len(parts) > 1 else None
                rows.append({"characteristic": parts[0].lower(), "tolerance": float(val.group(1)) if val else None,
                             "diameter_zone": len(parts) > 1 and parts[1].startswith("⌀"),
                             "datums": [p for p in parts[2:] if p]})
        if rows:
            return {"text": raw, "kind": "gdt", "frames": rows,
                    "note": "形位公差不改变公称几何，不写进特征表的尺寸"}

    # 总注：作用于图上所有没单独标的棱边
    m = (re.search(r"ALL\s+CHAMFERS?\s*=?\s*" + _NUM + r"\s*(?:MM)?\s*X\s*45", t, re.I)
         or re.search(r"未注倒角\s*C?\s*" + _NUM, t))
    if m:
        return {**out, "kind": "general_note", "chamfer": {"size": float(m.group(1)), "angle": 45.0},
                "note": "总注：所有没单独标注的棱边都倒这个角。逐条确认哪些边算'棱边'，不要漏掉也不要倒到功能面上"}
    m = (re.search(r"(?:FILLETS?\s*(?:AND|&)\s*ROUNDS?|ALL\s+(?:FILLETS|ROUNDS))\s*=?\s*R\s*" + _NUM, t, re.I)
         or re.search(r"未注圆角\s*R\s*" + _NUM, t))
    if m:
        return {**out, "kind": "general_note", "fillet": {"radius": float(m.group(1))},
                "note": "总注：所有没单独标注的内外圆角（铸件常见）都是这个半径"}
    # 后置数量 3 PLCS / 4 PLACES / 3处；件数 2 REQD（要做几件，和几何无关）；IN LINE（几个孔同轴）
    trailing = None
    m = re.search(r"\s*(\d+)\s*(?:PLCS|PLACES|PL|处)\.?\s*$", t, re.I)
    if m:
        trailing, t = int(m.group(1)), t[:m.start()].strip()
    m = re.search(r"\s*(\d+)\s*REQ'?D\.?\s*$", t, re.I)
    if m:
        out["parts_required"], t = int(m.group(1)), t[:m.start()].strip()
    if re.search(r"\s*IN\s+LINE\s*$", t, re.I):
        out["in_line"], t = True, re.sub(r"\s*IN\s+LINE\s*$", "", t, flags=re.I)
        out["note"] = "IN LINE：这几个孔同轴，一起钻"
    if trailing:
        t = f"{trailing}X " + t if not re.match(r"^\d+X", t) else t
    # 倒角 2 X 45° CHAMFER / 6mm X 45° CHAMFER / 3×45°CHAM：第一个数是倒角尺寸，不是数量
    m = re.fullmatch(r"(?:(\d+)X\s+(?=\S+\s*(?:MM)?\s*X\s*45))?" + _NUM + r"\s*(?:MM)?\s*X\s*45\s*°?\s*(?:CHAMFER|CHAM\.?)?", t, re.I)
    if m:
        return {**out, "kind": "chamfer", "count": int(m.group(1)) if m.group(1) else 1,
                "size": float(m.group(2)), "angle": 45.0}
    # 极限尺寸 ⌀.310 - .312 / ⌀1.4590/1.4585 / ⌀31.82-31.75：两个很接近的数是上下限
    m = re.fullmatch(r"(⌀)?\s*" + _NUM + r"\s*[-/]\s*" + _NUM, t)
    if m:
        a, b = float(m.group(2)), float(m.group(3))
        if abs(a - b) <= 0.05 * max(a, b):
            mean = round((a + b) / 2, 6)
            return {**out, "kind": "diameter" if m.group(1) else "dimension",
                    ("diameter" if m.group(1) else "value"): mean, "limits": sorted([a, b]),
                    **({"feature_hint": {"diameter": mean}} if m.group(1) else {}),
                    "note": "极限尺寸：给的是上下限，建模取中间值"}
    # 球面切口 ⌀3 HEMISPHERICAL CUT
    m = re.fullmatch(r"⌀\s*" + _NUM + r"\s*(?:HEMI)?SPHERICAL(?:\s*CUT)?", t, re.I)
    if m:
        return {**out, "kind": "spherical_cut", "diameter": float(m.group(1)),
                "note": "半球形凹坑：用 revolve 切除，轮廓是半圆"}

    # 倒角 1 X 45°（要在"数量 X"之前判断，不然 1 X 被当成数量）
    m = re.fullmatch(_NUM + r"\s*X\s*45\s*°?", t)
    if m:
        return {**out, "kind": "chamfer", "count": 1, "size": float(m.group(1)), "angle": 45.0}
    # 单独的分布圆：PCD80 / ⌀80 B.C.
    m = re.fullmatch(r"(?:PCD\s*⌀?\s*" + _NUM + r"|(?:ON\s*)?⌀\s*" + _NUM + r"(?:\s*±\s*" + _NUM +
                     r")?\s*(?:B\.?C\.?|PCD))", t)
    if m:
        return {**out, "kind": "bolt_circle", "value": float(m.group(1) or m.group(2)),
                "note": "分布圆直径，孔的数量和直径在另一个标注里"}
    # 六角对边 10 A/F
    m = re.fullmatch(_NUM + r"\s*(?:±\s*" + _NUM + r"\s*)?A/F", t)
    if m:
        return {**out, "kind": "across_flats", "value": float(m.group(1)),
                "note": "六角或两平面的对边距离"}
    count = 1
    m = re.match(r"^(\d+)X\s*", t)
    if m:
        count, t = int(m.group(1)), t[m.end():]
    out["count"] = count
    # 阵列 (2X5)：行 × 列
    grid = re.search(r"\(\s*(\d+)\s*X\s*(\d+)\s*\)", t)
    if grid:
        out["grid"] = {"rows": int(grid.group(1)), "columns": int(grid.group(2))}
        t = (t[:grid.start()] + t[grid.end():]).strip()
    # "30 × 40 ↧4" 被当成了数量 30：数量后面直接是"数 ↧数"，其实是矩形凹槽 宽 × 长 × 深
    m = re.fullmatch(_NUM + r"\s*↧D?\s*" + _NUM, t)
    if m and count > 1:
        return {**out, "count": 1, "kind": "slot",
                "slot": {"width": float(count), "length": float(m.group(1)), "depth": float(m.group(2))},
                "note": "写法是 宽 × 长 ↧深。没有圆角时是矩形凹槽；有半圆端时是腰形槽"}

    # 倒角 C0.5 / 0.5 X 45°，可带公差
    m = re.match(r"C\s*" + _NUM, t) or re.match(_NUM + r"\s*X\s*45\s*°?", t)
    if m:
        tol, rest = _tol(t[m.end():])
        if not rest.strip():
            return {**out, "kind": "chamfer", "size": float(m.group(1)), "angle": 45.0,
                    **({"tolerance": tol} if tol else {})}
    # 高度 / 台阶标注 H 12（cadsy 等生成器在俯视图里标凸台、台阶高度）
    m = re.match(r"H\s+" + _NUM, t)
    if m:
        tol, rest = _tol(t[m.end():])
        if not rest.strip():
            return {**out, "kind": "height", "value": float(m.group(1)), **({"tolerance": tol} if tol else {}),
                    "note": "高度标注：这个面相对基准面的高度，看是哪个视图里标的"}
    t = re.sub(r"^SLOT\s*", "", t, flags=re.I)
    if re.fullmatch(r"S?R", t):
        return {**out, "kind": "fillet", "radius": None,
                "note": "只写 R 不写数：半径由别的几何决定（相切、和另一段同心等），不要猜数"}
    m = re.fullmatch(_NUM + r"\s*X\s*" + _NUM + r"\s*KEYWAYS?(?:\s*EQS)?", t, re.I)
    if m:
        return {**out, "kind": "keyway", "keyway": {"width": float(m.group(1)), "depth": float(m.group(2))},
                "equally_spaced": "EQS" in t,
                "note": "键槽 宽 × 深；深度从哪个面量起要看图（孔壁还是轴面）"}
    # 圆角 R5 ±0.05
    m = re.match(r"^S?R\s*" + _NUM, t)
    if m:
        tol, rest = _tol(t[m.end():])
        return {**out, "kind": "sphere_radius" if t.startswith("SR") else "fillet", "radius": float(m.group(1)),
                **({"tolerance": tol} if tol else {})}
    # 槽 7 X 29 X 2.5 ↧D（宽 × 长 × 深）
    m = re.fullmatch(_NUM + r"\s*X\s*" + _NUM + r"(?:\s*X\s*" + _NUM + r")?\s*(↧D?\s*" + _NUM + r"?|THRU)?", t)
    if m and (m.group(3) or m.group(4)):
        slot = {"width": float(m.group(1)), "length": float(m.group(2))}
        if m.group(4) == "THRU":
            slot["depth"] = "through_all"
        elif m.group(5):
            slot["depth"] = float(m.group(5))
        elif m.group(3):
            slot["depth"] = float(m.group(3))
        return {**out, "kind": "slot", "slot": slot,
                "note": "长度是槽的总长（含两端半圆）还是中心距，要看图上尺寸线落在哪里"}

    hint: dict = {}
    # 螺纹 M8 / M8x1.25 / M6-6H
    m = re.match(r"^M\s*" + _NUM + r"(?:\s*X\s*" + _NUM + r")?(?:\s*-\s*(\d[A-Za-z]{1,2}))?", t)
    mi = re.match(r"^(#\d+|\d+-\d+/\d+|\d+/\d+|\d*\.\d+|\d+)\s*-\s*(\d+)\s*(UNC|UNF|UNEF|UNS|UN)"
                  r"(?:\s*-\s*(\d[AB]))?", t, re.I)
    if mi and not m:
        size = mi.group(1)
        if size.startswith("#"):
            nominal = 0.060 + 0.013 * int(size[1:])
        elif "/" in size:
            whole, _, frac = size.rpartition("-")
            n, d = frac.split("/")
            nominal = (float(whole) if whole else 0.0) + int(n) / int(d)
        else:
            nominal = float(size)
        out["kind"] = "threaded_hole"
        out["thread"] = {"size": f"{size}-{mi.group(2)} {mi.group(3).upper()}", "nominal_diameter": round(nominal, 4),
                         "threads_per_inch": int(mi.group(2))}
        if mi.group(4):
            out["thread"]["tolerance_class"] = mi.group(4)
        rest = t[mi.end():]
        out["note"] = "英制螺纹：尺寸单位是英寸。特征表写底孔直径（查表），公称直径和牙数写进 thread"
    elif m:
        out["kind"] = "threaded_hole"
        out["thread"] = {"size": f"M{m.group(1)}", "nominal_diameter": float(m.group(1))}
        if m.group(2):
            out["thread"]["pitch"] = float(m.group(2))
        if m.group(3):
            out["thread"]["tolerance_class"] = m.group(3)
        rest = t[m.end():]
        out["note"] = "特征表写螺纹底孔直径（查 standards.py），公称直径写进 thread"
    else:
        m = re.match(r"^⌀\s*" + _NUM, t)
        if not m:
            m2 = re.fullmatch(_NUM, t)
            if m2:
                return {**out, "kind": "dimension", "value": float(m2.group(1))}
            tol, rest = _tol(t[m2.end():]) if (m2 := re.match(_NUM, t)) else (None, t)
            if m2 and not rest.strip():
                return {**out, "kind": "dimension", "value": float(m2.group(1)), "tolerance": tol}
            return out
        out["kind"] = "hole"
        out["diameter"] = float(m.group(1))
        hint["diameter"] = out["diameter"]
        rest = t[m.end():]
    tol, rest = _tol(rest)
    if tol:
        out["tolerance"] = tol

    def take(pattern):
        nonlocal rest
        mm = re.match(r"\s*" + pattern, rest)
        if mm:
            rest = rest[mm.end():]
        return mm

    while rest.strip():
        if take(r"THRU(?: ALL)?"):
            out["depth"] = "through_all"
        elif (mm := take(r"↧D?\s*" + _NUM)):
            target = out.get("cbore") or out.get("spotface")
            if target is not None and "depth" not in target:
                target["depth"] = float(mm.group(1))
            elif "depth" not in out:
                out["depth"] = float(mm.group(1))
        elif (mm := take(r"⌴\s*(SF)?\s*⌀?\s*" + _NUM + r"(?:\s*(SF))?")):
            key = "spotface" if (mm.group(1) or mm.group(3)) else "cbore"
            out[key] = {"diameter": float(mm.group(2))}
            t2, rest = _tol(rest)
            if t2:
                out[key]["tolerance"] = t2
        elif (mm := take(r"⌵\s*⌀\s*" + _NUM + r"(?:\s*X\s*" + _NUM + r"\s*°)?")):
            out["csink"] = {"diameter": float(mm.group(1)), "angle": float(mm.group(2)) if mm.group(2) else 90.0}
        elif take(r"EQS"):
            out["equally_spaced"] = True
        elif (mm := take(r"(?:ON\s*)?⌀\s*" + _NUM + r"(?:\s*±\s*" + _NUM + r")?\s*(?:B\.?C\.?|PCD)")):
            out["bolt_circle"] = {"pcd": float(mm.group(1)), "count": count}
        elif (mm := take(r"PCD\s*⌀?\s*" + _NUM)):
            out["bolt_circle"] = {"pcd": float(mm.group(1)), "count": count}
        elif (mm := take(r"±\s*" + _NUM)) or (mm := take(r"\+\s*" + _NUM + r"\s*/?\s*-\s*" + _NUM)):
            # 公差跟在最近的那个数后面（沉孔深度、孔深、沉孔直径）
            tol_ = ({"plus_minus": float(mm.group(1))} if mm.group(0).lstrip().startswith("±")
                    else {"upper": float(mm.group(1)), "lower": -float(mm.group(2))})
            target = out.get("spotface") or out.get("cbore") or out.get("csink")
            (target if target is not None else out).setdefault("tolerance", tol_)
        elif take(r"SF"):
            if "cbore" in out:
                out["spotface"] = out.pop("cbore")
        elif take(r"[,;]"):
            continue
        else:
            out["unparsed"] = rest.strip()
            break

    if out["kind"] == "hole" and out["count"] == 1 and not any(
            k in out for k in ("depth", "cbore", "spotface", "csink", "bolt_circle", "grid")):
        out["kind"] = "diameter"   # 单独的 ⌀80：可能是孔，也可能是轴、凸台的外径，看图上标在哪
    if out["kind"] in ("hole", "diameter"):
        if "depth" in out:
            hint["depth"] = out["depth"]
        if "cbore" in out:
            hint["cbore"] = {k: v for k, v in out["cbore"].items() if k in ("diameter", "depth")}
        if "spotface" in out:
            hint["cbore"] = {k: v for k, v in out["spotface"].items() if k in ("diameter", "depth")}
            out["note"] = "锪平按很浅的沉孔建；深度没标时只是刮平表面，要问清楚"
        if "csink" in out:
            hint["csink"] = out["csink"]
        if "bolt_circle" in out:
            hint["bolt_circle"] = {"pcd": out["bolt_circle"]["pcd"], "count": count}
        if "grid" in out:
            out["note"] = f"{count} 个孔排成 {out['grid']['rows']} 行 × {out['grid']['columns']} 列，孔距看图上的尺寸"
        out["feature_hint"] = hint
    return out


def primary_value(parsed: dict) -> float | None:
    for key in ("diameter", "radius", "size", "value"):
        if isinstance(parsed.get(key), (int, float)):
            return float(parsed[key])
    if parsed.get("kind") == "slot":
        return parsed["slot"]["width"]
    if parsed.get("kind") == "threaded_hole":
        return parsed["thread"]["nominal_diameter"]
    return None


def numbers(parsed: dict) -> list[float]:
    """解析结果里的几何数（不含数量、公差）。"""
    out = []
    for key in ("diameter", "radius", "size", "value"):
        if isinstance(parsed.get(key), (int, float)):
            out.append(float(parsed[key]))
    if isinstance(parsed.get("depth"), (int, float)):
        out.append(float(parsed["depth"]))
    for key in ("cbore", "spotface", "csink", "slot"):
        for k, v in (parsed.get(key) or {}).items():
            if k != "angle" and isinstance(v, (int, float)):
                out.append(float(v))
    if parsed.get("bolt_circle"):
        out.append(parsed["bolt_circle"]["pcd"])
    if parsed.get("thread"):
        out.append(parsed["thread"]["nominal_diameter"])
    return out


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    print(json.dumps([parse(t) for t in sys.argv[1:]], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
