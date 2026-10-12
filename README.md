# drawing2sw

读机械零件工程图，自动在 SolidWorks 里建模。做成 Agent Skill（SKILL.md 格式），Claude、Codex、Qoder 等支持 skill 的 AI 工具都能用。

## 怎么工作

```
工程图 (DWG / DXF / PDF / 图片)
   │  preprocess_drawing.py   矢量图直接提取尺寸文字和圆
   ▼
AI 读图 → 特征表 part.json   （唯一需要 AI 的一步）
   │  validate_feature_table.py   schema + 工程规则检查
   ▼
用户确认低置信度项
   │
   ├─ preview_cadquery.py   任何系统可跑，出 STEP + 体积
   └─ sw_build.py            SolidWorks COM 建模
   ▼
verify_model.py   体积、包围盒误差 ≤ 1%，孔数一致
```

AI 只负责"看懂图，填表"。建模全是确定性代码，同一张表永远得到同一个零件。

## 参考了谁

| 来源 | 借鉴了什么 |
|---|---|
| [SolidPilot](https://glama.ai/mcp/servers/ihefudnp5d)（SolidWorks MCP） | 意图 → CAD 中立中间表示 → 确定性编译的分层；不支持就返回 `capability_blocked`，不降级；1% 体积误差的校验标准 |
| [MCP_CAD](https://glama.ai/mcp/servers/gvqccxa7vf) | 受限工具面（AI 不能调任意 API）；每次建模前人工确认；几何数据不离开本机 |
| [CAD-Coder](https://arxiv.org/abs/2505.14646)（MIT） | 用 CadQuery 作为 CAD 中立的验证后端 |
| [eDOCr](https://github.com/wiberganton/eDOCr) | 工程图 OCR 思路，路线图里用于扫描件 |
| Agent Skills 规范 | SKILL.md 只放流程，细节拆到 references/ 按需读取，脚本做确定性工作 |

## 当前状态 (v0.4)

| 模块 | 状态 |
|---|---|
| 特征表 schema | ✅ v0.4：基体拉伸/旋转、加料拉伸（凸台、筋板、肋、耳板）、切除、孔、倒角圆角、旋转切除、齿轮；直线+圆弧轮廓；任意斜面；图纸基础设定。v0.4 意图写法：拐角倒圆、切线连接、交点、按半径画弧、沉孔/埋头孔/钻尖，切点圆心由脚本算 |
| 单位 | ✅ 图纸用什么单位就填什么，脚本统一换算；mm / cm / m / inch；SolidWorks 文档单位自动跟随图纸 |
| 预处理 | ✅ DWG（自动转 DXF）/ DXF / 矢量 PDF / 图片。DXF 读块内标题栏、表格、显示文字、DIMLFAC、图层线型，并渲染成图片 |
| CadQuery 预览 | ✅ 出 STEP、体积、每一步的体积和位置；可渲染四个方向对照图纸 |
| SolidWorks 建模 | ✅ 每建一步都和预览比对，第一个对不上的特征立刻停下。拉伸、旋转、切除、孔、均布孔、圆角、倒角、斜面、渐开线齿轮都实测通过 |
| 读图测试 | 🟡 5 张真实图：DWG 齿轮、两道 CATICS 题（和答案模型差 0.0001% 以内）、一张教材架体图（无答案，待人工检查） |
| 国标查表 | 🟡 键槽、通孔、沉孔、螺纹底孔。数值未逐条核对标准原文 |
| 不支持 | ❌ 线性阵列、镜像、抽壳、拔模、扫描、放样、螺旋、钣金、装配体 |

## 安装

需要 Windows、SolidWorks、Python 3.12（3.13 以上太新，旧版本不用卸载，另装一个即可）。

在 drawing2sw 文件夹里打开终端，运行：

```
powershell -ExecutionPolicy Bypass -File install.ps1
```

自动建环境、装依赖、做自检。缺 Python 3.12 时会告诉你怎么装。详见 `references/setup.md`。

## 快速试用（不需要图纸）

下面的 `python` 在 Windows 上替换成 `.venv\Scripts\python.exe`。

```
cd drawing2sw
python scripts/validate_feature_table.py examples/flange_revolved.json
python scripts/preview_cadquery.py examples/flange_revolved.json -o work/flange.step
python scripts/verify_model.py examples/flange_revolved.json --report work/flange_report.json
# Windows + SolidWorks:
python scripts/check_env.py --sw
python scripts/sw_build.py examples/bracket_prismatic.json -o D:/out/plate.SLDPRT
python scripts/sw_build.py examples/bracket_inch.json -o D:/out/plate_inch.SLDPRT   # 英寸图示例
```

## 目录

```
SKILL.md          主流程（AI 读这个）
references/       读图和填表规则、坐标约定、特征表说明、各类图纸读法
schema/           特征表 JSON Schema
scripts/          确定性脚本：预处理、校验、展开几何、预览、SolidWorks 建模、对答案
standards/        国标查表数据
examples/         示例特征表
install.ps1       一键安装（Windows）

dev/              开发用（不属于 skill）：开发说明 DEVELOPING.md、出题工具、可选向量检索
tests/            开发用：测试图纸和答案、覆盖矩阵、几何自检
PROGRESS.md       开发交接文档
```

发布 skill 只需要上半部分。

## 怎么往里填东西

1. 往 `tests/drawings/` 放图纸，有答案模型更好
2. 让 AI 按 SKILL.md 盲读、建模、对答案，失败就分析原因
3. 读图规则写进 `references/reading-rules.md`；实现层的坑写进 `dev/DEVELOPING.md`
4. 需要新特征时，按 `dev/DEVELOPING.md`：先改 schema，能展开的在 `ftable.resolve()` 里展开，不能的同时改 preview 和 sw_build
