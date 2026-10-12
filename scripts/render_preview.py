"""把预览 STEP 渲染成四个方向的图（轴测、主视、俯视、左视），和图纸对照外形。

用法：
  python scripts/render_preview.py work/preview.step -o work/preview.png

坐标按 references/coordinates.md：Y 向上。图里的 "front" 是从 +Z 往 -Z 看，"left" 是从 -X 往 +X 看。
渲染很粗糙（matplotlib），只用来看结构对不对：有没有漏掉一块、肋和墙的位置、孔在哪一面。
需要 cadquery 和 matplotlib。
"""
from __future__ import annotations

import argparse
import sys

import numpy as np


def render(step: str, out: str, tol: float = 0.3) -> None:
    import cadquery as cq  # noqa: PLC0415
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: PLC0415

    shape = cq.importers.importStep(step).val()
    verts, tris = shape.tessellate(tol, tol)
    V = np.array([(v.x, v.z, v.y) for v in verts])  # matplotlib 的竖轴放模型 Y
    T = np.array(tris)
    P = V[T]
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
    light = np.clip(np.abs(n @ np.array([0.4, -0.5, 0.75])), 0, 1) * 0.7 + 0.3
    colors = np.c_[light, light, light, np.ones_like(light)]

    mn, mx = V.min(0), V.max(0)
    c, r = (mn + mx) / 2, (mx - mn).max() / 2
    views = [(25, -60, "iso"), (0, -90, "front (from +Z)"), (90, -90, "top (from +Y)"), (0, 180, "left (from -X)")]
    fig = plt.figure(figsize=(16, 5))
    for i, (el, az, title) in enumerate(views):
        ax = fig.add_subplot(1, 4, i + 1, projection="3d")
        pc = Poly3DCollection(P, linewidths=0.05, edgecolor=(0, 0, 0, 0.25))
        pc.set_facecolor(colors)
        ax.add_collection3d(pc)
        ax.set_xlim(c[0] - r, c[0] + r)
        ax.set_ylim(c[1] - r, c[1] + r)
        ax.set_zlim(c[2] - r, c[2] + r)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(el, az)
        ax.set_title(title)
        ax.set_xlabel("X")
        ax.set_ylabel("Z")
        ax.set_zlabel("Y")
    plt.tight_layout()
    plt.savefig(out, dpi=90)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("step")
    ap.add_argument("-o", "--out", default="work/preview.png")
    args = ap.parse_args()
    render(args.step, args.out)
    print(f"已保存 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
