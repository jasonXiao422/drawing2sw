# Upstream projects and data

Reviewed 2026-10-12. Code licenses and data licenses are separate; a paper or public repository alone is not permission to redistribute all linked data.

| Project | Integration in this release | License / limits |
|---|---|---|
| [CadQuery](https://github.com/CadQuery/cadquery) | Existing geometry backend; new public SVG exporter calls for orthographic visible/hidden lines. No upstream source copied. | Apache-2.0; transitive components have their own licenses. |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | New 3.x JSON importer and optional public Python API adapter. No weights bundled. | Apache-2.0 code; installation/model terms remain upstream. |
| [eDOCr2](https://github.com/javvi51/edocr2) | Studied engineering drawing segmentation/OCR and recognizer workflow. Not bundled. | MIT code; no assumption that all paper drawings have the same rights. |
| [Drawing2CAD](https://github.com/lllssc/Drawing2CAD) | Studied vector multi-view data preparation and separation of generation/evaluation. No trained model or dataset bundled. | MIT code; README says CAD data derives from DeepCAD. Check dataset terms separately. |
| [CAD2Program](https://github.com/manycore-research/CAD2Program) | Research reference only. Repository inspected is project website source, not an executable modeling backend. | Website CC-BY-SA-4.0. Nothing copied. |
| [MechVQA](https://github.com/xiaofengShi/MechVQA) | Candidate for future recognition/reasoning evaluation, not merged in this release. | Repository declares Apache-2.0; released dataset cards and image rights require separate review. |
| [cadsy/cad-technical-drawings](https://huggingface.co/datasets/cadsy/cad-technical-drawings) | 8 of 65 parts vendored unchanged in `data/external/cadsy` (STEP, ISO and ASME drawings, annotation labels); `dev/tools/import_cadsy.py` converts the full set locally. Used for evaluation and to derive callout-reading rules. | Apache-2.0, LICENSE kept. 3D models from [ADSKAILab/Zero-To-CAD-100k](https://huggingface.co/datasets/ADSKAILab/Zero-To-CAD-100k), Apache-2.0. |
| [solidworks-automation-skill](https://github.com/wzyn20051216/solidworks-automation-skill) | Studied for SolidWorks feature implementations (slots, counterbores, linear patterns, threaded holes). No code copied in this release. | MIT. |
| [Ortho2CAD](https://github.com/AdityaJoglekar/Ortho2CAD) | Studied its projection-comparison self-refinement method. Its dataset declares no license and is not used. | No license stated. Nothing copied. |
| [AutoCAD 2D Mechanical Drawings](https://github.com/Aadityajain-hub/AutoCAD_2D_Drawings) | Two PNG/DWG pairs vendored unchanged except filenames, plus original MIT LICENSE. | Copyright (c) 2025 Aaditya Jain. Commit and file checksums in data/external/aaditya-jain/PROVENANCE.json. No 3D ground truth. |

Existing runtime dependencies also include ezdxf, PyMuPDF, matplotlib, pywin32 and JSON Schema tooling. This repository's license does not replace theirs. PyMuPDF offers AGPL/commercial licensing; review dependency distribution terms before packaging a proprietary binary or service. The skill archive contains our source and requirement declarations, not vendored dependency binaries.

The original skill README records SolidPilot, MCP_CAD and CAD-Coder as architectural influences. This release preserves that history without importing their source code.
