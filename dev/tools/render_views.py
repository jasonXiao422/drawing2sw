"""README / 网页用：把 STEP 投影成第三角排布的三视图线图（隐藏线虚线），不标尺寸。

用法: python dev/tools/render_views.py part.json|in.step out.png [--views front,top,right] [--up y|z]

传特征表时用 make_test_drawing.py 的精确隐藏线；传 STEP 时用多边形隐藏线（STEP 读回来的几何有时让精确算法崩溃）。只用来展示，不是出图工具。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def project_poly(shape, view: str, deflection: float = 0.004) -> dict:
    """多边形隐藏线（HLRBRep_PolyAlgo）。精确 HLR 在某些模型上会让进程崩溃（Mini Crank Case 实测），
    展示用图走多边形算法：先网格化，再按三角面求可见性。返回和 make_test_drawing.project 一样的结构。"""
    import make_test_drawing as m
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_PolyAlgo, HLRBRep_PolyHLRToShape
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    BRepMesh_IncrementalMesh(shape, deflection, False, 0.05, True)
    d, x = m.VIEWS[view]
    algo = HLRBRep_PolyAlgo()
    algo.Load(shape)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*d), gp_Dir(*x))))
    algo.Update()
    h = HLRBRep_PolyHLRToShape()
    h.Update(algo)

    def edges(comp):
        out = []
        if comp is None or comp.IsNull():
            return out
        ex = TopExp_Explorer(comp, TopAbs_EDGE)
        while ex.More():
            c = BRepAdaptor_Curve(TopoDS.Edge_s(ex.Current()))
            a0, a1 = c.Value(c.FirstParameter()), c.Value(c.LastParameter())
            out.append(("line", (a0.X(), a0.Y()), (a1.X(), a1.Y())))
            ex.Next()
        return out

    vis = edges(h.VCompound()) + edges(h.OutLineVCompound())
    hid = edges(h.HCompound()) + edges(h.OutLineHCompound())
    return {"visible": vis, "hidden": hid}


def render(step: str, out: str, views=("front", "top", "right"), z_up: bool = False, ink="#1d2422") -> None:
    import cadquery as cq
    import make_test_drawing as m   # 要在 matplotlib 之前导入，反过来在 Windows 上会崩溃
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mp

    if step.lower().endswith(".json"):
        # 特征表：现场建模，用精确隐藏线。从 STEP 读回来的几何有时会让精确 HLR 崩溃（Mini Crank Case 实测）
        import ftable
        import preview_cadquery
        built = preview_cadquery.build(ftable.load(step))
        shape = (built[0] if isinstance(built, tuple) else built).val()
        project = m.project
    else:
        wp = cq.importers.importStep(step)
        shape = wp.val()
        project = project_poly
    if z_up:
        shape = shape.rotate((0, 0, 0), (1, 0, 0), -90)
    proj = {v: project(shape.wrapped, v) for v in views}
    boxes = {v: m.bbox(p["visible"] + p["hidden"]) for v, p in proj.items()}
    size = max(max(b[2] - b[0], b[3] - b[1]) for b in boxes.values())
    gap = size * 0.18
    fb = boxes["front"]
    off = {"front": (0.0, 0.0)}
    if "top" in proj:      # 第三角：俯视在上
        off["top"] = (0.0, fb[3] + gap - boxes["top"][1])
    if "right" in proj:    # 右视在右
        off["right"] = (fb[2] + gap - boxes["right"][0], 0.0)

    fig, ax = plt.subplots(figsize=(8, 8))
    for v, p in proj.items():
        dx, dy = off[v]
        for kind, ls, lw, col in (("hidden", (0, (4, 3)), 0.7, "#8a9290"), ("visible", "-", 1.1, ink)):
            for e in p[kind]:
                if e[0] == "line":
                    ax.plot([e[1][0] + dx, e[2][0] + dx], [e[1][1] + dy, e[2][1] + dy], color=col, ls=ls, lw=lw)
                elif e[0] == "circle":
                    ax.add_patch(plt.Circle((e[1][0] + dx, e[1][1] + dy), e[2], fill=False, color=col, ls=ls, lw=lw))
                elif e[0] == "arc":
                    ax.add_patch(mp.Arc((e[1][0] + dx, e[1][1] + dy), 2 * e[2], 2 * e[2], theta1=e[3], theta2=e[4],
                                        color=col, ls=ls, lw=lw))
                else:
                    xs, ys = zip(*e[1])
                    ax.plot([x + dx for x in xs], [y + dy for y in ys], color=col, ls=ls, lw=lw)
    ax.set_aspect("equal")
    ax.autoscale()
    ax.axis("off")
    fig.savefig(out, dpi=140, bbox_inches="tight", pad_inches=0.15, transparent=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step")
    ap.add_argument("out")
    ap.add_argument("--views", default="front,top,right")
    ap.add_argument("--up", choices=["y", "z"], default="y")
    a = ap.parse_args()
    render(a.step, a.out, tuple(a.views.split(",")), a.up == "z")


if __name__ == "__main__":
    main()
