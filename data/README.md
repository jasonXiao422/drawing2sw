# Drawing2SW evaluation data

`synthetic/manifest.json`: 12 original plate drawings with analytic expected properties, STEP and feature-table answers. MIT, copyright 2026 drawing2sw contributors. Only small, fully specified prismatic parts; no general engineering-drawing accuracy claim.

`generated/manifest.json`: 12 drawings from `dev/tools/generate_dataset.py` (seed 2026): plates with hole patterns, windows and fillets; disks with bolt circles; stepped shafts; flanges. Four GB, four ISO, four ASME (inch, third angle). Each case ships DXF with real dimension entities, a PDF with a text layer, a PNG and a simulated scan, plus `answer.json` / `answer.step`. `answer.json` has `dimension_labels`: for every dimension on the sheet, which feature and parameter it belongs to, its DXF handle, its position on the PDF and PNG, and the observation ID that `preprocess_drawing.py` assigns. MIT. Regenerate or create larger sets locally with a different `--seed`; the generator is deterministic for a given seed and library versions.

`external_cases.json`: two third-party drawing cases for manual/OCR evaluation. Each case has a PNG and DWG, no 3D ground truth. Attribution and the upstream MIT license are in `external/aaditya-jain/PROVENANCE.json` and `LICENSE`. Filenames are shortened; contents are unchanged.

Never expose `answer.json`, `answer.step` or manifests with expected properties to a model during a blind run. Use `scripts/benchmark.py prepare` and a clean skill package, with filesystem permissions scoped to those copies.

CATICS images, SolidWorks sample models, private drawings, downloaded model weights and local development artifacts are excluded from distribution. See `references/benchmark.md` for evaluation instructions.
