"""校验特征表：先过 JSON Schema，再做工程规则检查。

用法: python validate_feature_table.py part.json [--json]
退出码: 0 = 无 ERROR, 1 = 有 ERROR
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import jsonschema

import ftable

try:  # 底孔数据统一放在 standards/gb.json，查不到时退回内置的几个
    import standards as _std
    TAP_DRILL = {r[0]: r[2] for r in _std._table("tap_drill_coarse")["rows"]}
except Exception:  # noqa: BLE001
    TAP_DRILL = {"M3": 2.5, "M4": 3.3, "M5": 4.2, "M6": 5.0, "M8": 6.8,
                 "M10": 8.5, "M12": 10.2, "M16": 14.0, "M20": 17.5}
REVIEW_THRESHOLD = 0.9
RASTER_MAX_CONF = 0.85


def _segments_intersect(p1, p2, p3, p4) -> bool:
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def check_polygon(pts, label, errors):
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
            errors.append(f"{label}: 第 {i} 和第 {(i + 1) % n} 个点重合（零长度边）")
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _segments_intersect(pts[i], pts[(i + 1) % n], pts[j], pts[(j + 1) % n]):
                errors.append(f"{label}: 边 {i} 与边 {j} 自相交")
    area = 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                     for i in range(n))
    if abs(area) < 1e-6:
        errors.append(f"{label}: 轮廓面积为 0")


# 各标准默认的投影法。JIS 现行以第三角为主。
STD_PROJECTION = {"GB": "first_angle", "ISO": "first_angle", "DIN": "first_angle",
                  "ANSI": "third_angle", "ASME": "third_angle", "JIS": "third_angle"}
# 按单位判断"零件尺寸是否离谱"的范围（图纸单位下的最大尺寸）
SANE_SIZE = {"mm": (10, 5000), "cm": (1, 500), "m": (0.01, 5), "inch": (0.4, 200)}
# 依据原文里出现这些词，说明图纸是这个单位
UNIT_WORDS = {"inch": ("inch", "英寸", " in.", "\""), "mm": ("mm", "毫米", "millimet")}


def _raw_max_length(table: dict) -> float:
    """特征表里最大的长度数值（图纸单位），用来粗查单位是否填错。"""
    vals = []
    for f in table["features"]:
        pr = f.get("profile", {})
        vals += [pr.get(k, 0) for k in ("width", "height", "diameter")]
        vals += [abs(c) for p in pr.get("points", []) for c in p]
        vals += [abs(c) for p in f.get("half_profile", []) for c in p]
        if isinstance(f.get("depth"), (int, float)):
            vals.append(f["depth"])
    return max(vals or [0])


def check_setup(table: dict, errors: list[str], warnings: list[str]) -> None:
    """图纸基础设定：单位、标准、投影法。读尺寸之前必须先定好。"""
    part = table["part"]
    ds = part["drawing_setup"]
    unit = ds["length_unit"]
    if part["units"] != unit:
        errors.append(f"part.units={part['units']} 和 drawing_setup.length_unit={unit} 不一致。"
                      "特征表里的数值必须和图纸同一单位，不要自己换算")
    ev = ds.get("unit_evidence", "")
    ev_l = ev.lower()
    said = {u for u, words in UNIT_WORDS.items() if any(w in ev_l for w in words)}
    if said and unit not in said:
        errors.append(f"unit_evidence 原文说的是 {sorted(said)}（{ev}），但 length_unit 填的是 {unit}")
    if ds["confidence"] < REVIEW_THRESHOLD or any(w in ev for w in ("推断", "无明确", "猜", "assume")):
        warnings.append(f"单位没有明确依据（{unit}，依据: {ev}），必须请用户确认。单位错了整个零件就错了")
    lo, hi = SANE_SIZE[unit]
    size = _raw_max_length(table)
    if size and not (lo <= size <= hi):
        warnings.append(f"最大尺寸 {size:g} {unit} 不太像真实零件，检查单位是否填错（mm 和 inch 相差 25.4 倍）")
    std, proj = ds["standard"], part.get("projection", "unknown")
    want = STD_PROJECTION.get(std)
    if want and proj not in ("unknown", want):
        warnings.append(f"标准 {std} 通常用 {want}，表里是 {proj}。以图上的投影符号为准，请确认")
    if unit == "inch" and std in ("GB", "ISO", "DIN"):
        warnings.append(f"{std} 图纸却用英寸，少见，请确认")
    if ds.get("decimal_separator") == ",":
        warnings.append("图纸用逗号作小数点（如 12,5 = 12.5），确认所有数值已按小数点读")
    dd = ds.get("dual_dimensions", {})
    if dd.get("present") and dd.get("primary") and dd["primary"] != unit:
        errors.append(f"双单位标注的主单位是 {dd['primary']}，但 length_unit 是 {unit}，两者必须一致")


def validate(table: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    schema = ftable.load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    variants = {v["properties"]["type"]["const"]: v
                for v in schema["$defs"]["feature"]["oneOf"]}
    for e in sorted(validator.iter_errors(table), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in e.path) or "(root)"
        inst = e.instance
        # oneOf 的报错不具体：按 type 找到对应的子 schema，给出真正的错误
        if e.validator == "oneOf" and isinstance(inst, dict) and inst.get("type") in variants:
            sub = dict(variants[inst["type"]], **{"$defs": schema["$defs"]})
            for se in jsonschema.Draft202012Validator(sub).iter_errors(inst):
                sloc = "/".join(str(p) for p in se.path)
                errors.append(f"schema @ {loc}{'/' + sloc if sloc else ''} ({inst['type']}): {se.message}")
            continue
        if e.validator == "oneOf" and isinstance(inst, dict) and "type" in inst:
            errors.append(f"schema @ {loc}: 未知特征类型 '{inst['type']}'，可用: {sorted(variants)}")
            continue
        errors.append(f"schema @ {loc}: {e.message}")
    if errors:
        return errors, warnings  # 结构不对时不做后续检查

    check_setup(table, errors, warnings)
    if errors:
        return errors, warnings

    try:  # 展开意图写法（拐角倒圆、切线连接、交点、沉孔钻尖），算不出来就是读图或写法有错
        table = ftable.resolve(table)
    except ValueError as e:
        errors.append(f"展开失败 {e}")
        return errors, warnings
    table = ftable.to_mm(table)  # 以下几何规则统一在 mm 下检查
    part, feats = table["part"], table["features"]

    # 基体
    bases = [f for f in feats if f["type"] in ("base_extrude", "base_revolve")]
    if len(bases) != 1:
        errors.append(f"必须恰好有 1 个基体特征，现在有 {len(bases)} 个")
    elif feats[0] is not bases[0]:
        errors.append("基体特征必须排在第一个")
    else:
        want = "base_revolve" if part["part_type"] == "revolved" else "base_extrude"
        if bases[0]["type"] != want:
            warnings.append(f"part_type={part['part_type']} 但基体是 {bases[0]['type']}，确认零件类型")

    # id 唯一
    ids = [f["id"] for f in feats]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        errors.append(f"特征 id 重复: {sorted(dup)}")

    max_r = None
    for f in feats:
        label = f"[{f['id']}]"
        if f["type"] == "base_revolve":
            pts = f["half_profile"]
            if any(p[0] < 0 for p in pts):
                errors.append(f"{label} half_profile 有 r < 0 的点，轮廓不能跨过轴线")
            check_polygon(pts, label, errors)
            max_r = max(p[0] for p in pts)
        if "profile" in f and f["profile"]["shape"] == "polygon":
            check_polygon(f["profile"]["points"], label, errors)
        if "profile" in f and f["profile"]["shape"] == "path":
            errors += [f"{label} {m}" for m in ftable.path_check(f["profile"])]
            check_polygon(ftable.profile_points(f["profile"]), label, errors)
        if f["type"] == "revolve":
            (a1, a2) = f["axis"]
            if math.dist(a1, a2) < 1e-6:
                errors.append(f"{label} 旋转轴两个点重合")
            else:
                pts = ftable.profile_points(f["profile"]) if f["profile"]["shape"] != "circle" else []
                ax, ay = a2[0] - a1[0], a2[1] - a1[1]
                sides = {(ax * (p[1] - a1[1]) - ay * (p[0] - a1[0])) > 1e-6 for p in pts} - {None}
                signs = [ax * (p[1] - a1[1]) - ay * (p[0] - a1[0]) for p in pts]
                if signs and min(signs) < -1e-6 and max(signs) > 1e-6:
                    errors.append(f"{label} 旋转轮廓跨过了旋转轴，SolidWorks 会失败")
        if isinstance(f.get("plane"), dict):
            pl = f["plane"]
            dot = sum(a * b for a, b in zip(pl["normal"], pl["x_dir"]))
            nn = sum(a * a for a in pl["normal"]) ** 0.5
            if nn < 1e-9:
                errors.append(f"{label} 斜面 normal 是零向量")
            elif abs(dot) > 1e-6 * nn * max(1e-9, sum(a * a for a in pl["x_dir"]) ** 0.5):
                warnings.append(f"{label} 斜面 x_dir 和 normal 不垂直，脚本会自动去掉法向分量")

        if f["type"] == "hole":
            pts = ftable.hole_positions(f)
            if len(set((round(u, 6), round(v, 6)) for u, v in pts)) != len(pts):
                errors.append(f"{label} 有重复的孔位")
            if max_r is not None and f["plane"] == "top":
                for u, v in pts:
                    if (u * u + v * v) ** 0.5 + f["diameter"] / 2 > max_r + 1e-6:
                        warnings.append(f"{label} 孔 ({u:.2f},{v:.2f}) 超出回转体最大半径 {max_r}")
            th = f.get("thread")
            if th:
                key = th.split("x")[0].upper()
                if key in TAP_DRILL and abs(TAP_DRILL[key] - f["diameter"]) > 0.05:
                    warnings.append(f"{label} 螺纹 {th} 的粗牙底孔应为 {TAP_DRILL[key]}，表里是 {f['diameter']}（细牙可忽略）")

        if f["type"] == "spur_gear_teeth":
            if not bases or bases[0]["type"] != "base_revolve":
                errors.append(f"{label} 轮齿只能切在回转体轮坯（base_revolve）上")
            else:
                g = ftable.gear_params(f)
                if g["rf"] <= 0:
                    errors.append(f"{label} 齿根圆半径 ≤ 0，参数不对")
                if max_r is not None and abs(g["ra"] - max_r) > 0.05:
                    warnings.append(f"{label} 齿顶圆 da = {2 * g['ra']:g}，轮坯最大直径是 {2 * max_r:g}，不一致。"
                                    "检查模数、齿数、变位系数或轮坯外径")
                z_min = 2 * f.get("addendum_coef", 1) / math.sin(math.radians(f.get("pressure_angle", 20))) ** 2
                if f["teeth"] < z_min * (1 - f.get("shift_coef", 0)):
                    warnings.append(f"{label} 齿数 {f['teeth']} 少于不根切最少齿数 {z_min:.0f}，实际齿轮会根切，"
                                    "当前齿形在基圆以下用径向直线近似，和真实齿形有差别")
        conf = f["meta"]["confidence"]
        if conf < REVIEW_THRESHOLD or f["meta"].get("needs_review"):
            warnings.append(f"{label} 需要用户确认 (confidence={conf}): {f['meta'].get('evidence', '')}")
        fmt_ = part.get("source", {}).get("format")
        if fmt_ == "raster" and conf > RASTER_MAX_CONF:
            warnings.append(f"{label} 扫描图来源的置信度不应超过 {RASTER_MAX_CONF}")
        if fmt_ == "vector_pdf_notext" and conf > 0.9:
            warnings.append(f"{label} 没有文字层的 PDF，尺寸是看图读的，置信度不应超过 0.9")

    if part.get("projection", "unknown") == "unknown":
        warnings.append("投影法未知：非对称零件可能建成镜像，请用户确认")
    for q in table.get("open_questions", []):
        warnings.append(f"待确认问题: {q}")

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    errors, warnings = validate(ftable.load_raw(args.path))
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings},
                         ensure_ascii=False, indent=2))
    else:
        for e in errors:
            print("ERROR  ", e)
        for w in warnings:
            print("WARNING", w)
        print("通过" if not errors else f"未通过：{len(errors)} 个错误")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
