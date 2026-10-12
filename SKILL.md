---
name: drawing2sw
description: 读取机械零件工程图（DWG、DXF、矢量 PDF、扫描图、截图、CATICS 类着色题图），提取成结构化特征表，经用户确认后在 SolidWorks 中自动建模，并和标准答案对比校验。用于"按图建模""工程图转三维""读图纸建 SolidWorks 零件""CATICS 建模题"这类请求。支持回转类和棱柱类单个零件，包括凸台、筋板、肋、带圆弧和相切的外形、沉孔、螺纹孔、斜面上的特征。
---

# drawing2sw：工程图 → SolidWorks 零件

## 核心原则

1. **你只负责读图和填表，不直接写 SolidWorks 代码。**读图结果写成特征表 JSON，建模由 `scripts/` 里的确定性代码完成。同一张表永远得到同一个零件。
2. **只写图上标的东西，几何让脚本算。**图上写"R5""与 R14 相切""交点""4×Φ7 沉孔 Φ15"，表里就照这样写。切点、圆心、交点不要自己算（reading-rules R18）。
3. **不猜尺寸。**图上找不到的尺寸写进 `open_questions`，不要编一个看起来合理的数。
4. **超出能力就停。**遇到 schema 里没有的特征（钣金、曲面、螺旋、装配体），明确告诉用户"当前版本不支持 X"，不要用近似特征偷偷替代。
5. **图纸用什么单位，特征表就用什么单位。**英寸图填英寸，不要自己换算。单位必须有依据，找不到就问用户。
6. **每个特征都带置信度和依据。**`meta.evidence` 写清楚依据哪个视图的哪个尺寸。confidence < 0.9 的必须在确认环节展示给用户。
7. **不覆盖用户文件。**脚本保存时自动换文件名。
8. **能对答案就一定对。**题目给了体积、面积、距离，或者用户给了答案模型，建模前后都要对。体积对了还要看表面积。

## 怎么运行命令

SolidWorks 只在用户的 Windows 电脑上。先判断自己属于哪种：

- **能直接在用户 Windows 上执行命令**：自己跑，看结果、看报错、自己改，再跑。只把关键结论告诉用户。
- **不能**（在云端或沙盒里）：你改文件、算东西；**用户在 PowerShell 里跑命令，把输出贴回来**。

给用户命令时：

1. 每条命令单独一个代码块，前面写编号和一句话说明。
2. 第 1 条永远是 `cd` 到 skill 文件夹（PowerShell 的 `cd` 可以直接换盘符）。
3. Python 一律写 `.venv\Scripts\python.exe`，不写 `python`。
4. 路径里有空格或中文的，整个路径加英文双引号。
5. 说清楚"等它跑完再输下一条""把输出整段贴给我""哪条报错就停在那条"。第一次连 SolidWorks 可能要 1~2 分钟。
6. 一次只给当前需要的几条。

> **第 1 条：进入 skill 文件夹**
> ```
> cd D:\你的路径\drawing2sw
> ```
> **第 2 条：在 SolidWorks 里建模（要等一会）**
> ```
> .venv\Scripts\python.exe scripts\sw_build.py work\part.json -o D:/out/part.SLDPRT
> ```

下文的 `python` 都指 `.venv\Scripts\python.exe`（其他系统是 `.venv/bin/python`），不要用系统自带的 python。

## 流程

按顺序执行，每一步完成再进入下一步。

### 第 0 步：环境检查（每次会话开始时做一次）

1. 没有 `.venv` 说明还没安装。请用户在 skill 文件夹里运行 `powershell -ExecutionPolicy Bypass -File install.ps1`。不要自己去装系统级的 Python 或改系统设置。
2. 运行 `python scripts/check_env.py`，要用 SolidWorks 时加 `--sw`。
3. `ok` 为 false 时，把 `problems` 原样告诉用户，按 `references/setup.md` 排查。没解决不要继续建模。

### 第 1 步：预处理

`python scripts/preprocess_drawing.py <图纸文件> -o work/extract.json`。支持 .dwg .dxf .pdf 和图片。同一个零件有 DWG 就用 DWG，最准。

- DWG / DXF：自动转 DXF，提取尺寸实体（以 `displayed_text` 为准）、精确的圆和圆弧、图层、块里的标题栏文字和表格，并渲染一张图。**尺寸和孔位以提取结果为准**。
- 矢量 PDF：提取所有文字、尺寸值和线段。**尺寸数值以提取结果为准**，比看图准。
- 扫描图、截图：你直接看图读尺寸，所有特征置信度上限 0.85。脚本会自动把图纸切成几块：**先看 `work/views/overview.png`**（每块画了编号框），认出每个编号是哪个视图、标题栏、技术要求，再逐个看 `view_XX.png` 放大图读尺寸。不要自己写裁图脚本。切得不合适就用 `python scripts/split_views.py <图纸> -o work/views --gap 20`（加大 gap 合并、减小 gap 拆开）。还看不清的数字，请用户给更清楚的图，不要硬读。
- `setup_hints` 是单位、标准、投影法、比例的线索和原文，第 2 步用。

### 第 2 步：图纸基础设定（必做，先于读任何尺寸）

读 `references/units-standards.md` 和 `references/drawing-types.md`，定下这些并告诉用户：

- **单位**：mm / inch / cm / m，附依据（reading-rules R1）。`setup_hints.conflict` 不为空时必须问用户
- 标准：GB / ISO / ASME / ANSI / DIN / JIS；语言：中文 / 英文
- 投影法：first_angle / third_angle，以投影符号为准
- 比例、小数点写法、有没有双单位、一般公差、未注倒角圆角
- 文件格式：vector_pdf / dxf / raster
- 零件类型：revolved / prismatic / 不支持
- 视图组成：有哪些视图，剖视图的剖切线在哪（reading-rules R12），有没有局部放大

结果写进特征表的 `part.drawing_setup`。零件类型是"不支持"时，在这里停下。

### 第 3 步：读图，填特征表

先读：

- `references/reading-rules.md`：读图和填表规则，**从头扫一遍**
- `references/coordinates.md`：坐标和基准面约定
- `references/feature-table.md`：每个字段怎么填，含示例和 v0.4 写法
- 按零件类型读 `references/reading-revolved.md` 或 `references/reading-prismatic.md`

然后输出 `work/part.json`，必须符合 `schema/feature_table.schema.json`。

**读图顺序**：先在每个视图里认出每一块结构（底板、圆筒、肋、凸台、孔），再定坐标原点和三个方向，最后逐个读尺寸。每块结构至少在两个视图里找到它（reading-rules R8 R9）。

**填表顺序**：先基体（base_extrude 或 base_revolve），再加料（extrude：凸台、筋板、肋、耳板），再"切除 → 孔 → 倒角圆角"。带圆弧的外形用 `path` 或 `tangent_loop`，斜板上的特征用对象形式的 `plane`（coordinates.md "斜面"）。

辅助工具（都不用装额外的东西）：

- **几何计算**：`python scripts/geom2d.py intersect | tangent-circle | tangent-line | arc ...`，特征表写法覆盖不到时用，会列出全部解（feature-table.md 末尾有例子）。
- **拿不准某个符号、画法**：`python scripts/search_refs.py "关键词"`，在 references 里按关键词搜。
- **图纸只写了标准号或规格**（"键 GB/T 1096 16×10"、"4×M8 沉孔"、"M10 螺纹孔"）：`python scripts/standards.py key 56` / `tap M10` / `clearance M8` / `counterbore M8` / `countersink M8`。**图上标了的一律以图纸为准**，查表只补没写的数，evidence 写"按 GB/T xxxx 查表"，置信度不超过 0.9。

### 第 4 步：自动校验

`python scripts/validate_feature_table.py work/part.json`

- ERROR：按提示改表再跑，最多 3 轮，还不过就交给用户。"展开失败"说明 fillet / intersect / tangent_loop 算不出来，多半是读错了尺寸或写错了 near。
- 只有 WARNING：带到第 5 步给用户看。

### 第 5 步：用户确认

给用户看一张简短的表：

- **单位、标准、投影法**（每次都要给，单位错了整个零件就错了）
- 零件由哪几块结构组成，主要尺寸
- 所有 confidence < 0.9 的特征、`open_questions`、第 4 步的 WARNING
- 方位判断：孔、键槽、肋在前面还是后面，哪边是左（reading-rules R8）

用户确认或修改后再继续。用户说"不用确认"时可以跳过，但最后报告里仍要列出这些项。

### 第 6 步：预览（不需要 SolidWorks）

`python scripts/preview_cadquery.py work/part.json -o work/preview.step`

输出体积和包围盒。题目给了体积、面积、距离的，在这里先全部对上（reading-rules R23）。再用 `python scripts/render_preview.py work/preview.step -o work/preview.png` 渲染四个方向，和图纸的视图、轴测图对照外形：有没有漏掉一块，肋和墙在哪，孔在哪一面。

### 第 7 步：SolidWorks 建模

`python scripts/sw_build.py work/part.json -o <输出路径>.SLDPRT --report work/sw_report.json`

脚本先跑一遍预览，然后在 SolidWorks 里逐个特征建模，**每建一步就和预览比一次体积和位置**，第一个对不上的特征立刻停下并报告。遇到不支持的特征返回 `capability_blocked`，这时停下告诉用户。出错看下面"建模报错怎么办"。

### 第 8 步：校验并报告

有标准答案模型（.SLDPRT / .STEP）时，先量答案：`python scripts/answer_props.py <答案模型>`，在答案旁边写出 `answer_report.json`。只读打开，不改原文件。

然后对答案：

- 有答案模型：`python scripts/verify_model.py work/part.json --report work/sw_report.json --against <answer_report.json>`
- 只有题目给的体积：写进 `part.expected.volume_mm3`，`python scripts/verify_model.py work/part.json --report work/sw_report.json`
- 没有 SolidWorks：把 `--report` 换成预览报告

通过标准：体积、表面积、包围盒误差都在 1% 以内。面数只做提示。报告给用户：

- 通过 / 不通过，以及差在哪里；没有答案模型时明确说"只能请你对照图纸检查"
- 第 5 步里被跳过或按你的理解建的项
- **体积对了不等于对**（reading-rules R25），请用户在 SolidWorks 里对照图纸看一眼

### 第 9 步：记录经验

这次读错、并找到原因的，告诉用户，并说清楚"从图上本来该怎么看出来"。用户同意的话，按同样格式追加到 `references/reading-rules.md` 对应的分类末尾。只写规则，不写这张图的具体数字。

## 建模报错怎么办

| 报错 | 先查什么 |
|---|---|
| 逐步自检"对不上"，提示方向可能反了 | 这个特征的 `direction`、`offset` 正负、基准面法向（coordinates.md）。包围盒往反方向长了，就是方向反了 |
| 逐步自检"对不上"，但这个特征很小（钻尖、小倒角） | 看报告里预览的体积增量：切除后体积变大，是预览算错了，不是你的表错了。告诉用户，不要改表去凑 |
| 圆角报告的 api 名带"曲率连续-近似" | 圆角做出来了，但截面不是圆弧。查相邻轮廓是不是手算的切点，改成 fillet / intersect 写法再建（reading-rules R18） |
| 选边"只匹配到 x/y 条边" | `edges.points` 的点要落在边的内部（不是端点），误差 0.01 mm 以内；先在预览里核对这条边在哪 |
| 切除失败、拉伸失败 | 轮廓是否闭合、是否自交（validate 会查）；切除体是否根本没碰到实体 |
| "找不到成员"、COM 报错 | 这是脚本问题，不是读图问题。把报告里的 `reason` 和 `trace` 原样告诉用户 |

## 文件索引

| 文件 | 何时读 |
|---|---|
| `references/reading-rules.md` | 第 3 步之前从头扫一遍，必读 |
| `references/units-standards.md` | 第 2 步，必读：单位、标准、中英文标注对照 |
| `references/drawing-types.md` | 第 2 步 |
| `references/coordinates.md` | 第 3 步，必读 |
| `references/feature-table.md` | 第 3 步，必读 |
| `references/reading-revolved.md` / `reading-prismatic.md` | 按零件类型 |
| `references/projection.md` | 投影法不确定，或视图对应关系不清楚时 |
| `references/setup.md` | 环境检查失败时 |
| `schema/feature_table.schema.json` | 特征表格式的权威定义 |
| `examples/` | 三张完整的特征表示例（棱柱件、回转件、英寸件） |
| `scripts/geom2d.py` | 交点、相切圆、公切线、按半径定圆心 |
| `scripts/render_preview.py` | 预览渲染成四个方向的图，和图纸对照 |
| `scripts/split_views.py` | 扫描图、截图切成视图放大图（预处理会自动调用） |
| `scripts/standards.py` | 键槽、螺纹底孔、通孔、沉孔查表 |
| `scripts/search_refs.py` | 按关键词搜 references |
