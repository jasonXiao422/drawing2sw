"""尺寸归属检查：图上的尺寸有没有被分给正确的特征。

一个特征引用了某条观察（evidence_refs），那条观察里的数字应该能在这个特征的参数里找到：
直接写的值、孔距、到外轮廓的定位距离、回转轮廓的直径和台阶长度等。找不到，多半是尺寸分错了特征。
反过来，图上的尺寸没有被任何特征引用，可能漏了特征，也可能这个尺寸是参考尺寸。

这只是一致性检查：数值能对上不代表一定分对（两个特征可能刚好同一个数）。
所有长度按特征表单位（part.units），和图上写的数一致，不换算。
"""
from __future__ import annotations

import math
import re

_NUM = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?|[.,]\d+)")
_SKIP_KEYS = {"meta", "id", "type", "plane", "direction", "kind", "edges", "shape", "x_dir", "normal"}
def numbers_in(text: str) -> list[float]:
    """标注文字里的数字。'4× Ø9 THRU' -> [4, 9]；'.375' -> [0.375]；'12,5' -> [12.5]。"""
    out = []
    for m in _NUM.finditer(text or ""):
        s = m.group(1).replace(",", ".")
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


def primary_value(text: str) -> float | None:
    """标注的主数值：'4× Ø9 THRU' -> 9；'Ø20 H7' -> 20；'1 X 45°' -> 1。解析规则在 callouts.py。"""
    import callouts
    return callouts.primary_value(callouts.parse(text))


def looks_like_dimension(text: str) -> bool:
    """尺寸或孔、槽、倒角、圆角标注。形位公差、标题栏文字不算。"""
    import callouts
    return callouts.parse(text)["kind"] not in ("unknown", "gdt")


def _leaves(x, key=None, out=None):
    out = [] if out is None else out
    if key in _SKIP_KEYS:
        return out
    if isinstance(x, bool):
        return out
    if isinstance(x, (int, float)) and math.isfinite(x):
        out.append(abs(float(x)))
    elif isinstance(x, dict):
        for k, v in x.items():
            _leaves(v, k, out)
    elif isinstance(x, list):
        for v in x:
            _leaves(v, key, out)
    return out


def _chain(values: list[float], start: float | None = None) -> list[float]:
    """一组坐标能产生的距离：相邻差、首尾差，以及到基准的距离。"""
    vs = sorted(set(round(v, 9) for v in values))
    out = [b - a for a, b in zip(vs, vs[1:])]
    if len(vs) > 1:
        out.append(vs[-1] - vs[0])
    if start is not None:
        out += [abs(v - start) for v in vs]
    return out


def _profile_extent(profile: dict) -> tuple[float, float, float, float] | None:
    if not isinstance(profile, dict):
        return None
    shape = profile.get("shape")
    cu, cv = (profile.get("center") or [0, 0])[:2]
    if shape == "rect":
        w, h = profile.get("width", 0), profile.get("height", 0)
        return cu - w / 2, cu + w / 2, cv - h / 2, cv + h / 2
    if shape == "circle":
        r = profile.get("diameter", 0) / 2
        return cu - r, cu + r, cv - r, cv + r
    pts = profile.get("points")
    if isinstance(pts, list) and pts and all(isinstance(p, (list, tuple)) and len(p) >= 2
                                             and all(isinstance(c, (int, float)) for c in p[:2]) for p in pts):
        us, vs = [p[0] for p in pts], [p[1] for p in pts]
        return min(us), max(us), min(vs), max(vs)
    return None


def _extent(profile) -> tuple[float, float, float, float] | None:
    """轮廓的 (u0, u1, v0, v1)。path、tangent_loop 用 ftable 展开后的点。"""
    e = _profile_extent(profile)
    if e is not None or not isinstance(profile, dict):
        return e
    try:
        import ftable
        import geom2d
        pts = ftable.profile_points(ftable._resolve_profile(profile, geom2d), n_circle=72)
        return min(q[0] for q in pts), max(q[0] for q in pts), min(q[1] for q in pts), max(q[1] for q in pts)
    except Exception:  # noqa: BLE001
        return None


def feature_numbers(feature: dict, table: dict | None = None) -> list[float]:
    """这个特征"用到"的所有数：直接参数 + 常见标注方式能推出的距离。"""
    nums = _leaves(feature)
    base = None
    if table:
        feats = table.get("features", [])
        base = feats[0] if feats and feats[0] is not feature else None
    ext = _extent(base.get("profile")) if base and base.get("plane") == feature.get("plane", base.get("plane")) else None
    datum_u = datum_v = None
    if ext:
        datum_u, datum_v = ext[0], ext[2]
        if base.get("profile", {}).get("shape") == "circle":
            datum_u, datum_v = (base["profile"].get("center") or [0, 0])[:2]

    positions = feature.get("positions")
    if isinstance(positions, list) and positions:
        pts = [p for p in positions if isinstance(p, (list, tuple)) and len(p) >= 2
               and all(isinstance(c, (int, float)) for c in p[:2])]
        nums += _chain([p[0] for p in pts], datum_u) + _chain([p[1] for p in pts], datum_v)
        nums.append(float(len(positions)))
        if ext:
            nums += [abs(ext[1] - p[0]) for p in pts] + [abs(ext[3] - p[1]) for p in pts]
    bc = feature.get("bolt_circle")
    if isinstance(bc, dict):
        c = bc.get("center") or [0, 0]
        if datum_u is not None:
            nums += [abs(c[0] - datum_u), abs(c[1] - datum_v)]
    pe = _extent(feature.get("profile")) if feature is not base else None
    if pe and ext:
        u0, u1, v0, v1 = pe
        cu, cv = (u0 + u1) / 2, (v0 + v1) / 2   # 圆孔、对称槽常标到中心
        nums += [abs(u0 - datum_u), abs(v0 - datum_v), abs(ext[1] - u1), abs(ext[3] - v1),
                 abs(cu - datum_u), abs(cv - datum_v), abs(ext[1] - cu), abs(ext[3] - cv),
                 abs(u0 - ext[0]), abs(v0 - ext[2])]
    if pe:
        nums += [pe[1] - pe[0], pe[3] - pe[2]]
    hp = feature.get("half_profile")
    if isinstance(hp, list) and hp:
        rs = [p[0] for p in hp if isinstance(p, (list, tuple)) and len(p) >= 2]
        hs = [p[1] for p in hp if isinstance(p, (list, tuple)) and len(p) >= 2]
        nums += [2 * r for r in rs] + _chain(hs)
    # 高度：草图所在高度、拉伸到的高度（offset + depth），主视图常这样标
    off, dep = feature.get("offset"), feature.get("depth")
    if isinstance(off, (int, float)):
        nums.append(abs(off))
        if isinstance(dep, (int, float)):
            nums += [abs(off + dep), abs(off - dep)]
    if isinstance(dep, (int, float)) and table:
        base_dep = (table.get("features") or [{}])[0].get("depth")
        if isinstance(base_dep, (int, float)) and feature is not table["features"][0]:
            nums.append(abs(base_dep - dep))   # 从顶面往下切 dep，剩下的高度
    # path / tangent_loop 轮廓：展开后的真实外形（含圆角、切线）
    prof = feature.get("profile")
    if isinstance(prof, dict) and prof.get("shape") in ("path", "tangent_loop", "polygon"):
        try:
            import ftable
            import geom2d
            pts = ftable.profile_points(ftable._resolve_profile(prof, geom2d), n_circle=72)
            us, vs = [q[0] for q in pts], [q[1] for q in pts]
            nums += [max(us) - min(us), max(vs) - min(vs), max(abs(u) for u in us), max(abs(v) for v in vs)]
        except Exception:  # noqa: BLE001  展开失败由 validate 报，这里不重复
            pass
    # 直径写成 R 标注时（R1.5 对应直径 3 的圆）
    for key in ("diameter",):
        for holder in (feature, feature.get("profile") or {}, feature.get("cbore") or {}, feature.get("csink") or {}):
            if isinstance(holder.get(key), (int, float)):
                nums.append(holder[key] / 2)
    if feature.get("type") == "edge_treatment" and isinstance(feature.get("size"), (int, float)):
        nums.append(45.0)  # 1 X 45° 倒角
    return nums


def contains(nums: list[float], value: float, rel: float = 1e-3, abs_tol: float = 1e-6) -> bool:
    return any(abs(n - value) <= max(abs_tol, rel * max(abs(value), 1e-9)) for n in nums)


def check(table: dict, doc: dict) -> tuple[list[str], dict]:
    """返回 (警告列表, 统计)。doc 是 observations 证据文件。"""
    warnings = []
    lookup = {o["id"]: o for o in doc.get("observations", [])}
    cited = set()
    mismatched = 0
    for f in table.get("features", []):
        refs = (f.get("meta") or {}).get("evidence_refs", [])
        nums = feature_numbers(f, table)
        for ref in refs:
            cited.add(ref)
            o = lookup.get(ref)
            if not o or not looks_like_dimension(o.get("text", "")):
                continue
            value = primary_value(o["text"])
            if value and not contains(nums, value):
                mismatched += 1
                warnings.append(f"[{f.get('id')}] 引用了 {ref}「{o['text']}」，但这个特征的参数里找不到这个数，"
                                "检查尺寸是不是分错了特征")
    not_geometry = ("text", "label", "title_block_label", "title_block_value", "datum_definition",
                    "view_heading", "view_reference", "feature_control_frame")
    uncited = [o for o in doc.get("observations", [])
               if o["id"] not in cited and o.get("kind") not in not_geometry
               and not str(o.get("kind", "")).startswith("projection") and looks_like_dimension(o.get("text", ""))]
    uncited += [o for o in doc.get("observations", [])
                if o["id"] not in cited and o.get("kind") == "text" and looks_like_dimension(o.get("text", ""))
                and o.get("provider") in ("pdf_text", "paddleocr", "ocr")]
    if uncited:
        shown = "、".join(f"{o['id']}「{o['text']}」" for o in uncited[:12])
        more = f" 等 {len(uncited)} 条" if len(uncited) > 12 else ""
        warnings.append(f"这些像尺寸的标注没有被任何特征引用：{shown}{more}。"
                        "确认是不是漏了特征，或者它是参考尺寸 / 公差 / 比例")
    return warnings, {"cited_dimension_mismatches": mismatched, "uncited_dimensions": len(uncited)}
