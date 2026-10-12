"""把 cadsy/cad-technical-drawings（Apache-2.0）转成 drawing2sw 的评测格式，并统计零件特征。

来源: https://huggingface.co/datasets/cadsy/cad-technical-drawings
      3D 模型来自 ADSKAILab/Zero-To-CAD-100k（Apache-2.0）。
内容: 65 个 STEP 零件，每个一张 ISO 风格、一张 ASME 风格的图（2480×1754 PNG），
      标注框标签：dimension / callout / feature_control_frame / datum_definition / title_block_* ...

先下载到 data/downloads/cadsy（不进仓库），再运行:
  python dev/tools/import_cadsy.py data/downloads/cadsy -o work/cadsy
  python dev/tools/import_cadsy.py data/downloads/cadsy -o data/external/cadsy --limit 8 --copy

输出:
  manifest.json                    和 benchmark.py 兼容；几何答案由 STEP 计算，alignment = pose_free
  <part>/observations_<std>.json   cadsy 标签转成的观察（image_px 坐标）。相当于"完美 OCR"，
                                   用来单独测"尺寸归属和建模"，排除 OCR 误差
  feature_stats.json               每个零件的面类型、孔、圆角等统计，用来判断该先补哪些能力
"""
from __future__ import annotations

import argparse
import collections
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

W, H = 2480, 1754   # cadsy 图片尺寸，标签坐标按它归一化


def observations_from_labels(labels: dict, image: Path, sha: str) -> dict:
    obs = []
    counters = collections.Counter()
    for a in labels.get("annotations", []):
        if not str(a.get("text", "")).strip():
            continue
        counters[a["type"]] += 1
        x0, y0, x1, y1 = a["box"]
        obs.append({"id": f"{a['type']}-{counters[a['type']]}", "page": 1, "text": a["text"],
                    "bbox": [round(x0 * W, 1), round(y0 * H, 1), round(x1 * W, 1), round(y1 * H, 1)],
                    "coordinate_space": "image_px", "provider": "dataset_label",
                    "kind": a["type"] if a["type"] != "label" else "text", "view": a.get("view", "sheet")})
    return {"schema_version": "1.0", "source": {"file": image.name, "sha256": sha},
            "pages": [{"page": 1, "image": image.name, "size_px": [W, H]}],
            "observations": obs, "views": [], "open_questions": []}


def shape_stats(step: Path) -> dict:
    """面类型、圆柱孔（内圆柱面）、圆角候选、平面方向数等。粗略，只用来排优先级。"""
    import cadquery as cq
    shape = cq.importers.importStep(str(step)).val()
    faces = shape.Faces()
    kinds = collections.Counter(f.geomType() for f in faces)
    holes, bosses, radii = 0, 0, []
    normals = set()
    for f in faces:
        t = f.geomType()
        if t == "PLANE":
            n = f.normalAt()
            normals.add(tuple(round(abs(c), 2) for c in (n.x, n.y, n.z)))
        if t == "CYLINDER":
            # 法向朝向轴线 = 内圆柱面（孔）；背离 = 外圆柱面（轴、凸台、圆角）
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.BRepGProp import BRepGProp_Face
            from OCP.gp import gp_Pnt, gp_Vec
            ad = BRepAdaptor_Surface(f.wrapped)
            um, vm = (ad.FirstUParameter() + ad.LastUParameter()) / 2, (ad.FirstVParameter() + ad.LastVParameter()) / 2
            pnt, vec = gp_Pnt(), gp_Vec()
            BRepGProp_Face(f.wrapped).Normal(um, vm, pnt, vec)   # 已经考虑了面的朝向
            c = cq.Vector(pnt.X(), pnt.Y(), pnt.Z())
            n = cq.Vector(vec.X(), vec.Y(), vec.Z())
            ax = f._geomAdaptor().Cylinder().Axis()
            p = ax.Location()
            d = ax.Direction()
            v = (c.x - p.X(), c.y - p.Y(), c.z - p.Z())
            t_ = v[0] * d.X() + v[1] * d.Y() + v[2] * d.Z()
            radial = (v[0] - t_ * d.X(), v[1] - t_ * d.Y(), v[2] - t_ * d.Z())
            dot = radial[0] * n.x + radial[1] * n.y + radial[2] * n.z
            r = f._geomAdaptor().Cylinder().Radius()
            radii.append(round(r, 3))
            if dot < 0:
                holes += 1
            else:
                bosses += 1
    bb = shape.BoundingBox()
    oblique = [n for n in normals if sum(1 for c in n if c > 1e-3) > 1]
    return {"faces": len(faces), "face_types": dict(kinds), "inner_cylinders": holes,
            "outer_cylinders": bosses, "distinct_radii": len(set(radii)),
            "plane_directions": len(normals), "oblique_planes": len(oblique),
            "solids": len(cq.Workplane().add(shape).solids().vals()),
            "volume_mm3": round(shape.Volume(), 3), "surface_area_mm2": round(shape.Area(), 3),
            "bbox_mm": [round(bb.xlen, 4), round(bb.ylen, 4), round(bb.zlen, 4)]}


def text_stats(labels: dict) -> collections.Counter:
    """标注里出现的工程符号：螺纹、沉孔、深度、公差、形位公差、倒角等。"""
    c = collections.Counter()
    for a in labels.get("annotations", []):
        t = a.get("text", "")
        c[a["type"]] += 1
        for key, needle in (("thread_M", "M"), ("diameter", "Ø"), ("radius", "R"), ("counterbore", "⌴"),
                            ("countersink", "⌵"), ("depth", "↧"), ("plus_minus", "±"), ("chamfer_C", "C"),
                            ("times", "×"), ("THRU", "THRU"), ("degree", "°")):
            if needle in t:
                c[key] += 1
    return c


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="下载好的 cadsy 文件夹（含 metadata.jsonl）")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--copy", action="store_true", help="把图片、标签、STEP 复制进输出文件夹（用于发布样本）")
    args = ap.parse_args()
    from observations import dump, sha256

    src, out = Path(args.source), Path(args.out)
    if out.exists():
        ap.error("输出文件夹已存在，换一个新的")
    out.mkdir(parents=True)
    rows = [json.loads(x) for x in (src / "metadata.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    if args.limit:
        rows = rows[:args.limit]
    cases, stats, symbols = [], [], collections.Counter()
    for row in rows:
        pid = row["part_id"]
        step = src / row["model_step"]
        if not step.exists():
            print(f"{pid}: 缺少 STEP，跳过")
            continue
        folder = out / pid
        folder.mkdir()
        try:
            st = shape_stats(step)
        except Exception as e:  # noqa: BLE001
            print(f"{pid}: STEP 读不出来 ({e})")
            continue
        st["part_id"] = pid
        stats.append(st)
        rel = (lambda p: f"{pid}/{Path(p).name}") if args.copy else (lambda p: str((src / p).resolve()))
        if args.copy:
            for key in ("model_step", "asme_image", "asme_labels", "iso_image", "iso_labels"):
                shutil.copyfile(src / row[key], folder / Path(row[key]).name)
        for std in ("iso", "asme"):
            image = src / row[f"{std}_image"]
            labels = json.loads((src / row[f"{std}_labels"]).read_text(encoding="utf-8"))
            symbols.update(text_stats(labels))
            dump(observations_from_labels(labels, image, sha256(image)), folder / f"observations_{std}.json")
        cases.append({"id": pid, "drawing": rel(row["iso_image"]), "sha256": sha256(src / row["iso_image"]),
                      "inputs": {"png_iso": rel(row["iso_image"]), "png_asme": rel(row["asme_image"])},
                      "answer_step": rel(row["model_step"]),
                      "expected": {k: st[k] for k in ("volume_mm3", "surface_area_mm2", "bbox_mm")},
                      "alignment": "pose_free", "license": "Apache-2.0",
                      "source": "cadsy/cad-technical-drawings (from ADSKAILab/Zero-To-CAD-100k)",
                      "evaluation": "geometry_only; no dimension-to-feature labels"})
        print(f"{pid}: {st['faces']} faces, {st['inner_cylinders']} inner cyl, {st['oblique_planes']} oblique",
              flush=True)
    dump({"schema_version": "1.1", "purpose": "External synthetic drawings of Zero-to-CAD parts with STEP answers",
          "license": "Apache-2.0", "cases": cases}, out / "manifest.json")
    summary = {"parts": len(stats), "annotation_symbols": dict(symbols),
               "faces_median": sorted(s["faces"] for s in stats)[len(stats) // 2] if stats else 0,
               "with_inner_cylinders": sum(1 for s in stats if s["inner_cylinders"]),
               "with_oblique_planes": sum(1 for s in stats if s["oblique_planes"]),
               "with_bspline_or_other": sum(1 for s in stats if set(s["face_types"]) - {"PLANE", "CYLINDER", "CONE", "TORUS"}),
               "multi_solid": sum(1 for s in stats if s["solids"] != 1),
               "face_type_totals": dict(sum((collections.Counter(s["face_types"]) for s in stats), collections.Counter()))}
    dump({"summary": summary, "parts": stats}, out / "feature_stats.json")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
