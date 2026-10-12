# 开发说明：改脚本、加特征

给要改 drawing2sw 代码的人和 AI 看。只用 skill 读图建模的话不用读。
项目进度、待办、历史记录在根目录 `PROGRESS.md`。

## 目录：哪些是 skill，哪些是开发用的

| 位置 | 属于 | 内容 |
|---|---|---|
| `SKILL.md`、`references/`、`schema/`、`standards/`、`examples/`、`scripts/` | skill 本体 | 用户的 AI 读的说明、特征表格式、运行时脚本 |
| `install.ps1`、`requirements.txt`、`README.md` | skill 本体 | 安装和介绍 |
| `dev/` | 开发 | 本文件、出题工具、可选的向量检索、模型对比记录 |
| `tests/` | 开发 | 测试图纸和答案、覆盖矩阵、几何自检 |
| `PROGRESS.md`、`CLAUDE.md` | 开发 | 交接文档、本地 AI 的工作规则 |

发布 skill 时只带"skill 本体"那几项。`tests/drawings/` 里有版权不明的图纸和答案模型，不能公开。

### scripts/（运行时，skill 用）

| 脚本 | 作用 |
|---|---|
| `check_env.py` | 环境检查（Python 包、SolidWorks 连接、模板） |
| `preprocess_drawing.py` | 读 DWG / DXF / PDF / 图片，提取文字、尺寸、圆、单位线索、标题栏 |
| `dwg2dxf.py` | DWG 转 DXF（ODA → 本机 AutoCAD / 中望 / 浩辰 → SolidWorks），也能 DXF 转 DWG |
| `ftable.py` | 特征表公共层：读表、`resolve()` 展开 v0.4 写法、`to_mm()` 单位换算、坐标系、孔位、齿轮几何 |
| `geom2d.py` | 二维几何（交点、相切、拐角倒圆、切线连接）；也是命令行计算器 |
| `validate_feature_table.py` | schema + 工程规则检查 |
| `preview_cadquery.py` | CadQuery 预览，出 STEP、体积，`trace` 记录每一步体积和包围盒 |
| `sw_build.py` | SolidWorks 建模，逐步和预览比对 |
| `answer_props.py` | 量答案模型（SLDPRT / STEP），`--step` 导出 STEP 做诊断 |
| `verify_model.py` | 对答案：体积、表面积、包围盒、面数 |
| `standards.py` + `standards/gb.json` | 国标查表（键槽、螺纹底孔、通孔、沉孔） |
| `search_refs.py` | 零依赖关键词检索 references 和 SKILL.md |
| `text_boxes.py` | 图片找文字框并编号，`emit` 按"编号 → 原文"生成视觉观察；`check_boxes` 给 validate 用，查手写框里有没有字 |
| `split_views.py` | 图片切视图：去图框长线和彩色水印，膨胀连通，出总览图和每块放大图（只用 numpy / scipy / PIL） |
| `render_preview.py` | 预览 STEP 渲染成四个方向的图 |

### dev/（开发用）

| 位置 | 作用 |
|---|---|
| `dev/tools/make_test_drawing.py` | 用特征表合成测试图（HLR 三视图 + 尺寸 + 标题栏，出 DXF / PDF / PNG / 扫描件 / DWG），`--batch` 批量 |
| `dev/tools/sw_make_exam.py` | 用 SolidWorks 把零件出成考卷。**不可靠**：模型尺寸时有时无、孔位尺寸插不进，见下文"出题" |
| `dev/rag/` | 可选的向量检索（fastembed + Chroma），装在 `dev\rag\.venv`，默认不用 |
| `dev/model-notes.md` | 不同 AI 模型读图表现的记录表（还没测） |
| `tests/test_geom2d.py` | geom2d / resolve 的解析值自检 |

## 原则

- **AI 不直接写 SolidWorks 代码。**新能力一律做成特征表里的新类型或新字段，再由脚本确定性地实现。
- **能展开的先展开。**新写法如果能用已有特征表达（拐角倒圆 → path 圆弧，沉孔 → 两个 hole，钻尖 → revolve 切除），就在 `ftable.resolve()` 里展开，后端不用改，已经实测过的 SolidWorks 代码不动。几何计算放 `geom2d.py`，`tests/test_geom2d.py` 加解析值核对。
- **两个后端同时改。**每个新特征必须在 `preview_cadquery.py` 和 `sw_build.py` 里都实现，用预览给 SolidWorks 当逐步参照。
- **按题目需要加，不预先做。**一道测试题做不出来，才加它缺的那一样。
- **每道测试题的产出只算两样**：skill 多一个现成写法（AI 少算一样东西），或者 `references/reading-rules.md` 多一条规则（AI 少犯一种错）。只是"这张图建对了"不算产出。
- 旧的特征表必须照样能用。

## 改动顺序

1. `schema/feature_table.schema.json`：加类型或字段，写清 description。只加不改；大改时升 `schema_version`，旧版本号保留在 enum 里。
2. `scripts/ftable.py`：新字段里有长度的，`to_mm` 必须换算。能展开的写进 `resolve()`。
3. `scripts/preview_cadquery.py`：CadQuery 实现，先在这里把体积对上。
4. `scripts/validate_feature_table.py`：能静态查出的错误在这里查。
5. `scripts/sw_build.py`：SolidWorks 实现，遵守下面的 COM 规则。
6. 文档：`references/feature-table.md`（字段 + 示例）、`coordinates.md`（涉及坐标时）、`SKILL.md`（流程变了时）、`tests/COVERAGE.md`。

## 回归测试（改完建模代码必跑）

```
.venv\Scripts\python.exe tests\test_geom2d.py
.venv\Scripts\python.exe scripts\validate_feature_table.py <每张表>
```

CadQuery 预览体积要和以前一样：

| 表 | 预览体积 mm³ |
|---|---|
| examples/bracket_inch.json | 53194.869 |
| examples/bracket_prismatic.json | 51240.708 |
| examples/flange_revolved.json | 158682.892 |
| tests/drawings/001_圆柱齿轮/part.json | 1140388.609 |
| tests/drawings/002_CATICS_3D08-L01/part.json | 181656.005 |
| tests/drawings/003_CATICS_3D12-H06/part.json | 402045.100 |
| tests/drawings/003_CATICS_3D12-H06/part_v04.json | 402045.156 |
| tests/drawings/006_架体/part.json | 176734.349 |

改了 `sw_build.py` 的，再在 SolidWorks 上跑一遍 003 part_v04（答案 402042.42）和 006（21 步自检）。

## 实现层的坑（编号是历史编号，代码注释里引用的就是这些）

### 一、SolidWorks COM

| # | 规则 | 原因 |
|---|---|---|
| 1 | 长度一律 mm → m（`* MM`）再传 API；文档单位只影响显示 | API 内部用米，模板单位可能是米，界面会显示 0.05 |
| 2 | 基准面按特征树顺序取前三个，不按名字 | 中文版叫"前视基准面" |
| 3 | 不用屏幕操作和快捷键，只走 API | 中文输入法会吃掉快捷键 |
| 5 8 23 | 所有无参方法和属性一律 `call(obj, "名字")` | pywin32 后期绑定把无参方法暴露成属性，再加括号就"'str' object is not callable"或"找不到成员"。RevisionNumber、CreateSelectData、GetEdges、GetMathUtility、ActiveSketch、ArrayData 都是 |
| 6 | 零件模板依次试：用户设置 → GetDocumentTemplate → ProgramData 下搜 `*.prtdot` | 中文版模板叫 gb_part.prtdot，默认设置可能为空 |
| 7 9 | 选边：遍历实体全部边，用 `GetClosestPointOn` 求目标点到边的距离（容差 0.01 mm），再 `Select4`；目标点取边的内部点 | `SelectByID2` 按坐标拾取会被前面的面挡住；闭合圆边的"参数中点"取决于起点，CadQuery 和 SolidWorks 不同 |
| 16 | 重复特征"画一个 + 阵列"；曲线用样条和真圆弧，不用折线 | 2400 条线的草图能建出来，但齿面全是条纹、模型没法改 |
| 17 | `InsertAxis2` 在 ModelDoc2 上，不在 FeatureManager 上 | 方法分散在 ModelDoc2 / FeatureManager / SketchManager / ModelDocExtension，调用前查清楚 |
| 24 | 斜面草图坐标：读 `ModelToSketchTransform` 的 `ArrayData` 自己算，不用 MathUtility；包围盒用实体 `GetBodyBox` | MathUtility 在 pywin32 下调不动；GetPartBox 会把辅助草图点算进去 |
| 30 | 拉伸切除默认方向和草图法向相反，`cut()` 里 positive 要反向 | 拉伸凸台沿法向，切除往"面里面"切 |
| 31 | 圆角先试 7 种普通设置（每次失败后重新选边），最后退到曲率连续（选项 +256，api 名带"近似"） | 普通圆角在轮廓接缝不严格相切时失败。真正的解法是轮廓用精确切点（reading-rules R18），兜底只是保证能建完 |
| — | 圆弧用 `Create3PointArc`（起点、终点、弧上一点） | 不受顺逆时针和草图坐标翻转影响 |
| — | 斜面：3D 草图三点 + 重合约束建基准面；失败退回贴实体平面建 | 通用 |
| — | 旋转切除用 `FeatureRevolve2` 的 IsCut=True；轴用 `CreateCenterLine` | 一个函数管加料和切除 |
| — | 草图期间 `AddToDB = True`，关掉"创建时输入尺寸" | 避免自动吸附和弹窗 |
| — | 不支持就抛 `CapabilityBlocked`，不做近似替代；失败报告带 `trace` | 宁可停下，不能偷偷建错 |
| — | 拷贝出来的同一个零件（answer.SLDPRT 和它的副本）不要同时在 SolidWorks 里打开 | 内部文档 ID 相同，SolidWorks 会弄混引用 |
| 34 | 零厚度几何：新实体和已有实体只沿一条边相接（例如桥底和旁边槽底同高、桥下是空腔），`FeatureExtrusion2` 合并返回 None；封闭在实体内部的空腔用切除也会失败 | SolidWorks 不允许非流形边，OCC 允许。先改写成等价的"先切开口坑、再加回实体"；仍是线接触时特征表写 `"merge": false`，几何不变，零件变成多实体，报告里说明（cadsy part_0023） |
| 41 | 线性阵列：方向轴用两个默认基准面的交线（X = 前视∩上视，Y = 前视∩右视，Z = 上视∩右视）；`FeatureLinearPattern5` 选择 mark：特征 4、方向 1 是 1、方向 2 是 2；没有第二方向时 Num2 = 1。先按不翻转建，和预览这一步对不上就删掉换 FlipDir 再建 | 交线轴的正向由 SolidWorks 决定，事先不知道。合成测试里 -X/-Z 网格需要两个都翻转，自动找到 |
| 41b | 圆周阵列 `circular_pattern`：`FeatureCircularPattern5(count, 相邻角弧度, flip, "NULL", False, EqualSpacing=False, ...)`，特征 mark 4、轴 mark 1；不是整圈时和线性阵列一样按预览试方向。实测：绕 -Y 不翻转、绕 +Y 要翻转 | 齿轮用的是 EqualSpacing=True + 总角 2π，这里改成给相邻角，部分圆周也能写 |
| 44 | 包围盒用 `IBody2.GetExtremePoint` 沿 ±X/±Y/±Z 取精确极值点，`GetBodyBox` 只作兜底 | `GetBodyBox` 对曲面是松的：端面开半圆口的 Ø4 孔多出 0.132 mm，超过逐步自检 0.05 的容差误报，豆包因此关掉了自检（Mini Crank Case） |
| 45 | 逐步自检除了体积、包围盒，还比质心（预览 trace 的 center_mm，SolidWorks CreateMassProperty.CenterOfMass），容差 max(0.01 mm, 2e-4 × 包围盒对角线) | 阵列复制件落在零件内部（凹槽、内部孔）时转反了，体积和包围盒都不变，以前会误判方向正确。另：阵列复制件落在悬空处（例如落在前一个阵列切出的槽上），SolidWorks 会静默丢掉这个复制件，预览却算进去，体积对不上会报出来 |
| 46 | 保存：直接 `SaveAs3` 覆盖同名文件，成功后才删 `name_1` 这类旧编号；保存失败状态 `save_failed`、退出码 2，旧文件和模型窗口都保留 | 以前先删旧文件再保存，保存失败时状态仍是 ok、退出码 0，旧零件已经没了（Codex 审查发现）。用只读的目标文件实测过 |
| 47 | 关旧窗口：存过盘、又有未保存改动的文档一律不关（`kept_open_unsaved`）；目标文件就是它时直接停（`blocked_target_open`），不建模 | 以前带 drawing2sw 标记的文档不管有没有改动都关掉，用户在模型上手动改了没存就会丢（Codex 审查发现）。用 SetSaveFlag 模拟实测过 |
| 48 | 建模前强制关卡：完整校验（含 v0.5 证据、手写框里有字）→ 预览。校验错误 `blocked_validation`、预览算不出 `blocked_preview_failed`、孔口被盖住 `blocked_covered_holes`，都不启动 SolidWorks，退出码 3。只有没装 CadQuery 时可以不自检地继续，报告写明 | 以前 sw_build 只做展开和换单位，AI 跳过 validate 也能直接建；预览失败也照样建（Codex 审查发现）。tests/test_sw_safety.py |
| 49 | 近似默认禁止：圆角只剩曲率连续、样条只剩折线、齿槽阵列只剩折线时抛 `ApproxNeeded`，状态 `needs_approval_approx`、不保存；`--allow-approx --reason` 才用，报告 `approximations` 列出 | J 定的原则：用户默认拿到的要么是精确模型，要么是明确的失败；不确定的交还用户，用户说不清交给用户的 AI 判断。open_questions 同理（blocking / confirm 要 resolution） |
| 50 | 抽壳：CadQuery 2.8 用 `Solid.hollow(faces, -t, kind="intersection")`（`Shape.shell()` 是取壳体的访问器，不是抽壳）；`kind="arc"` 会给向外偏移的锐边加圆角，和 SolidWorks 不一致（向外抽壳实测差 390 mm³），旋转体上还报 `no parameter on edge` | intersection 下向外抽壳 84154.689 = 手算，旋转杯能算 |
| 51 | SolidWorks 抽壳：`ModelDoc2.InsertFeatureShell(厚度米, outward)`，没有返回值；先按点选要去掉的面（`Face2.GetClosestPointOn`，和选边一样），建完看特征树最后一个是不是 `Shell` | 圆角半径 < 壁厚时 SolidWorks 也能成功，内壁变尖角，所以校验只提示不拦 |
| 42 | 镜像：`InsertMirrorFeature2(False, False, False, False, 0)`，要镜像的特征 mark 1，镜像面 mark 2 | 和阵列的 mark 约定不一样 |
| 43 | 零厚度的点：盲孔底正好落在实体底面所在平面、孔壁又和下面凸起的侧面相切（孔边 = 凸起边），切除后只剩一个点相连，`FeatureCut4` 返回 None。OCC 能建，答案 STEP 也是这样 | 和 #34 同类，SolidWorks 不允许非流形。不改尺寸迎合程序，报告给用户（cadsy part_0001：浅 0.01 就能建）|
| — | `sw_build` 建完隐藏自己创建的偏移基准面 | 否则打开零件时一层层基准面挡住模型 |
| 36 | 保存用 `SaveAs3(path, 0, 1)`（静默保存），不要用选项 2（另存副本） | 选项 2 只把副本写到磁盘，窗口里的文档一直是没保存的"零件N"，每建一次多一个关不掉的窗口 |
| — | 新建的零件写自定义属性 `drawing2sw`，建模前 `close_previous` 关掉带这个属性的文档和 out 里的文档；成功才保存并覆盖同名旧版本，失败直接关闭不存 | 用户只需要一个窗口、一个最新文件；旧的错误零件要一个个手动删很麻烦 |

### 二、CadQuery / OCC

| # | 规则 | 原因 |
|---|---|---|
| 32 | `resolve()` 把同圆同向的相邻圆弧、共线直线合成一段 | 多出的顶点让后面贴着这个面的布尔运算静默出错（加料体积为 0） |
| 33 | 展开出的切除体不能和已有曲面重合，只允许贴平面；钻尖只画锥体三角形 | 曲面完全重合时布尔运算不稳定，切除后体积甚至变大 |
| — | 逐步自检报某个很小的特征"对不上"，先看预览的体积增量是否合理 | 切除后体积变大，一定是预览错了，不是 SolidWorks 错了 |
| 37 | 斜面上的孔：孔的草图面必须和零件表面完全共面，两者用同一组数算（例如斜面高度写 17−11·tan30°，不要写取整的 10.65）。差 0.01° 孔口就会被零厚度的皮盖住 | 体积几乎不变，逐步自检也过；`preview_cadquery.report` 的 covered_hole_mouths 会报出来（Mini Crank Case 实测） |
| 38 | 按点选边：两个点落在同一条边上算匹配，只选一次 | SolidWorks 的整圆是一条边，CadQuery 也是；以前 sw_build 跳过已选的边，第二个点就报"只匹配到 1/2" |
| 39 | 按点选边：点不能落在圆柱接缝线的端点上（CadQuery 圆柱的接缝在 +x 方向，(x0+r, y, 0) 同时在圆边和接缝线上）。preview 现在会报"同时落在两条边上" | 以前静默选中接缝线，倒角圆角倒在接缝上等于没倒（Pivot Arm 四处倒角只出来一处） |
| 40 | 精确隐藏线 HLRBRep_Algo 对某些从 STEP 读回来的实体会让进程崩溃（access violation，捕获不到）；同一个模型在内存里直接建出来就没事 | dev/tools/render_views.py 传特征表走精确算法，传 STEP 走 HLRBRep_PolyAlgo（Mini Crank Case 实测） |
| 35 | 和答案 STEP 比对称差时，布尔要带模糊容差（benchmark.BOOL_TOL），并检查合并体积不小于任一实体 | 两个独立建出来的实体面几乎重合时，不带容差的布尔静默返回空，读对的零件被判成完全不重合 |

### 三、出题（dev/tools/sw_make_exam.py，没做通）

- `InsertModelAnnotations3` 的类型要一类一类分开插，合成一个掩码会一个都插不进。
- 只有"标记为工程图"的尺寸能插进来（类型 32768）。孔向导的位置草图尺寸即使标记了也插不进。
- 逐个设视图 `Position` 会把视图移出图纸；建完视图再改比例，视图线条会丢；关掉"三视图自动缩放"（全局设置 86）只出一个视图。
- 同样代码多次运行，插入的尺寸数 27 → 22 → 0，原因没查清。
- 结论：自动出"尺寸齐全"的图不可靠，测试用真实图纸。要继续做的话，考虑 DimXpert 自动标注或孔表（InsertHoleTable2）。

## 改动记录格式

每次改动写进 `PROGRESS.md` 的变更日志：

```
### 日期 时间 标题
- 改了：哪个文件，改了什么
- 新增：新文件、新特征、新规则编号
- 没改：明确列出没动的部分，方便回滚和排查
- 测试：在哪测的（CadQuery / SolidWorks / 只做语法检查），结果数字
```

没实测的一定写"没实测"，不要写"完成"。
