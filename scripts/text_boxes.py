"""图片图纸的文字框：自动找出像文字的块并编号，AI 按编号说"这是什么字"，坐标由脚本填。

图片、无文字 PDF 没有文字层，observations 是空的。以前要 AI 自己写每条标注的 bbox，
它看不准像素坐标，只能估一个整数，框经常落在空白或线上（豆包 Mini Crank Case 测试）。

用法:
  1) 找文字框，出带编号的总览图和分块放大图:
     python scripts/text_boxes.py detect work/drawing.png -o work/text_boxes.json
  2) 看图，写一个 labels.json，只写编号和读到的原文:
     [{"box": "t17", "text": "Ø12.5"}, {"box": "t20+t21", "text": "M2x0.4-6H 8 PLCS", "kind": "callout"}]
     一条标注被拆成几个框时用 + 连起来；kind 可省略（dimension / callout / text / note）
  3) 生成观察，追加到预处理出的证据文件（provider = visual）:
     python scripts/text_boxes.py emit work/text_boxes.json work/labels.json --observations work/extract_observations.json -o work/observations.json

只依赖 numpy / scipy / Pillow。找框是图像处理，不认字：编号里会有箭头、虚线段之类的杂框，不用理它们。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


def ink_mask(img: Image.Image) -> np.ndarray:
    """深色笔画和彩色笔画（很多图的尺寸是红色、蓝色）都算墨迹。"""
    rgb = np.asarray(img.convert("RGB")).astype(np.int16)
    gray = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    return (gray < 170) | ((chroma > 60) & (gray < 225))


def _components(mask: np.ndarray):
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    return lab, ndimage.find_objects(lab)


def char_like(sl, img_h: int) -> bool:
    h = sl[0].stop - sl[0].start
    w = sl[1].stop - sl[1].start
    big, small = max(w, h), min(w, h)
    hmax = max(40, int(img_h * 0.03))
    if big < 4 or big > hmax:
        return False
    if small <= 2 and big > 12:      # 细长：尺寸线、虚线段、引线
        return False
    return True


def detect(path: str) -> dict:
    img = Image.open(path)
    mask = ink_mask(img)
    H, W = mask.shape
    _, objs = _components(mask)
    chars = [sl for sl in objs if sl is not None and char_like(sl, H)]
    keep = np.zeros_like(mask)
    heights = []
    for sl in chars:
        keep[sl] |= mask[sl]
        heights.append(max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start))
    ch = float(np.median(heights)) if heights else 10.0
    r = max(2, int(round(ch * 0.45)))   # 同一个词里的字、Ø 和数字之间的空隙
    merged = ndimage.binary_dilation(keep, structure=np.ones((2 * r + 1, 2 * r + 1)))
    _, words = _components(merged)
    boxes = []
    for sl in words:
        if sl is None:
            continue
        sub = keep[sl]
        ys, xs = np.nonzero(sub)
        if len(xs) == 0:
            continue
        x0, x1 = sl[1].start + xs.min(), sl[1].start + xs.max() + 1
        y0, y1 = sl[0].start + ys.min(), sl[0].start + ys.max() + 1
        if max(x1 - x0, y1 - y0) < 5:
            continue
        boxes.append([int(x0), int(y0), int(x1), int(y1)])
    boxes.sort(key=lambda b: (round(b[1] / (2 * ch)), b[0]))
    return {"image": str(path), "size_px": [W, H], "char_height_px": round(ch, 1),
            "boxes": [{"id": f"t{i + 1}", "bbox": b} for i, b in enumerate(boxes)]}


def draw(path: str, data: dict, out_png: Path, tiles: int = 2) -> list[str]:
    img = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(img)
    for b in data["boxes"]:
        x0, y0, x1, y1 = b["bbox"]
        d.rectangle((x0 - 1, y0 - 1, x1 + 1, y1 + 1), outline=(0, 120, 255), width=1)
        d.text((x0, max(0, y0 - 11)), b["id"], fill=(0, 90, 220))
    img.save(out_png)
    written = [str(out_png)]
    W, H = img.size
    for i in range(tiles):            # 分块放大，编号看得清
        for j in range(tiles):
            box = (j * W // tiles, i * H // tiles, (j + 1) * W // tiles, (i + 1) * H // tiles)
            t = img.crop(box)
            t = t.resize((t.width * 2, t.height * 2), Image.LANCZOS)
            p = out_png.with_name(f"{out_png.stem}_{i + 1}{j + 1}.png")
            t.save(p)
            written.append(str(p))
    return written


def emit(boxes_path: str, labels_path: str, obs_path: str, out: str, page: int = 1) -> dict:
    data = json.loads(Path(boxes_path).read_text(encoding="utf-8"))
    labels = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    doc = json.loads(Path(obs_path).read_text(encoding="utf-8"))
    lookup = {b["id"]: b["bbox"] for b in data["boxes"]}
    used = {o["id"] for o in doc["observations"]}
    for item in labels:
        ids = [s.strip() for s in item["box"].split("+")]
        missing = [i for i in ids if i not in lookup]
        if missing:
            raise SystemExit(f"文字框编号不存在: {missing}（{item}）")
        bs = [lookup[i] for i in ids]
        bbox = [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]
        oid = "vis-" + "-".join(i[1:] for i in ids)
        if oid in used:
            raise SystemExit(f"观察 {oid} 已经存在，同一个框不要写两次")
        used.add(oid)
        doc["observations"].append({"id": oid, "page": page, "text": item["text"], "bbox": bbox,
                                    "coordinate_space": "image_px", "provider": "visual",
                                    "kind": item.get("kind", "dimension"), "text_box": item["box"]})
    doc["open_questions"] = [q for q in doc.get("open_questions", []) if not q.startswith("No text extracted")]
    Path(out).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


# ------------------------------------------------------------ 校验：手写的视觉观察，框里要有字

def _page_image(doc: dict, page: int, base_dirs: list[Path]) -> Path | None:
    p = next((p for p in doc.get("pages", []) if p.get("page") == page), None)
    name = (p or {}).get("image") or doc.get("source", {}).get("file")
    if not name:
        return None
    for base in base_dirs:
        cand = (base / name)
        if cand.exists():
            return cand
    return None


def check_boxes(doc: dict, base_dirs: list[Path]) -> tuple[list[str], list[str]]:
    """provider 为 visual / human、坐标是原图像素的观察：框里一个像字的笔画都没有，就是框错了地方。"""
    errors, warnings = [], []
    cache = {}
    for o in doc.get("observations", []):
        if o.get("provider") not in ("visual", "human") or o.get("coordinate_space") != "image_px":
            continue
        pg = o.get("page", 1)
        if pg not in cache:
            path = _page_image(doc, pg, base_dirs)
            cache[pg] = (ink_mask(Image.open(path)) if path else None)
            if path is None:
                warnings.append(f"找不到第 {pg} 页的图片，没法检查手写观察的框是否落在字上")
        mask = cache[pg]
        if mask is None:
            continue
        H = mask.shape[0]
        x0, y0, x1, y1 = [int(round(c)) for c in o["bbox"]]
        # 在稍大一圈的范围里找笔画，再看它们和原框的关系：完全没有落进框的 = 框错了地方；
        # 落进框、但伸出框外不止几个像素 = 没框全（紧贴笔画边缘的框不算）
        pad = max(4, (y1 - y0) // 2)
        X0, Y0 = max(0, x0 - pad), max(0, y0 - pad)
        sub = mask[Y0:y1 + pad, X0:x1 + pad]
        _, objs = _components(sub)
        inside, cut = 0, 0
        for sl in objs:
            if sl is None or not char_like(sl, H):
                continue
            cy0, cy1 = Y0 + sl[0].start, Y0 + sl[0].stop
            cx0, cx1 = X0 + sl[1].start, X0 + sl[1].stop
            ox = min(cx1, x1) - max(cx0, x0)
            oy = min(cy1, y1) - max(cy0, y0)
            if ox <= 0 or oy <= 0:
                continue
            inside += 1
            if cx0 < x0 - 2 or cy0 < y0 - 2 or cx1 > x1 + 2 or cy1 > y1 + 2:
                cut += 1
        if not inside:
            errors.append(f"{o['id']}「{o.get('text')}」: 框 {o['bbox']} 里没有字（只有空白或线）。"
                          "用 scripts/text_boxes.py detect 找到真实的文字框，再用 emit 生成观察")
        elif cut:
            warnings.append(f"{o['id']}「{o.get('text')}」: 框 {o['bbox']} 把字切断了，可能没框全")
    return errors, warnings


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect", help="找文字框，出 JSON、带编号的总览图和分块放大图")
    d.add_argument("image")
    d.add_argument("-o", "--out", default="work/text_boxes.json")
    d.add_argument("--tiles", type=int, default=2, help="分块数（每边），默认 2 × 2")
    e = sub.add_parser("emit", help="按 labels.json 生成视觉观察")
    e.add_argument("boxes")
    e.add_argument("labels")
    e.add_argument("--observations", required=True, help="预处理出的 extract_observations.json")
    e.add_argument("-o", "--out", required=True)
    e.add_argument("--page", type=int, default=1)
    args = ap.parse_args()
    if args.cmd == "detect":
        data = detect(args.image)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        pics = draw(args.image, data, out.with_suffix(".png"), args.tiles)
        print(json.dumps({"boxes": len(data["boxes"]), "json": str(out), "overview": pics[0], "tiles": pics[1:]},
                         ensure_ascii=False, indent=2))
    else:
        doc = emit(args.boxes, args.labels, args.observations, args.out, args.page)
        print(f"已写入 {args.out}，观察 {len(doc['observations'])} 条")


if __name__ == "__main__":
    main()
