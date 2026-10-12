"""生成带"尺寸归属"标准答案的合成工程图数据集。

每个零件随机生成一张特征表，按 GB / ISO / ASME 之一出图（make_test_drawing.py：隐藏线三视图 + 真正的
DXF 尺寸实体），并记录每个尺寸属于哪个特征的哪个参数。这是公开数据集里很少有的标签：
OCR 只能告诉你图上有个 Ø9，这里还告诉你它是哪个孔的直径。

用法:
  python dev/tools/generate_dataset.py -o work/dataset --count 30 --seed 1
  python dev/tools/generate_dataset.py -o data/generated --count 8 --seed 2026 --formats dxf,pdf,png

每个案例文件夹:
  drawing.dxf / drawing.pdf / drawing_notext.pdf / drawing.png / drawing_scan.jpg   给模型的输入（按 --formats）
  answer.json   标准答案：特征表、体积、表面积、包围盒、dimension_labels
  answer.step   标准答案实体
manifest.json 和 benchmark.py 的格式兼容。

dimension_labels 每一项:
  feature, param       这个尺寸属于哪个特征的哪个参数（param 是标注方式，比如 positions.u 是孔的 u 向定位）
  value, value_mm      图上的数（图纸单位）和毫米值
  handle               DXF 尺寸实体句柄
  pdf_pt / png_px      渲染图上文字中心的位置
  observations         preprocess_drawing.py 对 dxf / pdf 输入给出的观察 ID

数据完全由脚本生成，MIT 许可。几何都是简单零件族，不代表真实图纸的难度。
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

STANDARDS = ("GB", "ISO", "ASME")


# ---------------------------------------------------------------- 取整

def _q(x: float, inch: bool) -> float:
    """取成图纸上常见的数：mm 取整或 0.5，inch 取 1/8（三位小数能精确显示）。"""
    step = 1 / 8 if inch else (0.5 if x < 20 else 1.0)
    return round(round(x / step) * step, 4)


def _meta(evidence: str) -> dict:
    return {"confidence": 1.0, "evidence": evidence}


def _part(name: str, unit: str, std: str, kind: str) -> dict:
    projection = "third_angle" if std == "ASME" else "first_angle"
    return {"name": name, "part_type": kind, "units": unit, "projection": projection,
            "drawing_setup": {"length_unit": unit, "unit_evidence": "title block",
                              "standard": std, "language": "zh" if std == "GB" else "en",
                              "scale": "1:1", "confidence": 1.0},
            "material": random.choice(["Q235", "45", "6061-T6", "304"])}


# ---------------------------------------------------------------- 零件族

def plate(rng: random.Random, unit: str, std: str, name: str) -> dict:
    """矩形板：孔组（单孔 / 对角两孔 / 2×2 / 一排三孔），可选中间方窗或圆孔，可选竖直棱圆角。"""
    inch = unit == "inch"
    s = 1 / 25.4 if inch else 1.0
    W = _q(rng.uniform(60, 160) * s, inch)
    H = _q(rng.uniform(40, 0.85 * W / s) * s, inch)
    T = _q(rng.uniform(5, 20) * s, inch)
    plane = rng.choice(["top", "front"])
    centered = rng.random() < 0.5
    c0 = [0.0, 0.0] if centered else [W / 2, H / 2]
    u0, v0 = c0[0] - W / 2, c0[1] - H / 2
    d = _q(rng.uniform(5, 13) * s, inch)
    e = _q(max(d * 1.3, rng.uniform(8, 16) * s), inch)   # 孔中心到边
    pattern = rng.choice(["single", "pair", "grid", "row"])
    if pattern == "single":
        pos = [[u0 + e, v0 + e]]
    elif pattern == "pair":
        pos = [[u0 + e, v0 + e], [u0 + W - e, v0 + H - e]]
    elif pattern == "grid":
        pos = [[u0 + e, v0 + e], [u0 + W - e, v0 + e], [u0 + e, v0 + H - e], [u0 + W - e, v0 + H - e]]
    else:
        pitch = _q((W - 2 * e) / 2, inch)
        pos = [[u0 + e + i * pitch, v0 + e] for i in range(3)]
    pos = [[round(a, 4), round(b, 4)] for a, b in pos]
    feats = [{"id": "plate", "type": "base_extrude", "plane": plane,
              "profile": {"shape": "rect", "width": W, "height": H, "center": c0},
              "depth": T, "meta": _meta("generated")}]
    # 中间开口：放在孔带以内，不和孔干涉
    inner_u0, inner_u1 = u0 + e + d, u0 + W - e - d
    inner_v0, inner_v1 = v0 + e + d, v0 + H - e - d
    cut = rng.choice(["none", "rect", "circle"])
    if cut != "none" and inner_u1 - inner_u0 > 12 * s and inner_v1 - inner_v0 > 12 * s:
        if cut == "rect":
            w = _q(rng.uniform(0.3, 0.8) * (inner_u1 - inner_u0), inch)
            h = _q(rng.uniform(0.3, 0.8) * (inner_v1 - inner_v0), inch)
            cu = _q(rng.uniform(inner_u0 + w / 2, inner_u1 - w / 2) - u0, inch) + u0
            cv = _q(rng.uniform(inner_v0 + h / 2, inner_v1 - h / 2) - v0, inch) + v0
            feats.append({"id": "window", "type": "cut_extrude", "plane": plane,
                          "profile": {"shape": "rect", "width": w, "height": h, "center": [round(cu, 4), round(cv, 4)]},
                          "depth": "through_all", "direction": "both", "meta": _meta("generated")})
        else:
            dia = _q(rng.uniform(0.3, 0.8) * min(inner_u1 - inner_u0, inner_v1 - inner_v0), inch)
            cu = _q(rng.uniform(inner_u0 + dia / 2, inner_u1 - dia / 2) - u0, inch) + u0
            cv = _q(rng.uniform(inner_v0 + dia / 2, inner_v1 - dia / 2) - v0, inch) + v0
            feats.append({"id": "bore", "type": "cut_extrude", "plane": plane,
                          "profile": {"shape": "circle", "diameter": dia, "center": [round(cu, 4), round(cv, 4)]},
                          "depth": "through_all", "direction": "both", "meta": _meta("generated")})
    feats.append({"id": "holes", "type": "hole", "plane": plane, "diameter": d, "positions": pos,
                  "depth": "through_all", "direction": "both", "meta": _meta("generated")})
    if rng.random() < 0.5:
        r = _q(rng.uniform(0.25, 0.8) * (e - d / 2), inch)
        if r > 0:
            feats.append({"id": "corner_fillets", "type": "edge_treatment", "kind": "fillet", "size": r,
                          "edges": "vertical", "meta": _meta("generated")})
    return {"schema_version": "0.4", "part": _part(name, unit, std, "prismatic"), "features": feats,
            "open_questions": []}


def disk(rng: random.Random, unit: str, std: str, name: str) -> dict:
    """圆盘：中心孔 + 分布圆孔（起始角在坐标轴上）。"""
    inch = unit == "inch"
    s = 1 / 25.4 if inch else 1.0
    D = _q(rng.uniform(70, 160) * s, inch)
    T = _q(rng.uniform(6, 20) * s, inch)
    d0 = _q(rng.uniform(0.2, 0.4) * D, inch)
    n = rng.choice([3, 4, 6, 8])
    d = _q(rng.uniform(0.06, 0.1) * D, inch)
    pcd = _q(rng.uniform(d0 + 2.5 * d, D - 2.5 * d), inch)
    plane = rng.choice(["top", "front"])
    feats = [{"id": "disk", "type": "base_extrude", "plane": plane,
              "profile": {"shape": "circle", "diameter": D, "center": [0, 0]}, "depth": T, "meta": _meta("generated")},
             {"id": "center_bore", "type": "cut_extrude", "plane": plane,
              "profile": {"shape": "circle", "diameter": d0, "center": [0, 0]},
              "depth": "through_all", "direction": "both", "meta": _meta("generated")},
             {"id": "bolt_holes", "type": "hole", "plane": plane, "diameter": d,
              "bolt_circle": {"pcd": pcd, "count": n, "start_angle": rng.choice([0, 90])},
              "depth": "through_all", "direction": "both", "meta": _meta("generated")}]
    return {"schema_version": "0.4", "part": _part(name, unit, std, "prismatic"), "features": feats,
            "open_questions": []}


def shaft(rng: random.Random, unit: str, std: str, name: str) -> dict:
    """阶梯轴：2 到 4 段，可选通孔，可选端部倒角。"""
    inch = unit == "inch"
    s = 1 / 25.4 if inch else 1.0
    n = rng.randint(2, 4)
    radii = sorted({_q(rng.uniform(8, 30) * s, inch) for _ in range(n)}, reverse=rng.random() < 0.5)
    if len(radii) < 2:
        radii = [radii[0], _q(radii[0] * 1.4, inch)]
    lengths = [_q(rng.uniform(15, 50) * s, inch) for _ in radii]
    bore = _q(rng.uniform(0.25, 0.6) * min(radii), inch) if rng.random() < 0.4 else 0.0
    prof, h = [[bore, 0.0]], 0.0
    for r, L in zip(radii, lengths):
        prof.append([r, round(h, 4)])
        h += L
        prof.append([r, round(h, 4)])
    prof.append([bore, round(h, 4)])
    feats = [{"id": "shaft", "type": "base_revolve", "half_profile": prof, "meta": _meta("generated")}]
    if rng.random() < 0.5:
        c = _q(min(1.5 * s, 0.1 * radii[-1]), inch) or (1 / 8 if inch else 0.5)
        feats.append({"id": "end_chamfer", "type": "edge_treatment", "kind": "chamfer", "size": c,
                      "edges": "top_outer", "meta": _meta("generated")})
    return {"schema_version": "0.4", "part": _part(name, unit, std, "revolved"), "features": feats,
            "open_questions": []}


def flange(rng: random.Random, unit: str, std: str, name: str) -> dict:
    """法兰：盘 + 颈 + 通孔 + 分布圆孔。"""
    inch = unit == "inch"
    s = 1 / 25.4 if inch else 1.0
    R = _q(rng.uniform(40, 80) * s, inch)
    t = _q(rng.uniform(8, 20) * s, inch)
    rh = _q(rng.uniform(0.35, 0.55) * R, inch)
    H = _q(t + rng.uniform(15, 40) * s, inch)
    rb = _q(rng.uniform(0.35, 0.7) * rh, inch)
    d = _q(rng.uniform(0.12, 0.2) * (R - rh), inch) * 2
    d = _q(d, inch)
    pcd = _q(rh + R, inch)          # 分布圆在颈和外缘中间
    n = rng.choice([4, 6, 8])
    prof = [[rb, 0], [R, 0], [R, t], [rh, t], [rh, H], [rb, H]]
    feats = [{"id": "body", "type": "base_revolve", "half_profile": prof, "meta": _meta("generated")},
             {"id": "bolt_holes", "type": "hole", "plane": "top", "offset": 0, "diameter": d,
              "bolt_circle": {"pcd": pcd, "count": n, "start_angle": rng.choice([0, 90])},
              "depth": "through_all", "direction": "both", "meta": _meta("generated")}]
    return {"schema_version": "0.4", "part": _part(name, unit, std, "revolved"), "features": feats,
            "open_questions": []}


FAMILIES = {"plate": plate, "disk": disk, "shaft": shaft, "flange": flange}


# ---------------------------------------------------------------- 标签对应到观察 ID

def _attach_observations(folder: Path, labels: list[dict], files: dict) -> dict:
    """用 skill 自己的预处理跑一遍输入，把每个标签对到观察 ID。对不上的说明预处理有缺口。"""
    import observations
    import preprocess_drawing as pre
    stats = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if "dxf" in files:
            ext = pre.from_dxf(Path(files["dxf"]), tmp)
            doc = observations.from_extract(ext, Path(files["dxf"]))
            by_handle = {o.get("entity_handle"): o["id"] for o in doc["observations"] if o.get("entity_handle")}
            hit = 0
            for lab in labels:
                oid = by_handle.get(lab["handle"])
                if oid:
                    lab.setdefault("observations", {})["dxf"] = oid
                    hit += 1
            stats["dxf"] = {"labels": len(labels), "matched": hit}
        if "pdf" in files:
            ext = pre.from_pdf(Path(files["pdf"]), tmp, 100)
            doc = observations.from_extract(ext, Path(files["pdf"]))
            hit = 0
            for lab in labels:
                if "pdf_pt" not in lab:
                    continue
                x, y = lab["pdf_pt"]
                cands = [o for o in doc["observations"]
                         if o["bbox"][0] - 2 <= x <= o["bbox"][2] + 2 and o["bbox"][1] - 2 <= y <= o["bbox"][3] + 2]
                if cands:
                    lab.setdefault("observations", {})["pdf"] = min(
                        cands, key=lambda o: (o["bbox"][2] - o["bbox"][0]) * (o["bbox"][3] - o["bbox"][1]))["id"]
                    hit += 1
            stats["pdf"] = {"labels": len(labels), "matched": hit}
            page = ext["pages"][0]["size_pt"]
            if "png" in files:
                from PIL import Image
                with Image.open(files["png"]) as im:
                    kx, ky = im.width / page[0], im.height / page[1]
                for lab in labels:
                    if "pdf_pt" in lab:
                        lab["png_px"] = [round(lab["pdf_pt"][0] * kx, 1), round(lab["pdf_pt"][1] * ky, 1)]
    return stats


# ---------------------------------------------------------------- 主流程

def make_case(rng: random.Random, folder: Path, family: str, std: str, formats: set[str]) -> dict:
    import cadquery as cq
    import ftable
    import make_test_drawing as mtd
    import preview_cadquery
    from observations import dump, sha256

    unit = "inch" if std == "ASME" else "mm"
    table = FAMILIES[family](rng, unit, std, folder.name)
    resolved = ftable.to_mm(ftable.resolve(table))
    solid = preview_cadquery.build(resolved)
    if len(solid.solids().vals()) != 1:
        raise ValueError("not a single solid")
    ans = mtd.make(table, std, folder, with_unit=True, scan="scan" in formats, dwg=False)
    cq.exporters.export(solid, str(folder / "answer.step"))
    files = {k: v for k, v in ans["files"].items() if k in ("dxf", "pdf", "png")}
    stats = _attach_observations(folder, ans["dimension_labels"], files)
    keep = {"dxf": "drawing.dxf", "pdf": "drawing.pdf", "pdf_notext": "drawing_notext.pdf",
            "png": "drawing.png", "scan": "drawing_scan.jpg"}
    for key, name in keep.items():
        if key not in formats and (folder / name).exists():
            (folder / name).unlink()
    if "render_error" in ans["files"]:
        raise RuntimeError(ans["files"]["render_error"])
    answer = {"source_table": table, "standard": std, "family": family,
              "volume_mm3": ans["volume_mm3"], "surface_area_mm2": ans["surface_area_mm2"],
              "bbox_mm": ans["bbox_mm"], "hole_count": ans["hole_count"],
              "dimension_labels": ans["dimension_labels"], "observation_match": stats}
    dump(answer, folder / "answer.json")
    inputs = {k: name for k, name in keep.items() if k in formats and (folder / name).exists()}
    primary = inputs.get("pdf") or inputs.get("dxf") or next(iter(inputs.values()))
    return {"id": folder.name, "family": family, "standard": std, "units": unit,
            "drawing": f"{folder.name}/{primary}", "sha256": sha256(folder / primary),
            "inputs": {k: f"{folder.name}/{v}" for k, v in inputs.items()},
            "answer_step": f"{folder.name}/answer.step", "answer_table": f"{folder.name}/answer.json",
            "expected": {"volume_mm3": ans["volume_mm3"], "surface_area_mm2": ans["surface_area_mm2"],
                         "bbox_mm": ans["bbox_mm"], "hole_count": ans["hole_count"]},
            "dimension_count": len(ans["dimension_labels"]), "observation_match": stats,
            "license": "MIT", "evaluation": "synthetic_geometry_and_association",
            "alignment": "pose_free"}


def generate(out: Path, count: int, seed: int, families: list[str], formats: set[str]) -> list[dict]:
    if out.exists():
        raise ValueError("输出文件夹已存在，换一个新的")
    out.mkdir(parents=True)
    rng = random.Random(seed)
    cases, failures = [], []
    i = 0
    while len(cases) < count and i < count * 3:
        family = families[i % len(families)]
        std = STANDARDS[(i // len(families)) % len(STANDARDS)]
        folder = out / f"{family}-{std.lower()}-{len(cases) + 1:03}"
        i += 1
        try:
            cases.append(make_case(rng, folder, family, std, formats))
            m = cases[-1]["observation_match"]
            print(f"{folder.name}: {cases[-1]['dimension_count']} dims, match {m}", flush=True)
        except Exception as e:  # noqa: BLE001  随机参数偶尔会做出不合法的零件，换一组
            failures.append({"folder": folder.name, "error": str(e)[:300]})
            shutil.rmtree(folder, ignore_errors=True)
            print(f"{folder.name}: skipped ({str(e)[:120]})", flush=True)
    from observations import dump
    dump({"schema_version": "1.1", "generator": "dev/tools/generate_dataset.py", "seed": seed,
          "purpose": "Synthetic drawings with dimension-to-feature labels. Not a real-world accuracy claim.",
          "license": "MIT", "cases": cases, "skipped": failures}, out / "manifest.json")
    return cases


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--families", default=",".join(FAMILIES))
    ap.add_argument("--formats", default="dxf,pdf,pdf_notext,png,scan",
                    help="保留哪些输入：dxf,pdf,pdf_notext,png,scan")
    args = ap.parse_args()
    fams = [f for f in args.families.split(",") if f]
    bad = [f for f in fams if f not in FAMILIES]
    if bad:
        ap.error(f"未知零件族 {bad}，可选 {sorted(FAMILIES)}")
    formats = set(args.formats.split(","))
    cases = generate(Path(args.out), args.count, args.seed, fams, formats)
    print(json.dumps({"cases": len(cases)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
