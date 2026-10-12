"""README / 网页用的轴测渲染图（不是读图工具）。

用法: python dev/tools/render_hero.py in.step out.png [仰角 方位角] [--size 1600] [--up y|z]

带深度缓冲的光栅化：孔、凹槽、内腔的遮挡关系是对的（以前按三角形中心排序画，孔会被画成凸起）。
棱边按面法向夹角描出来，看起来像 CAD 截图。只依赖 cadquery、numpy、Pillow。
"""
from __future__ import annotations

import argparse
import math

import numpy as np
from PIL import Image, ImageFilter


def view_matrix(elev: float, azim: float):
    """世界坐标（Y 向上）-> 屏幕坐标：x 向右，y 向上，z 朝向观察者。"""
    e, a = math.radians(elev), math.radians(azim)
    eye = np.array([math.cos(e) * math.sin(a), math.sin(e), math.cos(e) * math.cos(a)])
    up = np.array([0.0, 1.0, 0.0])
    right = np.cross(up, eye)
    right /= np.linalg.norm(right)
    up2 = np.cross(eye, right)
    return np.stack([right, up2, eye])


def render(step: str, out: str, elev: float = 28, azim: float = -40, size: int = 1600,
           z_up: bool = False, base=(0.62, 0.68, 0.72), bg=(0, 0, 0, 0)) -> None:
    import cadquery as cq
    shape = cq.importers.importStep(step).val()
    verts, tris = shape.tessellate(0.02, 0.15)
    V = np.array([(v.x, v.y, v.z) for v in verts])
    if z_up:
        V = V[:, [0, 2, 1]] * np.array([1, 1, -1])
    T = np.array(tris)
    R = view_matrix(elev, azim)
    P = V @ R.T                                  # 屏幕坐标
    lo, hi = P.min(0), P.max(0)
    pad = 0.06
    scale = (1 - 2 * pad) * size / max(hi[0] - lo[0], hi[1] - lo[1])
    W = int((hi[0] - lo[0]) * scale + 2 * pad * size)
    H = int((hi[1] - lo[1]) * scale + 2 * pad * size)
    sx = (P[:, 0] - lo[0]) * scale + pad * size
    sy = H - ((P[:, 1] - lo[1]) * scale + pad * size)
    sz = P[:, 2]

    tri = T
    n = np.cross(V[tri[:, 1]] - V[tri[:, 0]], V[tri[:, 2]] - V[tri[:, 0]])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    nv = n @ R.T                                  # 屏幕空间法向
    light = np.array([-0.35, 0.55, 0.76])
    light /= np.linalg.norm(light)
    lam = np.clip(nv @ light, 0, 1)
    spec = np.clip(nv[:, 2], 0, 1) ** 24 * 0.25
    shade = 0.38 + 0.55 * lam

    depth = np.full((H, W), -np.inf)
    color = np.zeros((H, W, 3))
    normal_buf = np.zeros((H, W, 3))
    for k, (i0, i1, i2) in enumerate(tri):
        x = np.array([sx[i0], sx[i1], sx[i2]])
        y = np.array([sy[i0], sy[i1], sy[i2]])
        z = np.array([sz[i0], sz[i1], sz[i2]])
        x0, x1 = max(int(x.min()), 0), min(int(math.ceil(x.max())), W - 1)
        y0, y1 = max(int(y.min()), 0), min(int(math.ceil(y.max())), H - 1)
        if x1 < x0 or y1 < y0:
            continue
        den = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / den
        w1 = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        zz = w0 * z[0] + w1 * z[1] + w2 * z[2]
        sub = depth[y0:y1 + 1, x0:x1 + 1]
        win = inside & (zz > sub)
        sub[win] = zz[win]
        c = np.array(base) * shade[k] + spec[k]
        color[y0:y1 + 1, x0:x1 + 1][win] = c
        normal_buf[y0:y1 + 1, x0:x1 + 1][win] = nv[k]

    mask = np.isfinite(depth)
    # 棱边：相邻像素法向变化大或深度跳变
    nb = normal_buf
    dn = np.zeros((H, W))
    dn[:, 1:] = np.maximum(dn[:, 1:], 1 - np.sum(nb[:, 1:] * nb[:, :-1], axis=2))
    dn[1:, :] = np.maximum(dn[1:, :], 1 - np.sum(nb[1:, :] * nb[:-1, :], axis=2))
    dz = np.zeros((H, W))
    dfin = np.where(mask, depth, np.nan)
    dz[:, 1:] = np.nan_to_num(np.abs(np.diff(dfin, axis=1)), nan=1e9)
    dz[1:, :] = np.maximum(dz[1:, :], np.nan_to_num(np.abs(np.diff(dfin, axis=0)), nan=1e9))
    edge = ((dn > 0.12) | (dz > 3.0 / scale * 4)) & mask
    color[edge] *= 0.35

    rgba = np.zeros((H, W, 4))
    rgba[..., :3] = np.clip(color, 0, 1)
    rgba[..., 3] = mask.astype(float)
    img = Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")
    img = img.resize((W // 2, H // 2), Image.LANCZOS)    # 2× 超采样抗锯齿
    if bg[3]:
        canvas = Image.new("RGBA", img.size, tuple(int(v * 255) if isinstance(v, float) else v for v in bg))
        canvas.alpha_composite(img)
        img = canvas
    img.save(out, optimize=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step")
    ap.add_argument("out")
    ap.add_argument("elev", nargs="?", type=float, default=28)
    ap.add_argument("azim", nargs="?", type=float, default=-40)
    ap.add_argument("--size", type=int, default=1600, help="渲染边长（像素，输出是一半）")
    ap.add_argument("--up", choices=["y", "z"], default="y", help="模型哪根轴朝上")
    a = ap.parse_args()
    render(a.step, a.out, a.elev, a.azim, a.size, a.up == "z")


if __name__ == "__main__":
    main()
