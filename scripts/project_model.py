"""Export orthographic SVGs and a local drawing overlay for HUMAN review.

Uses CadQuery's public SVG/HLR exporter. No image similarity score is reported:
sections, annotation lines and conventional gear/thread drawing need interpretation.
"""
from __future__ import annotations
import argparse
import base64
import html
import json
from pathlib import Path

VIEWS = {"front": (0, 0, 1), "top": (0, 1, 0), "left": (-1, 0, 0), "right": (1, 0, 0)}


def export_views(step, out, drawing=None):
    import cadquery as cq
    from observations import sha256, dump
    out = Path(out)
    if out.exists():
        raise ValueError("Choose a new output directory; existing review artifacts are not overwritten")
    shape = cq.importers.importStep(str(step)).val()
    out.mkdir(parents=True)
    files = {}
    for name, direction in VIEWS.items():
        svg = cq.exporters.getSVG(shape, opts={"width": 900, "height": 700,
            "projectionDir": direction, "showAxes": False, "showHidden": True,
            "strokeColor": (190, 25, 25), "hiddenColor": (80, 120, 180), "strokeWidth": 0.6})
        (out / f"{name}.svg").write_text(svg, encoding="utf-8")
        files[name] = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    manifest = {"step_sha256": sha256(step), "views": VIEWS,
                "review_status": "needs_human_review", "automatic_drawing_verification": False,
                "note": "Camera direction is explicit; screen roll/scale must be aligned to the drawing."}
    if drawing:
        from PIL import Image
        import io
        with Image.open(drawing) as im:
            im = im.convert("RGB")
            size = im.size
            buf = io.BytesIO()
            im.save(buf, format="PNG")
        original = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        manifest["drawing_sha256"] = sha256(drawing)
        content = '''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Drawing2SW projection review</title><style>
body{font:15px system-ui;margin:20px;background:#f4f6fa;color:#172033}
header{position:sticky;top:0;background:#fff;padding:16px;z-index:2;border:1px solid #ccd3df}
label{display:inline-block;margin:8px}input{width:80px}#stage{position:relative;margin-top:16px;background:white}
#drawing{display:block}#projection{position:absolute;top:0;left:0;transform-origin:0 0;mix-blend-mode:multiply;pointer-events:none}
</style><header><b>Drawing2SW · Projection review</b>
<p>Align the view using translation, uniform scale and rotation. Red: visible edges. Blue: hidden edges.
Ordinary projection cannot validate a section view. This page does not certify dimensional correctness.</p>
<label>View <select id="view"><option>front</option><option>top</option><option>left</option><option>right</option></select></label>
<label>X px <input id="x" type="number" value="0"></label><label>Y px <input id="y" type="number" value="0"></label>
<label>Scale <input id="scale" type="number" min="0.01" step="0.01" value="1"></label>
<label>Rotation ° <input id="rotation" type="number" value="0"></label>
<label>Opacity <input id="opacity" type="range" min="0" max="1" step="0.05" value="0.7"></label>
<button id="save">Save alignment</button></header>
<div id="stage"><img id="drawing" src="__DRAWING__" width="__WIDTH__" height="__HEIGHT__"><img id="projection"></div>
<script>const images=__IMAGES__, provenance=__PROVENANCE__;
const ids=['view','x','y','scale','rotation','opacity'], el=Object.fromEntries(ids.map(x=>[x,document.getElementById(x)]));
function update(){let p=document.getElementById('projection');p.src=images[el.view.value];p.style.opacity=el.opacity.value;
p.style.transform=`translate(${Number(el.x.value)}px,${Number(el.y.value)}px) rotate(${Number(el.rotation.value)}deg) scale(${Math.max(.01,Number(el.scale.value))})`;}
ids.forEach(id=>el[id].addEventListener('input',update));update();
document.getElementById('save').onclick=()=>{let data={...provenance,alignment:Object.fromEntries(ids.map(id=>[id,el[id].value]))};
let u=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));let a=document.createElement('a');
a.href=u;a.download='alignment.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};</script></html>'''
        content = content.replace("__DRAWING__", original).replace("__WIDTH__", str(size[0])).replace("__HEIGHT__", str(size[1]))
        content = content.replace("__IMAGES__", json.dumps(files)).replace("__PROVENANCE__", json.dumps(manifest))
        (out / "review.html").write_text(content, encoding="utf-8")
    dump(manifest, out / "projection_report.json")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("step")
    ap.add_argument("--drawing", help="Original page image or a single-view crop")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    print(json.dumps(export_views(args.step, args.out, args.drawing), indent=2))


if __name__ == "__main__":
    main()
