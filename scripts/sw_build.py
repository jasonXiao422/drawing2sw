"""按特征表在 SolidWorks 中建模（Windows + pywin32）。

用法:
  python sw_build.py --check                         # 环境检查
  python sw_build.py part.json -o D:/out/part.SLDPRT [--report work/sw_report.json]

设计规则（见 dev/DEVELOPING.md）:
  * 所有数值经 API 传入，统一 mm -> m，不依赖零件模板单位。
  * 基准面按特征树顺序取前三个 RefPlane，不按名字，中英文界面通用。
  * 草图期间关闭"创建时输入尺寸"并打开 AddToDB，避免弹窗和自动吸附。
  * 不支持的情况返回 capability_blocked，不做近似替代。

状态: 拉伸基体、切除、通孔已在 SolidWorks 2025 学生版实测通过（体积与手算一致）。
      v0.3 新增（待实测）：加料拉伸 extrude、圆弧轮廓 path（三点画弧）、任意斜面（三点建基准面，兜底用平面实体面）。
      倒角/圆角：用 preview_cadquery.edge_points 算出边中点，再按坐标选边，待实测。
      旋转基体、负偏移基准面待实测/实现。问题记到 dev/DEVELOPING.md。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import ftable

MM = 0.001  # mm -> m

# SolidWorks 常量（swconst）
SW_DEFAULT_TEMPLATE_PART = 8          # swUserPreferenceStringValue_e.swDefaultTemplatePart
SW_INPUT_DIM_ON_CREATE = 10           # swUserPreferenceToggle_e.swInputDimValOnCreate
END_BLIND, END_THROUGH_ALL, END_MIDPLANE = 0, 1, 6
REFPLANE_DISTANCE = 8                 # swRefPlaneReferenceConstraint_Distance
REFPLANE_COINCIDENT = 4               # swRefPlaneReferenceConstraint_Coincident
# 文档单位（只影响界面显示，几何一律按米传入，见 DEVELOPING.md #1）
SW_UNIT_SYSTEM = 471                  # swUserPreferenceIntegerValue_e.swUnitSystem
SW_UNITS_LINEAR = 51                  # swUserPreferenceIntegerValue_e.swUnitsLinear
UNIT_SYSTEM = {"mm": 5, "inch": 3, "cm": 4, "m": 4}   # MMGS / IPS / 自定义
LINEAR_UNIT = {"mm": 0, "cm": 1, "m": 2, "inch": 3}   # swLengthUnit_e


class CapabilityBlocked(Exception):
    pass


def call(obj, name: str, *args):
    """兼容 pywin32 后期绑定：无参方法有时被暴露成属性，直接返回值而不是函数。"""
    attr = getattr(obj, name)
    # 属性返回的 COM 对象 (CDispatch) 本身也是 callable，调用它会报"找不到成员"，直接返回
    if type(attr).__name__ == "CDispatch" or not callable(attr):
        return attr
    return attr(*args)


# ---------------------------------------------------------------- 连接与环境

def connect():
    if sys.platform != "win32":
        raise SystemExit("SolidWorks 只能在 Windows 上运行。其他系统请用 preview_cadquery.py。")
    import win32com.client  # noqa: PLC0415

    import time  # noqa: PLC0415

    # SolidWorks 没开时，Dispatch 会自动启动它。启动较慢，等它加载完再继续。
    print("连接 SolidWorks（没开会自动启动，首次可能要 1~2 分钟）...", flush=True)
    app = win32com.client.Dispatch("SldWorks.Application")
    app.Visible = True
    t0 = time.time()
    while time.time() - t0 < 180:
        try:
            if call(app, "StartupProcessCompleted"):
                break
        except Exception:  # noqa: BLE001  旧版本没有这个属性，直接继续
            break
        time.sleep(2)
    print(f"SolidWorks 已就绪（{time.time() - t0:.0f} s）", flush=True)
    return app


MARK = "drawing2sw"   # 自己新建的零件都写这个自定义属性，下次建模前据此关掉


def _is_ours(d) -> bool:
    try:
        mgr = call(d, "Extension").CustomPropertyManager("")
        return MARK in (call(mgr, "GetNames") or ())
    except Exception:  # noqa: BLE001
        return False


def close_previous(app, out_dir: Path) -> list[str]:
    """建新零件前关掉旧窗口：
    1. 带 drawing2sw 标记的文档：skill 自己建的（包括中途失败、没保存的），直接关，不保存；
    2. 路径在输出文件夹里、没有未保存改动的文档。
    用户自己打开的其他文件不动；输出文件夹里被手动改过、还没保存的也不动。"""
    closed = []
    out_dir = str(out_dir.resolve()).lower()
    for d in list(call(app, "GetDocuments") or ()):
        try:
            path = (call(d, "GetPathName") or "").lower()
            title = call(d, "GetTitle")
            in_out = bool(path) and path.startswith(out_dir)
            ours = _is_ours(d)
            if not (ours or in_out):
                continue
            if in_out and call(d, "GetSaveFlag") and not ours:
                print(f"跳过（有未保存的改动）：{path}", flush=True)
                continue
            app.CloseDoc(title)
            closed.append(path or title)
        except Exception:  # noqa: BLE001
            pass
    return closed


def remove_versions(out: Path) -> list[str]:
    """删掉同名零件的旧版本（name.SLDPRT、name_1.SLDPRT ...）。放弃的建模不留。"""
    import re as _re  # noqa: PLC0415
    pat = _re.compile(_re.escape(out.stem) + r"(_\d+)?" + _re.escape(out.suffix), _re.I)
    removed = []
    for f in out.parent.glob("*"):
        if f.is_file() and pat.fullmatch(f.name):
            try:
                f.unlink()
                removed.append(f.name)
            except OSError:
                removed.append(f"{f.name}（被占用，没删掉）")
    return removed


def find_part_template(app) -> tuple[str | None, list[str]]:
    """按顺序找零件模板，返回 (第一个存在的路径, 试过的全部路径)。"""
    import glob  # noqa: PLC0415
    import os  # noqa: PLC0415

    tried: list[str] = []
    try:
        tried.append(app.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART) or "")
    except Exception:  # noqa: BLE001
        pass
    try:
        tried.append(app.GetDocumentTemplate(1, "", 0, 0, 0) or "")  # swDocPART = 1
    except Exception:  # noqa: BLE001
        pass
    for root in (r"C:\ProgramData\SOLIDWORKS", r"C:\ProgramData\SolidWorks"):
        hits = glob.glob(os.path.join(root, "*", "templates", "*.prtdot"))
        hits.sort(key=lambda p: (not os.path.basename(p).lower().startswith(("gb_part", "part")), p))
        tried.extend(hits)
    for p in tried:
        if p and os.path.isfile(p):
            return p, tried
    return None, tried


def env_check() -> dict:
    info = {"ok": False}
    try:
        app = connect()
        tpl, tried = find_part_template(app)
        info.update(
            ok=tpl is not None,
            revision=call(app, "RevisionNumber"),
            language=call(app, "GetCurrentLanguage"),
            part_template=tpl,
        )
        if tpl is None:
            info["error"] = "找不到零件模板(.prtdot)。试过: " + "; ".join(t or "(空)" for t in tried)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        info["error"] = f"无法连接 SldWorks.Application: {e}"
    return info


# ---------------------------------------------------------------- 基础操作

class Builder:
    def __init__(self, app):
        self.app = app
        tpl, tried = find_part_template(app)
        if tpl is None:
            raise RuntimeError("找不到零件模板(.prtdot)。试过: " + "; ".join(t or "(空)" for t in tried))
        self.doc = app.NewDocument(tpl, 0, 0, 0)
        if self.doc is None:
            raise RuntimeError(f"用模板新建零件失败: {tpl}。请检查 SolidWorks 里是否有未关闭的对话框")
        try:  # 标记：下次建模前 close_previous 会关掉它
            call(self.doc, "Extension").CustomPropertyManager("").Add3(MARK, 30, "1", 1)
        except Exception:  # noqa: BLE001
            pass
        self.sm = self.doc.SketchManager
        self.fm = self.doc.FeatureManager
        self.planes = self._default_planes()
        self.xform = None     # 斜面草图：模型 -> 草图坐标变换；默认基准面为 None（草图坐标就是 u, v）
        self.frame = None     # 当前草图的 ftable.plane_frame
        self.flip = False     # 草图法向与特征表 normal 相反时为 True，拉伸方向要反过来
        self.custom_planes = {}
        self._prev_input_dim = app.GetUserPreferenceToggle(SW_INPUT_DIM_ON_CREATE)
        app.SetUserPreferenceToggle(SW_INPUT_DIM_ON_CREATE, False)

    def set_doc_units(self, unit: str) -> dict:
        """把零件文档单位设成和图纸一致，打开模型看到的数字就和图纸一样。失败不影响建模。"""
        ext = call(self.doc, "Extension")
        res = {"requested": unit}
        try:
            ext.SetUserPreferenceInteger(SW_UNIT_SYSTEM, 0, UNIT_SYSTEM[unit])
            ext.SetUserPreferenceInteger(SW_UNITS_LINEAR, 0, LINEAR_UNIT[unit])
            got = ext.GetUserPreferenceInteger(SW_UNITS_LINEAR, 0)
            res["linear_readback"] = {v: k for k, v in LINEAR_UNIT.items()}.get(got, got)
            res["ok"] = res["linear_readback"] == unit
        except Exception as e:  # noqa: BLE001
            res.update(ok=False, error=str(e))
        return res

    def close_prefs(self):
        self.app.SetUserPreferenceToggle(SW_INPUT_DIM_ON_CREATE, self._prev_input_dim)

    def _default_planes(self) -> dict:
        found = []
        feat = call(self.doc, "FirstFeature")
        while feat is not None and len(found) < 3:
            if call(feat, "GetTypeName2") == "RefPlane":
                found.append(feat)
            feat = call(feat, "GetNextFeature")
        if len(found) < 3:
            raise RuntimeError("没有找到三个默认基准面")
        return {"front": found[0], "top": found[1], "right": found[2]}

    def select_plane(self, name: str, offset: float = 0.0):
        self.doc.ClearSelection2(True)
        base = self.planes[name]
        if abs(offset) < 1e-9:
            base.Select2(False, 0)
            return
        if offset < 0:
            # TODO: 反向偏移需要 InsertRefPlane 的翻转选项，实测后补上
            raise CapabilityBlocked(f"{name} 基准面负偏移 {offset} mm 暂未实现")
        base.Select2(False, 0)
        plane = self.fm.InsertRefPlane(REFPLANE_DISTANCE, offset * MM, 0, 0, 0, 0)
        if plane is None:
            raise RuntimeError(f"创建偏移基准面失败 ({name} + {offset} mm)")
        self.doc.ClearSelection2(True)
        plane.Select2(False, 0)

    # ------------------------------------------------------------ 斜面（任意平面）
    # 做法 1：3D 草图画三个点（原点、原点+x_dir、原点+y_dir），用"重合"约束过三点建基准面。
    # 做法 2（兜底）：找一个法向平行、包含原点的平面实体面，和它重合建基准面。
    # 草图坐标系由 SolidWorks 自己定，所以画图时用 ModelToSketchTransform 把模型坐标换成草图坐标。

    def _vt_array(self, vals):
        import pythoncom  # noqa: PLC0415
        import win32com.client  # noqa: PLC0415
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(vals))

    def _plane_by_points(self, fr):
        o = fr["origin"]
        pts = [o, tuple(o[i] + 10 * fr["x_dir"][i] for i in range(3)),
               tuple(o[i] + 10 * fr["y_dir"][i] for i in range(3))]
        self.doc.ClearSelection2(True)
        self.sm.Insert3DSketch(True)
        self.sm.AddToDB = True
        sps = [self.sm.CreatePoint(p[0] * MM, p[1] * MM, p[2] * MM) for p in pts]
        self.sm.AddToDB = False
        self.sm.Insert3DSketch(True)
        if any(sp is None for sp in sps):
            raise RuntimeError("3D 草图点创建失败")
        self.doc.ClearSelection2(True)
        selmgr = call(self.doc, "SelectionManager")
        for i, sp in enumerate(sps):
            sd = call(selmgr, "CreateSelectData")
            sd.Mark = i
            if not sp.Select4(True, sd):
                raise RuntimeError(f"选不中第 {i + 1} 个参考点")
        plane = self.fm.InsertRefPlane(REFPLANE_COINCIDENT, 0, REFPLANE_COINCIDENT, 0, REFPLANE_COINCIDENT, 0)
        if plane is None:
            raise RuntimeError("三点建基准面失败")
        return plane

    def _plane_by_face(self, fr):
        o = [c * MM for c in fr["origin"]]
        n = fr["normal"]
        for body in (self.doc.GetBodies2(0, True) or ()):
            for face in (call(body, "GetFaces") or ()):
                surf = call(face, "GetSurface")
                if not call(surf, "IsPlane"):
                    continue
                fn = call(face, "Normal")
                if abs(abs(sum(a * b for a, b in zip(fn, n))) - 1) > 1e-6:
                    continue
                cp = face.GetClosestPointOn(*o)
                if cp is None or sum((cp[i] - o[i]) ** 2 for i in range(3)) ** 0.5 > 1e-6:
                    continue
                self.doc.ClearSelection2(True)
                face.Select4(False, None)
                plane = self.fm.InsertRefPlane(REFPLANE_COINCIDENT, 0, 0, 0, 0, 0)
                if plane is not None:
                    return plane
        raise RuntimeError("没找到包含原点、法向平行的平面实体面")

    def custom_plane(self, fr):
        key = tuple(round(c, 6) for c in fr["origin"] + fr["normal"] + fr["x_dir"])
        if key in self.custom_planes:
            return self.custom_planes[key]
        errs = []
        for fn in (self._plane_by_points, self._plane_by_face):
            try:
                plane = fn(fr)
                self.custom_planes[key] = plane
                self.last_plane_method = fn.__name__
                return plane
            except Exception as e:  # noqa: BLE001
                errs.append(f"{fn.__name__}: {e}")
        raise RuntimeError("斜面建不出来。" + " | ".join(errs))

    def _apply(self, p):
        """模型坐标 (m) -> 草图坐标 (m)。用 MathTransform.ArrayData 自己算，不用 MathUtility（DEVELOPING.md #24）。
        ArrayData: [0:9] 旋转 3x3, [9:12] 平移, [12] 比例。行向量/列向量约定在 begin_sketch 里实测选定。"""
        R, T, k = self._R, self._T, self._k
        if self._rowvec:
            return [k * sum(p[j] * R[j * 3 + i] for j in range(3)) + T[i] for i in range(3)]
        return [k * sum(R[i * 3 + j] * p[j] for j in range(3)) + T[i] for i in range(3)]

    def _model_pt(self, u: float, v: float, w: float = 0.0):
        fr = self.frame
        return [(fr["origin"][i] + u * fr["x_dir"][i] + v * fr["y_dir"][i] + w * fr["normal"][i]) * MM
                for i in range(3)]

    def to_sketch(self, u: float, v: float) -> tuple[float, float]:
        """特征表草图坐标 (mm) -> SolidWorks 草图坐标 (m)。"""
        if self.xform is None:
            return u * MM, v * MM
        d = self._apply(self._model_pt(u, v))
        if abs(d[2]) > 1e-7:
            raise RuntimeError(f"斜面草图坐标换算出错：点不在草图平面上 (z={d[2]:.3g} m)")
        return d[0], d[1]

    def _setup_xform(self, xform):
        a = list(call(xform, "ArrayData"))
        self._R, self._T, self._k = a[0:9], a[9:12], (a[12] if len(a) > 12 and a[12] else 1.0)
        # 两种约定都试：平面上的点换算后 z 应为 0
        test = [self._model_pt(0, 0), self._model_pt(10, 0), self._model_pt(0, 10)]
        errs = {}
        for rv in (True, False):
            self._rowvec = rv
            errs[rv] = max(abs(self._apply(q)[2]) for q in test)
        self._rowvec = min(errs, key=errs.get)
        if errs[self._rowvec] > 1e-7:
            raise RuntimeError(f"斜面草图变换不对：平面上的点 z 偏差 {errs}")
        self.xform = xform
        self.flip = self._apply(self._model_pt(0, 0, 1))[2] < 0

    def begin_sketch(self, plane, offset: float = 0.0):
        self.xform, self.frame, self.flip = None, None, False
        if isinstance(plane, str):
            self.select_plane(plane, offset)
        else:
            self.frame = ftable.plane_frame(plane, offset)
            pl = self.custom_plane(self.frame)
            self.doc.ClearSelection2(True)
            pl.Select2(False, 0)
        self.sm.InsertSketch(True)
        self.sm.AddToDB = True
        if self.frame is not None:
            sk = call(self.sm, "ActiveSketch")
            self._setup_xform(call(sk, "ModelToSketchTransform"))

    def end_sketch(self):
        self.sm.AddToDB = False
        self.sm.InsertSketch(True)  # 退出草图
        # 显式选中刚建的草图（特征树最后一个），供后续拉伸/切除/旋转使用
        self.doc.ClearSelection2(True)
        self.doc.FeatureByPositionReverse(0).Select2(False, 0)

    def circle(self, u: float, v: float, r: float):
        x, y = self.to_sketch(u, v)
        self.sm.CreateCircleByRadius(x, y, 0, r * MM)

    def draw_profile(self, profile: dict):
        if profile["shape"] == "circle":
            u, v = profile.get("center", [0, 0])
            self.circle(u, v, profile["diameter"] / 2)
            return
        if profile["shape"] == "path":
            cur = tuple(profile["start"])
            for sg in profile["segments"]:
                a, b2 = self.to_sketch(*cur), self.to_sketch(*sg["to"])
                if "center" in sg:
                    m = self.to_sketch(*ftable.arc_mid(cur, sg))
                    # 三点画弧，不依赖顺/逆时针，斜面草图坐标系翻转也不影响
                    if self.sm.Create3PointArc(a[0], a[1], 0, b2[0], b2[1], 0, m[0], m[1], 0) is None:
                        raise RuntimeError(f"画圆弧失败 {cur} -> {sg['to']}")
                else:
                    self.sm.CreateLine(a[0], a[1], 0, b2[0], b2[1], 0)
                cur = tuple(sg["to"])
            return
        self.draw_polyline(ftable.profile_points(profile))

    def draw_polyline(self, pts):
        n = len(pts)
        for i in range(n):
            (x1, y1), (x2, y2) = self.to_sketch(*pts[i]), self.to_sketch(*pts[(i + 1) % n])
            self.sm.CreateLine(x1, y1, 0, x2, y2, 0)

    # ------------------------------------------------------------ 特征

    def extrude(self, depth: float, midplane: bool, reverse: bool = False, merge: bool = True):
        cond = END_MIDPLANE if midplane else END_BLIND
        # 第 2 个参数 Flip=False；第 3 个 Dir：反向。斜面草图法向和特征表相反时再反一次
        # 倒数第 6 个参数 Merge：合并到已有实体
        f = self.fm.FeatureExtrusion2(
            True, False, reverse != self.flip, cond, 0, depth * MM, 0,
            False, False, False, False, 0, 0,
            False, False, False, False, merge, True, True, 0, 0, False)
        if f is None:
            raise RuntimeError("拉伸失败。如果新实体和已有实体只沿一条边相接（零厚度几何），SolidWorks 不允许合并，"
                               "见 DEVELOPING.md 零厚度几何一条" if merge else "拉伸失败")
        return f

    def cut(self, depth, direction: str):
        through = depth == "through_all"
        d = 0 if through else float(depth) * MM
        t = END_THROUGH_ALL if through else END_BLIND
        both = direction == "both"
        f = self.fm.FeatureCut4(
            # 切除默认方向和草图法向相反（拉伸凸台是沿法向），所以 positive 要反向（DEVELOPING.md #30）
            not both, False, (direction == "positive") != self.flip, t, t if both else 0, d, d if both else 0,
            False, False, False, False, 0, 0,
            False, False, False, False, False, True, True, True, True, False, 0, 0, False, False)
        if f is None:
            raise RuntimeError("切除失败")
        return f

    # ------------------------------------------------------------ 选边
    # 不用 SelectByID2 按坐标拾取：它沿视图方向打射线，背面的边会被挡住（DEVELOPING.md #7）。
    # 改为遍历实体的全部边，算每条边的中点，和目标中点按距离匹配，再直接选中边对象。

    @staticmethod
    def _edge_midpoint(edge) -> tuple[float, float, float]:
        """返回边的参数中点 (mm)。先用 GetCurveParams3，失败退回 GetCurveParams2。"""
        curve = call(edge, "GetCurve")
        try:
            cp = call(edge, "GetCurveParams3")
            u0, u1 = cp.UMinValue, cp.UMaxValue
        except Exception:  # noqa: BLE001
            p = call(edge, "GetCurveParams2")  # [sx,sy,sz, ex,ey,ez, umin, umax, ...]
            u0, u1 = p[6], p[7]
        pt = curve.Evaluate2((u0 + u1) / 2, 0)
        return pt[0] / MM, pt[1] / MM, pt[2] / MM

    def all_edges(self) -> list:
        bodies = self.doc.GetBodies2(0, False) or ()  # swSolidBody = 0
        edges = []
        for body in bodies:
            edges.extend(call(body, "GetEdges") or ())
        return edges

    @staticmethod
    def _dist_to_edge(edge, t) -> float:
        """目标点 t (mm) 到边的最近距离 (mm)。点在边上时为 0，对直线、圆、样条都适用。"""
        r = edge.GetClosestPointOn(t[0] * MM, t[1] * MM, t[2] * MM)
        return math.dist(t, (r[0] / MM, r[1] / MM, r[2] / MM))

    def select_edges(self, pts_mm, mark: int = 0, tol: float = 0.01) -> dict:
        """按"目标点落在哪条边上"选边（DEVELOPING.md #9）。返回诊断信息 dict。
        首选 GetClosestPointOn 求点到边的距离；失败时退回比较边的参数中点。"""
        edges = self.all_edges()
        mids = []
        for e in edges:
            try:
                mids.append(self._edge_midpoint(e))
            except Exception:  # noqa: BLE001
                mids.append(None)

        def dist(i, t):
            try:
                return self._dist_to_edge(edges[i], t)
            except Exception:  # noqa: BLE001
                return math.dist(t, mids[i]) if mids[i] is not None else float("inf")

        self.doc.ClearSelection2(True)
        sm = call(self.doc, "SelectionManager")
        # 无参方法必须走 call()：pywin32 可能把它暴露成属性，再加 () 会报"找不到成员"（DEVELOPING.md #5）
        data = call(sm, "CreateSelectData")
        data.Mark = mark

        picked, unmatched, duplicate = set(), [], 0
        for t in pts_mm:
            best, best_d = None, float("inf")
            for i in range(len(edges)):
                d = dist(i, t)
                if d < best_d:
                    best, best_d = i, d
            if best is None or best_d > tol:
                unmatched.append({"target": [round(c, 3) for c in t], "nearest_mm": round(best_d, 4)})
                continue
            if best in picked:   # 两个点落在同一条边上（例如整圆在 SolidWorks 里只有一条边），只选一次
                duplicate += 1
                continue
            e = edges[best]
            ok = False
            for how in (lambda: e.Select4(True, data), lambda: e.Select2(True, mark)):
                try:
                    ok = bool(how())
                except Exception:  # noqa: BLE001
                    ok = False
                if ok:
                    break
            if ok:
                picked.add(best)
            else:
                unmatched.append({"target": [round(c, 3) for c in t], "nearest_mm": round(best_d, 4),
                                  "note": "找到了边但 Select 返回 False"})

        try:
            selected = sm.GetSelectedObjectCount2(-1)
        except Exception:  # noqa: BLE001
            selected = None
        return {
            "matched": len(picked) + duplicate,
            "targets": len(pts_mm),
            "same_edge_points": duplicate,
            "selected_in_sw": selected,
            "edges_total": len(edges),
            "midpoints_failed": sum(m is None for m in mids),
            "unmatched": unmatched,
        }

    def fillet(self, r: float, reselect=None) -> str:
        """圆角。半径大于相邻凹角半径时默认设置会失败（DEVELOPING.md #31），依次换设置重试。
        reselect：失败后选择集会被清掉，每次重试前调用它重新选边。"""
        import pythoncom  # noqa: PLC0415
        import win32com.client  # noqa: PLC0415

        empty = win32com.client.VARIANT(pythoncom.VT_EMPTY, None)
        # swFeatureFilletOptions_e：1 沿相切传播，2 等半径，32 圆形角，64 附加边，128 保留特征
        # swFilletOverFlowType_e：0 默认，1 保持边线，2 保持曲面
        combos = [
            ("默认", 195, 0),
            ("保持曲面", 195, 2),
            ("保持边线", 195, 1),
            ("圆形角", 195 | 32, 0),
            ("不保留特征", 67, 0),
            ("不保留特征+保持曲面", 67, 2),
            ("不保留特征+保持边线", 67, 1),
            # 256 曲率连续：半径 ≥ 凹角半径时唯一能成功的设置（003 实测），但截面不是圆弧，体积偏小
            ("曲率连续-近似", 195 | 256, 0),
        ]
        attempts = []
        for i, (name, opt, ovf) in enumerate(combos):
            def fn(opt=opt, ovf=ovf, first=(i == 0)):
                if not first and reselect is not None:
                    self.doc.ClearSelection2(True)
                    reselect()
                res = self.fm.FeatureFillet3(opt, r * MM, 0, ovf, 0, 0, 0)
                if res is None and first:  # 有的版本不接受 0 当数组，换 VT_EMPTY 再试一次
                    res = self.fm.FeatureFillet3(opt, r * MM, 0, ovf, empty, empty, empty)
                return res
            attempts.append((f"FeatureFillet3({name}, opt={opt}, overflow={ovf})", fn))
        return self._try(attempts, "圆角")

    def chamfer(self, d: float) -> str:
        # swChamferAngleDistance = 1，等边 45°
        attempts = [("InsertFeatureChamfer",
                     lambda: self.fm.InsertFeatureChamfer(4, 1, d * MM, math.radians(45), 0, 0, 0, 0))]
        return self._try(attempts, "倒角")

    @staticmethod
    def _try(attempts, label: str) -> str:
        errors = []
        for name, fn in attempts:
            try:
                if fn() is not None:
                    return name
                errors.append(f"{name}: 返回空")
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}: {e}")
        raise RuntimeError(f"{label}失败。尝试过: " + " | ".join(errors))

    # ------------------------------------------------------------ 齿轮用
    last_errors: list = []

    def draw_spline(self, pts) -> str:
        """过点画样条。不同版本 API 名字不一样，逐个试；都不行就画折线。"""
        import pythoncom  # noqa: PLC0415
        import win32com.client  # noqa: PLC0415

        flat = []
        for u, v in pts:
            flat += [u * MM, v * MM, 0.0]
        arr = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat)
        for name, fn in (("CreateSpline2", lambda: self.sm.CreateSpline2(arr, True)),
                         ("CreateSpline", lambda: self.sm.CreateSpline(arr))):
            try:
                if fn() is not None:
                    return name
            except Exception as e:  # noqa: BLE001
                self.last_errors.append(f"{name}: {e}")
        for (u1, v1), (u2, v2) in zip(pts, pts[1:]):
            self.sm.CreateLine(u1 * MM, v1 * MM, 0, u2 * MM, v2 * MM, 0)
        return "polyline"

    def line(self, a, b2):
        self.sm.CreateLine(a[0] * MM, a[1] * MM, 0, b2[0] * MM, b2[1] * MM, 0)

    def draw_gear_space(self, g: dict) -> str:
        """按 ftable.gear_space_profile 的闭合顺序画一个齿槽。"""
        self.line(g["outer"][1], g["right"][0])
        how = self.draw_spline(g["right"])
        last = g["right"][-1]
        if g["right_radial"]:
            self.line(last, g["right_radial"])
            last = g["right_radial"]
        r = g["root"]
        # 圆心、起点、终点、方向 +1 = 逆时针
        self.sm.CreateArc(0, 0, 0, r["start"][0] * MM, r["start"][1] * MM, 0,
                          r["end"][0] * MM, r["end"][1] * MM, 0, 1)
        if g["left_radial"]:
            self.line(g["left_radial"], g["left"][0])
        self.draw_spline(g["left"])
        self.line(g["left"][-1], g["outer"][0])
        self.line(g["outer"][0], g["outer"][1])
        return how

    def make_y_axis(self):
        """前视、右视基准面相交 = 模型 Y 轴，回转体的轴线。"""
        self.doc.ClearSelection2(True)
        self.planes["front"].Select2(False, 0)
        self.planes["right"].Select2(True, 0)
        # InsertAxis2 在零件文档 ModelDoc2 上，不在 FeatureManager 上（DEVELOPING.md #17）
        errs = []
        for name, fn in (("doc.InsertAxis2", lambda: self.doc.InsertAxis2(True)),
                         ("doc.InsertAxis", lambda: self.doc.InsertAxis())):
            try:
                fn()
                break
            except Exception as e:  # noqa: BLE001
                errs.append(f"{name}: {e}")
        else:
            raise RuntimeError(" | ".join(errs))
        axis = self.doc.FeatureByPositionReverse(0)
        if call(axis, "GetTypeName2") != "RefAxis":
            raise RuntimeError(f"没有建出基准轴，最后一个特征是 {call(axis, 'GetTypeName2')}")
        self.doc.ClearSelection2(True)
        return axis

    def circular_pattern(self, feat, count: int) -> str | None:
        """把 feat 绕 Y 轴均布 count 个（含自身）。成功返回用的 API 名，失败返回 None。"""
        self.last_errors = []
        try:
            axis = self.make_y_axis()
        except Exception as e:  # noqa: BLE001
            self.last_errors.append(f"基准轴: {e}")
            return None
        full = 2 * math.pi
        attempts = [
            ("FeatureCircularPattern5", lambda: self.fm.FeatureCircularPattern5(
                count, full, False, "NULL", False, True, False, False, False, False, 1, 0, "NULL", False)),
            ("FeatureCircularPattern4", lambda: self.fm.FeatureCircularPattern4(
                count, full, False, "NULL", False, True, False)),
            ("FeatureCircularPattern3", lambda: self.fm.FeatureCircularPattern3(
                count, full, False, "NULL", False, True)),
        ]
        for name, fn in attempts:
            # 每次重新选：要阵列的特征 mark 4，阵列轴 mark 1
            self.doc.ClearSelection2(True)
            feat.Select2(False, 4)
            axis.Select2(True, 1)
            try:
                if fn() is not None:
                    return name
                self.last_errors.append(f"{name}: 返回空")
            except Exception as e:  # noqa: BLE001
                self.last_errors.append(f"{name}: {e}")
        return None

    def check_step(self, f: dict, exp: dict, log: list, rel_tol: float = 1e-3, box_tol: float = 0.05):
        """和 CadQuery 预览的同一步比体积和绝对包围盒。对不上就停，说明是哪个特征。"""
        self.doc.ForceRebuild3(False)
        vol = call(self.doc.Extension, "CreateMassProperty").Volume * 1e9
        bx = None
        for body in (self.doc.GetBodies2(0, True) or ()):
            b2 = body.GetBodyBox()
            bx = list(b2) if bx is None else [min(bx[i], b2[i]) for i in range(3)] + [max(bx[i + 3], b2[i + 3]) for i in range(3)]
        bmin = [c / MM for c in bx[:3]] if bx else None
        bmax = [c / MM for c in bx[3:]] if bx else None
        ok_v = abs(vol - exp["volume_mm3"]) <= max(rel_tol * exp["volume_mm3"], 1.0)
        ok_b = bmin is not None and all(abs(a - e) <= box_tol for a, e in zip(bmin + bmax, exp["bbox_min"] + exp["bbox_max"]))
        if log and log[-1].get("id") == f["id"]:
            log[-1]["step_check"] = "ok" if ok_v and ok_b else "mismatch"
        if not (ok_v and ok_b):
            raise RuntimeError(
                f"[{f['id']}] 这一步和预览对不上：SolidWorks 体积 {vol:.3f}，预览 {exp['volume_mm3']:.3f}；"
                f"SolidWorks 包围盒 {[round(c, 3) for c in (bmin or [])]}→{[round(c, 3) for c in (bmax or [])]}，"
                f"预览 {[round(c, 3) for c in exp['bbox_min']]}→{[round(c, 3) for c in exp['bbox_max']]}。"
                "常见原因：拉伸或切除方向反了、基准面偏移方向反了、选错了边")

    def revolve(self, cut: bool = False, angle_deg: float = 360.0):
        # 第 4 个参数 IsCut；草图里的中心线自动当旋转轴
        f = self.fm.FeatureRevolve2(
            True, True, False, cut, False, False, 0, 0, math.radians(angle_deg), 0,
            False, False, 0, 0, 0, 0, 0, True, True, True)
        if f is None:
            raise RuntimeError("旋转失败")
        return f


def build_gear_teeth(b: "Builder", f: dict) -> dict:
    """画一个齿槽（渐开线样条 + 齿根圆弧），切除，再绕 Y 轴圆周阵列 z 个。
    阵列失败时退回：剩下的齿槽全画在一张草图里一次切除（DEVELOPING.md #16）。"""
    z = int(f["teeth"])
    g = ftable.gear_space_profile(f, 0)
    b.begin_sketch("top")
    curve = b.draw_gear_space(g)
    b.end_sketch()
    cut0 = b.cut("through_all", "both")
    info = {"id": f["id"], "status": "ok", "curve": curve}
    pattern_api = b.circular_pattern(cut0, z)
    if pattern_api:
        info["method"] = f"一个齿槽 + 圆周阵列 ({pattern_api})"
        return info
    # 兜底：剩下 z-1 个齿槽用折线画在一张草图里
    polys = ftable.gear_space_polygons(f)[1:]
    b.begin_sketch("top")
    try:
        b.sm.DisplayWhenAdded = False
    except Exception:  # noqa: BLE001
        pass
    for poly in polys:
        b.draw_polyline(poly)
    try:
        b.sm.DisplayWhenAdded = True
    except Exception:  # noqa: BLE001
        pass
    b.end_sketch()
    b.cut("through_all", "both")
    info["method"] = "阵列失败，兜底：其余齿槽用折线一次切除"
    info["pattern_errors"] = b.last_errors
    return info


def sketch_plane_for(f: dict) -> float:
    """贯穿且两侧时偏移量不影响结果，直接用基准面，减少辅助基准面。"""
    if f.get("depth") == "through_all" and f.get("direction", "both") == "both":
        return 0.0
    return float(f.get("offset", 0))


def build(table: dict, b: Builder, steps: list | None = None) -> list[dict]:
    """逐个特征建模。steps 是 CadQuery 预览每一步的体积和包围盒；给了就每步自检，
    第一个对不上的特征立刻停下并报告（DEVELOPING.md #30）。"""
    log = []
    b.log = log  # 出错时 main 也能拿到已经建好的特征列表

    def one(f):
        t = f["type"]
        if t == "base_extrude":
            off = 0.0  # midplane 由 END_MIDPLANE 处理
            b.begin_sketch(f["plane"], off)
            b.draw_profile(f["profile"])
            b.end_sketch()
            b.extrude(f["depth"], f.get("midplane", False))
        elif t == "base_revolve":
            b.begin_sketch("front")
            ys = [p[1] for p in f["half_profile"]]
            b.sm.CreateCenterLine(0, (min(ys) - 5) * MM, 0, 0, (max(ys) + 5) * MM, 0)
            b.draw_polyline([tuple(p) for p in f["half_profile"]])
            b.end_sketch()
            b.revolve()
        elif t == "revolve":
            b.begin_sketch(f["plane"], float(f.get("offset", 0)))
            (x1, y1), (x2, y2) = b.to_sketch(*f["axis"][0]), b.to_sketch(*f["axis"][1])
            b.sm.CreateCenterLine(x1, y1, 0, x2, y2, 0)
            b.draw_profile(f["profile"])
            b.end_sketch()
            b.revolve(cut=bool(f.get("cut")), angle_deg=float(f.get("angle", 360)))
        elif t == "extrude":
            dirn = f.get("direction", "positive")
            b.begin_sketch(f["plane"], float(f.get("offset", 0)))
            b.draw_profile(f["profile"])
            b.end_sketch()
            b.extrude(f["depth"], dirn == "midplane", reverse=dirn == "negative", merge=f.get("merge", True))
            if f["plane"] not in ("front", "top", "right"):
                log.append({"id": f["id"], "status": "ok", "plane_method": getattr(b, "last_plane_method", "cached"),
                            "sketch_flipped": b.flip})
                return
        elif t == "cut_extrude":
            b.begin_sketch(f["plane"], sketch_plane_for(f))
            b.draw_profile(f["profile"])
            b.end_sketch()
            b.cut(f["depth"], f.get("direction", "both"))
        elif t == "hole":
            b.begin_sketch(f["plane"], sketch_plane_for(f))
            r = f["diameter"] / 2
            for u, v in ftable.hole_positions(f):
                b.circle(u, v, r)
            b.end_sketch()
            b.cut(f["depth"], f.get("direction", "both"))
        elif t == "spur_gear_teeth":
            log.append(build_gear_teeth(b, f))
            return
        elif t == "edge_treatment":
            try:
                import preview_cadquery  # noqa: PLC0415  用 CadQuery 算出目标边的位置
            except ImportError as e:
                raise CapabilityBlocked(f"[{f['id']}] 倒角/圆角需要 cadquery 定位边: {e}") from e
            pts = preview_cadquery.edge_points(table, f["id"])
            # FeatureFillet3 要求待圆角的边 mark = 1；倒角用 0
            sel = b.select_edges(pts, mark=1 if f["kind"] == "fillet" else 0)
            if sel["matched"] != len(pts):
                raise RuntimeError(f"[{f['id']}] 只匹配到 {sel['matched']}/{len(pts)} 条边。诊断: "
                                   + json.dumps(sel, ensure_ascii=False))
            if f["kind"] == "fillet":
                api = b.fillet(f["size"], reselect=lambda: b.select_edges(pts, mark=1))
            else:
                api = b.chamfer(f["size"])
            log.append({"id": f["id"], "status": "ok", "api": api, "select": sel})
            return
        else:
            raise CapabilityBlocked(f"[{f['id']}] 不支持的特征类型 {t}")
        log.append({"id": f["id"], "status": "ok"})

    for i, f in enumerate(table["features"]):
        one(f)
        if steps:
            b.check_step(f, steps[i], log)
    return log


def measure(doc) -> dict:
    mp = call(doc.Extension, "CreateMassProperty")
    box = doc.GetPartBox(True)
    try:  # GetPartBox 会把草图点、基准面也算进去（DEVELOPING.md #24），优先用实体的包围盒
        bx = None
        for body in (doc.GetBodies2(0, True) or ()):
            b2 = body.GetBodyBox()
            bx = list(b2) if bx is None else [min(bx[i], b2[i]) for i in range(3)] + [max(bx[i + 3], b2[i + 3]) for i in range(3)]
        if bx:
            box = bx
    except Exception:  # noqa: BLE001
        pass
    faces = 0
    try:
        for body in (doc.GetBodies2(0, True) or ()):  # 0 = 实体
            faces += body.GetFaceCount()
    except Exception:  # noqa: BLE001
        faces = None
    return {
        "volume_mm3": round(mp.Volume * 1e9, 3),
        "surface_area_mm2": round(mp.SurfaceArea * 1e6, 3),
        "bbox_mm": [round(abs(box[i + 3] - box[i]) / MM, 4) for i in range(3)],
        "face_count": faces,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("-o", "--out", help="保存路径 .SLDPRT；已存在时自动改名")
    ap.add_argument("--report", default="work/sw_report.json")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-step-check", action="store_true", help="不和 CadQuery 预览逐步比对")
    args = ap.parse_args()

    if args.check:
        info = env_check()
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0 if info["ok"] else 1
    if not args.path:
        ap.error("需要特征表路径，或使用 --check")

    table = ftable.load(args.path)
    app = connect()
    rep = {"backend": "solidworks", "hole_count_from_table": ftable.count_holes(table)}
    if args.out:
        closed = close_previous(app, Path(args.out).parent)
        if closed:
            rep["closed_previous"] = closed
            print(f"已关闭上次的零件 {len(closed)} 个", flush=True)
    steps = None
    if not args.no_step_check:
        try:
            import preview_cadquery  # noqa: PLC0415
            steps = []
            preview_cadquery.build(table, trace=steps)
            print(f"预览算好了 {len(steps)} 步，建模时逐步自检", flush=True)
        except Exception as e:  # noqa: BLE001  没装 cadquery 或预览失败：不自检，照常建模
            print(f"跳过逐步自检：{e}", flush=True)
            steps = None
    b = Builder(app)
    rep["doc_units"] = b.set_doc_units(table["part"].get("source_units", "mm"))
    try:
        rep["features"] = build(table, b, steps)
        rep["status"] = "ok"
        separate = [f["id"] for f in table["features"] if f.get("merge") is False]
        if separate:
            rep["multi_body"] = {"features": separate,
                                 "note": "这些特征按特征表 merge=false 建成单独实体（零厚度几何），几何不变，表面积会多算接触面"}
    except CapabilityBlocked as e:
        rep.update(status="capability_blocked", reason=str(e))
        rep["features"] = getattr(b, "log", None)
    except Exception as e:  # noqa: BLE001
        import traceback  # noqa: PLC0415
        rep.update(status="error", reason=str(e))
        rep["features"] = getattr(b, "log", None)
        # 记下出错的代码行，方便定位是哪个 COM 调用失败
        rep["trace"] = [ln.strip() for ln in traceback.format_exc().splitlines()
                        if ln.strip() and "^^^" not in ln][-7:-1]
    finally:
        b.close_prefs()
    try:  # 隐藏建模时创建的偏移基准面，打开零件时不挡视线（DEVELOPING.md）
        feat = call(b.doc, "FirstFeature")
        hidden = 0
        while feat is not None:
            if call(feat, "GetTypeName2") == "RefPlane" and all(feat is not p for p in b.planes.values()):
                b.doc.ClearSelection2(True)
                feat.Select2(False, 0)
                b.doc.BlankRefGeom()
                hidden += 1
            feat = call(feat, "GetNextFeature")
        b.doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001  只影响显示
        pass
    try:
        b.doc.ForceRebuild3(False)
        rep.update(measure(b.doc))
    except Exception as e:  # noqa: BLE001
        rep["measure_error"] = str(e)

    if args.out:
        # 只有成功的零件才保存：覆盖同名旧版本（连同 name_1 这类旧编号一起删掉）。
        # 失败的不保存，窗口直接关掉不存盘；报告里有建到哪一步、为什么失败。
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        if rep["status"] == "ok":
            removed = remove_versions(out)
            if removed:
                rep["replaced_old"] = removed
            # 选项 1 = 静默保存，窗口里的文档就是这个文件（以前用 2 另存副本，窗口里积累没保存的"零件N"）
            err = b.doc.SaveAs3(str(out), 0, 1)
            rep["saved"] = str(out) if err == 0 else None
            if err:
                rep["save_error"] = err
        else:
            rep["saved"] = None
            try:
                app.CloseDoc(call(b.doc, "GetTitle"))
                rep["discarded"] = "建模失败，零件没有保存，窗口已关闭"
            except Exception:  # noqa: BLE001
                pass

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
