"""Drawing evidence shared by preprocessing, OCR import and feature validation.

Coordinates always refer to the ORIGINAL page/image, never a resized crop.
IDs are stable for an unchanged source and unchanged extractor ordering.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def from_extract(extract, source):
    source = Path(source)
    doc = {"schema_version": "1.0", "source": {"file": source.name, "sha256": sha256(source)},
           "pages": [], "observations": [], "views": [], "open_questions": []}
    for p in extract.get("pages", []):
        page = p["page"]
        info = {"page": page, "image": p["image"]}
        if "size_pt" in p:
            info["size_pt"] = p["size_pt"]
        from PIL import Image
        with Image.open(p["image"]) as im:
            info["size_px"] = list(im.size)
        doc["pages"].append(info)
        for i, item in enumerate(p.get("text_items", [])):
            doc["observations"].append({"id": f"p{page}-text-{i+1}", "page": page,
                "text": item["text"], "bbox": item["bbox"], "coordinate_space": "pdf_pt",
                "provider": "pdf_text", "kind": "text"})
    for i, item in enumerate(extract.get("dxf", {}).get("dimensions", [])):
        text = item.get("displayed_text") or item.get("text", "")
        doc["observations"].append({"id": f"dxf-dim-{i+1}", "page": 1,
            "text": text, "point": item.get("at", [0, 0]), "coordinate_space": "dxf_wcs",
            "provider": "dxf_dimension", "kind": item.get("kind", "dimension"),
            "entity_handle": item.get("entity_handle", ""),
            "requires_review": bool(item.get("override_replaces_value"))})
    if not doc["observations"]:
        doc["open_questions"].append("No text extracted. Import OCR or record visual observations with original-image bounding boxes.")
    return doc


def validate_document(doc):
    import jsonschema
    try:
        json.dumps(doc, allow_nan=False)
    except (ValueError, TypeError):
        return ["Evidence contains non-finite numbers or non-JSON values"]
    schema_path = Path(__file__).resolve().parents[1] / "schema" / "observations.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = [f"observations @ {'/'.join(map(str, e.path))}: {e.message}"
              for e in jsonschema.Draft202012Validator(schema).iter_errors(doc)]
    if errors:
        return errors
    ids = [o["id"] for o in doc["observations"]]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate observation IDs")
    pages = {p["page"]: p for p in doc["pages"]}
    if len(pages) != len(doc["pages"]):
        errors.append("Duplicate page numbers")
    for o in doc["observations"]:
        if o["coordinate_space"] == "dxf_wcs":
            if "point" not in o:
                errors.append(f"{o['id']}: DXF evidence needs an entity point")
            continue
        p = pages.get(o["page"])
        size_key = "size_pt" if o["coordinate_space"] == "pdf_pt" else "size_px"
        if not p or size_key not in p or "bbox" not in o:
            errors.append(f"{o['id']}: missing page, coordinate size or bounding box")
            continue
        x0, y0, x1, y1 = o["bbox"]
        w, h = p[size_key]
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            errors.append(f"{o['id']}: bounding box outside original page or empty")
    view_ids = [v["id"] for v in doc["views"]]
    if len(view_ids) != len(set(view_ids)):
        errors.append("Duplicate view IDs")
    for v in doc["views"]:
        if v["page"] not in pages:
            errors.append(f"{v['id']}: unknown page")
        for ref in v["observation_refs"]:
            if ref not in ids:
                errors.append(f"{v['id']}: unknown observation {ref}")
    return errors


def check_feature_evidence(table, doc=None):
    errors, warnings = [], []
    strict = table.get("schema_version") == "0.5"
    if doc is None:
        if strict:
            errors.append("v0.5 requires --observations pointing to the source evidence document")
        return errors, warnings
    errors.extend(validate_document(doc))
    if errors:
        return errors, warnings
    expected_hash = table.get("part", {}).get("source", {}).get("sha256")
    if strict and not expected_hash:
        errors.append("v0.5 requires part.source.sha256 from the original drawing")
    if expected_hash and expected_hash != doc["source"]["sha256"]:
        errors.append("Feature table and observations refer to different source files (SHA-256 mismatch)")
    lookup = {o["id"]: o for o in doc["observations"]}
    for f in table.get("features", []):
        meta = f.get("meta", {})
        refs = meta.get("evidence_refs", [])
        if strict and (not refs or not meta.get("evidence", "").strip()):
            errors.append(f"[{f['id']}] v0.5 needs evidence text AND evidence_refs")
        for ref in refs:
            o = lookup.get(ref)
            if o is None:
                errors.append(f"[{f['id']}] unknown evidence reference: {ref}")
            elif o.get("requires_review") or o.get("score", 1) < 0.9:
                warnings.append(f"[{f['id']}] review source observation {ref}: {o['text']}")
    warnings.append("Evidence links prove traceability, not that a dimension was assigned to the correct feature.")
    return errors, warnings
