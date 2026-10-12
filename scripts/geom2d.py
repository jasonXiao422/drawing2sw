"""二维草图几何：交点、相切、拐角倒圆、按半径画弧、切线连接的圆。

两种用法：
1. ftable.resolve() 调用，把特征表里的"意图写法"（拐角 R5、R5 和 R14 用切线连、交点）展开成 path 的直线和圆弧。
2. 命令行计算器，给 AI 算特征表写法覆盖不到的点：

   python scripts/geom2d.py intersect "circle:0,0,45" "x:16"
   python scripts/geom2d.py tangent-circle 12 "circle:36,-16,16" "line:30,0,30,-50"
   python scripts/geom2d.py tangent-line "circle:0,15.5,5" "circle:0,0,14"
   python scripts/geom2d.py arc 0,45 16,42 --r 45 --cw

对象写法：circle:cx,cy,r　line:x1,y1,x2,y2　x:a（竖线 u=a）　y:b（横线 v=b）　point:x,y
只依赖标准库。
"""
from __future__ import annotations

import argparse
import json
import math
import sys

EPS = 1e-9
TOL = 1e-6


# ---------------------------------------------------------------- 基本对象
# line:   {"kind": "line", "p": (x, y), "d": 单位方向}
# circle: {"kind": "circle", "c": (x, y), "r": r}

def line(p, q) -> dict:
    d = (q[0] - p[0], q[1] - p[1])
    n = math.hypot(*d)
    if n < EPS:
        raise ValueError(f"直线的两个点重合: {p}")
    return {"kind": "line", "p": tuple(p), "d": (d[0] / n, d[1] / n)}


def circle(c, r) -> dict:
    if r < 0:
        raise ValueError(f"圆半径不能为负: {r}")
    return {"kind": "circle", "c": tuple(c), "r": float(r)}


def parse_obj(o) -> dict:
    """特征表里的对象：{"x": a} {"y": b} {"line": [[x1,y1],[x2,y2]]} {"line": {"through": [x,y], "angle": 度}}
    {"circle": {"center": [x,y], "r": r}}；命令行里的字符串 "circle:cx,cy,r" 等。"""
    if isinstance(o, str):
        kind, _, rest = o.partition(":")
        v = [float(s) for s in rest.split(",")]
        if kind == "x":
            return line((v[0], 0), (v[0], 1))
        if kind == "y":
            return line((0, v[0]), (1, v[0]))
        if kind == "line":
            return line(v[:2], v[2:4])
        if kind == "circle":
            return circle(v[:2], v[2])
        if kind == "point":
            return circle(v[:2], 0)
        raise ValueError(f"不认识的对象: {o}")
    if "x" in o:
        return line((o["x"], 0), (o["x"], 1))
    if "y" in o:
        return line((0, o["y"]), (1, o["y"]))
    if "line" in o:
        ln = o["line"]
        if isinstance(ln, dict):
            a = math.radians(ln["angle"])
            p = ln["through"]
            return line(p, (p[0] + math.cos(a), p[1] + math.sin(a)))
        return line(ln[0], ln[1])
    if "circle" in o:
        return circle(o["circle"]["center"], o["circle"]["r"])
    if "point" in o:
        return circle(o["point"], 0)
    raise ValueError(f"不认识的对象: {o}")


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


# ---------------------------------------------------------------- 交点

def intersect(a: dict, b: dict) -> list[tuple[float, float]]:
    if a["kind"] == "circle" and b["kind"] == "line":
        a, b = b, a
    if a["kind"] == "line" and b["kind"] == "line":
        den = _cross(a["d"], b["d"])
        if abs(den) < EPS:
            return []
        t = _cross(_sub(b["p"], a["p"]), b["d"]) / den
        return [(a["p"][0] + t * a["d"][0], a["p"][1] + t * a["d"][1])]
    if a["kind"] == "line":  # 直线和圆
        c, r = b["c"], b["r"]
        w = _sub(a["p"], c)
        t0 = -(w[0] * a["d"][0] + w[1] * a["d"][1])
        foot = (a["p"][0] + t0 * a["d"][0], a["p"][1] + t0 * a["d"][1])
        h2 = r * r - math.dist(foot, c) ** 2
        if h2 < -TOL:
            return []
        h = math.sqrt(max(h2, 0.0))
        if h < TOL:
            return [foot]
        return [(foot[0] - h * a["d"][0], foot[1] - h * a["d"][1]),
                (foot[0] + h * a["d"][0], foot[1] + h * a["d"][1])]
    # 两圆
    c1, r1, c2, r2 = a["c"], a["r"], b["c"], b["r"]
    d = math.dist(c1, c2)
    if d < EPS or d > r1 + r2 + TOL or d < abs(r1 - r2) - TOL:
        return []
    x = (d * d + r1 * r1 - r2 * r2) / (2 * d)
    h = math.sqrt(max(r1 * r1 - x * x, 0.0))
    ex = ((c2[0] - c1[0]) / d, (c2[1] - c1[1]) / d)
    m = (c1[0] + x * ex[0], c1[1] + x * ex[1])
    if h < TOL:
        return [m]
    return [(m[0] - h * ex[1], m[1] + h * ex[0]), (m[0] + h * ex[1], m[1] - h * ex[0])]


def pick_near(pts, near, what: str = "交点"):
    if not pts:
        raise ValueError(f"{what}不存在（两个对象不相交）")
    if near is None:
        if len(pts) > 1:
            raise ValueError(f"{what}有 {len(pts)} 个: {[_r(p) for p in pts]}，要给 near 指定大概位置")
        return pts[0]
    return min(pts, key=lambda p: math.dist(p, near))


def _r(p, nd: int = 4):
    return [round(c, nd) + 0.0 for c in p]


# ---------------------------------------------------------------- 偏移、垂足

def offsets(o: dict, r: float) -> list[dict]:
    """到 o 距离为 r 的所有曲线。"""
    if o["kind"] == "line":
        n = (-o["d"][1], o["d"][0])
        return [line((o["p"][0] + s * r * n[0], o["p"][1] + s * r * n[1]),
                     (o["p"][0] + s * r * n[0] + o["d"][0], o["p"][1] + s * r * n[1] + o["d"][1]))
                for s in (1, -1)]
    out = [circle(o["c"], o["r"] + r)]
    if abs(o["r"] - r) > TOL:
        out.append(circle(o["c"], abs(o["r"] - r)))
    return out


def foot(o: dict, q) -> tuple[float, float]:
    """q 在 o 上的切点（垂足）。"""
    if o["kind"] == "line":
        w = _sub(q, o["p"])
        t = w[0] * o["d"][0] + w[1] * o["d"][1]
        return (o["p"][0] + t * o["d"][0], o["p"][1] + t * o["d"][1])
    c, r = o["c"], o["r"]
    d = math.dist(q, c)
    if d < EPS:
        raise ValueError("圆角圆心和圆弧圆心重合")
    return (c[0] + r * (q[0] - c[0]) / d, c[1] + r * (q[1] - c[1]) / d)


def tangent_circles(r: float, a: dict, b: dict) -> list[dict]:
    """半径 r、同时和 a、b 相切的所有圆：[{center, t_a, t_b}]。"""
    out = []
    for oa in offsets(a, r):
        for ob in offsets(b, r):
            for q in intersect(oa, ob):
                if any(math.dist(q, s["center"]) < 1e-6 for s in out):
                    continue
                out.append({"center": q, "t_a": foot(a, q), "t_b": foot(b, q)})
    return out


def tangent_lines(a: dict, b: dict) -> list[dict]:
    """两个圆（半径可为 0 表示点）的所有公切线：[{type, t_a, t_b}]。"""
    out = []
    ca, cb = a["c"], b["c"]
    dd = _sub(cb, ca)
    L = math.hypot(*dd)
    if L < EPS:
        return out
    phi = math.atan2(dd[1], dd[0])
    for sa, sb, kind in ((1, 1, "外公切线"), (1, -1, "内公切线")):
        ra, rb = sa * a["r"], sb * b["r"]
        k = (ra - rb) / L
        if abs(k) > 1 + TOL:
            continue
        al = math.acos(max(-1.0, min(1.0, k)))
        for th in {phi - al, phi + al}:
            n = (math.cos(th), math.sin(th))
            ta = (ca[0] + ra * n[0], ca[1] + ra * n[1])
            tb = (cb[0] + rb * n[0], cb[1] + rb * n[1])
            if not any(math.dist(ta, s["t_a"]) < 1e-6 and math.dist(tb, s["t_b"]) < 1e-6 for s in out):
                out.append({"type": kind, "t_a": ta, "t_b": tb})
    return out


def arc_center(p0, p1, r: float, ccw: bool, large: bool = False):
    """过 p0、p1，半径 r 的圆弧的圆心。默认取小于半圆的那段。"""
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    ch = math.dist(p0, p1)
    if ch < EPS:
        raise ValueError("圆弧起点终点重合，按半径定不了圆心")
    h2 = r * r - (ch / 2) ** 2
    if h2 < -TOL:
        raise ValueError(f"半径 R{r} 小于弦长一半 {ch / 2:.4f}，圆弧不存在")
    h = math.sqrt(max(h2, 0.0))
    left = (-(p1[1] - p0[1]) / ch, (p1[0] - p0[0]) / ch)
    s = 1 if ccw != large else -1  # 逆时针小弧：圆心在弦的左边
    return (mx + s * h * left[0], my + s * h * left[1])


# ---------------------------------------------------------------- path 的段

class Seg:
    """path 里的一段。arc 的 ccw 和特征表一致（草图 u-v 里逆时针为 True）。"""

    def __init__(self, p0, p1, center=None, ccw=True):
        self.p0, self.p1 = tuple(p0), tuple(p1)
        self.center = tuple(center) if center is not None else None
        self.ccw = ccw

    @property
    def is_arc(self):
        return self.center is not None

    def geom(self) -> dict:
        if self.is_arc:
            return circle(self.center, math.dist(self.p0, self.center))
        return line(self.p0, self.p1)

    def sweep(self, p=None) -> float:
        """从 p0 沿本段方向走到 p（默认 p1）转过的角度，0 ~ 2π。"""
        p = self.p1 if p is None else p
        a0 = math.atan2(self.p0[1] - self.center[1], self.p0[0] - self.center[0])
        a1 = math.atan2(p[1] - self.center[1], p[0] - self.center[0])
        s = (a1 - a0) % (2 * math.pi) if self.ccw else (a0 - a1) % (2 * math.pi)
        return s

    def contains(self, p, tol: float = 1e-6) -> bool:
        """p（已在本段的直线/圆上）是否落在 p0~p1 之间。"""
        if not self.is_arc:
            L = math.dist(self.p0, self.p1)
            t = ((p[0] - self.p0[0]) * (self.p1[0] - self.p0[0]) + (p[1] - self.p0[1]) * (self.p1[1] - self.p0[1])) / L
            return -tol <= t <= L + tol
        full = self.sweep()
        s = self.sweep(p)
        r = math.dist(self.p0, self.center)
        return s * r <= full * r + tol or (2 * math.pi - s) * r <= tol

    def tangent(self, p) -> tuple[float, float]:
        """在 p 处沿本段前进方向的单位切向。"""
        if not self.is_arc:
            return line(self.p0, self.p1)["d"]
        rx, ry = p[0] - self.center[0], p[1] - self.center[1]
        n = math.hypot(rx, ry)
        return (-ry / n, rx / n) if self.ccw else (ry / n, -rx / n)

    def to_json(self) -> dict:
        out = {"to": _r(self.p1, 6)}
        if self.is_arc:
            out["center"] = _r(self.center, 6)
            out["ccw"] = self.ccw
        return out


def fillet_corner(a: Seg, b: Seg, r: float) -> Seg:
    """a 的终点 = b 的起点处倒 R r。原地缩短 a、b，返回插在中间的圆角弧。凸角、凹角都可以。"""
    v = a.p1
    best = None
    for s in tangent_circles(r, a.geom(), b.geom()):
        ta, tb = s["t_a"], s["t_b"]
        if not (a.contains(ta) and b.contains(tb)):
            continue
        cost = math.dist(ta, v) + math.dist(tb, v)
        if best is None or cost < best[0]:
            best = (cost, s)
    if best is None:
        raise ValueError(f"拐角 {_r(v)} 倒不了 R{r}：相邻两段太短，或者半径太大")
    s = best[1]
    q, ta, tb = s["center"], s["t_a"], s["t_b"]
    ccw = _cross(_sub(ta, q), a.tangent(ta)) > 0
    a.p1, b.p0 = ta, tb
    return Seg(ta, tb, q, ccw)


# ---------------------------------------------------------------- 切线连接的一圈圆

def tangent_loop(circles: list[dict]) -> tuple[list[float], list[dict]]:
    """一圈圆依次用切线连起来（耳板、连杆、腰形槽、凸轮外形）。
    circles: [{"center": [x,y], "r": r, "convex": True}]，r=0 是尖角点；convex=False 是往里凹的圆弧。
    按逆时针排；排反了自动倒过来。返回 (start, segments)。"""
    if len(circles) < 2:
        raise ValueError("tangent_loop 至少要 2 个圆")

    def build(cs):
        n = len(cs)
        outs, ins = [None] * n, [None] * n
        for i in range(n):
            j = (i + 1) % n
            ca, cb = cs[i]["center"], cs[j]["center"]
            ra = cs[i]["r"] * (1 if cs[i].get("convex", True) else -1)
            rb = cs[j]["r"] * (1 if cs[j].get("convex", True) else -1)
            dd = _sub(cb, ca)
            L = math.hypot(*dd)
            if L < EPS:
                raise ValueError(f"第 {i + 1}、{j + 1} 个圆圆心重合")
            k = (ra - rb) / L
            if abs(k) > 1 + TOL:
                raise ValueError(f"第 {i + 1}、{j + 1} 个圆没有这种切线（一个圆包住了另一个）")
            # 逆时针一圈的外法向在前进方向右边；凸圆的切点 = 圆心 + r * 外法向
            th = math.atan2(dd[1], dd[0]) - math.acos(max(-1.0, min(1.0, k)))
            nv = (math.cos(th), math.sin(th))
            outs[i] = (ca[0] + ra * nv[0], ca[1] + ra * nv[1])
            ins[j] = (cb[0] + rb * nv[0], cb[1] + rb * nv[1])
        segs = []
        for i in range(n):
            j = (i + 1) % n
            segs.append(Seg(outs[i], ins[j]))
            if cs[j]["r"] > TOL and math.dist(ins[j], outs[j]) > 1e-9:
                segs.append(Seg(ins[j], outs[j], cs[j]["center"], cs[j].get("convex", True)))
        return outs[0], segs

    start, segs = build(circles)
    if signed_area(start, segs) < 0:
        start, segs = build(list(reversed(circles)))
    return list(start), segs


def signed_area(start, segs: list[Seg], n_arc: int = 64) -> float:
    pts = [tuple(start)]
    for s in segs:
        if s.is_arc:
            sw = s.sweep()
            a0 = math.atan2(s.p0[1] - s.center[1], s.p0[0] - s.center[0])
            r = math.dist(s.p0, s.center)
            sg = 1 if s.ccw else -1
            pts += [(s.center[0] + r * math.cos(a0 + sg * sw * k / n_arc),
                     s.center[1] + r * math.sin(a0 + sg * sw * k / n_arc)) for k in range(1, n_arc)]
        pts.append(s.p1)
    return sum(_cross(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))) / 2


# ---------------------------------------------------------------- 命令行

def _fmt(obj):
    if isinstance(obj, tuple):
        return _r(obj)
    if isinstance(obj, list):
        return [_fmt(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _fmt(v) for k, v in obj.items()}
    return obj


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="草图几何计算器（结果是草图 u-v 坐标）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("intersect", help="两个对象的交点")
    p.add_argument("a")
    p.add_argument("b")
    p = sub.add_parser("tangent-circle", help="半径 R、同时和两个对象相切的圆（相切圆弧、圆角）")
    p.add_argument("r", type=float)
    p.add_argument("a")
    p.add_argument("b")
    p = sub.add_parser("tangent-line", help="两个圆（或点和圆）的公切线")
    p.add_argument("a")
    p.add_argument("b")
    p = sub.add_parser("arc", help="过两点、给定半径的圆弧圆心")
    p.add_argument("p0")
    p.add_argument("p1")
    p.add_argument("--r", type=float, required=True)
    p.add_argument("--cw", action="store_true", help="顺时针（默认逆时针）")
    p.add_argument("--large", action="store_true", help="大于半圆的那段")
    args = ap.parse_args()

    if args.cmd == "intersect":
        res = intersect(parse_obj(args.a), parse_obj(args.b))
    elif args.cmd == "tangent-circle":
        res = [{"center": s["center"], "切点_a": s["t_a"], "切点_b": s["t_b"]}
               for s in tangent_circles(args.r, parse_obj(args.a), parse_obj(args.b))]
    elif args.cmd == "tangent-line":
        a, b = parse_obj(args.a), parse_obj(args.b)
        if a["kind"] != "circle" or b["kind"] != "circle":
            raise SystemExit("tangent-line 只接受 circle: 或 point:")
        res = [{"类型": s["type"], "切点_a": s["t_a"], "切点_b": s["t_b"]} for s in tangent_lines(a, b)]
    else:
        p0 = [float(c) for c in args.p0.split(",")]
        p1 = [float(c) for c in args.p1.split(",")]
        res = {"center": arc_center(p0, p1, args.r, not args.cw, args.large)}
    res = _fmt(res)
    if isinstance(res, list):
        if not res:
            print("无解（不相交 / 不存在这样的圆或切线）")
        for i, r in enumerate(res, 1):
            print(f"{i}. {json.dumps(r, ensure_ascii=False)}")
    else:
        print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
