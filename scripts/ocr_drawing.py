"""Import PaddleOCR 3.x results in ORIGINAL image pixels. See references/ocr.md."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import observations


def normalize_paddle(payload, page):
    if isinstance(payload, dict) and "res" in payload:
        payload = payload["res"]
    if not isinstance(payload, dict):
        raise ValueError("Expected one PaddleOCR 3.x result object for one full-page image")
    texts, scores = payload.get("rec_texts"), payload.get("rec_scores")
    boxes = payload.get("rec_polys", payload.get("rec_boxes"))
    if not isinstance(texts, list) or not isinstance(scores, list) or not isinstance(boxes, list):
        raise ValueError("Paddle result needs rec_texts, rec_scores and rec_polys/rec_boxes")
    if not (len(texts) == len(scores) == len(boxes)):
        raise ValueError("Mismatched PaddleOCR result lengths")
    result = []
    for i, (text, score, box) in enumerate(zip(texts, scores, boxes)):
        if not isinstance(text, str) or not text.strip():
            continue
        if len(box) == 4 and all(isinstance(x, (int, float)) for x in box):
            bbox = box
        else:
            if len(box) < 3 or any(len(p) != 2 for p in box):
                raise ValueError("Invalid OCR polygon")
            xs, ys = zip(*box)
            bbox = [min(xs), min(ys), max(xs), max(ys)]
        result.append({"id": f"p{page}-ocr-{i+1}", "page": page, "text": text,
                       "score": score, "bbox": bbox, "coordinate_space": "image_px",
                       "provider": "paddleocr", "kind": "text", "requires_review": True})
    return result


def attach(doc, payload, page):
    doc = json.loads(json.dumps(doc))
    if page not in {p["page"] for p in doc["pages"]}:
        raise ValueError("Unknown page; run preprocessing first")
    incoming = normalize_paddle(payload, page)
    if any(o["page"] == page and o["provider"] == "paddleocr" for o in doc["observations"]):
        raise ValueError("Page already contains OCR. Start from the original extract to avoid stale references.")
    doc["observations"].extend(incoming)
    errors = observations.validate_document(doc)
    if errors:
        raise ValueError("; ".join(errors))
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("observations")
    ap.add_argument("--page", type=int, default=1)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--paddle-json")
    group.add_argument("--engine", choices=["paddleocr"])
    ap.add_argument("--lang", default="ch")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    if Path(args.out).exists():
        ap.error("Output already exists; choose a new filename")
    doc = json.loads(Path(args.observations).read_text(encoding="utf-8"))
    if args.paddle_json:
        payload = json.loads(Path(args.paddle_json).read_text(encoding="utf-8"))
    else:
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            ap.error("Install PaddleOCR in an isolated environment; see references/ocr.md")
        page = next((p for p in doc["pages"] if p["page"] == args.page), None)
        if page is None:
            ap.error("Unknown page")
        image = Path(page["image"])
        if not image.is_file():
            ap.error("Page image missing; use the same working directory as preprocessing")
        engine = PaddleOCR(lang=args.lang, device="cpu", use_doc_orientation_classify=False,
                          use_doc_unwarping=False, use_textline_orientation=False)
        results = list(engine.predict(str(image)))
        if len(results) != 1:
            ap.error("Expected exactly one page result")
        payload = results[0].json
        if isinstance(payload, str):
            payload = json.loads(payload)
    output = attach(doc, payload, args.page)
    observations.dump(output, args.out)
    print(json.dumps({"out": args.out, "observations": len(output["observations"])}))


if __name__ == "__main__":
    main()
