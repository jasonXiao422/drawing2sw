"""geom2d / ftable.resolve 自检：用解析面积核对展开结果。

运行：.venv\\Scripts\\python.exe tests\\test_geom2d.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import ftable  # noqa: E402
import geom2d as g  # noqa: E402


def area(profile):
    segs, cur = [], profile["start"]
    for s in profile["segments"]:
        segs.append(g.Seg(cur, s["to"], s.get("center"), s.get("ccw", True)))
        cur = s["to"]
    return g.signed_area(profile["start"], segs, n_arc=2000)


def resolve_profile(pr):
    t = {"features": [{"id": "t", "type": "extrude", "profile": pr, "meta": {}}]}
    return ftable.resolve(t)["features"][0]["profile"]


def check(name, got, want, tol=1e-3):
    ok = abs(got - want) <= tol * max(1.0, abs(want))
    print(f"{'OK ' if ok else 'BAD'} {name}: {got:.4f}（应为 {want:.4f}）")
    return ok


results = []

# 1. 矩形 100×60 四角 R10（凸角）
rect = {"shape": "path", "start": [0, 0], "segments": [
    {"to": [100, 0], "fillet": 10}, {"to": [100, 60], "fillet": 10},
    {"to": [0, 60], "fillet": 10}, {"to": [0, 0], "fillet": 10}]}
results.append(check("矩形四角 R10", area(resolve_profile(rect)), 6000 - 4 * (100 - 25 * math.pi)))

# 2. L 形，凹角 R5：凹角倒圆补料 (1 - π/4)·25
L = {"shape": "path", "start": [0, 0], "segments": [
    {"to": [60, 0]}, {"to": [60, 20]}, {"to": [20, 20], "fillet": 5}, {"to": [20, 50]}, {"to": [0, 50]}, {"to": [0, 0]}]}
results.append(check("L 形凹角 R5", area(resolve_profile(L)), 60 * 20 + 20 * 30 + (1 - math.pi / 4) * 25))

# 3. 起点也倒角（最后一段的 fillet），顺时针走
cw = {"shape": "path", "start": [0, 0], "segments": [
    {"to": [0, 60]}, {"to": [100, 60]}, {"to": [100, 0]}, {"to": [0, 0], "fillet": 10}]}
results.append(check("顺时针、起点 R10", abs(area(resolve_profile(cw))), 6000 - (100 - 25 * math.pi)))

# 4. 腰形槽：两个 R10 圆心距 50
slot = {"shape": "tangent_loop", "circles": [{"center": [0, 0], "r": 10}, {"center": [50, 0], "r": 10}]}
results.append(check("腰形槽", area(resolve_profile(slot)), 50 * 20 + math.pi * 100))

# 5. 两个不等圆：R20 和 R10，圆心距 60（耳板外形）。面积 = 两切线和圆弧围成
r1, r2, d = 20.0, 10.0, 60.0
a = math.acos((r1 - r2) / d)
want = (r1 * r1 * (math.pi - a) + r2 * r2 * a  # 两段圆弧扇形... 用梯形 + 扇形组合
        + (r1 + r2) * d * math.sin(a))
results.append(check("R20+R10 切线外形", area(resolve_profile(
    {"shape": "tangent_loop", "circles": [{"center": [0, 0], "r": r1}, {"center": [d, 0], "r": r2}]})), want))

# 6. 点到圆的切线（r=0 是尖点）：水滴形
drop = resolve_profile({"shape": "tangent_loop", "circles": [{"center": [0, 0], "r": 10}, {"center": [30, 0], "r": 0}]})
a = math.acos(10 / 30)
results.append(check("水滴形（点到圆切线）", area(drop), 10 * 10 * (math.pi - a) + 10 * 30 * math.sin(a)))

# 7. 按半径画弧：半圆头
semi = {"shape": "path", "start": [0, 0], "segments": [
    {"to": [40, 0]}, {"to": [40, 20]}, {"to": [0, 20], "radius": 20, "ccw": True, "large": False}, {"to": [0, 0]}]}
# R20 过 (40,20)、(0,20)：弦长 40 = 直径，正好半圆凸出
results.append(check("按半径画弧（半圆）", area(resolve_profile(semi)), 800 + math.pi * 200))

# 8. 交点
p = g.pick_near(g.intersect(g.parse_obj({"circle": {"center": [0, 0], "r": 45}}), g.parse_obj({"x": 16})), [16, 40])
results.append(check("R45 与 x=16 交点 v", p[1], math.sqrt(45 ** 2 - 16 ** 2)))

# 9. 线和圆弧的拐角：003 槽角 R5 圆心应在 (11, 38.4578)
t = g.Seg((0, 45), (16, math.sqrt(45 ** 2 - 256)), (0, 0), False)
b = g.Seg(t.p1, (16, 30))
fa = g.fillet_corner(t, b, 5)
results.append(check("弧-线拐角 R5 圆心 u", fa.center[0], 11) and check("弧-线拐角 R5 圆心 v", fa.center[1], 38.457769))

# 10. 埋头孔展开：Φ10 孔、Φ20×90° 埋头，锥高 5
tab = {"part": {"units": "mm"}, "features": [{"id": "h", "type": "hole", "plane": "front", "offset": 10, "diameter": 10,
                                              "positions": [[0, 0]], "depth": 20, "direction": "negative",
                                              "csink": {"diameter": 20}, "meta": {}}]}
fs = ftable.resolve(tab)["features"]
cone = [f for f in fs if f["id"] == "h__csink1"][0]
# front 面 z=10 往 -Z 钻；锥画在 top 面（法向 Y），草图 v = -Z；Φ10 处锥深 5 → 模型 (5, 0, 5) → 草图 (5, -5)
results.append(check("埋头孔展开出 2 个特征", len(fs), 2, 0))
results.append(check("埋头孔锥面到 Φ10 处的位置误差", math.dist(cone["profile"]["points"][2], [5, -5]), 0))

print("全部通过" if all(results) else "有失败")
sys.exit(0 if all(results) else 1)
