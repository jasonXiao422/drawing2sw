"""扫描图、截图自动切视图：每个视图（连同它的尺寸）裁出来放大，再出一张标了编号的总览图。

AI 先看总览图认出每块是什么（主视图、剖视图、标题栏、技术要求），再逐块看放大图读尺寸。
不用自己写裁图脚本，也不用一轮轮试着裁。

用法：
  python scripts/split_views.py 图纸.png -o work/views
输出：
  work/views/overview.png        原图上画了编号框
  work/views/view_01.png ...     每块放大（长边约 1600 像素，最多放大 4 倍）
  work/views/views.json          每块的编号、在原图里的位置、放大倍数

只用 numpy、scipy、PIL。切得不理想时可以调 --gap（视图之间的空白，默认按图大小自动取）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage


def ink_mask(img: Image.Image) -> np.ndarray:
    """线条和文字（深色、不带颜色）。水印、彩色标记不算。"""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    gray = a.mean(axis=2)
    spread = a.max(axis=2) - a.min(axis=2)
    dark = gray < 150
    if np.median(gray) < 100:  # 黑底白线（CAD 截图）
        dark = gray > 105
    return dark & (spread < 70)


def remove_long_lines(mask: np.ndarray, frac: float = 0.55) -> np.ndarray:
    """去掉图框、标题栏外框这类贯穿大半张图的直线，免得所有视图被框连成一块。"""
    m = mask.copy()
    h, w = m.shape
    for axis, length in ((1, w), (0, h)):
        st = np.zeros((3, 3), int)
        if axis == 1:
            st[1, :] = 1  # 只沿水平方向连通
        else:
            st[:, 1] = 1
        lab, n = ndimage.label(m, structure=st)
        if n == 0:
            continue
        for i, s in enumerate(ndimage.find_objects(lab), 1):
            if s[axis].stop - s[axis].start > frac * length:
                m[s][lab[s] == i] = False
    return m


def split(src: str, out_dir: str, gap: int | None = None, min_frac: float = 0.002) -> dict:
    img = Image.open(src).convert("RGB")
    W, H = img.size
    mask = remove_long_lines(ink_mask(img))
    gap = gap or max(10, int(0.012 * max(W, H)))
    grown = ndimage.binary_dilation(mask, structure=np.ones((gap, gap), bool))
    lab, _ = ndimage.label(grown)
    boxes = []
    for s in ndimage.find_objects(lab):
        y0, y1, x0, x1 = s[0].start, s[0].stop, s[1].start, s[1].stop
        if (x1 - x0) * (y1 - y0) < min_frac * W * H:
            continue
        if (x1 - x0) > 0.97 * W and (y1 - y0) > 0.97 * H:
            continue
        boxes.append([x0, y0, x1, y1])
    def inside(a, b):  # a 的面积 90% 以上落在 b 里
        ix = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
        return ix >= 0.9 * (a[2] - a[0]) * (a[3] - a[1])
    boxes = [a for a in boxes if not any(a is not b and inside(a, b) and
                                         (b[2] - b[0]) * (b[3] - b[1]) > (a[2] - a[0]) * (a[3] - a[1]) for b in boxes)]
    boxes.sort(key=lambda b: (round(b[1] / (0.15 * H)), b[0]))  # 先上后下，同一排从左到右

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    over = img.copy()
    d = ImageDraw.Draw(over)
    try:
        font = ImageFont.truetype("arial.ttf", max(14, int(0.025 * max(W, H))))
    except OSError:
        font = ImageFont.load_default()
    views = []
    for k, (x0, y0, x1, y1) in enumerate(boxes, 1):
        m = gap // 2
        x0, y0, x1, y1 = max(0, x0 - m), max(0, y0 - m), min(W, x1 + m), min(H, y1 + m)
        crop = img.crop((x0, y0, x1, y1))
        s = max(1.0, min(4.0, 1600 / max(crop.size)))
        if s > 1:
            crop = crop.resize((int(crop.width * s), int(crop.height * s)), Image.LANCZOS)
        name = f"view_{k:02d}.png"
        crop.save(out / name)
        cx, cy = (x0 + x1) / 2 / W, (y0 + y1) / 2 / H
        where = ("上" if cy < 0.4 else "下" if cy > 0.6 else "中") + ("左" if cx < 0.4 else "右" if cx > 0.6 else "中")
        views.append({"id": k, "file": str(out / name), "bbox_px": [x0, y0, x1, y1], "scale": round(s, 2),
                      "position": where})
        d.rectangle((x0, y0, x1, y1), outline=(220, 0, 0), width=max(2, W // 500))
        d.text((x0 + 4, y0 + 2), str(k), fill=(220, 0, 0), font=font)
    over.save(out / "overview.png")
    res = {"source": src, "size_px": [W, H], "gap_px": gap, "overview": str(out / "overview.png"), "views": views,
           "how_to_use": "先看 overview.png 认出每个编号是哪个视图（主视图、剖视图、局部放大、标题栏、技术要求），"
                         "再逐个看 view_XX.png 读尺寸。一个视图被切成两块、或者两个视图连成一块时，按总览图自己判断；"
                         "切得太碎可以加大 --gap，连成一块可以减小 --gap。"}
    (out / "views.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("-o", "--out", default="work/views")
    ap.add_argument("--gap", type=int, default=None, help="视图之间的空白像素；默认取长边的 1.2%")
    args = ap.parse_args()
    res = split(args.image, args.out, args.gap)
    print(json.dumps({"overview": res["overview"], "gap_px": res["gap_px"],
                      "views": [(v["id"], v["position"], v["bbox_px"]) for v in res["views"]]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
