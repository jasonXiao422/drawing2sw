# 特征表填写说明

正式定义在 `schema/feature_table.schema.json`。这里讲怎么填，以及常见情况的写法。完整示例见 `examples/`。

## 整体结构

```json
{
  "schema_version": "0.2",
  "part": { "name": "...", "part_type": "revolved", "units": "mm",
            "drawing_setup": { "length_unit": "mm", "unit_evidence": "标题栏：单位 mm",
                               "standard": "GB", "language": "zh", "confidence": 0.98 },
            "projection": "first_angle",
            "source": { "file": "...", "format": "vector_pdf", "standard": "GB" },
            "expected": { "volume_mm3": 12345.6 } },
  "features": [ ... ],
  "open_questions": [ {"question": "...", "level": "confirm", "assumed": "...", "affects": ["..."]} ]
}
```

`expected` 只在有标准答案时填（例如有原 SolidWorks 模型）。不要自己估算填进去。

**单位**：`units` 必须等于 `drawing_setup.length_unit`。所有长度（profile、depth、offset、diameter、positions、pcd、size）都按这个单位填，和图纸上的数字一模一样。只有 `expected` 永远用 mm。`drawing_setup` 怎么填见 `units-standards.md`。

## 基本特征类型

| type | 用途 | 关键字段 |
|---|---|---|
| base_extrude | 棱柱体基体，必须是第一个特征 | plane, profile, depth, midplane |
| base_revolve | 回转体基体，必须是第一个特征 | half_profile |
| cut_extrude | 切槽、开口、台阶切除 | plane, offset, profile, depth, direction |
| hole | 光孔、螺纹底孔 | plane, offset, diameter, positions 或 bolt_circle, depth, thread |
| edge_treatment | 倒角、圆角 | kind, size, edges |
| linear_pattern | 一排或一格相同的结构（脚、槽、筋、孔） | features, direction, count, spacing（可选 direction2, count2, spacing2） |
| circular_pattern | 绕轴一圈的相同结构（齿、缺口、轮辐） | features, axis, count（可选 angle） |
| mirror | 关于基准面对称的结构 | features, plane, offset |
| shell | 盒体、壳体、杯子：挖空成等厚的壳 | thickness, open_faces（要去掉的面），outward |
| （拉伸类的参数）draft | 压铸 / 注塑件的拔模 | draft（单侧角度），draft_outward |

只能有一个基体特征。没有的特征类型不要自创，按 SKILL.md 开头的说明报告能力缺口。

## profile 三种形状

```json
{ "shape": "rect", "width": 80, "height": 40, "center": [0, 0] }
{ "shape": "circle", "diameter": 20, "center": [10, 0] }
{ "shape": "polygon", "points": [[0,0],[60,0],[60,20],[20,40],[0,40]] }
```

polygon 按顺序首尾相连，不要重复首点。

## depth 和 direction

- `depth: "through_all"`：贯穿。孔和切除默认 `direction: "both"`，两侧都打穿，最不容易出错。
- 盲孔、台阶：`depth` 写数值，`direction` 写 `positive`（沿法向）或 `negative`。`offset` 写草图所在高度。

## 加料拉伸、直线圆弧轮廓、斜面、旋转

### extrude：加料拉伸

基体之后的凸台、筋板、耳板都用它。可以有多个。

```json
{"id": "boss", "type": "extrude", "plane": "top", "offset": 12,
 "profile": {"shape": "circle", "diameter": 50}, "depth": 26, "direction": "positive", "meta": {...}}
```

direction：positive 沿法向，negative 反向，midplane 两侧对称（depth 是总厚，筋板常用）。

`"merge": false`：只在零厚度几何时用。新加的实体和已有实体只沿一条边相接（例如桥底和旁边槽底同高、桥下面是空腔），SolidWorks 不允许合并。写了以后 SolidWorks 里是单独的实体，几何不变，报告里会列出来，交付时要告诉用户。

### path：直线 + 圆弧轮廓

耳板、腰形槽、带 R 角的外形用它。圆弧给圆心和方向，脚本用三点画弧。

```json
"profile": {"shape": "path", "start": [30, 0], "segments": [
  {"to": [36, 0]},
  {"to": [39.4286, -31.6283], "center": [36, -16], "ccw": false},
  {"to": [30, -43.3496], "center": [42, -43.3496], "ccw": true},
  {"to": [30, 0]}]}
```

- 相切关系要自己算出切点（两圆相切：切点在圆心连线上）。validate 会检查圆弧两端半径相等、轮廓闭合。
- 加料的轮廓可以和已有实体重叠，会自动合并。

### 斜面

见 `coordinates.md` 的"斜面"一节。extrude、cut_extrude、hole 都能用。

### revolve：任意轴旋转（加料或切除）

孔口倒角、钻头锥尖、端部锥面倒角、环槽都用它。轴是草图平面里的一条线。

```json
{"id": "back_chamfer", "type": "revolve", "plane": "right", "axis": [[0, 0], [-1, 0]], "cut": true,
 "profile": {"shape": "polygon", "points": [[-60, 49], [-70, 39], [-75, 39], [-75, 75], [-60, 75]]}, "meta": {...}}
```

- right 基准面的 u = -Z，所以"沿 Z 的轴"写成 [[0,0],[-1,0]]，深度 Z 写成负的 u。
- 切除轮廓可以多画一点伸到空气里，避免和已有面重合。轮廓不能跨过轴线（validate 会查）。
- 钻头 120° 锥尖：锥高 = 孔半径 / tan60°。

### 按点选边

内部的边、只要一部分边时，edges 写成点：

```json
"edges": {"points": [[0, 45, 6], [16, 35.35, 6]]}
```

每个点必须正好落在边上（误差 0.01 mm 以内），取边的中间点，不要取端点。

### 切到曲面为止

extrude 只能切到平面。要切到圆柱面（例如槽底 R150），先切到曲面最深处，再用 extrude 把曲面外侧补回来。见 reading-rules.md R21。

## v0.4 新增：只写图上标的，切点圆心让脚本算

原则：**图上标的是"R5""与 R14 相切""交点""4×Φ7 沉孔 Φ12 深 6"，表里就照这样写**。不要自己算切点、圆心再填数。
自己算再四舍五入，切点不是严格相切，SolidWorks 圆角会在接缝处失败（reading-rules.md R18）。
脚本在读表时（`ftable.resolve`）展开成 v0.3 的写法，预览和 SolidWorks 用的是展开后的结果。
写完跑 validate，算不出来（不相交、半径太大）会报"展开失败"和是哪一段。

### 点写成交点

path 的 `start`、`to`、`center` 都可以写成两个对象的交点，有两个交点时取离 `near` 最近的：

```json
{"to": {"intersect": [{"circle": {"center": [0, 0], "r": 45}}, {"x": 16}], "near": [16, 42]}}
```

对象：`{"x": a}` 竖线、`{"y": b}` 横线、`{"line": [[u1, v1], [u2, v2]]}`、`{"line": {"through": [u, v], "angle": 60}}`、`{"circle": {"center": [u, v], "r": r}}`。

### 拐角倒圆：fillet

某段的终点是个尖角、图上标了 R，就在这一段写 `"fillet": R`。凸角、凹角、直线和圆弧之间都行。最后一段的 fillet 倒在起点。

```json
{"shape": "path", "start": [0, 0], "segments": [
  {"to": [100, 0], "fillet": 10}, {"to": [100, 60], "fillet": 10},
  {"to": [0, 60], "fillet": 10},  {"to": [0, 0],   "fillet": 10}]}
```

写的是倒圆之前的尖角点（两条边延长后的交点），不是切点。

### 圆弧只知道半径：radius

`{"to": [0, 20], "radius": 20, "ccw": true}`：脚本算圆心。默认取小于半圆的一段，要大的一段加 `"large": true`。

### 一圈圆用切线连：tangent_loop

耳板、连杆、腰形槽、凸轮这类"几个圆、圆之间用公切线连"的外形：

```json
{"shape": "tangent_loop", "circles": [
  {"center": [0, 15.5], "r": 5}, {"center": [0, 0], "r": 14},
  {"center": [0, -15.5], "r": 5}, {"center": [0, 0], "r": 14}]}
```

- 按逆时针排（排反了脚本自动倒过来）。同一个圆可以出现两次（上面是中间大圆的左右两侧）。
- `"r": 0` 是尖角点（过点作圆的切线）；`"convex": false` 是往里凹的圆弧。

### 沉孔、埋头孔、钻尖

```json
{"id": "ear_hole", "type": "hole", "plane": "top", "offset": 69, "diameter": 7,
 "positions": [[26, -40], [-26, -40]], "depth": 16, "direction": "negative",
 "cbore": {"diameter": 12, "depth": 6}, "tip_angle": 120, "meta": {...}}
```

- `cbore`：沉孔台阶；`csink`：埋头孔 `{"diameter": 20, "angle": 90}`；`tip_angle`：盲孔钻尖顶角（118 或 120），depth 只算圆柱部分。
- 必须写 `direction`（从哪个面钻进去），不能是 both。
- 展开后会多出 `ear_hole__cbore`、`ear_hole__tip1` 这类特征，逐步自检和报告里看到的是展开后的名字。

### 线性阵列 linear_pattern、圆周阵列 circular_pattern、镜像 mirror

先建一个，再复制。和 SolidWorks 里工程师的做法一样，模型的特征树也是"一个凸台 + 阵列"。

```json
{"id": "foot", "type": "extrude", "plane": "top", "direction": "negative", "depth": 3,
 "profile": {"shape": "rect", "width": 5, "height": 29, "center": [-27, 0]}, "meta": {...}},
{"id": "feet", "type": "linear_pattern", "features": ["foot"],
 "direction": "+X", "count": 5, "spacing": 12, "meta": {...}},
{"id": "hole_r", "type": "mirror", "features": ["hole_l"], "plane": "right", "meta": {...}}
```

- `features`：要复制的特征 id，必须写在阵列 / 镜像前面。只能是 extrude、cut_extrude、hole、revolve。带 cbore / csink / tip_angle 的孔，展开出的部分自动一起复制。
- `direction`：模型坐标轴 `+X -X +Y -Y +Z -Z`。原特征是第一个，其余往这个方向排。`count` 含原特征，`spacing` 是相邻中心距。
- 网格：再写 `direction2`、`count2`、`spacing2`，第二方向必须和第一方向垂直。
- `mirror` 的 `plane`：front（法向 +Z）、top（+Y）、right（+X），`offset` 沿法向偏移，目前只支持 ≥ 0。
- `circular_pattern`：`{"features": ["tooth_cut"], "axis": "+Z", "count": 6}`，绕过原点的模型坐标轴转，正角度按右手定则。`angle` 是相邻两个的夹角，不写就是整圈均布（360 / count）。轴要过原点，所以回转结构的中心放在原点。只有孔的分布圆继续用 hole 的 `bolt_circle`。
- 倒角圆角写在阵列 / 镜像后面，选边点覆盖所有复制件。
- 整件对称的外形直接把基体画全，不要镜像基体。
- 一排孔也可以直接在 hole 的 `positions` 里列全，结果一样。图上写"5× 等距"、或者是凸台、槽这类非孔结构时用阵列更省事。
- 看着对称的两个孔，标注不同（一个 THRU、一个 ↧10）就分开写，不能镜像。

### 拔模 draft（压铸件、注塑件）

`base_extrude`、`extrude`、`cut_extrude` 都可以加：

```json
{"id": "body", "type": "base_extrude", "plane": "top", "profile": {...}, "depth": 57, "draft": 0.25}
{"id": "cavity", "type": "cut_extrude", "plane": "top", "offset": 57, "direction": "negative",
 "profile": {...}, "depth": 54, "draft": 0.25}
```

- `draft`：**单侧**拔模角（侧面和拉伸方向的夹角），度。默认向内收：离草图面越远轮廓越小；`"draft_outward": true` 向外放。
- 草图画在**尺寸标得全的那一端**，另一端的尺寸由拔模算出来，用来核对（另一端尺寸 = 这一端 ∓ 2 × 深度 × tan(拔模角)）。
- 只能用于单方向、深度是数值的拉伸 / 切除。
- 压铸件常见内外反向拔模：外形往开口方向收、内腔往开口方向放，壁厚从根部到开口变化。这种零件用"带拔模的拉伸 + 带拔模的切除"，**不能用抽壳**（抽壳只能做等厚壁）。
- 图上标的角度先用两端尺寸核对：有的图标的是两侧墙的夹角（例如标 0.50°，两端尺寸算出来单侧是 0.25°）。对不上就写进 open_questions。

### 抽壳 shell

```json
{"id": "shell", "type": "shell", "thickness": 2, "open_faces": {"points": [[45, 60, 0]]}, "meta": {...}}
```

- `thickness`：壁厚。`open_faces`：要去掉的面，每个面取一个点（模型坐标，面的内部点，不要取在边上）；不写就是完全封闭的空心件。
- 默认向内抽壳，外形不变；`"outward": true` 向外加厚，原来的外形变成内腔。向外时锐边保持尖角（和 SolidWorks 一致）。
- **外形的圆角写在抽壳之前**，内壁会自动带上"圆角 − 壁厚"的圆角。圆角半径小于壁厚时，内壁在那里变成尖角，校验会提示。
- 抽壳会把已有的孔也变成薄壁管（例如盒子中间的通孔）。孔不想要管壁，就把孔放到抽壳之后再切。
- 多厚度抽壳（个别面更厚）还不支持，遇到时报告能力缺口。

### 特征表写法覆盖不到的：命令行计算器

圆心未知的相切圆弧（例如"R12 同时和 R16 圆、侧边直线相切"）、要先看看有几个解的情况，用 `scripts/geom2d.py` 算，结果抄进表里（保留 6 位小数）：

```
python scripts/geom2d.py tangent-circle 12 "circle:36,-16,16" "x:30"
python scripts/geom2d.py intersect "circle:0,0,45" "x:16"
python scripts/geom2d.py tangent-line "circle:0,15.5,5" "circle:0,0,14"
python scripts/geom2d.py arc 0,45 16,42.0595 --r 45 --cw
```

会列出全部解，按图选一个。evidence 里写用的哪条命令。

## edges 选择器

| 值 | 含义 |
|---|---|
| all_outer | 所有外轮廓边 |
| top_outer | 沿法向最远端面的外轮廓边 |
| bottom_outer | 最近端面的外轮廓边 |
| vertical | 平行于拉伸方向的边（棱柱体竖直棱） |

"未注倒角 C1" 一般写成 `all_outer` + chamfer 1，并在 evidence 里注明来自技术要求。

## meta 写法

```json
"meta": { "confidence": 0.95, "evidence": "主视图 Ø40；左视图确认为通孔", "needs_review": false }
```

confidence 参考：

| 情况 | confidence |
|---|---|
| 矢量提取到数值，视图对应明确 | 0.95 以上 |
| 数值明确，但位置要靠推断 | 0.8 ~ 0.9 |
| 扫描图读出的数值 | 最多 0.85 |
| 按比例量出来的（用两个已标尺寸校准过，reading-rules R32） | 最多 0.75，并加 open_questions |
| 没校准的估量，或靠"看起来像" | 0.5 以下，并加 open_questions |

## open_questions

不确定的问题写成对象，分三级：

```json
"open_questions": [
  {"question": "曲轴孔 Ø12.5 深度没标", "level": "confirm", "affects": ["crank_bore"],
   "assumed": "深 13（轴测图里缸孔通进曲轴腔，留 2 后壁）"},
  {"question": "Ø4 缺口在主视图和俯视图位置对不上", "level": "blocking", "affects": ["notch"]},
  {"question": "材料没写", "level": "note"}
]
```

| level | 含义 | 建 SolidWorks 前 |
|---|---|---|
| blocking | 没有答案就建不出来：关键尺寸缺失、尺寸互相矛盾、单位不明、能力缺口 | 必须解决 |
| confirm | 表里先用了假设值：孔深 / 倒角没标、按比例量、按标准查表 | 必须有人拍板 |
| note | 不影响几何：公差、材料、粗糙度、技术要求 | 只提示 |

拍板后加 `resolution`：

```json
{"question": "曲轴孔深度没标", "level": "confirm", "assumed": "深 13",
 "resolution": {"by": "user", "answer": "深 13"}}
{"question": "M2 螺纹孔深度没标", "level": "confirm", "assumed": "深 4",
 "resolution": {"by": "ai", "answer": "深 4", "reason": "用户不确定；M2 常用螺纹深 2–3 倍直径，壁厚允许 4"}}
```

- 用户回答：`by: "user"`。用户说不知道、让 AI 判断：`by: "ai"`，**必须写 reason**。
- 没有 resolution 的 blocking / confirm，sw_build 停下报 `needs_confirmation`，列出未解决的问题。
- 报告的 `decided_by_ai` 列出所有由 AI 判断的项，交付时要告诉用户。
- 旧写法（纯字符串）在 v0.5 表里当 confirm 处理，v0.4 及以前当 note 处理。

## 公差和螺纹

- 带公差的尺寸（Ø40 h7、20±0.1）：建模取**公称尺寸**，公差写在 evidence 里。
- 螺纹孔 M8：diameter 填底孔直径（M8 粗牙为 6.8），`thread: "M8x1.25"`。常用底孔表见 `reading-prismatic.md`。
