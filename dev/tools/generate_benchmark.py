"""Generate original, fully specified plate drawings and hidden answers.

This is a small deterministic regression set, not evidence of real-world accuracy.
PDF dimensions and an explicit datum define two unequal-position through holes.
"""
from __future__ import annotations
import argparse
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from observations import dump, sha256


def make_case(index, folder):
    import cadquery as cq
    import pymupdf
    from preview_cadquery import build
    import ftable
    unit = "inch" if index >= 6 else "mm"
    k = 25.4 if unit == "inch" else 1
    n = index % 6
    w, h, t, d = (3 + n*.25, 2 + n*.125, .25, .25) if unit == "inch" else (80+n*5, 50+n*3, 6+n, 6+n*.5)
    positions = [[w*.2, h*.25], [w*.7, h*.65]]
    table = {"schema_version": "0.4", "part": {"name": folder.name, "part_type": "prismatic",
        "units": unit, "projection": "third_angle", "drawing_setup": {"length_unit": unit,
        "unit_evidence": f"All dimensions: {unit}", "standard": "ASME", "language": "en", "confidence": 1}},
        "features": [{"id": "plate", "type": "base_extrude", "plane": "front",
          "profile": {"shape": "rect", "width": w, "height": h, "center": [w/2,h/2]},
          "depth": t, "meta": {"confidence": 1, "evidence": "Generated dimensions W,H,T"}},
          {"id": "holes", "type": "hole", "plane": "front", "diameter": d, "positions": positions,
           "depth": "through_all", "direction": "both", "meta": {"confidence": 1, "evidence": "Generated hole coordinate table"}}],
        "open_questions": []}
    folder.mkdir(parents=True)
    dump(table, folder / "answer.json")
    result = build(ftable.to_mm(ftable.resolve(table)))
    cq.exporters.export(result, str(folder / "answer.step"))
    expected = {"volume_mm3": (w*h - 2*math.pi*(d/2)**2)*t*k**3,
                "surface_area_mm2": (2*(w*h-2*math.pi*(d/2)**2)+2*(w+h)*t+2*math.pi*d*t)*k*k,
                "bbox_mm": [w*k,h*k,t*k], "hole_count": 2}
    assert abs(result.val().Volume()-expected["volume_mm3"])/expected["volume_mm3"] < 1e-8
    doc=pymupdf.open()
    page=doc.new_page(width=842,height=595)
    def text(x,y,s,size=11):
        page.insert_text((x,y),s,fontsize=size)
    def line(a,b,dashes=None):
        page.draw_line(a,b,color=(0,0,0),width=.7,dashes=dashes)
    text(35,35,"Drawing2SW synthetic benchmark | " + folder.name,17)
    text(35,57,f"All dimensions: {unit} | THIRD ANGLE | 2 equal THROUGH holes | No fillets/chamfers")
    text(35,77,"Datum: front lower-left corner (0,0,0); X right, Y up, Z toward viewer. Thickness extends +Z.",10)
    scale=min(320/w,240/h)
    x0,y0=65,390
    def pt(x,y): return (x0+x*scale,y0-y*scale)
    page.draw_rect(pymupdf.Rect(pt(0,h),pt(w,0)),color=(0,0,0),width=1)
    for x,y in positions:
        page.draw_circle(pt(x,y),d*scale/2,color=(0,0,0),width=1)
        cx,cy=pt(x,y)
        line((cx-d*scale,cy),(cx+d*scale,cy),'[4 2]')
        line((cx,cy-d*scale),(cx,cy+d*scale),'[4 2]')
    # Width / height dimensions with extension lines and arrowheads.
    def dimension(a,b,label,tx,ty):
        line(a,b)
        dx,dy=b[0]-a[0],b[1]-a[1]; length=math.hypot(dx,dy); ux,uy=dx/length,dy/length
        for p,s in ((a,1),(b,-1)):
            for side in (-1,1): line(p,(p[0]+s*6*ux+side*2*uy,p[1]+s*6*uy-side*2*ux))
        text(tx,ty,label)
    for x in (0,w): line(pt(x,0),(pt(x,0)[0],425))
    dimension((x0,415),(x0+w*scale,415),f"W = {w:g}",x0+w*scale/2-20,410)
    for y in (0,h): line(pt(0,y),(40,pt(0,y)[1]))
    dimension((45,y0),(45,y0-h*scale),f"H = {h:g}",50,y0-h*scale/2)
    text(x0,450,"FRONT VIEW")
    # Third-angle top above front, right to its right, linked to the same datum.
    page.draw_rect(pymupdf.Rect(x0,110,x0+w*scale,110+t*scale),color=(0,0,0))
    for x,y in positions:
        for sign in (-1,1):
            xx=x0+(x+sign*d/2)*scale
            line((xx,110),(xx,110+t*scale),'[4 2]')
    text(x0,103,f"TOP VIEW   thickness T = {t:g}")
    xr=440
    page.draw_rect(pymupdf.Rect(xr,y0-h*scale,xr+t*scale,y0),color=(0,0,0))
    for x,y in positions:
        for sign in (-1,1):
            yy=y0-(y+sign*d/2)*scale
            line((xr,yy),(xr+t*scale,yy),'[4 2]')
    text(xr,450,"RIGHT VIEW")
    text(545,175,"HOLE COORDINATES",13)
    text(545,198,"X and Y measured from datum")
    text(545,225,"ID       X          Y         DIAMETER")
    for i,(x,y) in enumerate(positions): text(545,250+i*25,f"{i+1}       {x:g}       {y:g}       {d:g}")
    text(545,325,"Both holes: THROUGH")
    text(35,555,"Original synthetic data, MIT. Drawing is complete for nominal solid geometry; no manufacturing tolerances specified.",9)
    drawing=folder/'drawing.pdf'
    doc.save(str(drawing))
    page.get_pixmap(dpi=150).save(str(folder/'drawing.png'))
    doc.close()
    return {"id":folder.name,"drawing":folder.name+'/drawing.pdf',"sha256":sha256(drawing),
            "answer_step":folder.name+'/answer.step',"answer_table":folder.name+'/answer.json',
            "expected":expected,"license":"MIT","evaluation":"synthetic_geometry",
            "datum":"front lower-left, X right, Y up, Z toward viewer; thickness in +Z"}


def generate(out,count=12):
    out=Path(out)
    if out.exists(): raise ValueError('Use a new output directory')
    if not 1 <= count <= 12: raise ValueError('count must be 1..12')
    out.mkdir(parents=True)
    cases=[make_case(i,out/f'plate-{i+1:02}') for i in range(count)]
    dump({"schema_version":"1.0","purpose":"Pipeline regression; not a generalization benchmark","cases":cases},out/'manifest.json')
    return cases


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('-o','--out',required=True)
    ap.add_argument('--count',type=int,default=12)
    args=ap.parse_args()
    print(f'Generated {len(generate(args.out,args.count))} cases')
