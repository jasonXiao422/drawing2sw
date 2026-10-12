"""出考题：用 SolidWorks 把一个现成零件出成工程图，答案（零件本身）单独放。

方向说明：skill 本身是"图纸 → 建模"。这个脚本只用来出测试题，就像老师先有答案再出卷子。
被测的 AI 只能看 drawing.pdf / drawing.png，不能看 answer/ 里的东西。

用法：
  python dev/tools/sw_make_exam.py <零件.sldprt> tests/drawings/004_名字

输出：
  <out>/drawing.pdf、drawing.png、drawing.dwg   考卷（第一角三视图 + 轴测图 + 模型里的尺寸、孔标注）
  <out>/answer/answer.SLDPRT                  零件副本
  <out>/answer/answer_report.json             体积、表面积、包围盒、特征树（读图时不要打开）
原零件只读打开，不改。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
from pathlib import Path

import pythoncom
import win32com.client

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import sw_build  # noqa: E402
from sw_build import call  # noqa: E402

SW_DOC_PART, SW_DOC_DRAWING = 1, 3
SW_OPEN_SILENT, SW_OPEN_READONLY = 1, 2
# swInsertAnnotation_e，一类一类分开插（合在一个掩码里会一个都插不进去，10-10 实测）：
# 标记为工程图的尺寸 32768、孔标注 1048576、孔向导位置尺寸 131072、基准 2、形位公差 32、表面粗糙度 128、装饰螺纹 1
ANNOT_GROUPS = [32768, 1048576, 131072, 2, 32, 128, 1]
FEATURE_SKIP = ("Folder", "OriginProfileFeature", "RefPlane", "ProfileFeature", "DetailCabinet", "MaterialFolder")


def _byref():
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


SW_AUTO_SCALE_3VIEW = 86  # swAutomaticScaling3ViewDrawings
SHEETS = {"a3": (0.42, 0.297), "a2": (0.594, 0.42)}
STD_SCALES = [1, 1.5, 2, 2.5, 3, 4, 5, 10, 20, 50]  # 缩小比例 1:k


def drawing_template(sheet: str) -> str:
    for root in glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS *\templates"):
        p = os.path.join(root, f"gb_{sheet}.drwdot")
        if os.path.isfile(p):
            return p
    raise RuntimeError(f"找不到 gb_{sheet}.drwdot 工程图模板")


def mark_all_dims(doc) -> int:
    """把零件里所有特征和草图尺寸都标成"给工程图用"，插模型尺寸时才插得进来（孔位、圆角常常没标）。"""
    n = 0

    def mark(f):
        nonlocal n
        d = call(f, "GetFirstDisplayDimension")
        while d is not None:
            try:
                d.MarkedForDrawing = True
                n += 1
            except Exception:  # noqa: BLE001
                pass
            d = call(f, "GetNextDisplayDimension", d)

    f = call(doc, "FirstFeature")
    while f is not None:
        mark(f)
        s = call(f, "GetFirstSubFeature")
        while s is not None:
            mark(s)
            s = call(s, "GetNextSubFeature")
        f = call(f, "GetNextFeature")
    return n


def feature_tree(doc) -> list[dict]:
    out = []
    f = call(doc, "FirstFeature")
    while f is not None:
        t = call(f, "GetTypeName2")
        if not any(s in t for s in FEATURE_SKIP):
            out.append({"name": call(f, "Name"), "type": t})
        f = call(f, "GetNextFeature")
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("part")
    ap.add_argument("out")
    ap.add_argument("--sheet", choices=sorted(SHEETS), default="a2")
    ap.add_argument("--scale", type=float, default=0, help="缩小比例 1:k 的 k；默认按零件大小选，单个视图约 110 mm")
    args = ap.parse_args()

    src = str(Path(args.part).resolve())
    out = Path(args.out).resolve()
    ans_dir = out / "answer"
    ans_dir.mkdir(parents=True, exist_ok=True)

    app = sw_build.connect()

    # 1. 答案：零件副本 + 量测 + 特征树
    shutil.copy2(src, ans_dir / "answer.SLDPRT")
    part = app.OpenDoc6(src, SW_DOC_PART, SW_OPEN_SILENT | SW_OPEN_READONLY, "", _byref(), _byref())
    if part is None:
        raise SystemExit(f"打不开零件: {src}")
    rep = sw_build.measure(part)
    rep.update(source=src, features=feature_tree(part),
               bodies=len(part.GetBodies2(0, True) or ()))
    (ans_dir / "answer_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    # 2. 出图用的零件副本：尺寸全部标成"给工程图"。放在 answer/ 里，读图的 AI 不看
    exam_src = ans_dir / "exam_src.SLDPRT"
    shutil.copy2(src, exam_src)
    os.chmod(exam_src, 0o666)
    ep = app.OpenDoc6(str(exam_src), SW_DOC_PART, SW_OPEN_SILENT, "", _byref(), _byref())
    n_marked = mark_all_dims(ep)
    ep.Save3(1, _byref(), _byref())

    W, H = SHEETS[args.sheet]
    k = args.scale or next((c for c in STD_SCALES if max(rep["bbox_mm"]) / c <= 110), STD_SCALES[-1])
    drw = app.NewDocument(drawing_template(args.sheet), 0, 0, 0)
    if drw is None:
        raise SystemExit("新建工程图失败")
    sheet = call(drw, "GetCurrentSheet")
    # 三视图由 SolidWorks 自己排、自动定比例。10-10 实测：逐个设视图位置会跑出图纸；建完再改比例视图线条会丢；
    # 关掉"三视图自动缩放"（全局设置 86）只出一个视图。所以 --scale 目前不生效，比例由 SolidWorks 决定
    sheet.SetScale(1, k, True, False)
    ok = drw.Create1stAngleViews2(str(exam_src))
    views = []
    v = call(drw, "GetFirstView")
    v = call(v, "GetNextView") if v else None
    while v is not None:
        views.append(v)
        v = call(v, "GetNextView")
    iso = None
    for name in ("*等轴测", "*Isometric"):
        iso = drw.CreateDrawViewFromModelView3(str(exam_src), name, 0.82 * W, 0.72 * H, 0)
        if iso is not None:
            break
    if iso is not None:
        for fn in (lambda: iso.SetDisplayMode4(False, 2, False, True, False),
                   lambda: iso.SetDisplayMode3(False, 2, False, True)):
            try:
                fn()
                break
            except Exception:  # noqa: BLE001
                pass
    drw.ClearSelection2(True)
    n_ann = {}
    for t in ANNOT_GROUPS:
        drw.ClearSelection2(True)
        ann = drw.InsertModelAnnotations3(0, t, True, False, False, True)
        n_ann[t] = len(ann) if ann else 0
    try:
        call(drw, "ForceRebuild3", False)
    except Exception:  # noqa: BLE001
        pass

    # 3. 导出考卷
    files = {}
    for ext in ("pdf", "dwg"):
        p = out / f"drawing.{ext}"
        r = drw.SaveAs3(str(p), 0, SW_OPEN_SILENT | 2)
        files[ext] = str(p) if p.exists() else f"失败({r})"
    drw.SaveAs3(str(ans_dir / "drawing.SLDDRW"), 0, SW_OPEN_SILENT)
    try:  # SolidWorks 直接存 PNG 是屏幕截图，只截到一角；改从 PDF 渲染
        import fitz  # noqa: PLC0415
        pg = fitz.open(str(out / "drawing.pdf"))[0]
        pg.get_pixmap(dpi=200).save(str(out / "drawing.png"))
        files["png"] = str(out / "drawing.png")
    except Exception as e:  # noqa: BLE001
        files["png"] = f"失败({e})"
    app.CloseDoc(call(drw, "GetTitle"))
    app.CloseDoc(call(part, "GetTitle"))
    app.CloseDoc(call(ep, "GetTitle"))

    print(json.dumps({"scale": f"1:{k}", "dims_marked": n_marked, "views": ok, "n_views": len(views), "iso": iso is not None, "annotations": n_ann,
                      "files": files, "answer": {k: rep[k] for k in ("volume_mm3", "bbox_mm", "face_count")}},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
