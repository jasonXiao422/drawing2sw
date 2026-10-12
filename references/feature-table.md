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
  "open_questions": [ "..." ]
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

只能有一个基体特征。没有的特征类型不要自创，按 SKILL.md 原则 3 处理。

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
| 靠比例量出来的，或靠"看起来像" | 0.5 以下，并加 open_questions |

## 公差和螺纹

- 带公差的尺寸（Ø40 h7、20±0.1）：建模取**公称尺寸**，公差写在 evidence 里。
- 螺纹孔 M8：diameter 填底孔直径（M8 粗牙为 6.8），`thread: "M8x1.25"`。常用底孔表见 `reading-prismatic.md`。
