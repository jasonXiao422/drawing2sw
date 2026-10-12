"""Prepare isolated drawing-only inputs and score saved model outputs offline.

No model API keys, paid calls or answer files enter the prepared input directory.
Preparing a folder alone is not a security sandbox: run the model outside the
repository, granting access to the input folder plus a clean skill distribution.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import time
import observations


def load_case(manifest, case_id):
    manifest = Path(manifest).resolve()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    matches = [c for c in data["cases"] if c["id"] == case_id]
    if len(matches) != 1:
        raise ValueError("Case ID missing or duplicated")
    return manifest.parent, matches[0]


def case_path(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Case file escapes dataset root")
    return path


def prepare(manifest, case_id, out, input_format=None):
    root, case = load_case(manifest, case_id)
    if input_format:
        if input_format not in case.get("inputs", {}):
            raise ValueError(f"Case has no {input_format} input; available: {sorted(case.get('inputs', {}))}")
        source = case_path(root, case["inputs"][input_format])
    else:
        source = case_path(root, case["drawing"])
    out = Path(out)
    if out.exists():
        raise ValueError("Use a new input directory")
    digest = observations.sha256(source)
    if not input_format and case.get("sha256") and digest != case["sha256"]:
        raise ValueError("Drawing checksum mismatch")
    out.mkdir(parents=True)
    shutil.copyfile(source, out / ("drawing" + source.suffix.lower()))
    (out / "TASK.md").write_text(
        "Read the supplied single-part mechanical drawing with drawing2sw. Produce observations.json and part.json v0.5. "
        "Do not access answer models or alter skill scripts. Record ambiguities; do not invent missing dimensions. "
        "Run feature validation and a CadQuery preview if supported. Save the initial part.json before repairs. "
        "Report exact model version, elapsed time, number of repairs and human interventions. "
        "If unsupported or underdimensioned, report that outcome instead of approximating.\n", encoding="utf-8")
    observations.dump({"case_id": case_id, "source_sha256": digest, "answer_included": False}, out / "input_manifest.json")


def _rotations():
    """24 个保持手性的轴向旋转（不含镜像，镜像错误必须被判出来）。"""
    import itertools
    out = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            m = [[0.0] * 3 for _ in range(3)]
            for i, j in enumerate(perm):
                m[i][j] = float(signs[i])
            det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                   + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
            if det > 0:
                out.append(m)
    return out


def pose_free_difference(actual, answer):
    """不管模型把零件摆在哪个基准面上：试 24 种轴向旋转，对齐包围盒中心，取对称差最小的。"""
    import cadquery as cq
    ab = answer.BoundingBox()
    target = sorted([ab.xlen, ab.ylen, ab.zlen])
    best = None
    for m in _rotations():
        from OCP.gp import gp_Trsf
        trsf = gp_Trsf()
        trsf.SetValues(*m[0], 0.0, *m[1], 0.0, *m[2], 0.0)
        shape = cq.Shape.cast(actual.moved(cq.Location(trsf)).wrapped)
        bb = shape.BoundingBox()
        dims = [bb.xlen, bb.ylen, bb.zlen]
        if any(abs(a - b) > 0.01 * max(b, 1e-9) for a, b in zip(dims, [ab.xlen, ab.ylen, ab.zlen])):
            continue
        shape = shape.translate(cq.Vector(ab.center.x - bb.center.x, ab.center.y - bb.center.y,
                                          ab.center.z - bb.center.z))
        delta = abs(shape.cut(answer).Volume()) + abs(answer.cut(shape).Volume())
        if best is None or delta < best:
            best = delta
        if best <= 1e-9 * max(abs(answer.Volume()), 1.0):
            break   # 已经完全重合，不用再试别的摆法
    if best is None:  # 包围盒对不上任何摆法
        best = abs(actual.Volume()) + abs(answer.Volume())
    return best, target


def score_association(table, evidence, labels, answer_table):
    """每个标准尺寸：模型有没有观察到它、有没有特征引用它、引用它的特征对不对。"""
    import association
    gt_type = {f["id"]: f["type"] for f in answer_table.get("features", [])}
    obs = (evidence or {}).get("observations", [])

    def locate(lab):
        for o in obs:
            space = o.get("coordinate_space")
            if space == "dxf_wcs" and o.get("entity_handle") and o["entity_handle"] == lab.get("handle"):
                return o
            if space == "pdf_pt" and "pdf_pt" in lab and "bbox" in o:
                x, y = lab["pdf_pt"]
                b = o["bbox"]
                if b[0] - 3 <= x <= b[2] + 3 and b[1] - 3 <= y <= b[3] + 3:
                    return o
            if space == "image_px" and "png_px" in lab and "bbox" in o:
                x, y = lab["png_px"]
                b = o["bbox"]
                if b[0] - 8 <= x <= b[2] + 8 and b[1] - 8 <= y <= b[3] + 8:
                    return o
        return None

    citing = {}
    for f in table.get("features", []):
        for ref in (f.get("meta") or {}).get("evidence_refs", []):
            citing.setdefault(ref, []).append(f)
    rows, counts = [], {"labels": len(labels), "observed": 0, "cited": 0, "correct": 0, "wrong_feature": 0}
    for lab in labels:
        o = locate(lab)
        row = {"feature": lab["feature"], "param": lab["param"], "value": lab["value"],
               "observation": o["id"] if o else None, "status": "not_observed"}
        if o:
            counts["observed"] += 1
            feats = citing.get(o["id"], [])
            row["status"] = "uncited"
            if feats:
                counts["cited"] += 1
                ok = [f for f in feats if f.get("type") == gt_type.get(lab["feature"])
                      and association.contains(association.feature_numbers(f, table), lab["value"])]
                row["cited_by"] = [f.get("id") for f in feats]
                if ok:
                    counts["correct"] += 1
                    row["status"] = "correct"
                else:
                    counts["wrong_feature"] += 1
                    row["status"] = "wrong_feature"
        rows.append(row)
    n = max(counts["labels"], 1)
    counts["association_recall"] = round(counts["correct"] / n, 4)
    return {"summary": counts, "labels": rows,
            "note": "correct = a feature of the right type cites the dimension and uses its value"}


def score(manifest, case_id, table_path, evidence_path, model, interventions=0):
    import ftable
    from validate_feature_table import validate
    from verify_model import compare
    start = time.monotonic()
    root, case = load_case(manifest, case_id)
    table = ftable.load_raw(table_path)
    evidence = ftable.load_raw(evidence_path) if evidence_path else None
    errors, warnings = validate(table, evidence)
    drawing_hash = observations.sha256(case_path(root, case["drawing"]))
    allowed = {drawing_hash} | {observations.sha256(case_path(root, v)) for v in case.get("inputs", {}).values()}
    if evidence and evidence["source"]["sha256"] not in allowed:
        errors.append("Evidence does not match the benchmark drawing")
    elif evidence:
        drawing_hash = evidence["source"]["sha256"]
    result = {"case_id": case_id, "model": model, "source_sha256": drawing_hash,
              "table_sha256": observations.sha256(table_path), "human_interventions": interventions,
              "schema_valid": not errors, "errors": errors, "warnings": warnings,
              "status": "invalid" if errors else "unscored", "drawing_verified": False}
    if errors:
        return result
    if not case.get("expected"):
        result["reason"] = "No independently defined ground truth; manual review required"
        return result
    try:
        from preview_cadquery import build, report
        converted = ftable.load(table_path)
        shape = build(converted)
        props = report(shape, converted)
        result["properties"] = compare(props, case["expected"], case["expected"].get("hole_count"))
        result["status"] = "properties_passed" if result["properties"]["verified"] else "failed"
        if case.get("answer_step"):
            import cadquery as cq
            answer = cq.importers.importStep(str(case_path(root, case["answer_step"]))).val()
            actual = shape.val()
            if case.get("alignment") == "pose_free":
                delta, _ = pose_free_difference(actual, answer)
                mode = "pose_free_24_rotations_no_mirror"
            else:  # Coordinate-sensitive comparison; the case must specify the same datum.
                delta = abs(actual.cut(answer).Volume()) + abs(answer.cut(actual).Volume())
                mode = "same_datum"
            relative = delta / max(abs(answer.Volume()), 1e-9)
            result["symmetric_difference"] = {"volume_mm3": delta, "relative": relative,
                                               "pass": relative <= 1e-5, "alignment": mode}
            result["status"] = "geometry_passed" if result["properties"]["verified"] and relative <= 1e-5 else "failed"
    except Exception as exc:
        result.update(status="build_failed", reason=str(exc))
    answer_path = case.get("answer_table")
    if answer_path:
        answer_doc = json.loads(case_path(root, answer_path).read_text(encoding="utf-8"))
        if answer_doc.get("dimension_labels"):
            result["association"] = score_association(table, evidence, answer_doc["dimension_labels"],
                                                      answer_doc.get("source_table", {}))
    result["evaluation_seconds"] = round(time.monotonic() - start, 3)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["prepare", "score"])
    ap.add_argument("manifest")
    ap.add_argument("--case", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--table")
    ap.add_argument("--observations")
    ap.add_argument("--model")
    ap.add_argument("--human-interventions", type=int, default=0)
    ap.add_argument("--format", help="prepare: which input to hand out (dxf, pdf, pdf_notext, png, scan)")
    args = ap.parse_args()
    if Path(args.out).exists():
        ap.error("Output already exists")
    if args.action == "prepare":
        prepare(args.manifest, args.case, args.out, args.format)
    else:
        if not args.table or not args.model:
            ap.error("score needs --table and --model")
        result = score(args.manifest, args.case, args.table, args.observations, args.model, args.human_interventions)
        observations.dump(result, args.out)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] not in ("geometry_passed", "properties_passed"):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
