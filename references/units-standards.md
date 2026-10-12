# 单位、标准与中英文标注

SKILL.md 第 2 节读图前必读。先把图纸的基础设定定下来，再读任何尺寸。单位错了，后面每个数都错，而且体积校验发现不了（因为特征表本身是自洽的）。

## 铁律

1. **图纸写什么数，特征表就填什么数。**英寸图填英寸，毫米图填毫米。不要自己换算。换算由 `ftable.to_mm()` 统一做，只做一次。
2. **单位必须有依据。**`unit_evidence` 照抄图上原文。找不到原文就写"无明确标注，按 X 推断"，并写进 `open_questions`。置信度按依据定（全 skill 统一用这一档）：
   - 图上原文（标题栏、技术要求、UNITS 注释）：0.95 以上
   - DXF 文件头 `$INSUNITS` / `$MEASUREMENT`，或齿轮 m·z 和分度圆对上：最多 0.85，请用户确认
   - 只凭语言、Ø 符号、配合代号这类推断：最多 0.6，请用户确认
3. **比例不影响数值。**比例 1:2 的图，标注 40 就是 40。永远按标注数字，不按图上量出来的长度。
4. **双单位只读主单位。**`25.4 [1.000]` 这种，方括号里是副单位，忽略。
5. **一张图只有一个主单位。**同一张图里出现两种单位线索时，停下来问用户。

## 单位从哪里找

按顺序找，找到就停：

| 位置 | 中文图常见写法 | 英文图常见写法 |
|---|---|---|
| 标题栏 | 单位：mm；单位 毫米 | UNITS: MM / INCH |
| 技术要求 / 注释 | 未注尺寸单位为 mm | UNLESS OTHERWISE SPECIFIED, DIMENSIONS ARE IN INCHES |
| 公差块 | 未注公差按 GB/T 1804-m | TOLERANCES: .XX ±.01 .XXX ±.005（这种写法 = 英寸） |
| DXF 文件头 | `$INSUNITS`、`$MEASUREMENT` | 同左。经常被导出程序填错，和标题栏冲突时以标题栏为准 |
| 数值写法 | 12.5、Ø40 | .375、1/4"、2-1/2"（前导小数点和分数几乎只出现在英寸图） |

`preprocess_drawing.py` 会把这些线索整理到 `setup_hints`。它只给线索，结论由你判断并写进 `drawing_setup`。

## 标准、投影法、语言

| 标准 | 地区 | 默认投影 | 默认单位 | 语言 |
|---|---|---|---|---|
| GB / GB/T | 中国 | 第一角 | mm | 中文 |
| ISO | 国际、欧洲 | 第一角 | mm | 英文或当地语言 |
| DIN | 德国 | 第一角 | mm | 德文 / 英文；**小数点常用逗号** 12,5 |
| JIS | 日本 | 第三角为主 | mm | 日文 / 英文 |
| ANSI / ASME Y14.5 | 美国 | 第三角 | inch（也有公制 ASME 图） | 英文 |

标准和投影法不一致时，以图上的投影符号为准，见 `projection.md`。

## 中英文标注对照

| 含义 | GB / 中文 | ASME / 英文 | 建模时怎么填 |
|---|---|---|---|
| 直径 | Ø40、φ40 | Ø1.500、1.500 DIA | diameter |
| 半径 | R5 | R.20、.20 RAD | 圆角 size |
| 球径 | SR10 | SR.50 | 没有专门写法。回转件端部球面可试 revolve 的 path 轮廓画圆弧，没实测过，要向用户说明 |
| 数量 | 4×Ø9、4-Ø9 | 4X Ø.344 | positions 或 bolt_circle 的个数 |
| 均布 | 均布、EQS | EQ SP、EQUALLY SPACED | bolt_circle |
| 节圆 | PCD80、Ø80 节圆 | B.C. Ø3.150、BC | bolt_circle.pcd |
| 通孔 | 通孔、通 | THRU | depth: through_all |
| 深度 | 深 10、↧10 | DP .50、↧.50 | depth 数值 |
| 沉孔 / 柱孔 | 沉孔 Ø18 深 11、⌴ | CBORE Ø.70 ↧.43、⌴ | hole 的 cbore，见 reading-prismatic.md |
| 埋头孔 | 锪孔 90°、⌵ | CSK Ø.50 X 82°、⌵ | hole 的 csink，见 reading-prismatic.md |
| 倒角 | C1、1×45° | .04 X 45°、CHAM | edge_treatment chamfer |
| 未注倒角 | 未注倒角 C0.5 | BREAK ALL SHARP EDGES .01 | drawing_setup.default_chamfer，并问用户要不要建 |
| 螺纹 | M8、M8×1.25-6H | 1/4-20 UNC-2B、M8X1.25 | thread 记录规格，diameter 填底孔 |
| 典型 | 同类、相同 | TYP | 同样的特征在别处也有，逐个找出来 |
| 参考尺寸 | (40) | (1.500)、REF | 不用于建模，只用来核对 |
| 基本尺寸 | 方框 [40] | 方框 [1.500] | 理论正确尺寸，按数值建模 |

## 英寸图的坑

- 分数要换成小数：1/4 = 0.25，2-1/2 = 2.5，5/16 = 0.3125。在特征表里写小数，evidence 里写原文。
- 英制螺纹 1/4-20 UNC：1/4 是公称直径（英寸），20 是每英寸牙数。底孔查表（1/4-20 底孔 #7 = 0.201），查不到就问用户。
- 英尺：3'-6" = 42 英寸。零件图很少见，出现时确认。

## drawing_setup 示例

中文国标图：

```json
"units": "mm",
"drawing_setup": {
  "length_unit": "mm", "unit_evidence": "标题栏：单位 mm",
  "standard": "GB", "language": "zh", "scale": "1:2",
  "general_tolerance": "GB/T 1804-m", "default_chamfer": 0.5,
  "notes": ["未注倒角 C0.5", "锐边倒钝"], "confidence": 0.98
}
```

美标英寸图：

```json
"units": "inch",
"drawing_setup": {
  "length_unit": "inch", "unit_evidence": "UNLESS OTHERWISE SPECIFIED DIMENSIONS ARE IN INCHES",
  "standard": "ASME", "language": "en", "scale": "1:1",
  "general_tolerance": ".XX ±.01 .XXX ±.005", "confidence": 0.97
}
```

完整的英寸示例见 `examples/bracket_inch.json`。

## 校验脚本会查什么

`validate_feature_table.py` 自动检查：

| 检查 | 级别 |
|---|---|
| `part.units` 和 `length_unit` 不一致 | ERROR |
| `unit_evidence` 原文说英寸，却填了 mm（或反过来） | ERROR |
| 双单位的主单位和 `length_unit` 不一致 | ERROR |
| 单位没有明确依据，或置信度 < 0.9 | WARNING，必须问用户 |
| 最大尺寸不像真实零件（例如 mm 图最大才 4） | WARNING，可能单位填错 |
| 标准和投影法不匹配 | WARNING |
| 国标 / ISO 图用英寸，或用逗号作小数点 | WARNING |

建模时 SolidWorks 的零件文档单位会自动设成和图纸一致，所以打开模型看到的数字和图纸一样。
