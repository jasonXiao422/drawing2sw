"""读标准答案模型（.SLDPRT / .STEP / .STP / .IGS），量出体积、包围盒、表面积、面数。

用法:
  python answer_props.py tests/drawings/002_xxx/answer.SLDPRT
  python answer_props.py tests/drawings/002_xxx/answer.SLDPRT --step   # 另存一份 answer.step，给 CadQuery 逐面比对
  -> 写出同目录 answer_report.json，格式与 sw_build 的 sw_report.json 一致，
     可直接用 verify_model.py part.json --report work/sw_report.json --against <answer_report.json> 对答案。

只读打开，不保存、不改原文件。量完关闭。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sw_build import MM, call, connect

SW_DOC_PART = 1
SW_OPEN_SILENT, SW_OPEN_READONLY = 1, 2


def open_model(app, path: Path):
    import pythoncom  # noqa: PLC0415
    import win32com.client  # noqa: PLC0415

    err = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warn = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    if path.suffix.lower() == ".sldprt":
        doc = app.OpenDoc6(str(path), SW_DOC_PART, SW_OPEN_SILENT | SW_OPEN_READONLY, "", err, warn)
    else:  # STEP / IGES 等中性格式，导入后是新零件
        data = app.GetImportFileData(str(path))
        doc = app.LoadFile4(str(path), "r", data, err)
    if doc is None:
        raise RuntimeError(f"打不开 {path.name}，错误码 {err.value}")
    return doc


def measure_answer(doc) -> dict:
    doc.ForceRebuild3(False)
    mp = call(doc.Extension, "CreateMassProperty")
    box = doc.GetPartBox(True)
    faces = 0
    for body in (doc.GetBodies2(0, True) or ()):  # 0 = 实体
        faces += body.GetFaceCount()
    return {
        "volume_mm3": round(mp.Volume * 1e9, 3),
        "surface_area_mm2": round(mp.SurfaceArea * 1e6, 3),
        "bbox_mm": [round(abs(box[i + 3] - box[i]) / MM, 4) for i in range(3)],
        "face_count": faces,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--report", help="默认写到模型同目录 answer_report.json")
    ap.add_argument("--step", action="store_true", help="另存 answer.step（盲读做完之后诊断用，不改原文件）")
    args = ap.parse_args()

    path = Path(args.model).resolve()
    app = connect()
    doc = open_model(app, path)
    rep = {"backend": "answer", "source": str(path), "status": "ok", **measure_answer(doc)}
    if args.step:
        step = path.with_name("answer.step")
        # SaveAs3 选项 3 = 静默 + 另存副本，原 SLDPRT 不动
        err = doc.SaveAs3(str(step), 0, 3)
        rep["step"] = str(step) if err == 0 and step.exists() else None
        if rep["step"] is None:
            rep["step_error"] = err
    try:
        app.CloseDoc(call(doc, "GetTitle"))
    except Exception:  # noqa: BLE001
        pass
    out = Path(args.report) if args.report else path.with_name("answer_report.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
