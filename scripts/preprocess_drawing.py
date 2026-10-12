"""图纸预处理：从 DWG / DXF / 矢量 PDF 里直接提取文字、尺寸和几何，扫描图则只导出页面图片。
DWG 会先自动转成 DXF（scripts/dwg2dxf.py）。准确度：DWG = DXF > 矢量 PDF > 扫描图。

用法: python preprocess_drawing.py drawing.pdf -o work/extract.json [--dpi 150]

输出 JSON 的关键字段:
  format              vector_pdf | dxf | raster
  pages[].dimension_candidates   看起来像尺寸的文字 (Ø40, R5, M8, 20±0.1, C1 ...)
  pages[].image       渲染出的 PNG，给模型看图用
  dxf.dimensions      DXF 尺寸实体的实测值 (最可靠)
  dxf.circles         所有圆的圆心和直径 (孔位)
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DIM_PATTERN = re.compile(
    r"(?:\d+\s*[x×X]\s*)?"                     # 4x
    r"(?:[ØΦφ⌀]|R|SR|M|C)?\s*"                  # 前缀
    r"(?:\d+-\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?|\.\d+)\"?"   # 数值：12.5 / 12,5 / .375 / 1/4 / 2-1/2
    r"(?:\s*[x×X]\s*\d*\.?\d+)?"               # M8x1.25
    r"(?:\s*(?:±|\+|-)\s*\d*\.?\d+)?"          # 公差 ±0.1 / ±.005
    r"(?:\s*[a-hA-H]\d{1,2})?"                  # h7 / H7
)
PREFIX_HINT = {"Ø": "diameter", "Φ": "diameter", "φ": "diameter", "⌀": "diameter",
               "R": "radius", "SR": "sphere_radius", "M": "thread", "C": "chamfer"}


# ---------------------------------------------------------------- 图纸基础设定线索
# 只给线索和原文，不替 AI 下结论。规则见 references/units-standards.md
SETUP_RULES = [
    # (字段, 值, 正则)  正则不区分大小写
    ("length_unit", "mm", r"单位\s*[:：]?\s*(mm|毫米)|(?:dimensions?|dims?)\s+(?:are\s+)?in\s+(?:mm|millimet)|\bunits?\s*[:：]?\s*mm\b|\(mm\)|\bMMGS\b"),
    ("length_unit", "inch", r"(?:dimensions?|dims?)\s+(?:are\s+)?in\s+inch|\bunits?\s*[:：]?\s*(?:inch|in)\b|单位\s*[:：]?\s*(?:英寸|inch)|\bIPS\b|\binches\b"),
    ("length_unit", "cm", r"单位\s*[:：]?\s*(cm|厘米)|\bunits?\s*[:：]?\s*cm\b"),
    ("length_unit", "m", r"单位\s*[:：]?\s*(m|米)(?![m米])"),
    ("standard", "GB", r"\bGB\s*/?\s*T?\s*\d+|国标"),
    ("standard", "ISO", r"\bISO\s*\d+"),
    ("standard", "ASME", r"\bASME\s*Y14"),
    ("standard", "ANSI", r"\bANSI\b"),
    ("standard", "DIN", r"\bDIN\s*\d+"),
    ("standard", "JIS", r"\bJIS\b"),
    ("projection", "first_angle", r"first\s*angle|第一角|第一分角"),
    ("projection", "third_angle", r"third\s*angle|第三角|第三分角"),
    ("scale", None, r"(?:比例|scale)\s*[:：]?\s*(\d+\s*[:：]\s*\d+)"),
    ("general_tolerance", None, r"(GB\s*/?\s*T\s*1804\s*-?\s*[fmcv]|ISO\s*2768\s*-?\s*[fmcv][HKL]?)"),
    ("general_tolerance", None, r"(\.X{2,3}\s*[±+]\s*\.?\d+)"),
    ("default_chamfer", None, r"未注倒角\s*(C\s*\d+(?:\.\d+)?)"),
    ("default_fillet", None, r"未注圆角\s*(R\s*\d+(?:\.\d+)?)"),
]
_CJK = re.compile(r"[\u4e00-\u9fff]")
_INCH_FRACTION = re.compile(r"^\d+/\d+\"?$|^\d+-\d+/\d+\"?$")
_DECIMAL_COMMA = re.compile(r"^\d+,\d{1,3}$")
_DUAL = re.compile(r"\d+(?:\.\d+)?\s*\[\s*\d*\.\d+\s*\]")


def detect_setup(texts: list[str], numbers: list[str]) -> dict:
    """从全部文字里找单位、标准、投影法、比例等线索。返回 {字段: [{value, text}]} 和数值特征。"""
    hints: dict[str, list] = {}
    for t in texts:
        for field, value, pat in SETUP_RULES:
            m = re.search(pat, t, re.IGNORECASE)
            if m:
                v = value if value is not None else re.sub(r"\s+", "", m.group(1))
                item = {"value": v, "text": t[:120]}
                if item not in hints.setdefault(field, []):
                    hints[field].append(item)
    joined = " ".join(texts)
    cjk = len(_CJK.findall(joined))
    latin = len(re.findall(r"[A-Za-z]{3,}", joined))
    hints["language_guess"] = "zh" if cjk and cjk >= latin else ("en" if latin else "unknown")

    # 数值特征：英寸图常见 .xxx 三位小数和分数；逗号小数点；双单位
    nums = [n.strip() for n in numbers]
    dec = [n for n in nums if re.fullmatch(r"\d*\.\d+", n)]
    three = [n for n in dec if len(n.split(".")[1]) == 3]
    profile = {
        "count": len(nums),
        "leading_dot": sum(n.startswith(".") for n in nums),          # .375 这种写法几乎只在英寸图里出现
        "three_decimals": len(three),
        "fractions": sum(bool(_INCH_FRACTION.match(n)) for n in nums),
        "decimal_comma": sum(bool(_DECIMAL_COMMA.match(n)) for n in nums),
        "dual_dimension_texts": [t[:60] for t in texts if _DUAL.search(t)][:5],
    }
    hints["number_profile"] = profile
    units = {h["value"] for h in hints.get("length_unit", [])}
    if len(units) > 1:
        hints["conflict"] = f"图上同时出现多种单位线索 {sorted(units)}，可能是双单位标注，必须人工确认主单位"
    elif not units:
        lean = "inch" if (profile["leading_dot"] or profile["fractions"]) else None
        hints["conflict"] = ("没有找到明确的单位标注。" +
                             (f"数值写法偏向 {lean}（有 .xxx 或分数）。" if lean else "") +
                             "单位不能猜：写进 open_questions，请用户确认")
    return hints


def classify_token(text: str) -> str | None:
    t = text.strip()
    if not t or not DIM_PATTERN.fullmatch(t):
        return None
    for p in ("SR", "Ø", "Φ", "φ", "⌀", "R", "M", "C"):
        if re.sub(r"^\d+\s*[x×X]\s*", "", t).startswith(p):
            return PREFIX_HINT[p]
    return "linear"


def from_pdf(path: Path, out_dir: Path, dpi: int) -> dict:
    import pymupdf

    doc = pymupdf.open(path)
    pages = []
    vector_pages = 0
    notext_pages = 0
    for i, page in enumerate(doc):
        words = page.get_text("words")  # x0,y0,x1,y1,word,block,line,wno
        lines = {}
        for w in words:
            lines.setdefault((w[5], w[6]), []).append(w)
        text_items = []
        for ws in lines.values():
            txt = " ".join(w[4] for w in ws)
            bbox = [min(w[0] for w in ws), min(w[1] for w in ws),
                    max(w[2] for w in ws), max(w[3] for w in ws)]
            text_items.append({"text": txt, "bbox": [round(b, 1) for b in bbox]})
        dims = []
        for w in words:
            kind = classify_token(w[4])
            if kind:
                dims.append({"text": w[4], "kind": kind, "bbox": [round(b, 1) for b in w[:4]]})
        n_paths = len(page.get_drawings())
        if n_paths > 20 and text_items:
            vector_pages += 1
        elif n_paths > 20:
            notext_pages += 1  # 有矢量线但没有文字层：AutoCAD 用 SHX 字体打印的 PDF 常见
        img = out_dir / f"{path.stem}_p{i + 1}.png"
        page.get_pixmap(dpi=dpi).save(img)
        pages.append({"page": i + 1, "size_pt": [page.rect.width, page.rect.height],
                      "vector_path_count": n_paths, "text_items": text_items,
                      "dimension_candidates": dims, "image": str(img)})
    all_texts = [ti["text"] for p in pages for ti in p["text_items"]]
    all_nums = [w for p in pages for w in (d["text"] for d in p["dimension_candidates"])]
    all_nums += [w[4] for page in doc for w in page.get_text("words")
                 if re.fullmatch(r"\d*[.,]?\d+(?:/\d+)?\"?|\d+-\d+/\d+\"?", w[4])]
    if vector_pages == len(pages):
        fmt = "vector_pdf"
        note = "矢量 PDF：尺寸数值以 dimension_candidates 为准，看图用于理解视图关系。"
    elif vector_pages + notext_pages == len(pages) and notext_pages:
        fmt = "vector_pdf_notext"
        note = ("矢量 PDF，但没有文字层（文字被打印成线条，AutoCAD SHX 字体常见）。"
                "线条几何是精确的，尺寸数字只能看 image 读，读出的数要和几何比例核对。置信度上限 0.9。")
    else:
        fmt = "raster"
        note = "疑似扫描件：文字/线条提取不到，只能看 image 读图，所有置信度上限 0.85。"
    return {"format": fmt, "note": note, "setup_hints": detect_setup(all_texts, all_nums), "pages": pages}


DIMTYPE = {0: "linear", 1: "aligned", 2: "angular", 3: "diameter", 4: "radius", 5: "angular_3p", 6: "ordinate"}
# AutoCAD 控制码：%%c = Ø，%%d = °，%%p = ±
_CTRL = [("%%c", "Ø"), ("%%C", "Ø"), ("%%d", "°"), ("%%D", "°"), ("%%p", "±"), ("%%P", "±"),
         ("\\U+2205", "Ø"), ("\\U+00B0", "°"), ("\\U+00B1", "±")]


def decode_cad_text(t: str) -> str:
    for a, b in _CTRL:
        t = t.replace(a, b)
    t = re.sub(r"Ø\s*Ø", "Ø", t)  # 直径尺寸自带 Ø，文字里再写 %%c 会叠成 ØØ
    return t.strip()


_STACK = re.compile(r"([+-]?\d*\.?\d+)\s*\^\s*([+-]?\d*\.?\d+)")
_NUM = r"(\d+(?:\.\d+)?)"


def parse_tolerance(text: str) -> dict | None:
    """解析尺寸公差。支持 16±0.037、61 0^-0.2（AutoCAD 堆叠）、Ø56+0.025^0、40h7。
    建模用公称尺寸，公差只记录。"""
    t = text.replace(" ", "")
    m = re.search(_NUM + r"±(\d*\.?\d+)", t)
    if m:
        v = float(m.group(2))
        return {"nominal": float(m.group(1)), "upper": v, "lower": -v}
    m = re.search(_NUM + r"([+-]?\d*\.?\d+)\^([+-]?\d*\.?\d+)", t)
    if m:
        a, b = float(m.group(2)), float(m.group(3))
        return {"nominal": float(m.group(1)), "upper": max(a, b), "lower": min(a, b)}
    m = re.search(_NUM + r"([a-hA-H][a-z]?\d{1,2})$", t)
    if m:
        return {"nominal": float(m.group(1)), "fit": m.group(2)}
    return None


def pretty_stack(text: str) -> str:
    """把 AutoCAD 堆叠公差 '0^-0.2' 写成 '(+0/-0.2)'，方便人和 AI 读。"""
    def fmt(m):
        a, b = float(m.group(1)), float(m.group(2))
        hi, lo = max(a, b), min(a, b)
        return f"({hi:+g}/{lo:+g})"
    return _STACK.sub(fmt, text)


def _r(v, n=4):
    return [round(c, n) for c in list(v)[:2]]


def _dim_info(e) -> dict:
    """尺寸实体：类型、测量值、显示值（考虑 DIMLFAC 比例因子和文字覆盖）、位置。"""
    kind = DIMTYPE.get(e.dimtype & 7, str(e.dimtype))
    try:
        meas = e.get_measurement()
        meas = float(meas) if isinstance(meas, (int, float)) else None
    except Exception:  # noqa: BLE001
        meas = None
    lfac = 1.0
    try:
        lfac = float(e.override().get("dimlfac", 1.0) or 1.0)
    except Exception:  # noqa: BLE001
        pass
    if meas is not None and kind == "radius":
        pass  # 半径尺寸的测量值就是半径
    shown = None
    if meas is not None:
        shown = meas if kind.startswith("angular") else meas * lfac
    override = decode_cad_text(e.dxf.get("text", "") or "")
    # 文字覆盖里 "<>" 代表测量值；完全替换成别的数时，以覆盖文字为准，并标记出来核对
    text = override.replace("<>", f"{shown:g}") if override and shown is not None else override
    item = {"kind": kind, "measurement": round(meas, 6) if meas is not None else None,
            "dimlfac": lfac, "value_shown": round(shown, 6) if shown is not None else None,
            "text": text or (f"{shown:g}" if shown is not None else ""),
            "layer": e.dxf.layer, "at": _r(e.dxf.get("text_midpoint", e.dxf.get("defpoint", (0, 0))), 2)}
    if override and "<>" not in override and re.search(r"\d", override):
        item["override_replaces_value"] = True  # 标注文字被手改过，测量值不一定可信
    if kind in ("diameter", "radius") and not re.search(r"[ØR]", item["text"]):
        item["text"] = ("Ø" if kind == "diameter" else "R") + item["text"]
    # 最可靠：尺寸渲染块里的 MTEXT，就是图上实际显示的文字
    try:
        blk = e.get_geometry_block()
        shown_txt = [decode_cad_text(x.plain_text()) for x in blk if x.dxftype() == "MTEXT"] if blk else []
        shown_txt += [decode_cad_text(x.dxf.text) for x in blk if x.dxftype() == "TEXT"] if blk else []
        if shown_txt:
            raw = " ".join(t for t in shown_txt if t)
            item["displayed_text"] = pretty_stack(raw)
            tol = parse_tolerance(raw)
            if tol:
                item["tolerance"] = tol
    except Exception:  # noqa: BLE001
        pass
    return item


def _read_table(e) -> list[list[str]]:
    """AutoCAD 表格（ACAD_TABLE）：单元格文字在表格自己的图形块里，按位置拼成行。
    齿轮参数表、明细表常用这种表格。"""
    try:
        blk = e.doc.blocks.get(e.get_block_name())
    except Exception:  # noqa: BLE001
        return []
    cells = []
    for x in blk or []:
        if x.dxftype() in ("MTEXT", "TEXT"):
            txt = decode_cad_text(x.plain_text() if x.dxftype() == "MTEXT" else x.dxf.text)
            if txt:
                p = x.dxf.insert
                cells.append((-p.y, p.x, txt))
    cells.sort()
    rows, last_y = [], None
    for y, _x, txt in cells:
        if last_y is None or abs(y - last_y) > 1.5:  # 同一行的 y 差不多
            rows.append([])
            last_y = y
        rows[-1].append(txt)
    return rows


GEAR_KEYS = {"z": ("齿数", "z"), "m": ("模数", "法向模数", "端面模数", "m", "mn"),
             "alpha": ("齿形角", "压力角", "α", "αn"), "ha": ("齿顶高系数", "ha*", "han*"),
             "c": ("顶隙系数", "c*", "cn*"), "x": ("变位系数", "径向变位系数", "x", "xn"),
             "beta": ("螺旋角", "β"), "accuracy": ("精度等级",)}


def parse_gear_table(rows: list[list[str]]) -> dict | None:
    """从参数表里认出齿轮参数。返回 None 表示不是齿轮表。"""
    out = {}
    for row in rows:
        cells = [c.strip() for c in row]
        for key, names in GEAR_KEYS.items():
            if key in out:
                continue
            if any(c in names for c in cells[:-1]) and len(cells) >= 2:
                val = cells[-1]
                if key == "accuracy":
                    out[key] = val
                    continue
                m = re.search(r"-?\d+(?:\.\d+)?", val)
                if m:
                    out[key] = float(m.group())
    if "z" in out and "m" in out:
        z, m = out["z"], out["m"]
        x, ha, c = out.get("x", 0.0), out.get("ha", 1.0), out.get("c", 0.25)
        out["derived_mm"] = {"分度圆 d = m·z": m * z,
                             "齿顶圆 da = m(z + 2ha* + 2x)": m * (z + 2 * ha + 2 * x),
                             "齿根圆 df = m(z − 2ha* − 2c* + 2x)": m * (z - 2 * ha - 2 * c + 2 * x)}
        out["note"] = "用 derived_mm 和图上的 Ø 尺寸、圆核对。对得上，说明单位和参数都读对了"
        return out
    return None


def _walk(entities, sink, layout: str, depth: int = 0):
    """遍历实体，展开块（INSERT），读块属性。标题栏一般就在块里。"""
    for e in entities:
        t = e.dxftype()
        sink["counts"][t] = sink["counts"].get(t, 0) + 1
        if t == "INSERT":
            for a in getattr(e, "attribs", []):
                txt = decode_cad_text(a.dxf.text)
                if txt:
                    sink["texts"].append({"text": txt, "tag": a.dxf.tag, "block": e.dxf.name,
                                          "layout": layout, "at": _r(a.dxf.insert, 2)})
            if depth < 4:
                try:
                    _walk(e.virtual_entities(), sink, layout, depth + 1)
                except Exception:  # noqa: BLE001
                    pass
        elif t == "ACAD_TABLE":
            rows = _read_table(e)
            if rows:
                sink["tables"].append({"rows": rows, "layout": layout, "at": _r(e.dxf.insert, 2)})
        elif t == "DIMENSION":
            d = _dim_info(e)
            d["layout"] = layout
            sink["dims"].append(d)
        elif t in ("TEXT", "MTEXT", "ATTDEF"):
            raw = e.plain_text() if t == "MTEXT" else e.dxf.get("text", "")
            txt = decode_cad_text(raw)
            if txt:
                sink["texts"].append({"text": txt, "layout": layout, "at": _r(e.dxf.insert, 2)})
        elif t == "CIRCLE":
            sink["circles"].append({"center": _r(e.dxf.center), "diameter": round(2 * e.dxf.radius, 4),
                                    "layer": e.dxf.layer, "layout": layout})
        elif t == "ARC":
            sink["arcs"].append({"center": _r(e.dxf.center), "radius": round(e.dxf.radius, 4),
                                 "start_angle": round(e.dxf.start_angle, 2), "end_angle": round(e.dxf.end_angle, 2),
                                 "layer": e.dxf.layer})
        if t in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "SPLINE", "ELLIPSE"):
            lay = sink["layers"].setdefault(e.dxf.layer, {"entities": 0, "linetypes": set()})
            lay["entities"] += 1
            lay["linetypes"].add(e.dxf.get("linetype", "BYLAYER"))


def render_dxf(doc, out_png: Path) -> str | None:
    """把模型空间渲染成 PNG，给 AI 看视图关系。需要 matplotlib，没有就跳过。"""
    try:
        from ezdxf.addons.drawing import matplotlib as mpl_draw  # noqa: PLC0415
        mpl_draw.qsave(doc.modelspace(), str(out_png), bg="#FFFFFF", dpi=200)
        return str(out_png)
    except Exception:  # noqa: BLE001
        return None


def from_dxf(path: Path, out_dir: Path | None = None, converted_from: str | None = None) -> dict:
    import ezdxf  # noqa: PLC0415
    from ezdxf import recover  # noqa: PLC0415

    try:
        doc = ezdxf.readfile(path)
    except Exception:  # noqa: BLE001  文件有小错误时用 recover 模式读
        doc, _ = recover.readfile(path)
    sink = {"counts": {}, "dims": [], "texts": [], "circles": [], "arcs": [], "layers": {}, "tables": []}
    for layout in doc.layouts:
        _walk(layout, sink, layout.name)
    for name, lay in sink["layers"].items():
        lts = set()
        for lt in lay["linetypes"]:
            if lt.upper() == "BYLAYER":  # 线型跟随图层，查图层本身的线型
                try:
                    lt = doc.layers.get(name).dxf.linetype
                except Exception:  # noqa: BLE001
                    pass
            lts.add(lt)
        lay["linetypes"] = sorted(lts)
        if any(k in " ".join(lts).upper() for k in ("CENTER", "DASHDOT", "点划")):
            lay["looks_like"] = "中心线"
        elif any(k in " ".join(lts).upper() for k in ("HIDDEN", "DASHED", "虚线")):
            lay["looks_like"] = "虚线（不可见轮廓）"

    units = {0: "unitless", 1: "inch", 4: "mm", 5: "cm", 6: "m"}.get(doc.header.get("$INSUNITS", 0), "unknown")
    measurement = {0: "imperial", 1: "metric"}.get(doc.header.get("$MEASUREMENT", -1), "unknown")
    table_texts = [" ".join(r) for tb in sink["tables"] for r in tb["rows"]]
    hints = detect_setup([t["text"] for t in sink["texts"]] + table_texts,
                         [d["text"] for d in sink["dims"] if d["text"]])
    hints["dxf_header"] = {"$INSUNITS": units, "$MEASUREMENT": measurement,
                           "note": "$INSUNITS 常被导出程序乱填，和标题栏文字冲突时以标题栏为准"}
    if not hints.get("length_unit") and units in ("mm", "inch", "cm", "m"):
        agree = (units == "inch") == (measurement == "imperial") if measurement != "unknown" else True
        hints["conflict"] = (f"图上文字没写单位。DXF 文件头 $INSUNITS={units}、$MEASUREMENT={measurement}"
                             + ("，两者一致" if agree else "，两者矛盾") +
                             "。文件头可以作为依据，但置信度不超过 0.85，必须请用户确认。"
                             "有齿轮参数表时，用 m·z 和分度圆直径核对，对得上就能确认单位")
    gear = None
    for tb in sink["tables"]:
        gear = parse_gear_table(tb["rows"]) or gear
    if gear:
        hints["gear"] = gear
    if any(d["dimlfac"] != 1.0 for d in sink["dims"]):
        hints["dimlfac_note"] = "有尺寸带 DIMLFAC 比例因子（视图按比例画）：以 value_shown 为准，不要用 measurement"
    png = render_dxf(doc, (out_dir or path.parent) / f"{path.stem}_dxf.png")
    result = {
        "format": "dxf", "units": units, "setup_hints": hints,
        "note": ("DXF/DWG：尺寸以 dimensions[].displayed_text 为准，它就是图上实际显示的文字；"
                 "没有时用 value_shown（已乘 DIMLFAC）。两者应该一致，不一致要核对。"
                 "override_replaces_value=true 的尺寸文字被手改过，要和几何核对。"
                 "circles 是图上所有圆的精确圆心和直径，用来定孔位。image 是渲染图，用来看视图关系。"),
        "image": png,
        "dxf": {"entity_counts": sink["counts"], "layers": sink["layers"], "dimensions": sink["dims"],
                "tables": sink["tables"], "texts": sink["texts"],
                "circles": sink["circles"], "arcs": sink["arcs"]},
    }
    if converted_from:
        result["converted_from"] = converted_from
    return result


def from_raster(path: Path) -> dict:
    return {"format": "raster", "note": "图片输入：直接看图读尺寸，所有置信度上限 0.85。"
            "先看 views 里的 overview.png 认出每个视图，再逐个看放大图读尺寸。",
            "setup_hints": {"conflict": "图片无法提取文字：看图找标题栏里的单位、标准和投影符号，找不到就问用户"},
            "pages": [{"page": 1, "image": str(path)}]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("drawing")
    ap.add_argument("-o", "--out", default="work/extract.json")
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()

    src = Path(args.drawing)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower()
    if ext == ".pdf":
        result = from_pdf(src, out.parent, args.dpi)
    elif ext == ".dxf":
        result = from_dxf(src, out.parent)
    elif ext == ".dwg":
        import dwg2dxf  # noqa: PLC0415
        conv = dwg2dxf.convert(src, out.parent)
        if not conv["ok"]:
            raise SystemExit("DWG 转 DXF 失败：\n  " + "\n  ".join(conv["errors"]) + "\n" + dwg2dxf.HELP)
        print(f"DWG 已用 {conv['backend']} 转成 {conv['dxf']}")
        result = from_dxf(Path(conv["dxf"]), out.parent, converted_from=f"{src} ({conv['backend']})")
    elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"):
        result = from_raster(src)
    else:
        raise SystemExit(f"不支持的格式 {ext}。支持 .pdf .dxf .dwg 和图片。")
    result["source"] = str(src)
    if result["format"] in ("raster", "vector_pdf_notext"):
        # 看图读数的情况：自动切视图、放大，AI 不用自己裁图（scripts/split_views.py）
        import split_views  # noqa: PLC0415
        pages = result.get("pages", [])
        for p in pages:
            if p.get("image"):
                vd = out.parent / ("views" if len(pages) == 1 else f"views_p{p['page']}")
                try:
                    r = split_views.split(p["image"], str(vd))
                    p["views"] = {"overview": r["overview"], "count": len(r["views"]), "dir": str(vd),
                                  "how_to_use": r["how_to_use"]}
                    print(f"  第 {p['page']} 页切成 {len(r['views'])} 块：先看 {r['overview']}")
                except Exception as e:  # noqa: BLE001
                    p["views"] = {"error": str(e)}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    n = sum(len(p.get("dimension_candidates", [])) for p in result.get("pages", []))
    n += len(result.get("dxf", {}).get("dimensions", []))
    print(f"{result['format']}: 提取到 {n} 个尺寸候选 -> {out}")
    h = result.get("setup_hints", {})
    for field in ("length_unit", "standard", "projection", "scale"):
        vals = sorted({x["value"] for x in h.get(field, [])})
        print(f"  {field}: {', '.join(vals) if vals else '未找到'}")
    if h.get("gear"):
        g = h["gear"]
        print(f"  齿轮参数表: z={g.get('z'):g} m={g.get('m'):g} α={g.get('alpha', 20):g}° x={g.get('x', 0):g}")
        for k, v in g.get("derived_mm", {}).items():
            print(f"    {k} = {v:g}")
    if h.get("conflict"):
        print("  注意:", h["conflict"])


if __name__ == "__main__":
    main()
