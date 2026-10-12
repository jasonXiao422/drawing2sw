# 跨模型盲测

## 两类数据分别报告

- data/synthetic：本项目生成的 12 张双孔板图，6 张 mm、6 张 inch。尺寸和坐标全部给定，附解析体积/面积和 STEP，用于检测单位、孔位、厚度、镜像和工具链回归。覆盖窄，不能代表真实工程图成功率。
- data/generated：`dev/tools/generate_dataset.py` 生成的 12 张图，孔板、分布圆盘、阶梯轴、法兰各 3 张，GB / ISO / ASME 各 4 张。每张都有 DXF、带文字层的 PDF、PNG 和模拟扫描件。答案里有**尺寸归属标签**：图上每个尺寸属于哪个特征的哪个参数。用于评测"读对数"之外的"分对特征"。几何仍是简单零件族。
- data/external_cases.json：Aaditya Jain 的两组 MIT 图纸，PNG 和 DWG 原样保留，带固定提交和 SHA-256。没有三维标准答案，状态只能是 unscored/manual review，不能加入几何通过率分母。

这些数据是评测资源，不会因为放进仓库就训练或提升模型。外部图可能尺寸不足；正确指出缺失也是需要记录的结果。

## 隔离输入和答案

```powershell
.venv\Scripts\python.exe scripts\benchmark.py prepare data\synthetic\manifest.json --case plate-01 -o work\blind-plate-01
.venv\Scripts\python.exe scripts\package_skill.py -o dist\drawing2sw-0.5.zip
```

prepared 目录只含图纸、任务说明和输入哈希。用干净的新会话，仅授予输入目录和解压后的 skill 访问权，**不要授予整个开发仓库**。文件夹分离本身不是权限隔离；模型仍能读答案时不算盲测。

固定 skill 提交、图纸版本、图片分辨率、工具权限、模型完整版本、允许的重试次数。保留首次输出，再记录最多 3 次修正；记录人工干预、错误类型、总耗时。开发时新增的规则不能在同一测试轮途中更换。

同一个案例可以用不同输入格式测，比较模型在矢量和扫描件上的差距：

```powershell
.venv\Scripts\python.exe scripts\benchmark.py prepare data\generated\manifest.json --case flange-iso-008 --format scan -o work\blind-flange-scan
```

`--format` 可选 dxf、pdf、pdf_notext、png、scan，按案例 manifest 里的 inputs。

## 离线评分

模型运行结束后，由评测端执行（答案对模型隐藏）：

```powershell
.venv\Scripts\python.exe scripts\benchmark.py score data\synthetic\manifest.json --case plate-01 --table work\model\part.json --observations work\model\observations.json --model "provider/model-version" -o work\score.json
```

验证 schema 和证据来源，比较解析体积/表面积/包围盒；有 STEP 时额外在相同基准下计算两实体的对称差体积。合成图在图纸上明确了基准。更换模型坐标系时应先做有记录的刚体对齐，不能靠任意变换掩盖镜像。

data/generated 的案例标了 `alignment: pose_free`：模型可以把零件建在任何基准面上，评分时尝试 24 种轴向旋转（不含镜像），对齐包围盒中心后取对称差最小的一种。镜像件仍然判错。

有尺寸归属标签的案例，score 还会输出 `association`：

| 字段 | 含义 |
|---|---|
| observed | 模型的证据文件里有这个尺寸（DXF 按实体句柄，PDF 按坐标，PNG 按像素位置对应） |
| cited | 至少一个特征引用了它 |
| correct | 引用它的特征类型和答案一致，而且这个特征的参数里用到了这个数 |
| wrong_feature | 被引用了，但引用它的特征不对 |
| association_recall | correct / 尺寸总数 |

扫描件和 PNG 输入时，模型要自己用 OCR 或看图记录观察，并写原图像素 bbox，否则 observed 会是 0，这时只评几何。

geometry_passed 只代表参考几何在设定容差内一致，不代表特征树设计意图或加工要求一致。脚本评测的是提交的文件；first-pass 或 repaired 必须由运行记录区分，不得把修正后成绩写成首次正确率。

建议后续把真实、有独立答案的图扩展到 20–30 张，并保留按零件族划分的留出集。这里不提供虚构的 Claude、豆包或其他模型成绩。
