# Drawing2SW evaluation data

`synthetic/manifest.json`: 12 original plate drawings with analytic expected properties, STEP and feature-table answers. MIT, copyright 2026 drawing2sw contributors. Only small, fully specified prismatic parts; no general engineering-drawing accuracy claim.

`generated/manifest.json`: 12 drawings from `dev/tools/generate_dataset.py` (seed 2026): plates with hole patterns, windows and fillets; disks with bolt circles; stepped shafts; flanges. Four GB, four ISO, four ASME (inch, third angle). Each case ships DXF with real dimension entities, a PDF with a text layer, a PNG and a simulated scan, plus `answer.json` / `answer.step`. `answer.json` has `dimension_labels`: for every dimension on the sheet, which feature and parameter it belongs to, its DXF handle, its position on the PDF and PNG, and the observation ID that `preprocess_drawing.py` assigns. MIT. Regenerate or create larger sets locally with a different `--seed`; the generator is deterministic for a given seed and library versions.

`external/cadsy/manifest.json`: 8 of the 65 parts in [cadsy/cad-technical-drawings](https://huggingface.co/datasets/cadsy/cad-technical-drawings) (Apache-2.0): STEP, one ISO-style and one ASME-style drawing per part, and label boxes for every dimension, callout, GD&T frame and title-block field. Geometry answers come from the STEP; there are no dimension-to-feature labels. `observations_<std>.json` turn the labels into observations so the reading and modeling steps can be tested without OCR error. Download the full set into `data/downloads/cadsy` and run `dev/tools/import_cadsy.py` for all 65. These parts are closer to real drawings: tolerances and GD&T on most sheets, counterbores, spotfaces, blind holes and bolt circles.

`external_cases.json`: two third-party drawing cases for manual/OCR evaluation. Each case has a PNG and DWG, no 3D ground truth. Attribution and the upstream MIT license are in `external/aaditya-jain/PROVENANCE.json` and `LICENSE`. Filenames are shortened; contents are unchanged.

Never expose `answer.json`, `answer.step` or manifests with expected properties to a model during a blind run. Use `scripts/benchmark.py prepare` and a clean skill package, with filesystem permissions scoped to those copies.

CATICS images, SolidWorks sample models, private drawings, downloaded model weights and local development artifacts are excluded from distribution. See `references/benchmark.md` for evaluation instructions.
