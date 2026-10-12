"""用 CadQuery 按特征表建模预览，不需要 SolidWorks，可在任何系统运行。

用法: python preview_cadquery.py part.json -o work/preview.step [--report work/preview_report.json]

输出 STEP 文件，和一个包含体积、包围盒的报告，供 verify_model.py 比对。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cadquery as cq

import ftable


class CapabilityBlocked(Exception):
    pass


def cq_plane(plane, offset: float = 0.0) -> cq.Plane:
    fr = ftable.plane_frame(plane, offset)
    return cq.Plane(origin=fr["origin"], xDir=fr["x_dir"], normal=fr["normal"])


def sketch(wp: cq.Workplane, profile: dict) -> cq.Workplane:
    if profile["shape"] == "circle":
        u, v = profile.get("center", [0, 0])
        return wp.center(u, v).circle(profile["diameter"] / 2)
    if profile["shape"] == "path":
        cur = tuple(profile["start"])
        wp = wp.moveTo(*cur)
        segs = profile["segments"]
        for i, sg in enumerate(segs):
            last = i == len(segs) - 1
            if "center" in sg:
                wp = wp.threePointArc(ftable.arc_mid(cur, sg), tuple(sg["to"]))
            elif not last:
                wp = wp.lineTo(*sg["to"])
            cur = tuple(sg["to"])
        return wp.close()
    return wp.polyline(ftable.profile_points(profile)).close()


def span(depth, direction: str, big: float) -> tuple[float, float]:
    """返回 (起点相对草图面的偏移, 长度)。both + 数值 = 两侧各 depth。"""
    d = big if depth == "through_all" else float(depth)
    if direction == "positive":
        return 0.0, d
    if direction == "negative":
        return -d, d
    return -d, 2 * d


def extrude_tool(plane: str, offset: float, profile_fn, depth, direction, big):
    start, length = span(depth, direction, big)
    wp = cq.Workplane(cq_plane(plane, offset + start))
    return profile_fn(wp).extrude(length)


def outer_edges_of_extreme_face(solid: cq.Workplane, axis: str, top: bool):
    sel = (">" if top else "<") + axis
    face = solid.faces(sel).val()
    return list(face.outerWire().Edges())


def target_edges(result: cq.Workplane, f: dict, axis: str, base_type: str) -> list:
    """按 edge_treatment 的语义选择器找出目标边。SolidWorks 后端也用它来定位边。"""
    sel = f["edges"]
    edges = []
    if isinstance(sel, dict):  # 按点选边：每个点取距离最近的边
        allv = result.edges().vals()
        for pt in sel["points"]:
            v = cq.Vertex.makeVertex(*pt)
            ranked = sorted(allv, key=lambda e: e.distance(v))
            best = ranked[0]
            if best.distance(v) > 0.01:
                raise CapabilityBlocked(f"[{f['id']}] 点 {pt} 附近 0.01 mm 内没有边（最近 {best.distance(v):.3f} mm）")
            if len(ranked) > 1 and ranked[1].distance(v) <= 0.01 and not ranked[1].isSame(best):
                # 点落在两条边的交点上（常见：圆柱的接缝线端点），选哪条是碰运气
                raise CapabilityBlocked(
                    f"[{f['id']}] 点 {pt} 同时落在两条边上（{best.geomType()} 和 {ranked[1].geomType()}），"
                    "可能是圆柱接缝线的端点或两条边的交点。换成边中间的一个点（圆边换到另一侧或离开 z=0）")
            edges.append(best)
        return edges
    if sel in ("top_outer", "all_outer"):
        edges += outer_edges_of_extreme_face(result, axis, True)
    if sel in ("bottom_outer", "all_outer"):
        edges += outer_edges_of_extreme_face(result, axis, False)
    if sel in ("vertical", "all_outer") and base_type == "base_extrude":
        # 只取外轮廓角上的竖直直线边，排除孔的接缝线和内腔棱
        corners = [v.toTuple() for v in
                   result.faces(">" + axis).val().outerWire().Vertices()]
        for e in result.edges("|" + axis).vals():
            if e.geomType() != "LINE":
                continue
            ends = [e.startPoint().toTuple(), e.endPoint().toTuple()]
            if any(sum((a - b) ** 2 for a, b in zip(p, c)) < 1e-8
                   for p in ends for c in corners):
                edges.append(e)
    if not edges:
        raise CapabilityBlocked(f"[{f['id']}] 选择器 {sel} 没有选到边")
    return edges


def build(table: dict, stop_before: str | None = None, trace: list | None = None):
    """逐个特征建模。stop_before 给定时，建到该特征之前就返回 (result, axis, base_type)。
    trace 给定时，每个特征之后记下体积和绝对包围盒，给 SolidWorks 逐步自检用。"""
    feats = table["features"]
    result: cq.Workplane | None = None
    axis = "Z"
    base_type = None
    for f in feats:
        t = f["type"]
        if stop_before is not None and f["id"] == stop_before:
            return result, axis, base_type
        if t in ("base_extrude", "base_revolve"):
            base_type = t
        if t == "base_extrude":
            axis = {"front": "Z", "top": "Y", "right": "X"}[f["plane"]]
            off = -f["depth"] / 2 if f.get("midplane") else 0.0
            result = sketch(cq.Workplane(cq_plane(f["plane"], off)), f["profile"]).extrude(f["depth"])
        elif t == "base_revolve":
            axis = "Y"
            result = (cq.Workplane(cq_plane("front"))
                      .polyline([tuple(p) for p in f["half_profile"]]).close()
                      .revolve(360, (0, 0, 0), (0, 1, 0)))
        elif result is None:
            raise ValueError("第一个特征必须是基体")
        else:
            bb = result.val().BoundingBox()
            big = 4 * bb.DiagonalLength + 10
            if t == "revolve":
                wp = cq.Workplane(cq_plane(f["plane"], f.get("offset", 0)))
                (a1, a2) = f["axis"]
                solid = sketch(wp, f["profile"]).revolve(f.get("angle", 360), tuple(a1), tuple(a2))
                result = result.cut(solid) if f.get("cut") else result.union(solid)
            elif t == "extrude":
                d = float(f["depth"])
                dirn = f.get("direction", "positive")
                start = {"positive": 0.0, "negative": -d, "midplane": -d / 2}[dirn]
                wp = cq.Workplane(cq_plane(f["plane"], f.get("offset", 0) + start))
                result = result.union(sketch(wp, f["profile"]).extrude(d))
            elif t == "cut_extrude":
                tool = extrude_tool(f["plane"], f.get("offset", 0), lambda wp: sketch(wp, f["profile"]),
                                    f["depth"], f.get("direction", "both"), big)
                result = result.cut(tool)
            elif t == "hole":
                pts = ftable.hole_positions(f)
                r = f["diameter"] / 2
                tool = extrude_tool(f["plane"], f.get("offset", 0),
                                    lambda wp: wp.pushPoints(pts).circle(r),
                                    f["depth"], f.get("direction", "both"), big)
                result = result.cut(tool)
            elif t == "spur_gear_teeth":
                # 和 SolidWorks 一样：渐开线用样条，齿根用圆弧，一个齿槽一个闭合轮廓
                wp = cq.Workplane(cq_plane("top", -big))
                for k in range(int(f["teeth"])):
                    g = ftable.gear_space_profile(f, k)
                    wp = wp.moveTo(*g["outer"][1]).lineTo(*g["right"][0])
                    wp = wp.spline(g["right"][1:], includeCurrent=True)
                    if g["right_radial"]:
                        wp = wp.lineTo(*g["right_radial"])
                    wp = wp.threePointArc(g["root"]["mid"], g["root"]["end"])
                    if g["left_radial"]:
                        wp = wp.lineTo(*g["left"][0])
                    wp = wp.spline(g["left"][1:], includeCurrent=True)
                    wp = wp.lineTo(*g["outer"][0]).close()
                result = result.cut(wp.extrude(2 * big))
            elif t == "edge_treatment":
                obj = result.newObject(target_edges(result, f, axis, base_type))
                result = obj.chamfer(f["size"]) if f["kind"] == "chamfer" else obj.fillet(f["size"])
            else:
                raise CapabilityBlocked(f"[{f['id']}] 不支持的特征类型 {t}")
        if trace is not None:
            sol = result.val()
            bb = sol.BoundingBox()
            trace.append({"id": f["id"], "volume_mm3": sol.Volume(),
                          "bbox_min": [bb.xmin, bb.ymin, bb.zmin], "bbox_max": [bb.xmax, bb.ymax, bb.zmax]})
    if stop_before is not None:
        raise KeyError(f"特征 {stop_before} 不存在")
    return result


def edge_points(table: dict, feature_id: str) -> list[tuple[float, float, float]]:
    """给 SolidWorks 用：返回某个 edge_treatment 特征的目标边中点 (mm)。"""
    f = next(x for x in table["features"] if x["id"] == feature_id)
    if isinstance(f["edges"], dict):  # 按点选边：点本身就在边上，直接给 SolidWorks 用
        return [tuple(p) for p in f["edges"]["points"]]
    result, axis, base_type = build(table, stop_before=feature_id)
    return [e.positionAt(0.5).toTuple() for e in target_edges(result, f, axis, base_type)]


def covered_hole_mouths(solid, table: dict) -> list[dict]:
    """孔口被零厚度的面盖住：孔从草图面切进去，但草图面和零件表面差一点点不共面时，
    会留下一层"皮"，孔在下面切出来了、表面上没有开口。体积几乎不变，逐步自检也发现不了。
    检查办法：打开的孔口中心是空的，离实体最近的是孔边（距离约等于半径）；被盖住时距离为 0。"""
    out = []
    for f in table["features"]:
        if f.get("type") != "hole" or f.get("direction", "both") == "both" or "__" in str(f.get("id")):
            continue
        for u, v in ftable.hole_positions(f):
            p = ftable.to_model(f["plane"], u, v, f.get("offset", 0.0))
            d = solid.distance(cq.Vertex.makeVertex(*p))
            if d < min(0.05, f["diameter"] / 20):   # 打开的孔口中心到实体的距离约等于半径
                out.append({"id": f["id"], "position": [u, v], "mouth_mm": [round(c, 4) for c in p],
                            "note": "孔口中心落在一个面上：孔可能被零厚度的皮盖住。检查孔的草图面是不是和零件表面完全共面"
                                    "（两者要用同一组数算出来）"})
    return out


def report(result: cq.Workplane, table: dict) -> dict:
    solid = result.val()
    bb = solid.BoundingBox()
    covered = covered_hole_mouths(solid, table)
    return {
        **({"covered_hole_mouths": covered} if covered else {}),
        "backend": "cadquery",
        "volume_mm3": round(solid.Volume(), 3),
        "surface_area_mm2": round(solid.Area(), 3),
        "face_count": len(solid.Faces()),
        "bbox_mm": [round(bb.xlen, 4), round(bb.ylen, 4), round(bb.zlen, 4)],
        "hole_count_from_table": ftable.count_holes(table),
        "solid_count": len(result.solids().vals()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("-o", "--out", default="work/preview.step")
    ap.add_argument("--report", default=None, help="默认与 STEP 同名 _report.json")
    args = ap.parse_args()

    table = ftable.load(args.path)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = build(table)
    except CapabilityBlocked as e:
        print(json.dumps({"status": "capability_blocked", "reason": str(e)}, ensure_ascii=False))
        raise SystemExit(2)
    cq.exporters.export(result, str(out))
    rep = report(result, table)
    rep["status"] = "ok"
    rep["step"] = str(out)
    rp = Path(args.report) if args.report else out.with_name(out.stem + "_report.json")
    rp.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
