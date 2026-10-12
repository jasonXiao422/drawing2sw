"""从特征表生成带标准答案的测试图纸：三视图（隐藏线算法）+ 尺寸标注 + 标题栏。

用法:
  python make_test_drawing.py --batch                     # 全部示例和测试零件 × GB / ISO / ASME，输出到 tests/synthetic/
  python make_test_drawing.py examples/bracket_prismatic.json -o tests/synthetic/bracket_gb
  python make_test_drawing.py examples/bracket_inch.json --standard ASME -o tests/synthetic/bracket_asme
  选项: --standard GB|ISO|ASME   --no-unit（标题栏不写单位，测推断）   --no-scan（不出模拟扫描件）

输出（-o 指定的文件夹里）:
  drawing.dxf          带真正尺寸实体的 DXF
  drawing.pdf          矢量 PDF，带文字层（像 SolidWorks 导出的）
  drawing_notext.pdf   矢量 PDF，文字是线条（像 AutoCAD SHX 字体打印的）
  drawing.png          清晰图片
  drawing_scan.jpg     模拟扫描件（轻微旋转、模糊、噪点、JPEG 压缩）
  answer.json          标准答案（原特征表 + 体积、包围盒）
  drawing.dwg          Windows 上装了 AutoCAD / 中望 / 浩辰 时自动生成

不需要 SolidWorks，任何系统都能跑（需要 cadquery、ezdxf、matplotlib）。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))  # ftable 等在 skill 的 scripts/ 里

import ezdxf
from ezdxf.enums import TextEntityAlignment

import ftable
import preview_cadquery

# ---------------------------------------------------------------- 投影

VIEWS = {  # 视线方向（指向观察者）、视图 x 方向。见 references/coordinates.md
    "front": ((0, 0, 1), (1, 0, 0)),
    "top": ((0, 1, 0), (1, 0, 0)),
    "left": ((-1, 0, 0), (0, 0, 1)),   # 左视图：从左往右看，视图 x = +Z
    "right": ((1, 0, 0), (0, 0, -1)),  # 右视图：视图 x = -Z
}


def project(shape, view: str) -> dict:
    """隐藏线消除投影。返回 {visible: [...], hidden: [...]}，元素是 line / circle / arc / poly。"""
    from OCP.BRepAdaptor import BRepAdaptor_Curve  # noqa: PLC0415
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line  # noqa: PLC0415
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: PLC0415
    from OCP.HLRAlgo import HLRAlgo_Projector  # noqa: PLC0415
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape  # noqa: PLC0415
    from OCP.TopAbs import TopAbs_EDGE  # noqa: PLC0415
    from OCP.TopExp import TopExp_Explorer  # noqa: PLC0415
    from OCP.TopoDS import TopoDS  # noqa: PLC0415

    d, x = VIEWS[view]
    algo = HLRBRep_Algo()
    algo.Add(shape)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*d), gp_Dir(*x))))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)

    def edges(comp):
        out = []
        if comp is None or comp.IsNull():
            return out
        ex = TopExp_Explorer(comp, TopAbs_EDGE)
        while ex.More():
            c = BRepAdaptor_Curve(TopoDS.Edge_s(ex.Current()))
            t0, t1 = c.FirstParameter(), c.LastParameter()
            p0, p1 = c.Value(t0), c.Value(t1)
            if c.GetType() == GeomAbs_Line:
                out.append(("line", (p0.X(), p0.Y()), (p1.X(), p1.Y())))
            elif c.GetType() == GeomAbs_Circle:
                circ = c.Circle()
                cen, r = circ.Location(), circ.Radius()
                if abs((t1 - t0) - 2 * math.pi) < 1e-6:
                    out.append(("circle", (cen.X(), cen.Y()), r))
                else:
                    pm = c.Value((t0 + t1) / 2)
                    a0 = math.degrees(math.atan2(p0.Y() - cen.Y(), p0.X() - cen.X()))
                    a1 = math.degrees(math.atan2(p1.Y() - cen.Y(), p1.X() - cen.X()))
                    am = math.degrees(math.atan2(pm.Y() - cen.Y(), pm.X() - cen.X()))
                    if not _ccw_contains(a0, a1, am):
                        a0, a1 = a1, a0
                    out.append(("arc", (cen.X(), cen.Y()), r, a0, a1))
            else:
                n = 24
                pts = [c.Value(t0 + (t1 - t0) * i / n) for i in range(n + 1)]
                out.append(("poly", [(p.X(), p.Y()) for p in pts]))
            ex.Next()
        return out

    vis = edges(h.VCompound()) + edges(h.OutLineVCompound())
    hid = edges(h.HCompound()) + edges(h.OutLineHCompound())
    keys = {_key(e) for e in vis}
    hid = [e for e in hid if _key(e) not in keys]  # 和可见线重合的虚线不画
    return {"visible": _dedupe(vis), "hidden": _dedupe(hid)}


def _ccw_contains(a0, a1, am) -> bool:
    span = (a1 - a0) % 360
    return (am - a0) % 360 <= span


def _key(e):
    r = lambda v: round(v, 3)  # noqa: E731
    if e[0] == "line":
        a, b = sorted([(r(e[1][0]), r(e[1][1])), (r(e[2][0]), r(e[2][1]))])
        return ("line", a, b)
    if e[0] in ("circle", "arc"):
        return (e[0], r(e[1][0]), r(e[1][1]), r(e[2])) + tuple(r(v) for v in e[3:])
    return ("poly", tuple((r(x), r(y)) for x, y in (e[1][0], e[1][-1])))


def _dedupe(items):
    seen, out = set(), []
    for e in items:
        k = _key(e)
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


def bbox(prims):
    xs, ys = [], []
    for e in prims:
        if e[0] == "line":
            xs += [e[1][0], e[2][0]]
            ys += [e[1][1], e[2][1]]
        elif e[0] in ("circle", "arc"):
            xs += [e[1][0] - e[2], e[1][0] + e[2]]
            ys += [e[1][1] - e[2], e[1][1] + e[2]]
        else:
            xs += [p[0] for p in e[1]]
            ys += [p[1] for p in e[1]]
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------- 图纸风格

STYLES = {
    "GB": {"projection": "first_angle", "side": "left", "lang": "zh", "unit": "mm",
           "count": "{n}×", "thru": "", "eqs": " 均布", "pcd_note": "",
           "title": ["{name}", "材料 {material}", "比例 {scale}", "单位：mm", "第一角投影  GB/T 4458.1"],
           "notes_head": "技术要求"},
    "ISO": {"projection": "first_angle", "side": "left", "lang": "en", "unit": "mm",
            "count": "{n}× ", "thru": " THRU", "eqs": " EQS", "pcd_note": "",
            "title": ["{name}", "MATERIAL {material}", "SCALE {scale}", "DIMENSIONS IN MM",
                      "FIRST ANGLE PROJECTION  ISO 128", "GENERAL TOLERANCES ISO 2768-m"],
            "notes_head": "NOTES"},
    "ASME": {"projection": "third_angle", "side": "right", "lang": "en", "unit": "inch",
             "count": "{n}X ", "thru": " THRU", "eqs": " EQ SP", "pcd_note": " B.C.",
             "title": ["{name}", "MATERIAL {material}", "SCALE {scale}",
                       "UNLESS OTHERWISE SPECIFIED DIMENSIONS ARE IN INCHES",
                       "TOLERANCES: .XX ±.01  .XXX ±.005", "THIRD ANGLE PROJECTION  ASME Y14.5"],
             "notes_head": "NOTES"},
}
DIA = "%%c"  # 线性尺寸标直径时用；直径、半径尺寸会自动加 Ø / R，不要再写


# ---------------------------------------------------------------- 主体

class Sheet:
    def __init__(self, std: str, size: float, unit_k: float, inch: bool):
        self.std, self.st = std, STYLES[std]
        self.k = unit_k            # mm -> 图纸单位
        self.doc = ezdxf.new("R2018", setup=False)
        self.doc.header["$INSUNITS"] = 1 if inch else 4
        self.doc.header["$MEASUREMENT"] = 0 if inch else 1
        self.msp = self.doc.modelspace()
        self.labels = []           # 每个尺寸 / 标注文字属于哪个特征的哪个参数（数据集的标准答案）
        self.h = max(size * unit_k * 0.025, 2.5 * unit_k)  # 字高
        for name, lt, color in (("轮廓线", "CONTINUOUS", 7), ("虚线", "DASHED", 7),
                                ("中心线", "CENTER", 1), ("尺寸线", "CONTINUOUS", 3), ("文字", "CONTINUOUS", 7),
                                ("细实线", "CONTINUOUS", 8)):
            if lt not in self.doc.linetypes:
                self.doc.linetypes.add(lt, pattern=[0.4 * self.h, 0.25 * self.h, -0.12 * self.h] if lt == "DASHED"
                                       else [1.2 * self.h, 0.8 * self.h, -0.15 * self.h, 0.1 * self.h, -0.15 * self.h])
            self.doc.layers.add(name, linetype=lt, color=color)
        self.doc.styles.add("CN", font=_cjk_font())
        ds = self.doc.dimstyles.get("Standard")
        ds.dxf.dimtxt = self.h
        ds.dxf.dimasz = self.h * 0.9
        ds.dxf.dimexo = self.h * 0.3
        ds.dxf.dimexe = self.h * 0.5
        ds.dxf.dimgap = self.h * 0.3
        ds.dxf.dimtxsty = "CN"
        ds.dxf.dimtad = 1
        ds.dxf.dimdsep = ord(".")  # ezdxf 默认可能是逗号，英寸图会变成 3,250
        ds.dxf.dimtih = 0
        ds.dxf.dimtoh = 0
        if inch:
            ds.dxf.dimdec = 3
            ds.dxf.dimzin = 4      # 去掉前导 0：.375（ASME 写法）
        else:
            ds.dxf.dimdec = 2
            ds.dxf.dimzin = 8      # 去掉末尾 0：12.5、40

    # 图元，坐标已是图纸单位
    def prim(self, e, dx, dy, layer):
        a = {"layer": layer}
        k = 1.0
        if e[0] == "line":
            self.msp.add_line((e[1][0] * k + dx, e[1][1] * k + dy), (e[2][0] * k + dx, e[2][1] * k + dy), dxfattribs=a)
        elif e[0] == "circle":
            self.msp.add_circle((e[1][0] + dx, e[1][1] + dy), e[2], dxfattribs=a)
        elif e[0] == "arc":
            self.msp.add_arc((e[1][0] + dx, e[1][1] + dy), e[2], e[3], e[4], dxfattribs=a)
        else:
            self.msp.add_lwpolyline([(x + dx, y + dy) for x, y in e[1]], dxfattribs=a)

    def label(self, entity, kind, value, tag):
        """tag = (特征 id, 参数名)。value 是图纸单位下的数值。没有 tag 的尺寸不记（如图框）。"""
        if tag:
            self.labels.append({"handle": entity.dxf.handle, "kind": kind, "value": round(value, 6),
                                "value_mm": round(value / self.k, 6), "feature": tag[0], "param": tag[1]})

    def text(self, s, at, h=None, align=TextEntityAlignment.LEFT, rot=0, tag=None, value=None):
        t = self.msp.add_text(s, height=h or self.h, rotation=rot,
                              dxfattribs={"style": "CN", "layer": "文字"})
        t.set_placement(at, align=align)
        self.label(t, "note", value or 0.0, tag)

    def _dim(self, d, kind, value, tag):
        d.render()
        self.label(d.dimension, kind, value, tag)

    def hdim(self, p1, p2, y, text=None, tag=None):
        self._dim(self.msp.add_linear_dim(base=(p1[0], y), p1=p1, p2=p2, angle=0, text=text or "<>",
                                          dxfattribs={"layer": "尺寸线"}), "linear", abs(p2[0] - p1[0]), tag)

    def vdim(self, p1, p2, x, text=None, tag=None):
        self._dim(self.msp.add_linear_dim(base=(x, p1[1]), p1=p1, p2=p2, angle=90, text=text or "<>",
                                          dxfattribs={"layer": "尺寸线"}), "linear", abs(p2[1] - p1[1]), tag)

    def ddim(self, center, r, angle, text, tag=None):
        self._dim(self.msp.add_diameter_dim(center=center, radius=r, angle=angle, text=text,
                                            dxfattribs={"layer": "尺寸线"}), "diameter", 2 * r, tag)

    def rdim(self, center, r, angle, text, tag=None):
        self._dim(self.msp.add_radius_dim(center=center, radius=r, angle=angle, text=text,
                                          dxfattribs={"layer": "尺寸线"}), "radius", r, tag)

    def center_mark(self, c, size, layer="中心线"):
        self.msp.add_line((c[0] - size, c[1]), (c[0] + size, c[1]), dxfattribs={"layer": layer})
        self.msp.add_line((c[0], c[1] - size), (c[0], c[1] + size), dxfattribs={"layer": layer})


def _cjk_font() -> str:
    """渲染用的中文字体。Windows 上 AutoCAD 会自己替换成宋体。"""
    import glob  # noqa: PLC0415
    for pat in ("C:/Windows/Fonts/simsun.ttc", "C:/Windows/Fonts/msyh.ttc",
                "/usr/share/fonts/**/NotoSansCJK*.ttc", "/usr/share/fonts/**/*wqy*.tt?",
                "/usr/share/fonts/**/*CJK*.tt?"):
        hits = glob.glob(pat, recursive=True)
        if hits:
            return Path(hits[0]).name
    return "simsun.ttc"


def fmt(v_mm: float, k: float, inch: bool) -> str:
    v = v_mm * k
    if inch:
        s = f"{v:.3f}"
        return s[1:] if s.startswith("0.") else s
    return f"{v:.2f}".rstrip("0").rstrip(".")


def make(table_raw: dict, std: str, out_dir: Path, with_unit: bool = True, scan: bool = True,
         dwg: bool = True) -> dict:
    table = ftable.to_mm(ftable.resolve(table_raw))
    inch = std == "ASME"
    k = 1 / 25.4 if inch else 1.0
    st = STYLES[std]
    feats = table["features"]
    base = feats[0]
    revolved = base["type"] == "base_revolve"

    solid = preview_cadquery.build(table)
    gear = next((f for f in feats if f["type"] == "spur_gear_teeth"), None)
    # 齿轮按国标 GB/T 4459.2 规定画法：不画齿形，画齿顶线、分度线、齿根线。所以投影用不带齿的轮坯
    proj_table = {**table, "features": [f for f in feats if f["type"] != "spur_gear_teeth"]} if gear else table
    shape = preview_cadquery.build(proj_table).val() if gear else solid.val()
    if revolved:  # 回转体：轴线（模型 Y）横放，和图纸习惯一致
        shape = shape.rotate((0, 0, 0), (0, 0, 1), -90)
    shape_k = shape.scale(k) if k != 1 else shape
    side = st["side"]
    views = {v: project(shape_k.wrapped, v) for v in ("front", "top", side)}
    if revolved:
        views.pop("top")  # 回转体：主视图 + 端面视图就够了

    bb = shape.BoundingBox()
    size = max(bb.xlen, bb.ylen, bb.zlen)
    sh = Sheet(std, size, k, inch)
    gap = size * k * 0.55
    boxes = {v: bbox(p["visible"] + p["hidden"]) for v, p in views.items()}

    # 布置：第一角 俯视在下、左视在右；第三角 俯视在上、右视在右
    off = {"front": (0.0, 0.0)}
    fb = boxes["front"]
    if "top" in views:
        tb = boxes["top"]
        if st["projection"] == "first_angle":
            off["top"] = (0.0, fb[1] - gap - tb[3])
        else:
            off["top"] = (0.0, fb[3] + gap - tb[1])
    sb = boxes[side]
    off[side] = (fb[2] + gap - sb[0], 0.0)

    for v, p in views.items():
        dx, dy = off[v]
        for e in p["visible"]:
            sh.prim(e, dx, dy, "轮廓线")
        for e in p["hidden"]:
            sh.prim(e, dx, dy, "虚线")

    dimgap = sh.h * 3.6
    if revolved:
        dim_revolved(sh, table, off, boxes, side, k, inch, dimgap)
        if gear:
            gear_convention(sh, table, gear, off, side, k, dimgap)
    else:
        dim_prismatic(sh, table, off, boxes, side, k, inch, dimgap)

    # 图框、标题栏、技术要求、齿轮参数表
    xs = [off[v][0] + boxes[v][0] for v in views] + [off[v][0] + boxes[v][2] for v in views]
    ys = [off[v][1] + boxes[v][1] for v in views] + [off[v][1] + boxes[v][3] for v in views]
    x0, x1 = min(xs) - 6 * dimgap, max(xs) + 3 * dimgap
    y0, y1 = min(ys) - 4 * dimgap, max(ys) + 3 * dimgap
    tb_w = 32 * sh.h
    x1 = max(x1, x0 + tb_w * 1.6)
    if gear:
        x1 = max(xs) + 2 * dimgap + tb_w  # 参数表放在端面视图右边，不压图
    title_lines = []
    for line in st["title"]:
        if not with_unit and ("单位" in line or "DIMENSIONS" in line):
            continue
        title_lines.append(line.format(name=table_raw["part"]["name"],
                                       material=table_raw["part"].get("material", "-"), scale="1:1"))
    tb_w = max(tb_w, max(len(x) * (1.0 if any(ord(ch) > 0x2E80 for ch in x) else 0.82) for x in title_lines) * sh.h + 2 * sh.h)
    x1 = max(x1, x0 + tb_w * 1.3)
    tb_h = (len(title_lines) + 1) * sh.h * 1.8
    y0 -= tb_h
    sh.msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": "轮廓线"})
    sh.msp.add_lwpolyline([(x1 - tb_w, y0), (x1, y0), (x1, y0 + tb_h), (x1 - tb_w, y0 + tb_h)], close=True,
                          dxfattribs={"layer": "轮廓线"})
    for i, line in enumerate(title_lines):
        sh.text(line, (x1 - tb_w + sh.h, y0 + tb_h - (i + 1) * sh.h * 1.8))
    notes = list(table_raw["part"].get("drawing_setup", {}).get("notes", []))
    notes = [re.sub(r"^技术要求\s*\d+[.、]\s*", "", n) for n in notes
             if "齿轮参数" not in n and "不建模" not in n]
    if notes:
        sh.text(st["notes_head"], (x0 + sh.h, y0 + tb_h - sh.h * 1.8))
        for i, n in enumerate(notes[:5]):
            sh.text(f"{i + 1}. {n}", (x0 + sh.h, y0 + tb_h - (i + 2) * sh.h * 1.8), h=sh.h * 0.85)
    if gear:
        rows = ([("齿数", "z", f"{gear['teeth']}"), ("模数", "m", fmt(gear["module"], k, inch)),
                 ("压力角", "α", f"{gear.get('pressure_angle', 20):g}°"),
                 ("齿顶高系数", "ha*", f"{gear.get('addendum_coef', 1):g}"),
                 ("顶隙系数", "c*", f"{gear.get('clearance_coef', 0.25):g}"),
                 ("变位系数", "x", f"{gear.get('shift_coef', 0):g}")]
                if st["lang"] == "zh" else
                [("NUMBER OF TEETH", "N", f"{gear['teeth']}"), ("MODULE", "m", fmt(gear["module"], k, inch)),
                 ("PRESSURE ANGLE", "α", f"{gear.get('pressure_angle', 20):g}°")])
        tx, ty = x1 - tb_w, y1 - sh.h
        for i, row in enumerate(rows):
            for j, cell in enumerate(row):
                sh.text(cell, (tx + [0, 0.55, 0.75][j] * tb_w, ty - (i + 1) * sh.h * 1.8))

    out_dir.mkdir(parents=True, exist_ok=True)
    dxf_path = out_dir / "drawing.dxf"
    sh.doc.saveas(dxf_path)
    files = {"dxf": str(dxf_path)}
    text_at = {}
    files.update(render(sh.doc, out_dir, scan, text_at))
    for lab in sh.labels:  # 渲染图上这个尺寸的文字在哪（PDF 坐标，左上角为原点，单位 pt）
        if lab["handle"] in text_at:
            lab["pdf_text"], lab["pdf_pt"] = text_at[lab["handle"]]
    try:  # Windows 上装了 AutoCAD / 中望 / 浩辰 时，顺便出 DWG
        import dwg2dxf  # noqa: PLC0415
        if dwg and dwg2dxf.installed_cads():
            files["dwg"] = str(dwg2dxf.dxf_to_dwg(dxf_path, out_dir / "drawing.dwg"))
    except Exception as e:  # noqa: BLE001
        files["dwg_error"] = str(e)[:200]

    rep = preview_cadquery.report(solid, table)
    answer = {"source_table": table_raw, "standard": std, "unit_shown": with_unit,
              "volume_mm3": rep["volume_mm3"], "surface_area_mm2": rep["surface_area_mm2"],
              "bbox_mm": rep["bbox_mm"], "hole_count": rep["hole_count_from_table"],
              "dimension_labels": sh.labels, "files": files}
    (out_dir / "answer.json").write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")
    return answer


# ---------------------------------------------------------------- 尺寸：棱柱体

def dim_prismatic(sh: Sheet, t: dict, off, boxes, side, k, inch, g):
    """标注要能唯一确定几何：大小 + 相对外轮廓左下角的定位（链式标注）。每个尺寸带 (特征 id, 参数) 标签。"""
    feats = t["features"]
    base = feats[0]
    bid = base["id"]
    st = sh.st
    plane = base["plane"]
    if plane not in ("top", "front"):
        return  # 只标 top / front 基体，其他情况读图时靠几何
    prof_view = "top" if plane == "top" else "front"
    thick_view = "front" if plane == "top" else "top"
    dx, dy = off[prof_view]

    def P(u, v):  # 草图 (u, v) mm -> 轮廓视图上的图纸坐标
        return (u * k + dx, v * k + dy)

    pts = ftable.profile_points(base["profile"]) or []
    if base["profile"]["shape"] == "circle":
        cu, cv = base["profile"].get("center", [0, 0])
        r = base["profile"]["diameter"] / 2
        sh.ddim(P(cu, cv), r * k, 20, "<>", tag=(bid, "profile.diameter"))
        umin, umax, vmin, vmax = cu - r, cu + r, cv - r, cv + r
        datum = (cu, cv)          # 圆盘：定位尺寸从圆心量
    else:
        us, vs = [p[0] for p in pts], [p[1] for p in pts]
        umin, umax, vmin, vmax = min(us), max(us), min(vs), max(vs)
        sh.hdim(P(umin, vmin), P(umax, vmin), P(0, vmin)[1] - g, tag=(bid, "profile.width"))
        sh.vdim(P(umin, vmin), P(umin, vmax), P(umin, 0)[0] - g, tag=(bid, "profile.height"))
        datum = (umin, vmin)      # 矩形：定位尺寸从左下角量

    # 厚度：在另一个视图上标竖直尺寸
    tb = boxes[thick_view]
    tx, ty = off[thick_view]
    sh.vdim((tb[2] + tx, tb[1] + ty), (tb[2] + tx, tb[3] + ty), tb[2] + tx + g, tag=(bid, "depth"))

    def chain_u(fid, values, y, param, ref_v):
        """从基准开始，沿 u 方向链式标注到每个不同的 u 值。界线从 ref_v 引出（靠近被标的特征）。"""
        stops = [datum[0]] + [u for u in values if abs(u - datum[0]) > 1e-9]
        for a, b in zip(stops, stops[1:]):
            sh.hdim(P(a, ref_v), P(b, ref_v), y, tag=(fid, param))

    def chain_v(fid, values, x, param, ref_u):
        stops = [datum[1]] + [v for v in values if abs(v - datum[1]) > 1e-9]
        for a, b in zip(stops, stops[1:]):
            sh.vdim(P(ref_u, a), P(ref_u, b), x, tag=(fid, param))

    def lead_angle(q):
        """直径引线：文字朝离零件中心远的方向引出去（ezdxf 的文字在 angle + 180° 那一端）。"""
        cu0, cv0 = (umin + umax) / 2, (vmin + vmax) / 2
        out = math.degrees(math.atan2(q[1] - cv0, q[0] - cu0)) if (q[0], q[1]) != (cu0, cv0) else 135.0
        return (out + 180 + 15) % 360

    top, right, bottom, left = 1, 1, 2, 2   # 各边已经用了几层尺寸
    for f in feats[1:]:
        if f.get("plane", plane) != plane or f["id"].count("__"):
            continue
        fid = f["id"]
        if f["type"] == "hole":
            hp = ftable.hole_positions(f)
            n = len(hp)
            r = f["diameter"] / 2
            cnt = st["count"].format(n=n) if n > 1 else ""
            lead = min(hp, key=lambda q: (q[0] - umin) - (q[1] - vmin))   # 最靠左上的孔
            sh.ddim(P(*lead), r * k, lead_angle(lead), f"{cnt}<>{st['thru'] if f['depth'] == 'through_all' else ''}",
                    tag=(fid, "diameter"))
            for q in hp:
                sh.center_mark(P(*q), r * k * 1.4)
            if f.get("bolt_circle"):
                bc = f["bolt_circle"]
                c = bc.get("center", [0, 0])
                sh.msp.add_circle(P(*c), bc["pcd"] / 2 * k, dxfattribs={"layer": "中心线"})
                gap_angle = bc.get("start_angle", 0) + 180 / bc["count"] + 180   # 两孔之间，不穿孔
                sh.ddim(P(*c), bc["pcd"] / 2 * k, gap_angle, "<>" + st["pcd_note"], tag=(fid, "bolt_circle.pcd"))
                if abs(c[0] - datum[0]) > 1e-9 or abs(c[1] - datum[1]) > 1e-9:
                    chain_u(fid, [c[0]], P(0, vmax)[1] + g * top, "bolt_circle.center.u", c[1]); top += 1
                    chain_v(fid, [c[1]], P(umax, 0)[0] + g * right, "bolt_circle.center.v", c[0]); right += 1
            else:
                # 定位尺寸放在离孔近的那一侧，界线短，不穿过整个零件
                us_, vs_ = sorted({round(q[0], 6) for q in hp}), sorted({round(q[1], 6) for q in hp})
                if sum(vs_) / len(vs_) >= (vmin + vmax) / 2:
                    chain_u(fid, us_, P(0, vmax)[1] + g * top, "positions.u", max(vs_)); top += 1
                else:
                    chain_u(fid, us_, P(0, vmin)[1] - g * bottom, "positions.u", min(vs_)); bottom += 1
                if sum(us_) / len(us_) >= (umin + umax) / 2:
                    chain_v(fid, vs_, P(umax, 0)[0] + g * right, "positions.v", max(us_)); right += 1
                else:
                    chain_v(fid, vs_, P(umin, 0)[0] - g * left, "positions.v", min(us_)); left += 1
        elif f["type"] == "cut_extrude" and f["profile"]["shape"] == "rect":
            pr = f["profile"]
            cu, cv = pr.get("center", [0, 0])
            w, h = pr["width"], pr["height"]
            u0, v0 = cu - w / 2, cv - h / 2
            yb = P(0, vmin)[1] - g * bottom; bottom += 1
            xl = P(umin, 0)[0] - g * left; left += 1
            if abs(u0 - datum[0]) > 1e-9:
                sh.hdim(P(datum[0], v0), P(u0, v0), yb, tag=(fid, "profile.center.u"))
            sh.hdim(P(u0, v0), P(u0 + w, v0), yb, tag=(fid, "profile.width"))
            if abs(v0 - datum[1]) > 1e-9:
                sh.vdim(P(u0, datum[1]), P(u0, v0), xl, tag=(fid, "profile.center.v"))
            sh.vdim(P(u0, v0), P(u0, v0 + h), xl, tag=(fid, "profile.height"))
        elif f["type"] == "cut_extrude" and f["profile"]["shape"] == "circle":
            pr = f["profile"]
            c = pr.get("center", [0, 0])
            sh.ddim(P(*c), pr["diameter"] / 2 * k, 160, "<>", tag=(fid, "profile.diameter"))
            sh.center_mark(P(*c), pr["diameter"] / 2 * k * 1.3)
            if abs(c[0] - datum[0]) > 1e-9:
                chain_u(fid, [c[0]], P(0, vmin)[1] - g * bottom, "profile.center.u", c[1]); bottom += 1
            if abs(c[1] - datum[1]) > 1e-9:
                chain_v(fid, [c[1]], P(umin, 0)[0] - g * left, "profile.center.v", c[0]); left += 1
        elif f["type"] == "edge_treatment" and f["edges"] == "vertical" and f["kind"] == "fillet":
            n = len(pts) if pts else 1
            cnt = st["count"].format(n=n) if n > 1 else ""
            r = f["size"]
            cu, cv = umax - r, vmax - r   # 右上角
            sh.rdim(P(cu, cv), r * k, 45, f"{cnt}<>", tag=(fid, "size"))
        elif f["type"] == "edge_treatment" and f["kind"] == "chamfer":
            s = fmt(f["size"], k, inch)
            note = f"C{s}" if st["lang"] == "zh" else f"{s} X 45°"
            sh.text(note, P(umax, vmax + 0.3 * f["size"]), align=TextEntityAlignment.BOTTOM_LEFT,
                    tag=(fid, "size"), value=f["size"] * k)


# ---------------------------------------------------------------- 尺寸：回转体

def dim_revolved(sh: Sheet, t: dict, off, boxes, side, k, inch, g):
    feats = t["features"]
    base = feats[0]
    st = sh.st
    hp = base["half_profile"]
    bid = base["id"]
    dx, dy = off["front"]

    def F(h, r):  # 半剖轮廓 (r, h) -> 主视图图纸坐标。轴线横放：h 向右，r 向下（旋转 -90°）
        return (h * k + dx, -r * k + dy)

    # 轴线
    hs = [p[1] for p in hp]
    sh.msp.add_line(F(min(hs) - 5, 0), F(max(hs) + 5, 0), dxfattribs={"layer": "中心线"})
    # 每个不同半径标一个直径：取该半径上最长的轴向边的中点
    axial = {}
    n = len(hp)
    for i in range(n):
        (r1, h1), (r2, h2) = hp[i], hp[(i + 1) % n]
        if abs(r1 - r2) < 1e-9 and abs(h1 - h2) > 1e-9 and r1 > 0:
            axial.setdefault(r1, min(h1, h2))
            axial[r1] = min(axial[r1], h1, h2)
    # 直径尺寸放在视图左侧，从小到大往外排，不压图
    hmin = min(p[1] for p in hp)
    for i, (r, h_at) in enumerate(sorted(axial.items())):
        x = F(hmin, 0)[0] - g * (i + 1)
        sh.vdim(F(h_at, r), F(h_at, -r), x, text=DIA + "<>", tag=(bid, "half_profile.diameter"))
    # 轴向长度：所有台阶位置，链式标在下方
    hb = sorted({round(h, 6) for h in hs})
    rmax = max(p[0] for p in hp)
    for a, b in zip(hb, hb[1:]):
        sh.hdim(F(a, rmax), F(b, rmax), F(0, rmax)[1] - g, tag=(bid, "half_profile.length"))
    if len(hb) > 2:  # 总长：参考尺寸
        sh.hdim(F(hb[0], rmax), F(hb[-1], rmax), F(0, rmax)[1] - 2 * g, tag=(bid, "half_profile.total_length"))

    # 端面视图：均布孔、键槽
    sx, sy = off[side]
    sgn = 1 if side == "left" else -1

    def S(u, v):  # top 草图 (u=X, v=-Z) -> 端面视图。旋转后：左视图 x = -v，y = -u；右视图 x = v
        return (sgn * -v * k + sx, -u * k + sy)

    sh.center_mark(S(0, 0), rmax * k * 1.15)
    for f in feats[1:]:
        if f["type"] == "hole" and f.get("bolt_circle"):
            bc = f["bolt_circle"]
            pts = ftable.hole_positions(f)
            sh.msp.add_circle(S(0, 0), bc["pcd"] / 2 * k, dxfattribs={"layer": "中心线"})
            cnt = st["count"].format(n=len(pts))
            q = S(*pts[0]); c0 = S(0, 0)
            sh.ddim(q, f["diameter"] / 2 * k, (math.degrees(math.atan2(q[1] - c0[1], q[0] - c0[0])) + 195) % 360,
                    f"{cnt}<>{st['thru'] if f['depth'] == 'through_all' else ''}{st['eqs']}", tag=(f["id"], "diameter"))
            qa = [S(*q) for q in pts[:2]]
            a0 = math.degrees(math.atan2(qa[0][1] - S(0, 0)[1], qa[0][0] - S(0, 0)[0]))
            sh.ddim(S(0, 0), bc["pcd"] / 2 * k, a0 + 180 / len(pts) + 180, "<>" + st["pcd_note"],
                    tag=(f["id"], "bolt_circle.pcd"))
        elif f["type"] == "cut_extrude" and f["profile"]["shape"] == "rect":
            pr = f["profile"]
            cu, cv = pr.get("center", [0, 0])
            w, h = pr["width"], pr["height"]
            # 键槽：标宽度，和"孔对边到槽顶"（国标 d + t2 写法）
            bore = min((p[0] for p in hp if p[0] > 0), default=0)
            u0, u1, v0, v1 = cu - w / 2, cu + w / 2, cv - h / 2, cv + h / 2
            corners = [S(u0, v0), S(u1, v0), S(u1, v1), S(u0, v1)]
            xs, ys = [c[0] for c in corners], [c[1] for c in corners]
            if (u1 - u0) < (v1 - v0):   # 槽沿 v 方向伸出：宽度沿 u
                far = max(abs(v0), abs(v1))
                sh.vdim((min(xs), min(ys)), (min(xs), max(ys)), min(xs) - g * 0.5, tag=(f["id"], "profile.width"))
                tip = S(cu, far if abs(v1) >= abs(v0) else -far)
                opp = S(cu, -bore if abs(v1) >= abs(v0) else bore)
                sh.hdim(opp, tip, max(ys) + g * 0.8, tag=(f["id"], "keyway.bore_plus_depth"))
            else:
                far = max(abs(u0), abs(u1))
                sh.hdim((min(xs), max(ys)), (max(xs), max(ys)), max(ys) + g * 0.5, tag=(f["id"], "profile.height"))
                tip = S(far if abs(u1) >= abs(u0) else -far, cv)
                opp = S(-bore if abs(u1) >= abs(u0) else bore, cv)
                sh.vdim(opp, tip, max(xs) + g * 0.8, tag=(f["id"], "keyway.bore_plus_depth"))
        elif f["type"] == "edge_treatment" and f["kind"] == "chamfer":
            s = fmt(f["size"], k, inch)
            note = f"C{s}" if st["lang"] == "zh" else f"{s} X 45°"
            sh.text(note, F(max(hs), rmax + 0.6 * f["size"]), tag=(f["id"], "size"), value=f["size"] * k)


def gear_convention(sh: Sheet, t: dict, gear: dict, off, side, k, g):
    """齿轮规定画法：主视图画分度线（点画线）、齿根线（细实线）；端面视图画分度圆、齿根圆。
    标齿顶圆和分度圆直径。"""
    gp = ftable.gear_params(gear)
    hp = t["features"][0]["half_profile"]
    rim = [p for p in hp if abs(p[0] - gp["ra"]) < 1e-6]
    h0, h1 = min(p[1] for p in rim), max(p[1] for p in rim)
    dx, dy = off["front"]
    ext = 0.08 * (h1 - h0)
    for sign in (1, -1):
        y_d = -sign * gp["r"] * k + dy
        y_f = -sign * gp["rf"] * k + dy
        sh.msp.add_line(((h0 - ext) * k + dx, y_d), ((h1 + ext) * k + dx, y_d), dxfattribs={"layer": "中心线"})
        sh.msp.add_line((h0 * k + dx, y_f), (h1 * k + dx, y_f), dxfattribs={"layer": "细实线"})
    xd = (h1 + ext * 3) * k + dx
    sh.vdim((xd, gp["r"] * k + dy), (xd, -gp["r"] * k + dy), xd + g * 0.6, text="%%c<>")
    sx, sy = off[side]
    sh.msp.add_circle((sx, sy), gp["r"] * k, dxfattribs={"layer": "中心线"})
    sh.msp.add_circle((sx, sy), gp["rf"] * k, dxfattribs={"layer": "细实线"})


# ---------------------------------------------------------------- 输出

def _font_file() -> str | None:
    import glob  # noqa: PLC0415
    for pat in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc",
                "/usr/share/fonts/**/NotoSansCJK-Regular.ttc", "/usr/share/fonts/**/*CJK*.tt?",
                "/usr/share/fonts/**/*wqy*.tt?"):
        hits = sorted(glob.glob(pat, recursive=True))
        if hits:
            return hits[0]
    return None


def _all_texts(doc):
    """图上所有文字（含尺寸块里的显示文字）：(文字, 插入点, 字高, 旋转角, 水平对齐, 垂直对齐, 所属实体句柄)。"""
    from preprocess_drawing import decode_cad_text  # noqa: PLC0415
    ha_map = {0: "left", 1: "center", 2: "right", 4: "center"}
    va_map = {0: "baseline", 1: "bottom", 2: "center", 3: "top"}
    out = []

    def add(e, owner=None):
        n0 = len(out)
        _add(e)
        for i in range(n0, len(out)):
            out[i] = out[i] + (owner or e.dxf.handle,)

    def _add(e, dx=0.0, dy=0.0):
        t = e.dxftype()
        if t == "TEXT":
            pl = e.get_placement()   # (对齐方式, 第一点, 第二点)
            p = pl[1] if pl[0].name in ("LEFT", "ALIGNED", "FIT") or pl[2] is None else pl[2]
            hal = e.dxf.get("halign", 0)
            val = e.dxf.get("valign", 0)
            out.append((decode_cad_text(e.dxf.text), (p[0] + dx, p[1] + dy), e.dxf.height,
                        e.dxf.get("rotation", 0), ha_map.get(hal, "left"), va_map.get(val, "baseline")))
        elif t == "MTEXT":
            p = e.dxf.insert
            ap = e.dxf.get("attachment_point", 1)
            ha = ["left", "center", "right"][(ap - 1) % 3]
            va = ["top", "center", "bottom"][(ap - 1) // 3]
            rot = e.get_rotation() if hasattr(e, "get_rotation") else e.dxf.get("rotation", 0)
            out.append((decode_cad_text(e.plain_text()), (p[0] + dx, p[1] + dy), e.dxf.char_height, rot, ha, va))

    for e in doc.modelspace():
        if e.dxftype() in ("TEXT", "MTEXT"):
            add(e)
        elif e.dxftype() == "DIMENSION":
            blk = e.get_geometry_block()
            for x in blk or []:
                if x.dxftype() in ("TEXT", "MTEXT"):
                    add(x, e.dxf.handle)
    return out


def render(doc, out_dir: Path, scan: bool, text_at: dict | None = None) -> dict:
    """出两种 PDF：drawing.pdf 带文字层（像 SolidWorks 导出的），
    drawing_notext.pdf 文字是轮廓线（像 AutoCAD 用 SHX 字体打印的，提取不到文字）。"""
    files = {}
    try:
        import matplotlib  # noqa: PLC0415
        matplotlib.use("Agg")
        matplotlib.rcParams["pdf.fonttype"] = 42  # 嵌入 TrueType，PDF 里的文字可以提取
        import matplotlib.pyplot as plt  # noqa: PLC0415
        from ezdxf.addons.drawing import Frontend, RenderContext  # noqa: PLC0415
        from ezdxf.addons.drawing.config import (  # noqa: PLC0415
            BackgroundPolicy, ColorPolicy, Configuration, TextPolicy)
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend  # noqa: PLC0415
        from matplotlib.font_manager import FontProperties  # noqa: PLC0415

        def draw(text_policy):
            fig = plt.figure(figsize=(16.54, 11.69))  # A3 横向
            ax = fig.add_axes([0, 0, 1, 1])
            cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK,
                                text_policy=text_policy)
            Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(
                doc.modelspace(), finalize=True)
            return fig, ax

        # 1. 文字是轮廓线
        fig, ax = draw(TextPolicy.FILLING)
        p = out_dir / "drawing_notext.pdf"
        fig.savefig(p, facecolor="white")
        plt.close(fig)
        files["pdf_notext"] = str(p)

        # 2. 线条 + 真正的文字
        fig, ax = draw(TextPolicy.IGNORE)
        fp = FontProperties(fname=_font_file()) if _font_file() else None
        fig.canvas.draw()
        y0 = ax.transData.transform((0, 0))[1]
        y1 = ax.transData.transform((0, 1))[1]
        pt_per_unit = abs(y1 - y0) * 72 / fig.dpi
        artists = []
        for txt, (x, y), h, rot, ha, va, owner in _all_texts(doc):
            for i, line in enumerate(txt.split("\n")):
                artists.append((owner, line, ax.text(x, y - i * h * 1.6, line, fontsize=h * pt_per_unit * 1.25,
                                                     rotation=rot, ha=ha, va=va, rotation_mode="anchor",
                                                     fontproperties=fp, color="black")))
        if text_at is not None:  # 文字中心换算到 PDF 坐标（pt，原点左上角，和 PyMuPDF 一致）
            fig.canvas.draw()
            rr = fig.canvas.get_renderer()
            H = fig.get_figheight() * 72
            for owner, line, art in artists:
                bb = art.get_window_extent(rr)
                cx, cy = (bb.x0 + bb.x1) / 2 * 72 / fig.dpi, (bb.y0 + bb.y1) / 2 * 72 / fig.dpi
                text_at.setdefault(owner, (line, [round(cx, 2), round(H - cy, 2)]))
        pdf = out_dir / "drawing.pdf"
        png = out_dir / "drawing.png"
        fig.savefig(pdf, facecolor="white")
        fig.savefig(png, dpi=150, facecolor="white")
        plt.close(fig)
        files.update(pdf=str(pdf), png=str(png))
        if scan:
            files["scan"] = str(make_scan(png, out_dir / "drawing_scan.jpg"))
    except Exception as e:  # noqa: BLE001
        import traceback  # noqa: PLC0415
        files["render_error"] = traceback.format_exc()[-800:]
    return files


def make_scan(png: Path, out: Path) -> Path:
    """模拟扫描件：灰度、旋转 0.8°、轻微模糊、噪点、JPEG 压缩。"""
    import random  # noqa: PLC0415

    from PIL import Image, ImageFilter  # noqa: PLC0415

    random.seed(1)
    im = Image.open(png).convert("L").rotate(0.8, expand=True, fillcolor=255)
    im = im.filter(ImageFilter.GaussianBlur(0.7))
    px = im.load()
    w, h = im.size
    for _ in range(w * h // 60):
        x, y = random.randrange(w), random.randrange(h)
        px[x, y] = max(0, min(255, px[x, y] + random.randint(-60, 60)))
    im.save(out, quality=55)
    return out


BATCH_VARIANTS = [("GB", True), ("ISO", False), ("ASME", True)]  # (标准, 标题栏是否写单位)


def batch(root: Path, out_root: Path) -> list[dict]:
    """examples/ 和 tests/drawings/*/part.json 里的每个零件表，各出 GB / ISO（不写单位）/ ASME 三套图。"""
    tables = sorted(root.glob("examples/*.json")) + sorted(root.glob("tests/drawings/*/part.json"))
    rows = []
    for tp in tables:
        name = tp.parent.name if tp.name == "part.json" else tp.stem
        raw = ftable.load_raw(tp)
        for std, unit in BATCH_VARIANTS:
            if raw["part"]["units"] == "inch" and std != "ASME":
                continue
            out = out_root / f"{name}_{std}{'' if unit else '_nounit'}"
            if out.exists():
                shutil.rmtree(out)
            try:
                ans = make(raw, std, out, with_unit=unit)
                rows.append({"name": out.name, "volume_mm3": ans["volume_mm3"],
                             "ok": "render_error" not in ans["files"]})
            except Exception as e:  # noqa: BLE001
                rows.append({"name": out.name, "ok": False, "error": str(e)[:200]})
            print(rows[-1], flush=True)
    (out_root / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("table", nargs="?")
    ap.add_argument("-o", "--out", default="tests/synthetic")
    ap.add_argument("--batch", action="store_true", help="批量：所有示例和测试零件表 × 三种标准，输出到 -o 文件夹")
    ap.add_argument("--standard", choices=sorted(STYLES), default=None,
                    help="默认按特征表 drawing_setup.standard；英寸表默认 ASME")
    ap.add_argument("--no-unit", action="store_true", help="标题栏不写单位")
    ap.add_argument("--no-scan", action="store_true")
    ap.add_argument("--no-dwg", action="store_true", help="不调用 CAD 软件转 DWG（快很多）")
    args = ap.parse_args()

    if args.batch:
        batch(Path(__file__).resolve().parents[2], Path(args.out))
        return
    if not args.table:
        ap.error("需要零件表路径，或用 --batch")
    raw = ftable.load_raw(args.table)
    std = args.standard
    if not std:
        s = raw["part"].get("drawing_setup", {}).get("standard", "GB")
        std = "ASME" if s in ("ASME", "ANSI") else ("ISO" if s in ("ISO", "DIN") else "GB")
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    ans = make(raw, std, out, with_unit=not args.no_unit, scan=not args.no_scan, dwg=not args.no_dwg)
    print(json.dumps({k: ans[k] for k in ("standard", "volume_mm3", "bbox_mm", "files")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
