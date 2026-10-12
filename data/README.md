# Drawing2SW evaluation data

`synthetic/manifest.json`: 12 original plate drawings with analytic expected properties, STEP and feature-table answers. MIT, copyright 2026 drawing2sw contributors. Only small, fully specified prismatic parts; no general engineering-drawing accuracy claim.

`external_cases.json`: two third-party drawing cases for manual/OCR evaluation. Each case has a PNG and DWG, no 3D ground truth. Attribution and the upstream MIT license are in `external/aaditya-jain/PROVENANCE.json` and `LICENSE`. Filenames are shortened; contents are unchanged.

Never expose `answer.json`, `answer.step` or manifests with expected properties to a model during a blind run. Use `scripts/benchmark.py prepare` and a clean skill package, with filesystem permissions scoped to those copies.

CATICS images, SolidWorks sample models, private drawings, downloaded model weights and local development artifacts are excluded from distribution. See `references/benchmark.md` for evaluation instructions.
