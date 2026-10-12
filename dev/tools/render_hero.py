"""README / 网页用的轴测渲染图（不是读图工具）。用法: python dev/tools/render_hero.py in.step out.png [仰角 方位角]"""
import sys
import numpy as np
import cadquery as cq
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

step, out = sys.argv[1], sys.argv[2]
elev = float(sys.argv[3]) if len(sys.argv) > 3 else 26
azim = float(sys.argv[4]) if len(sys.argv) > 4 else -52
shape = cq.importers.importStep(step).val()
verts, tris = shape.tessellate(0.05, 0.1)
V = np.array([(v.x, -v.z, v.y) for v in verts])  # model Y up
P = V[np.array(tris)]
n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
light = np.array([-0.35, -0.55, 0.76]); light /= np.linalg.norm(light)
e, a = np.radians(elev), np.radians(azim)
eye = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
keep = n @ eye > 1e-6
P, n = P[keep], n[keep]
order = np.argsort(P.mean(1) @ eye)  # far to near
P, n = P[order], n[order]
lam = np.clip(n @ light, 0, 1)
fill = np.array([0.80, 0.84, 0.86]) * (0.42 + 0.58 * lam[:, None])
fill = np.clip(fill + np.array([-0.04, 0.0, 0.01]), 0, 1)

fig = plt.figure(figsize=(8, 6), dpi=200)
ax = fig.add_subplot(projection="3d", computed_zorder=False)
ax.add_collection3d(Poly3DCollection(P, facecolors=fill, edgecolors=fill, linewidths=0.6))
lo, hi = V.min(0), V.max(0)
c, r = (lo + hi) / 2, (hi - lo).max() / 2
for set_lim, i in ((ax.set_xlim, 0), (ax.set_ylim, 1), (ax.set_zlim, 2)):
    set_lim(c[i] - r, c[i] + r)
ax.set_box_aspect((1, 1, 1))
ax.view_init(elev=elev, azim=azim)
ax.set_proj_type("ortho")
ax.axis("off")
fig.subplots_adjust(0, 0, 1, 1)
fig.savefig(out, transparent=True, bbox_inches="tight", pad_inches=0.05)

from PIL import Image
im = Image.open(out); box = im.getchannel("A").getbbox()
im = im.crop(box); pad = 40
canvas = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad)); canvas.paste(im, (pad, pad)); canvas.save(out)
