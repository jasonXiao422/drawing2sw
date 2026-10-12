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


def prepare(manifest, case_id, out):
    root, case = load_case(manifest, case_id)
    source = case_path(root, case["drawing"])
    out = Path(out)
    if out.exists():
        raise ValueError("Use a new input directory")
    digest = observations.sha256(source)
    if case.get("sha256") and digest != case["sha256"]:
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
    if evidence and evidence["source"]["sha256"] != drawing_hash:
        errors.append("Evidence does not match the benchmark drawing")
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
            # Coordinate-sensitive comparison; the case must specify the same datum.
            delta = abs(actual.cut(answer).Volume()) + abs(answer.cut(actual).Volume())
            relative = delta / max(abs(answer.Volume()), 1e-9)
            result["symmetric_difference"] = {"volume_mm3": delta, "relative": relative,
                                               "pass": relative <= 1e-5}
            result["status"] = "geometry_passed" if result["properties"]["verified"] and relative <= 1e-5 else "failed"
    except Exception as exc:
        result.update(status="build_failed", reason=str(exc))
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
    args = ap.parse_args()
    if Path(args.out).exists():
        ap.error("Output already exists")
    if args.action == "prepare":
        prepare(args.manifest, args.case, args.out)
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
