# Drawing2SW

**面向机械单零件的跨模型读图建模工具链。** 将 DWG、DXF、PDF、图片转换成可追溯的特征表，再由确定性脚本生成 STEP 和 SolidWorks 零件。

Drawing2SW is a model-agnostic mechanical drawing-to-CAD skill with source-linked observations, deterministic feature compilation and explicit verification limits.

## v0.5 有什么变化

- 原图 → 标注/视图证据 → 特征表，特征引用标注 ID，并绑定原图 SHA-256。
- PaddleOCR 3.x JSON 导入与可选 CPU 推理适配器；不改 CAD 主环境。
- 缺失测量指标不能误报通过；区分属性校验和图纸正确性。CadQuery 报告增加表面积和面数。
- 四方向可见/隐藏线 SVG，以及可平移、旋转、缩放的本地叠图页。
- 12 张有解析几何答案的合成图，以及 2 组带 MIT 许可与来源的真实 PNG/DWG 挑战样例。
- 盲测输入打包、离线评分、干净 skill ZIP、自动化回归测试。

保留 drawing2sw 名称和既有命令。v0.2–0.4 特征表继续可用；v0.5 新表必须校验证据。不同模型的效果尚未通过统一盲测确认。

## 架构

```text
图纸 → 原生文字/几何提取、可选 OCR
     → observations.json（原文、位置、视图、来源）
     → 模型关联尺寸并填写 part.json
     → schema / 证据 / 工程规则校验
     → CadQuery STEP + 投影复核
     → SolidWorks 逐步建模
     → 属性检查、参考几何比较、人工复核
```

接口可跨模型使用。模型或宿主需要能读图片、读取引用文件、调用本地脚本；无本地执行能力时需另一执行端。工具不会为没有空间理解能力的模型自动补齐所有能力，也不承诺支持所有工程图。

## 安装与试用

推荐现有项目使用 Python 3.12。Windows + SolidWorks 可生成 SLDPRT；有 CadQuery 即可预览 STEP。安装步骤见 [setup](references/setup.md)。

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
.venv\Scripts\python.exe scripts\validate_feature_table.py examples\bracket_prismatic.json
.venv\Scripts\python.exe scripts\preview_cadquery.py examples\bracket_prismatic.json -o work\plate.step
.venv\Scripts\python.exe scripts\verify_model.py examples\bracket_prismatic.json --report work\plate_report.json
```

新图读法见 [SKILL.md](SKILL.md)。可追溯格式见 [evidence workflow](references/evidence-workflow.md)，OCR 见 [ocr.md](references/ocr.md)。完整 v0.5 示例放在 examples/evidence/。

## 当前边界

支持拉伸、旋转、切除、孔、沉孔、圆角倒角、斜面及渐开线直齿等 schema 内的单件特征。钣金、装配、扫描/放样、抽壳和通用镜像/线性阵列未覆盖。

几何通过不等于工程图读对：位置、镜像、制造公差、GD&T 和建模意图还需专门检查。投影工具供复核，尚未实现剖视自动比对。OCR 本地模型推理取决于可选依赖；适配器测试不代表尺寸识别率。

## 评测与数据

[评测说明](references/benchmark.md) · [数据来源](data/README.md) · [第三方声明](THIRD_PARTY_NOTICES.md)

合成集只覆盖尺寸完整的双孔板，不能用于宣称真实图纸成功率。外部图没有 3D 答案，单列人工评估。测试输入包不含答案；必须在独立权限范围内运行模型，不能给模型整个开发仓库。

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_v05*.py"
.venv\Scripts\python.exe tests\test_geom2d.py
.venv\Scripts\python.exe scripts\package_skill.py -o dist\drawing2sw-0.5.zip
```

skill 包只带运行所需脚本、参考、schema、示例、安装说明及许可证，不包含评测答案、原有私有图纸、虚拟环境或工作记录。

## 来源与许可

本项目代码及原创合成样例采用 MIT。两组第三方图纸版权属于 Aaditya Jain，保留其 MIT 许可证。依赖、模型和数据分别遵守上游条款，见 THIRD_PARTY_NOTICES.md。

原项目借鉴了 SolidPilot/MCP_CAD 的受限 CAD 执行与中间表示，以及 CAD-Coder 的 CadQuery 思路。本版进一步学习 PaddleOCR、eDOCr2、Drawing2CAD 的输入处理和评测设计；已实现的接入与仅供研究的项目明确分列。
