"""比对建模结果与标准答案。

用法:
  python verify_model.py part.json --report work/sw_report.json [--against work/preview_report.json]

参照优先级: --against 指定的报告 > 特征表 part.expected
通过标准（与 SolidPilot 的 compare_parts 一致）: 体积、包围盒误差 <= 1%，孔数一致。
注意：镜像件体积相同，体积校验发现不了投影法判反，投影法必须人工确认。
"""
from __future__ import annotations

import argparse
import json
import sys

import ftable

TOL = 0.01


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-9)


def compare(actual: dict, ref: dict, ref_holes: int | None) -> dict:
    checks = []
    if "volume_mm3" in ref and "volume_mm3" in actual:
        e = rel(actual["volume_mm3"], ref["volume_mm3"])
        checks.append({"item": "体积", "actual": actual["volume_mm3"], "expected": ref["volume_mm3"],
                       "rel_error": round(e, 5), "pass": e <= TOL})
    if "bbox_mm" in ref and "bbox_mm" in actual:
        a, r = sorted(actual["bbox_mm"]), sorted(ref["bbox_mm"])  # 排序后比，忽略朝向差异
        e = max(rel(x, y) for x, y in zip(a, r))
        checks.append({"item": "包围盒", "actual": actual["bbox_mm"], "expected": ref["bbox_mm"],
                       "rel_error": round(e, 5), "pass": e <= TOL})
    if "surface_area_mm2" in ref and "surface_area_mm2" in actual:
        # 表面积能抓到体积抓不到的错：漏倒角圆角、孔位置对但形状错
        e = rel(actual["surface_area_mm2"], ref["surface_area_mm2"])
        checks.append({"item": "表面积", "actual": actual["surface_area_mm2"],
                       "expected": ref["surface_area_mm2"], "rel_error": round(e, 5), "pass": e <= TOL})
    if ref.get("face_count") and actual.get("face_count"):
        # 面数只提示不判失败：STEP 导入、样条齿面会让面数不同
        checks.append({"item": "面数（仅提示）", "actual": actual["face_count"],
                       "expected": ref["face_count"], "pass": True,
                       "note": "一致" if actual["face_count"] == ref["face_count"] else "不一致，人工看一眼"})
    if ref_holes is not None:
        got = actual.get("hole_count_from_table")
        checks.append({"item": "孔数", "actual": got, "expected": ref_holes, "pass": got == ref_holes})
    if actual.get("status") not in (None, "ok"):
        checks.append({"item": "建模状态", "actual": actual["status"],
                       "reason": actual.get("reason"), "pass": False})
    return {"verified": bool(checks) and all(c["pass"] for c in checks), "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("table")
    ap.add_argument("--report", required=True, help="sw_report.json 或 preview 报告")
    ap.add_argument("--against", help="作为标准答案的另一份报告")
    args = ap.parse_args()

    table = ftable.load(args.table)
    actual = json.load(open(args.report, encoding="utf-8"))
    if args.against:
        ref = json.load(open(args.against, encoding="utf-8"))
        ref_holes = ref.get("hole_count_from_table")
    else:
        ref = table["part"].get("expected", {})
        ref_holes = ref.get("hole_count")
        if not ref:
            print("没有标准答案：特征表里没有 part.expected，也没有给 --against。")
            return 1
    res = compare(actual, ref, ref_holes)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print("通过" if res["verified"] else "未通过")
    return 0 if res["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
