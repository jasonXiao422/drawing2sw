# 分阶段读图与证据表（v0.5）

## 1. 观察原图

预处理同时生成 `extract.json` 和 `extract_observations.json`。后者包含原文件 SHA-256、页面尺寸、标注 ID、原文和位置。PDF 坐标是左上角起的 point；OCR/视觉坐标是原图像素；DXF 坐标是 WCS，不能当成像素使用。

先建立 `views`：视图编号、page、role、observation_refs 和必要说明。不能确定的角色写 unknown；剖视图记下剖切方向；局部放大记下对应位置。切图只用于放大观察，回填 bbox 时换回原图坐标。

从视觉读出的标注加入 observations，provider 用 visual；人工确认的用 human。不要伪造 OCR 分数，不要把推导结果写成原图文字。

图片没有文字层时，**不要自己估像素坐标**：模型看不准坐标，估出来的框常落在空白或线上。用脚本找框：

```powershell
.venv\Scripts\python.exe scripts\text_boxes.py detect work\drawing.png -o work\text_boxes.json
```

看 `text_boxes.png` 和分块放大图 `text_boxes_11.png`…，写 `labels.json`，只写编号和读到的原文，一条标注被拆成几个框时用 `+` 连起来：

```json
[{"box": "t58", "text": "17"}, {"box": "t105+t107+t110+t111", "text": "M2x0.4-6H 2 PLCS", "kind": "callout"}]
```

```powershell
.venv\Scripts\python.exe scripts\text_boxes.py emit work\text_boxes.json work\labels.json --observations work\extract_observations.json -o work\observations.json
```

找框只是图像处理，不认字，编号里有箭头、中心线、剖面线的杂框，不用理。校验时，provider 为 visual / human 的框里没有字会报错，把字切断会警告。

## 2. 建立关系

逐个记录尺寸属于哪个结构、起止基准、在哪个视图可交叉核对。将矛盾和缺失记入 open_questions。PDF/OCR 提取的数字也可能是页码、比例或公差；不能只因它是数字就用于建模。

模型自报 confidence 只是复核提示，不能解释成经过统计校准的正确概率。OCR score 同样不能衡量尺寸归属是否正确。扫描件仍沿用既有保守阈值，关键方位应通过其他视图核对。

## 3. 填特征表

新任务使用 schema_version 0.5，part.source.sha256 抄原图 SHA-256。每个特征同时提供：

```json
{"meta": {
  "confidence": 0.85,
  "evidence": "p1-text-7 的 W 定义外轮廓宽度；p1-text-12 的 T 定义厚度，单位来自标题栏。",
  "evidence_refs": ["p1-text-7", "p1-text-12"],
  "needs_review": true
}}
```

推导值在 evidence 解释公式和输入标注，几何计算继续使用 geom2d/ftable。标准查表值要说明标准、规格和查表状态；原图中至少要有可追溯的规格依据。无依据的必需尺寸停在问题列表，不填猜测值。

## 4. 校验边界

```powershell
.venv\Scripts\python.exe scripts\validate_feature_table.py work\part.json --observations work\extract_observations.json --json
```

v0.5 缺少证据文件、来源哈希不一致、引用不存在、标注框越界时失败。v0.2–0.4 保持兼容。

验证器证明引用完整性，无法证明模型确实看过这块图，也无法证明引用的尺寸属于这个特征。必须继续做图纸对照和关键尺寸检查。证据不是由模型签字就自动成立的。

### 尺寸归属检查（scripts/association.py）

提供 `--observations` 时，验证器还会做两项一致性检查，结果以警告给出：

1. 特征引用的每条尺寸观察，取它的主数值（去掉 4× 这样的数量，忽略 H7、±0.1 这类公差），在这个特征"用到的数"里找。用到的数包括直接参数、孔距、孔和窗口到外轮廓边或圆心基准的距离、回转轮廓的直径和台阶长度、分布圆直径。找不到就警告。
2. 证据里像尺寸的标注（Ø9、R5、4× Ø9 THRU、20±0.1、1 X 45°）没被任何特征引用，就列出来。

数能对上只说明一致，不说明一定对：两个特征可能刚好用同一个数。数对不上也可能是图纸用了这里没覆盖的标注方式（比如从另一个孔量起）。这时在 evidence 里写清楚基准和换算，警告可以保留，但要能解释。

## 5. 预览与投影复核

先输出 CadQuery STEP，再执行：

```powershell
.venv\Scripts\python.exe scripts\project_model.py work\preview.step --drawing work\drawing_p1.png -o work\projection-review
```

输出四方向 SVG 和自包含 review.html。用平移、等比缩放、旋转将对应视图对齐；先对外轮廓，再看孔中心和可见/隐藏线。可保存 alignment.json 记录所用模型、图纸哈希和对齐参数。此工具供人或能看图的模型复核，不会自动给出准确率。

剖视、断裂视图、局部放大以及齿轮/螺纹规定画法不能用普通投影直接判错。它们需要剖切或专门检查。模型不能确认时，请用户看具体标注或区域。

verify_model 的 verified 只指“所提供的几何属性通过”；drawing_verified 始终为 false。缺少参照指标会失败；仅孔数或面数不能判通过。默认包围盒忽略坐标轴排列，只有两模型基准对齐后才使用 --aligned-axes。
