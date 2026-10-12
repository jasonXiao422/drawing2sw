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
| — | `sw_build` 建完隐藏自己创建的偏移基准面 | 否则打开零件时一层层基准面挡住模型 |
| 36 | 保存用 `SaveAs3(path, 0, 1)`（静默保存），不要用选项 2（另存副本） | 选项 2 只把副本写到磁盘，窗口里的文档一直是没保存的"零件N"，每建一次多一个关不掉的窗口 |
| — | 新建的零件写自定义属性 `drawing2sw`，建模前 `close_previous` 关掉带这个属性的文档和 out 里的文档；成功才保存并覆盖同名旧版本，失败直接关闭不存 | 用户只需要一个窗口、一个最新文件；旧的错误零件要一个个手动删很麻烦 |

### 二、CadQuery / OCC

| # | 规则 | 原因 |
|---|---|---|
| 32 | `resolve()` 把同圆同向的相邻圆弧、共线直线合成一段 | 多出的顶点让后面贴着这个面的布尔运算静默出错（加料体积为 0） |
| 33 | 展开出的切除体不能和已有曲面重合，只允许贴平面；钻尖只画锥体三角形 | 曲面完全重合时布尔运算不稳定，切除后体积甚至变大 |
| — | 逐步自检报某个很小的特征"对不上"，先看预览的体积增量是否合理 | 切除后体积变大，一定是预览错了，不是 SolidWorks 错了 |
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
