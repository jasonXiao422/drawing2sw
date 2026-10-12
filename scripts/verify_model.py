"""比对建模结果与标准答案。

用法:
  python verify_model.py part.json --report work/sw_report.json [--against work/preview_report.json]

参照优先级: --against 指定的报告 > 特征表 part.expected
通过标准: 体积、表面积、包围盒误差 <= 1%（--tolerance 可改），单实体，孔数一致。
通过只说明测量属性对上了，不证明读图正确（drawing_verified 始终为 false）。
镜像件体积相同，体积校验发现不了投影法判反，投影法必须人工确认。
包围盒默认排序后比，忽略朝向；两模型坐标系对齐后才用 --aligned-axes。
"""
from __future__ import annotations
import argparse
import json
import math
import sys
import ftable

TOL = 0.01


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-9)


def finite_number(x):
    return isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)


def compare(actual, ref, ref_holes=None, *, tolerance=TOL, aligned_axes=False):
    if not finite_number(tolerance) or tolerance < 0:
        raise ValueError('tolerance must be finite and nonnegative')
    checks, diagnostics = [], []
    for key in ('volume_mm3', 'surface_area_mm2', 'bbox_mm'):
        if key not in ref:
            continue
        a, b = actual.get(key), ref[key]
        c = {'item': key, 'actual': a, 'expected': b, 'pass': False}
        if key == 'bbox_mm':
            valid = all(isinstance(v, (list, tuple)) and len(v) == 3
                        and all(finite_number(n) and n > 0 for n in v) for v in (a, b))
            if valid:
                a, b = (a, b) if aligned_axes else (sorted(a), sorted(b))
                error = max(rel(x, y) for x, y in zip(a, b))
        else:
            valid = all(finite_number(v) and v > 0 for v in (a, b))
            if valid:
                error = rel(a, b)
        if valid:
            c.update(rel_error=error, **{'pass': error <= tolerance})
        else:
            c['reason'] = 'missing_or_invalid_metric'
        checks.append(c)
    measured = len(checks)
    for label, report in (('actual', actual), ('reference', ref)):
        if report.get('status') not in (None, 'ok'):
            checks.append({'item': f'{label}_status', 'actual': report.get('status'), 'pass': False})
    for key in ('solid_count', 'face_count'):
        if key in actual or key in ref:
            d = {'item': key, 'actual': actual.get(key), 'expected': ref.get(key)}
            if key == 'face_count' and d['actual'] and d['expected'] and d['actual'] != d['expected']:
                d['note'] = '面数不一致，人工看一眼（STEP 导入、样条齿面也会让面数不同）'
            diagnostics.append(d)
    if actual.get('solid_count') is not None and actual['solid_count'] != 1:
        checks.append({'item': 'single_solid', 'actual': actual['solid_count'], 'pass': False})
    if ref_holes is not None:
        got = actual.get('hole_count_from_table')
        diagnostics.append({'item': 'declared_hole_count', 'actual': got,
                            'expected': ref_holes, 'matches': got == ref_holes,
                            'note': 'Count comes from the input table, not measured geometry.'})
        if got != ref_holes:
            checks.append({'item': 'declared_hole_count', 'actual': got, 'expected': ref_holes, 'pass': False})
    passed = measured > 0 and all(c['pass'] for c in checks)
    return {'verified': passed, 'scope': 'measured_properties_only', 'drawing_verified': False,
            'status': 'passed' if passed else ('unverified' if measured == 0 else 'failed'),
            'bbox_axes_aligned': aligned_axes, 'tolerance': tolerance,
            'checks': checks, 'diagnostics': diagnostics,
            'limitations': ['Position, handedness, individual dimensions and feature intent require separate checks.']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('table')
    ap.add_argument('--report', required=True)
    ap.add_argument('--against')
    ap.add_argument('--tolerance', type=float, default=TOL)
    ap.add_argument('--aligned-axes', action='store_true', help='Only after aligning both coordinate systems')
    args = ap.parse_args()
    table = ftable.load_raw(args.table)
    actual = ftable.load_raw(args.report)
    ref = ftable.load_raw(args.against) if args.against else table['part'].get('expected', {})
    if not ref:
        print('没有标准答案：特征表里没有 part.expected，也没有给 --against。')
        return 1
    holes = ref.get('hole_count', ref.get('hole_count_from_table'))
    result = compare(actual, ref, holes, tolerance=args.tolerance, aligned_axes=args.aligned_axes)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print({'passed': '通过（只代表测量属性）', 'failed': '未通过'}.get(result['status'], '无法判断：没有可比的测量属性'))
    return 0 if result['verified'] else 1


if __name__ == '__main__':
    sys.exit(main())
