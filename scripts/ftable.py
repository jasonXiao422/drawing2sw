"""特征表公共工具：读取、默认值、孔位展开、基准面坐标换算。

所有建模后端（CadQuery 预览、SolidWorks）都通过这里取数据，保证两边解释一致。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "feature_table.schema.json"

# 基准面约定，见 references/coordinates.md
# origin 偏移方向 = normal；草图 (u, v) -> 模型 = u * x_dir + v * y_dir
PLANES = {
    "front": {"normal": (0, 0, 1), "x_dir": (1, 0, 0), "y_dir": (0, 1, 0)},
    "top": {"normal": (0, 1, 0), "x_dir": (1, 0, 0), "y_dir": (0, 0, -1)},
    "right": {"normal": (1, 0, 0), "x_dir": (0, 0, -1), "y_dir": (0, 1, 0)},
}


# 换算到 mm 的系数。单位换算只在这里做一次，AI 和后端都不做换算（见 references/units-standards.md）
UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "inch": 25.4}


def load_raw(path: str | Path) -> dict:
    """原样读入，数值是图纸单位。校验 schema 时用。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load(path: str | Path) -> dict:
    """读入，展开意图写法，统一换算成 mm。建模、预览、校验几何都用这个。"""
    return to_mm(resolve(load_raw(path)))


# ---------------------------------------------------------------- 意图写法展开（v0.4）
# AI 在特征表里只写图上标的东西（拐角 R5、两圆相切、交点、沉孔、钻尖），切点和圆心由这里算。
# 展开后只剩 v0.3 的基本写法，预览和 SolidWorks 后端不用改。在图纸单位下展开，之后再 to_mm。

def resolve(table: dict) -> dict:
    import geom2d  # noqa: PLC0415

    out = json.loads(json.dumps(table))
    feats = []
    for f in out["features"]:
        label = f"[{f.get('id')}]"
        try:
            if isinstance(f.get("profile"), dict):
                f["profile"] = _resolve_profile(f["profile"], geom2d)
            if f.get("type") == "hole" and any(k in f for k in ("tip_angle", "cbore", "csink")):
                feats += _expand_hole(f)
                continue
        except ValueError as e:
            raise ValueError(f"{label} {e}") from e
        feats.append(f)
    # 阵列 / 镜像引用的孔如果展开成了多个特征（沉孔、钻尖），展开出的部分一起复制
    ids = [g.get("id") for g in feats]
    for f in feats:
        if f.get("type") in ("linear_pattern", "mirror"):
            f["features"] = [i for r in f["features"]
                             for i in ([j for j in ids if j == r or str(j).startswith(r + "__")] or [r])]
    out["features"] = feats
    return out


def _resolve_point(p, g, what):
    if isinstance(p, dict):
        objs = p.get("intersect")
        if not objs or len(objs) != 2:
            raise ValueError(f"{what}: 点对象要写成 {{\"intersect\": [对象1, 对象2], \"near\": [u, v]}}")
        return list(g.pick_near(g.intersect(g.parse_obj(objs[0]), g.parse_obj(objs[1])), p.get("near"),
                                f"{what} 的交点"))
    return list(p)


def _resolve_profile(pr: dict, g) -> dict:
    if pr.get("shape") == "tangent_loop":
        cs = [{"center": _resolve_point(c["center"], g, f"第 {i + 1} 个圆的圆心"), "r": c["r"],
               "convex": c.get("convex", True)} for i, c in enumerate(pr["circles"])]
        start, segs = g.tangent_loop(cs)
        return {"shape": "path", "start": [round(c, 6) for c in start], "segments": [s.to_json() for s in segs]}
    if pr.get("shape") != "path":
        return pr
    raw = pr["segments"]
    if not any(isinstance(pr["start"], dict) or "radius" in s or "fillet" in s or isinstance(s["to"], dict)
               or isinstance(s.get("center"), dict) for s in raw):
        return pr  # 纯 v0.3 写法，原样返回
    start = _resolve_point(pr["start"], g, "start")
    segs, cur = [], start
    for i, s in enumerate(raw):
        to = _resolve_point(s["to"], g, f"第 {i + 1} 段 to")
        ccw = s.get("ccw", True)
        if "center" in s:
            c = _resolve_point(s["center"], g, f"第 {i + 1} 段 center")
        elif "radius" in s:
            c = g.arc_center(cur, to, s["radius"], ccw, s.get("large", False))
        else:
            c = None
        segs.append(g.Seg(cur, to, c, ccw))
        cur = to
    n = len(segs)
    if math.dist(cur, start) > 1e-6:
        raise ValueError(f"path 没有闭合：终点 {cur} 不等于起点 {start}")
    fil = {}
    for i, s in enumerate(raw):
        if s.get("fillet"):
            try:
                fil[i] = g.fillet_corner(segs[i], segs[(i + 1) % n], s["fillet"])
            except ValueError as e:
                raise ValueError(f"第 {i + 1} 段末端: {e}") from e
    seq = []
    for i, s in enumerate(segs):
        seq.append(s)
        if i in fil:
            seq.append(fil[i])
    seq = _merge_segs(seq, g)
    return {"shape": "path", "start": [round(c, 6) for c in seq[0].p0], "segments": [s.to_json() for s in seq]}


def _merge_segs(seq: list, g) -> list:
    """相邻两段同圆同向的圆弧、或共线的直线合成一段。起点放在圆弧中间会把一段弧切成两段，
    多出的顶点会让 CadQuery 布尔运算出错（003 实测：r150_refill 加料变成 0）。"""
    def same(a, b):
        if a.is_arc != b.is_arc:
            return False
        if a.is_arc:
            return (a.ccw == b.ccw and math.dist(a.center, b.center) < 1e-6
                    and abs(math.dist(a.p0, a.center) - math.dist(b.p0, b.center)) < 1e-6)
        da, db = g.line(a.p0, a.p1)["d"], g.line(b.p0, b.p1)["d"]
        return abs(da[0] * db[1] - da[1] * db[0]) < 1e-9 and da[0] * db[0] + da[1] * db[1] > 0

    out = list(seq)
    changed = True
    while changed and len(out) > 2:
        changed = False
        for i in range(len(out)):
            a, b = out[i], out[(i + 1) % len(out)]
            if same(a, b) and (not a.is_arc or a.sweep() + b.sweep() < 2 * math.pi - 1e-6):
                merged = g.Seg(a.p0, b.p1, a.center, a.ccw)
                if i + 1 < len(out):
                    out[i:i + 2] = [merged]
                else:  # 最后一段和第一段合并，起点挪到 a.p0
                    out = [merged] + out[1:-1]
                changed = True
                break
    return out


def _expand_hole(f: dict) -> list[dict]:
    """沉孔 cbore、埋头孔 csink、钻头锥尖 tip_angle 展开成 hole + revolve 切除。"""
    f = dict(f)
    tip, cb, cs = f.pop("tip_angle", None), f.pop("cbore", None), f.pop("csink", None)
    d_ = f.get("direction", "both")
    if d_ == "both":
        raise ValueError("带沉孔 / 埋头孔 / 钻尖的孔要写 direction（positive 或 negative），从哪个面钻进去")
    meta = f["meta"]
    out = []
    if cb:
        out.append(dict(f, id=f"{f['id']}__cbore", diameter=cb["diameter"], depth=cb["depth"], meta=meta))
    out.append(f)
    plane, off = f["plane"], f.get("offset", 0.0)
    fr = plane_frame(plane, off)
    sgn = 1 if d_ == "positive" else -1
    dvec = tuple(sgn * c for c in fr["normal"])
    # 旋转切除画在"包含孔轴线、法向 = 孔所在面 y_dir"的平面上；能用默认基准面就用默认的
    std = next((k for k, p in PLANES.items()
                if abs(abs(sum(a * b for a, b in zip(p["normal"], fr["y_dir"]))) - 1) < 1e-9), None)
    R = f["diameter"] / 2
    pieces = []
    if tip:
        if f["depth"] == "through_all":
            raise ValueError("通孔没有钻尖，去掉 tip_angle")
        h = R / math.tan(math.radians(tip) / 2)
        D = f["depth"]
        # 只画锥体三角形。以前多画一段和孔壁重合的 0.5 圆柱带，曲面重合让 CadQuery 布尔算错体积（006 实测，DEVELOPING.md #33）
        pieces.append(("tip", [(0, D), (R, D), (0, D + h)]))
    if cs:
        Rc = cs["diameter"] / 2
        ang = math.radians(cs.get("angle", 90)) / 2
        hc = (Rc - R) / math.tan(ang)
        pieces.append(("csink", [(0, -1), (Rc + math.tan(ang), -1), (R, hc), (0, hc)]))
    for k, (u, v) in enumerate(hole_positions(f)):
        P = tuple(fr["origin"][i] + u * fr["x_dir"][i] + v * fr["y_dir"][i] for i in range(3))
        if std:
            sp = std
            soff = sum(a * b for a, b in zip(P, PLANES[std]["normal"]))
        else:
            sp = {"origin": list(P), "normal": list(fr["y_dir"]), "x_dir": list(fr["x_dir"])}
            soff = 0.0
        sf = plane_frame(sp, soff)

        def uv(r, t):
            X = [P[i] + t * dvec[i] + r * fr["x_dir"][i] for i in range(3)]
            w = [X[i] - sf["origin"][i] for i in range(3)]
            return [round(sum(a * b for a, b in zip(w, sf["x_dir"])), 6),
                    round(sum(a * b for a, b in zip(w, sf["y_dir"])), 6)]

        for name, prof in pieces:
            out.append({"id": f"{f['id']}__{name}{k + 1}", "type": "revolve", "plane": sp, "offset": soff,
                        "axis": [uv(0, 0), uv(0, 1)], "cut": True,
                        "profile": {"shape": "polygon", "points": [uv(r, t) for r, t in prof]},
                        "meta": meta})
    return out


def _scale_pts(pts, k):
    return [[c * k for c in p] for p in pts]


def _scale_profile(pr: dict, k: float) -> dict:
    pr = json.loads(json.dumps(pr))
    if pr.get("shape") == "path":
        pr["start"] = [c * k for c in pr["start"]]
        for sg in pr["segments"]:
            sg["to"] = [c * k for c in sg["to"]]
            if "center" in sg:
                sg["center"] = [c * k for c in sg["center"]]
        return pr
    for key in ("width", "height", "diameter"):
        if key in pr:
            pr[key] = pr[key] * k
    if "center" in pr:
        pr["center"] = [c * k for c in pr["center"]]
    if "points" in pr:
        pr["points"] = _scale_pts(pr["points"], k)
    return pr


def to_mm(table: dict) -> dict:
    """把特征表里所有长度从 part.units 换算成 mm。角度、置信度、part.expected（本来就是 mm）不动。"""
    unit = table["part"].get("units", "mm")
    if unit not in UNIT_TO_MM:
        raise ValueError(f"未知单位 {unit}，可用: {sorted(UNIT_TO_MM)}")
    k = UNIT_TO_MM[unit]
    out = json.loads(json.dumps(table))  # 深拷贝
    out["part"]["units"] = "mm"
    out["part"]["source_units"] = unit
    ds = out["part"].get("drawing_setup")
    if ds:
        for key in ("default_chamfer", "default_fillet"):
            if key in ds:
                ds[key] = ds[key] * k
    if k == 1.0:
        return out
    for f in out["features"]:
        if "profile" in f:
            f["profile"] = _scale_profile(f["profile"], k)
        if isinstance(f.get("plane"), dict):
            f["plane"]["origin"] = [c * k for c in f["plane"]["origin"]]
        if "axis" in f:
            f["axis"] = _scale_pts(f["axis"], k)
        if isinstance(f.get("edges"), dict):
            f["edges"] = {"points": _scale_pts(f["edges"]["points"], k)}
        if "half_profile" in f:
            f["half_profile"] = _scale_pts(f["half_profile"], k)
        if isinstance(f.get("depth"), (int, float)):
            f["depth"] = f["depth"] * k
        for key in ("offset", "diameter", "size", "module", "spacing", "spacing2"):
            if key in f:
                f[key] = f[key] * k
        if "positions" in f:
            f["positions"] = _scale_pts(f["positions"], k)
        if "bolt_circle" in f:
            bc = dict(f["bolt_circle"])
            bc["pcd"] = bc["pcd"] * k
            if "center" in bc:
                bc["center"] = [c * k for c in bc["center"]]
            f["bolt_circle"] = bc
    return out


def load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def hole_positions(feat: dict) -> list[tuple[float, float]]:
    """返回孔中心的草图坐标列表。positions 与 bolt_circle 可同时存在，结果合并。"""
    pts = [tuple(p) for p in feat.get("positions", [])]
    bc = feat.get("bolt_circle")
    if bc:
        r = bc["pcd"] / 2
        cu, cv = bc.get("center", [0, 0])
        a0 = bc.get("start_angle", 0)
        for i in range(bc["count"]):
            a = math.radians(a0 + 360 * i / bc["count"])
            pts.append((cu + r * math.cos(a), cv + r * math.sin(a)))
    return pts


AXIS_VEC = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0), "+Z": (0, 0, 1), "-Z": (0, 0, -1)}


def pattern_offsets(f: dict) -> list[tuple[float, float, float]]:
    """线性阵列每个复制件相对原特征的平移量 (mm)，不含原特征自己。"""
    d1, n1, s1 = AXIS_VEC[f["direction"]], f["count"], f["spacing"]
    d2, n2, s2 = AXIS_VEC.get(f.get("direction2"), (0, 0, 0)), f.get("count2", 1), f.get("spacing2", 0)
    out = []
    for j in range(n2 if "direction2" in f else 1):
        for i in range(n1):
            if i or j:
                out.append(tuple(i * s1 * a + j * s2 * b for a, b in zip(d1, d2)))
    return out


def mirror_plane(f: dict) -> tuple[tuple, tuple]:
    """镜像面 -> (面上一点, 法向)，模型坐标 mm。"""
    n = PLANES[f["plane"]]["normal"]
    off = float(f.get("offset", 0))
    return tuple(off * c for c in n), tuple(n)


def _unit(a):
    n = math.sqrt(sum(c * c for c in a))
    return tuple(c / n for c in a)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def plane_frame(plane, offset: float = 0.0) -> dict:
    """基准面 -> {origin, normal, x_dir, y_dir}（mm，单位向量）。plane 可以是名字，也可以是任意平面对象。
    y_dir = normal × x_dir，和三个默认基准面的约定一致。offset 沿 normal 平移。"""
    if isinstance(plane, str):
        p = PLANES[plane]
        o, n, x = (0.0, 0.0, 0.0), p["normal"], p["x_dir"]
    else:
        o, n = tuple(plane["origin"]), _unit(plane["normal"])
        x = plane["x_dir"]
        # 去掉 x_dir 里沿法向的分量，保证正交
        dot = sum(a * b for a, b in zip(x, n))
        x = _unit(tuple(a - dot * b for a, b in zip(x, n)))
    y = _cross(n, x)
    o = tuple(o[i] + offset * n[i] for i in range(3))
    return {"origin": o, "normal": tuple(n), "x_dir": tuple(x), "y_dir": y}


def to_model(plane, u: float, v: float, offset: float = 0.0) -> tuple[float, float, float]:
    fr = plane_frame(plane, offset)
    return tuple(fr["origin"][i] + u * fr["x_dir"][i] + v * fr["y_dir"][i] for i in range(3))


def arc_mid(start, seg) -> tuple[float, float]:
    """圆弧段的中点（给三点画弧用）。"""
    cu, cv = seg["center"]
    a0 = math.atan2(start[1] - cv, start[0] - cu)
    a1 = math.atan2(seg["to"][1] - cv, seg["to"][0] - cu)
    r = math.hypot(start[0] - cu, start[1] - cv)
    sweep = (a1 - a0) % (2 * math.pi)
    if not seg.get("ccw", True):
        sweep -= 2 * math.pi
    am = a0 + sweep / 2
    return (cu + r * math.cos(am), cv + r * math.sin(am))


def path_check(profile: dict, tol: float = 1e-3) -> list[str]:
    """检查 path 轮廓：圆弧两端到圆心距离相等，终点回到起点。"""
    errs, cur = [], profile["start"]
    for i, sg in enumerate(profile["segments"]):
        if "center" in sg:
            r0 = math.dist(cur, sg["center"])
            r1 = math.dist(sg["to"], sg["center"])
            if abs(r0 - r1) > tol:
                errs.append(f"第 {i + 1} 段圆弧两端半径不等：{r0:.4f} vs {r1:.4f}")
        cur = sg["to"]
    if math.dist(cur, profile["start"]) > tol:
        errs.append(f"轮廓没有闭合：终点 {cur} 不等于起点 {profile['start']}")
    return errs


def profile_points(profile: dict, n_circle: int = 0) -> list[tuple[float, float]]:
    """把 rect / polygon 轮廓转成点列（circle 返回空，由后端单独处理）。"""
    s = profile["shape"]
    if s == "rect":
        cu, cv = profile.get("center", [0, 0])
        w, h = profile["width"] / 2, profile["height"] / 2
        return [(cu - w, cv - h), (cu + w, cv - h), (cu + w, cv + h), (cu - w, cv + h)]
    if s == "polygon":
        return [tuple(p) for p in profile["points"]]
    if s == "path":  # 圆弧离散成折线，只用于检查和兜底
        pts, cur = [tuple(profile["start"])], tuple(profile["start"])
        for sg in profile["segments"]:
            if "center" in sg:
                cu, cv = sg["center"]
                a0 = math.atan2(cur[1] - cv, cur[0] - cu)
                m = arc_mid(cur, sg)
                am = math.atan2(m[1] - cv, m[0] - cu)
                sweep = 2 * ((am - a0 + math.pi) % (2 * math.pi) - math.pi)
                r = math.dist(cur, sg["center"])
                n = max(4, int(abs(sweep) / math.radians(3)))
                pts += [(cu + r * math.cos(a0 + sweep * j / n), cv + r * math.sin(a0 + sweep * j / n))
                        for j in range(1, n)]
            pts.append(tuple(sg["to"]))
            cur = tuple(sg["to"])
        if math.dist(pts[-1], pts[0]) < 1e-9:
            pts.pop()
        return pts
    return []


def count_holes(table: dict) -> int:
    return sum(len(hole_positions(f)) for f in table["features"] if f["type"] == "hole")


# ---------------------------------------------------------------- 渐开线直齿轮
GEAR_DEFAULTS = {"pressure_angle": 20.0, "addendum_coef": 1.0, "clearance_coef": 0.25,
                 "shift_coef": 0.0, "start_angle": 0.0}


def gear_params(f: dict) -> dict:
    """齿轮基本尺寸 (mm)。国标 GB/T 1356 基本齿廓。"""
    g = {**GEAR_DEFAULTS, **f}
    m, z = g["module"], g["teeth"]
    a = math.radians(g["pressure_angle"])
    ha, c, x = g["addendum_coef"], g["clearance_coef"], g["shift_coef"]
    r = m * z / 2
    return {"m": m, "z": z, "alpha": a, "r": r, "rb": r * math.cos(a),
            "ra": r + m * (ha + x), "rf": r - m * (ha + c - x),
            "s": m * (math.pi / 2 + 2 * x * math.tan(a)),  # 分度圆齿厚
            "start": math.radians(g["start_angle"])}


def _inv(a: float) -> float:
    return math.tan(a) - a


def gear_space_polygons(f: dict, n_flank: int = 16, n_root: int = 6) -> list[list[tuple[float, float]]]:
    """返回 z 个齿槽轮廓（草图坐标 u, v，单位 mm），每个都是闭合点列，切除后就是齿轮。

    齿廓：基圆以上是渐开线；齿根圆小于基圆时，基圆以下用径向直线连到齿根圆。
    齿根过渡圆角（国标 ρf ≈ 0.38m）暂不建，体积差约 0.3%，记在 evidence 里。
    齿槽外侧伸出齿顶圆 2 mm，保证切干净。
    """
    p = gear_params(f)
    r, rb, ra, rf, z = p["r"], p["rb"], p["ra"], p["rf"], p["z"]
    psi = p["s"] / (2 * r)                  # 分度圆上半齿厚对应的角度
    inv_a = _inv(p["alpha"])

    def flank_angle(rho: float) -> float:
        """齿 0 右侧齿廓在半径 rho 处的极角（齿中心线为 0）。"""
        if rho <= rb:
            return psi + inv_a  # 基圆以下：径向直线
        return psi + inv_a - _inv(math.acos(rb / rho))

    r_low = max(rf, rb)
    # 齿 0 的右齿廓，从齿顶往下
    radii = [ra - (ra - r_low) * i / (n_flank - 1) for i in range(n_flank)]
    right = [(rho, flank_angle(rho)) for rho in radii]
    if rf < rb:
        right.append((rf, flank_angle(rb)))
    pitch = 2 * math.pi / z
    a0, a1 = right[-1][1], pitch - right[-1][1]
    root = [(rf, a0 + (a1 - a0) * i / (n_root + 1)) for i in range(1, n_root + 1)]
    left = [(rho, pitch - ang) for rho, ang in reversed(right)]   # 齿 1 的左齿廓，从下往上
    out_r = ra + 2.0
    # 闭合顺序：外伸点 -> 右齿廓 -> 齿根 -> 左齿廓 -> 外伸点
    pts_polar = [(out_r, right[0][1])] + right + root + left + [(out_r, left[-1][1])]

    polys = []
    for k in range(z):
        rot = p["start"] + k * pitch
        polys.append([(rho * math.cos(a + rot), rho * math.sin(a + rot)) for rho, a in pts_polar])
    return polys



def gear_space_profile(f: dict, k: int = 0, n_flank: int = 12) -> dict:
    """第 k 个齿槽的结构化轮廓（草图坐标 u, v，mm），给 CAD 画光滑曲线用：
      right   齿 k 右齿廓的渐开线点（齿顶 -> 下），画样条
      right_radial  齿根圆小于基圆时，基圆到齿根圆的径向直线终点；否则 None
      root    齿根圆弧 {center, start, end, mid}，逆时针从 start 到 end
      left_radial / left   齿 k+1 左齿廓（下 -> 齿顶），画样条
      outer   [左外伸点, 右外伸点]：伸出齿顶圆 2 mm，用直线闭合
    闭合顺序：outer[1] -> right -> (right_radial) -> root -> (left_radial) -> left -> outer[0] -> outer[1]
    """
    p = gear_params(f)
    r, rb, ra, rf, z = p["r"], p["rb"], p["ra"], p["rf"], p["z"]
    psi = p["s"] / (2 * r)
    inv_a = _inv(p["alpha"])
    pitch = 2 * math.pi / z
    rot = p["start"] + k * pitch

    def ang(rho):
        return psi + inv_a - (_inv(math.acos(rb / rho)) if rho > rb else 0.0)

    def xy(rho, a):
        return (rho * math.cos(a + rot), rho * math.sin(a + rot))

    r_low = max(rf, rb)
    radii = [ra - (ra - r_low) * i / (n_flank - 1) for i in range(n_flank)]
    a_low = ang(r_low)
    out_r = ra + 2.0
    a_mid = pitch / 2
    return {
        "right": [xy(rho, ang(rho)) for rho in radii],
        "right_radial": xy(rf, a_low) if rf < rb else None,
        "root": {"center": (0.0, 0.0), "start": xy(rf, a_low), "end": xy(rf, pitch - a_low),
                 "mid": xy(rf, a_mid), "radius": rf},
        "left_radial": xy(rf, pitch - a_low) if rf < rb else None,
        "left": [xy(rho, pitch - ang(rho)) for rho in reversed(radii)],
        "outer": [xy(out_r, pitch - ang(ra)), xy(out_r, ang(ra))],
        "pitch_deg": 360.0 / z,
        "count": z,
    }
