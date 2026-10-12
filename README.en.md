<div align="center">

# Drawing2SW

**Reads your engineering drawings and models the part in SolidWorks.**

DWG · DXF · PDF · images → feature table → STEP / SLDPRT

[![CI](https://github.com/jasonXiao422/drawing2sw/actions/workflows/tests.yml/badge.svg)](https://github.com/jasonXiao422/drawing2sw/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-2f6f62.svg)](LICENSE)
[![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-3776ab.svg)](references/setup.md)
[![Platform](https://img.shields.io/badge/SolidWorks-Windows-c8102e.svg)](references/setup.md)
[![Skill](https://img.shields.io/badge/Agent%20Skill-Claude%20Code%20%7C%20Codex-555.svg)](#4-install-the-skill)
[![Download](https://img.shields.io/badge/download-drawing2sw.zip-c2410c.svg)](https://github.com/jasonXiao422/drawing2sw/releases/latest/download/drawing2sw.zip)

[Website](https://jasonxiao422.github.io/drawing2sw/?lang=en) · [中文](README.md) · [Quick start](#quick-start) · [How it works](#how-it-works) · [FAQ](#faq)

<br>

<table>
<tr>
<td align="center" width="55%"><img src="docs/assets/crankcase_views.png" alt="Mini Crank Case: views projected from the model" width="100%"></td>
<td align="center" width="45%"><img src="docs/assets/crankcase.png" alt="Mini Crank Case 3D model" width="88%"></td>
</tr>
<tr><td colspan="2" align="center"><sub><b>V-twin crank case</b>: two 30° cylinder faces, bores offset by 2 mm, eight tapped holes on inclined faces, side walls tangent to the relief arcs. 14 SolidWorks features, every step check passed</sub></td></tr>
<tr>
<td align="center" width="55%"><img src="docs/assets/pivotarm_views.png" alt="Pivot Arm: views projected from the model" width="100%"></td>
<td align="center" width="45%"><img src="docs/assets/pivotarm.png" alt="Pivot Arm 3D model" width="80%"></td>
</tr>
<tr><td colspan="2" align="center"><sub><b>S-shaped pivot arm</b>: R75 / R35 reverse arcs give an R55 centreline turning 74.17° each way, R12 blends and chamfers. 9 SolidWorks features, every step check passed</sub></td></tr>
</table>

<sub>Exercises 17 and 21 from Curtis Waguespack's <a href="https://inventortrenches.blogspot.com/">Inventor practice drawings</a>. The original sheets are copyrighted and not reproduced; the left column is projected back from our model (third angle) for comparison with the original.</sub>

</div>

## What it is

Drawing2SW is an **agent skill**. Give a part drawing to an agent that can run local commands (Claude Code, Codex, and similar). The skill tells it how to read the drawing and fill in a feature table. The scripts in this repo then build the 3D model.

The idea: **the model reads the drawing; deterministic code does the geometry.**

- The model does what it is good at: identifying views, finding dimensions, deciding which dimension belongs to which feature.
- Intersections, tangent points, unit conversion and every SolidWorks API call are handled by scripts. The model never improvises CAD code.
- Every feature records which annotation on the drawing it came from, so mistakes can be traced back to the source.
- After the build, volume, surface area and bounding box are compared automatically, and the report says plainly **what was not checked**.

## Features

| | |
|---|---|
| 📐 **Many inputs** | Native dimension entities from DWG/DXF, positioned text from PDF, automatic view splitting for scans and photos, optional PaddleOCR |
| 🧾 **Traceable intermediate format** | A CAD-neutral JSON feature table. Each feature carries `evidence_refs` and is bound to the source file's SHA-256 |
| 🧮 **Geometry in code** | Write only the dimensions on the drawing. `geom2d` solves tangent arcs, intersections and fillet points |
| 🛠 **Two backends** | CadQuery writes STEP on any OS. On Windows, SolidWorks is driven feature by feature over COM |
| 🔗 **Dimension association check** | Warns when a feature cites a dimension whose value it never uses (likely assigned to the wrong feature), and lists dimensions no feature uses |
| ✅ **Step-by-step self-check** | Each SolidWorks step is compared with CadQuery for volume and position, so failures point to a specific feature |
| 🔍 **Projection review** | Project the model into four wireframe views and overlay them on the drawing |
| 🧪 **Reproducible evaluation** | A synthetic drawing generator that labels which feature every dimension belongs to; scoring covers pose-free geometry (mirrors still fail) and dimension association |

## How it works

```mermaid
flowchart LR
    A[Drawing<br>DWG / DXF / PDF / image] --> B[Preprocess<br>extract dims and text]
    B --> C[observations.json<br>text + position + hash]
    C --> D{{Agent reads<br>links views and dims}}
    D --> E[part.json<br>feature table]
    E --> F[Validate<br>schema · evidence · rules]
    F --> G[CadQuery<br>STEP + projections]
    G --> H[SolidWorks<br>build + self-check]
    H --> I[Compare<br>volume · area · bbox]
```

Only the diamond is the model. Everything else is ordinary, repeatable Python.

## Quick start

### 1. Requirements

| Need | Notes |
|---|---|
| Windows 10 / 11 | macOS / Linux work for STEP preview only |
| Python **3.11 or 3.12** | CadQuery does not install on 3.13+. Other installed versions can stay |
| SolidWorks 2020+ | Optional. Student and education editions work |
| DWG converter | Optional, only for DWG input. AutoCAD, ZWCAD, GstarCAD or ODA File Converter |

### 2. Install

```powershell
git clone https://github.com/jasonXiao422/drawing2sw.git
cd drawing2sw
powershell -ExecutionPolicy Bypass -File install.ps1
```

`install.ps1` finds Python 3.12, creates `.venv`, installs dependencies and runs an environment check.

Dependencies come from the official PyPI by default; outside mainland China there is nothing to configure.

**Mainland China only, if downloads stall** (also Doubao users, whose agent defaults to the Huawei Cloud pip mirror): a slow mirror does not trigger the fallback. Press Ctrl+C and rerun with the Tsinghua mirror:

```powershell
$env:PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"; powershell -ExecutionPolicy Bypass -File install.ps1
```

<details>
<summary>Manual install / macOS / Linux</summary>

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/check_env.py
```

Add `--sw` to `check_env.py` to test the SolidWorks connection on Windows.

</details>

### 3. Run an example without any AI

```powershell
.venv\Scripts\python.exe scripts\validate_feature_table.py examples\bracket_prismatic.json
.venv\Scripts\python.exe scripts\preview_cadquery.py examples\bracket_prismatic.json -o work\plate.step
.venv\Scripts\python.exe scripts\verify_model.py examples\bracket_prismatic.json --report work\plate_report.json
```

With SolidWorks installed:

```powershell
.venv\Scripts\python.exe scripts\sw_build.py examples\bracket_prismatic.json -o work\plate.SLDPRT --report work\sw_report.json
```

Close any SolidWorks start-up dialogs first, or the build will wait on them.

<p align="center">
<img src="docs/assets/bracket.png" alt="Mounting plate example" width="42%">
&nbsp;&nbsp;&nbsp;
<img src="docs/assets/frame.png" alt="Bearing frame modelled from a GB textbook drawing" width="34%">
<br><sub>Left: repository example <code>bracket_prismatic.json</code>. Right: a bearing frame modelled from a GB textbook drawing, 21 SolidWorks step checks passed</sub>
</p>

### 4. Install the skill

**Easiest**: paste the text below to your agent (Claude Code, Codex, ...). It installs step by step and asks you first. The [website](https://jasonxiao422.github.io/drawing2sw/?lang=en#install) has a copy button.

<details>
<summary>Install prompt (click to copy)</summary>

```text
Please install the Drawing2SW skill for me. It reads engineering drawings (DWG, DXF, PDF, images) and models the part in SolidWorks.

Source: the official GitHub repository https://github.com/jasonXiao422/drawing2sw (MIT). Download only from this address, not from mirrors or third-party pages.

Before running each command, tell me what it does and wait for my OK.

1. Check the environment: run `git --version` and `py -3.12 --version` (or `py -3.11 --version`). If git or Python 3.11/3.12 is missing, tell me how to install it; don't install it for me.
2. Download into your skills folder. For Claude Code that is `%USERPROFILE%\.claude\skills\drawing2sw`; other agents should use their own personal skills folder, ask me if unsure:
   git clone --depth 1 https://github.com/jasonXiao422/drawing2sw.git <that folder>
   If the folder already exists, run `git pull` inside it instead.
3. Show me the first 20 lines of SKILL.md and explain what install.ps1 does (creates a .venv inside the skill folder, installs requirements.txt from PyPI, falls back to a mirror if that fails, then runs an environment check). Wait for my OK.
4. In the skill folder run: powershell -ExecutionPolicy Bypass -File install.ps1 (CadQuery is large, this takes a few minutes). It downloads from the official PyPI. Only if I am in mainland China and a package makes no download progress for several minutes: stop, set $env:PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple" and rerun the same command. Do not install other versions yourself.
5. Run `.venv\Scripts\python.exe scripts\check_env.py` and tell me the result. If I have SolidWorks, run it again with `--sw`.
6. Tell me it's ready and how to use it, for example: "Use drawing2sw to model D:\drawings\bracket.pdf in SolidWorks".

If your safety settings don't allow downloading or running these commands, just say so and I'll run them myself in a terminal.
```

</details>

If the agent says its safety settings block downloading third-party code, that is a normal safeguard; use the commands below instead.

**Download the package**: [drawing2sw.zip](https://github.com/jasonXiao422/drawing2sw/releases/latest/download/drawing2sw.zip) (the skill only, about 250 KB). Unzip into `%USERPROFILE%\.claude\skills\` so you get `skills\drawing2sw\SKILL.md`, then run `powershell -ExecutionPolicy Bypass -File install.ps1` inside the `drawing2sw` folder.


The entry point is [`SKILL.md`](SKILL.md). Put the repository where your agent looks for skills and run `install.ps1` there.

**Claude Code**

```powershell
git clone https://github.com/jasonXiao422/drawing2sw.git "$env:USERPROFILE\.claude\skills\drawing2sw"
cd "$env:USERPROFILE\.claude\skills\drawing2sw"
powershell -ExecutionPolicy Bypass -File install.ps1
```

Then type `/drawing2sw`, or just ask it to model a drawing. For a single project, use `.claude/skills/drawing2sw/` instead.

**Codex:** place it in `.agents/skills/drawing2sw/` in your project and invoke `$drawing2sw`. Check the current Codex docs for the exact location.

**Other agents:** any agent that can read local files and run local Python. Tell it: "Read `drawing2sw/SKILL.md` first and follow it."

### 5. Ask for a part

```text
Use drawing2sw to model D:\drawings\bracket.pdf as a SolidWorks part. Save it to D:\out\
```

The agent will stop and ask about units, projection method, keyway and hole orientation, and any dimension missing from the drawing. **Volume checks cannot catch these. A person has to look.**

## What it can build

| Category | Features |
|---|---|
| Revolved parts | Shafts, flanges, sleeves, discs: `base_revolve`, `revolve` about any axis |
| Prismatic parts | Plates, brackets, bases: `base_extrude`, `extrude`, `cut_extrude` |
| Profiles | Rectangles, circles, polygons, line-and-arc paths, tangent arc loops |
| Holes | Plain, tap drill, counterbore, countersink, drill point, bolt circles |
| Details | Chamfers, fillets, arbitrary inclined planes, cut up to a curved face |
| Copies | Linear patterns (row or grid) `linear_pattern`, circular patterns `circular_pattern`, mirror `mirror` |
| Thin walls | Shell `shell` (inward, outward, closed hollow) |
| Draft | Drafted extrudes and cuts `draft` (die-cast and molded parts, inner and outer draft can oppose) |
| Gears | Involute spur teeth |
| Drawing setup | mm / inch, first / third angle, scale, dual units, DIMLFAC |

**Not yet:** sheet metal, assemblies, sweep / loft, multi-thickness shell, mirroring the whole body. The agent reports the gap instead of faking it.

## How far to trust the result

- **"Passed" only means the measured properties matched.** `drawing_verified` is always `false`.
- **A mirrored part has the same volume.** A wrong projection method passes volume, area and bounding box.
- **Moving a hole 2 mm does not change the volume.** Hole positions need projection review or a boolean comparison with a reference STEP.
- **Both backends agreeing does not mean the drawing was read correctly.** They execute the same table.
- **Evidence links prove traceability,** not that a dimension was assigned to the right feature.

## Evaluation

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_v05*.py"
.venv\Scripts\python.exe tests\test_geom2d.py
```

Generate new synthetic drawings (hole plates, bolt-circle disks, stepped shafts, flanges; GB / ISO / ASME; DXF / PDF / PNG / simulated scan):

```powershell
.venv\Scripts\python.exe dev\tools\generate_dataset.py -o work\dataset --count 40 --seed 1
```

To compare models, follow [benchmark.md](references/benchmark.md) and build an answer-free input package with `scripts/benchmark.py prepare`. **Never give the model under test the whole repository;** `data/` contains answers.

## FAQ

<details><summary><b>Can I use it without SolidWorks?</b></summary>

Yes. The CadQuery backend writes STEP, which any CAD tool opens. `.SLDPRT` output needs Windows and SolidWorks.
</details>

<details><summary><b>CadQuery will not install</b></summary>

Check that `.venv` uses Python 3.11 or 3.12. It is only needed for preview.
</details>

<details><summary><b>Cannot connect to SldWorks.Application, or the build hangs</b></summary>

Open SolidWorks once by hand and close every dialog. A hidden dialog is the usual cause of a hang.
</details>

<details><summary><b>Which model works best?</b></summary>

No controlled blind comparison yet, so no claim. The model must see images and run local commands.
</details>

More in [setup and troubleshooting](references/setup.md) (Chinese).

## Contributing

Issues and PRs are welcome, especially drawings the agent misread (only ones you can share publicly) and new feature types. Read [`dev/DEVELOPING.md`](dev/DEVELOPING.md) first: make CadQuery match before touching the SolidWorks backend. Most internal docs are in Chinese.

## License

Code and original synthetic data: [MIT](LICENSE). The two drawings in `data/external/aaditya-jain/` are © Aaditya Jain under their MIT license. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
