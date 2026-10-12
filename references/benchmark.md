# 跨模型盲测

## 两类数据分别报告

- data/synthetic：本项目生成的 12 张双孔板图，6 张 mm、6 张 inch。尺寸和坐标全部给定，附解析体积/面积和 STEP，用于检测单位、孔位、厚度、镜像和工具链回归。覆盖窄，不能代表真实工程图成功率。
- data/external_cases.json：Aaditya Jain 的两组 MIT 图纸，PNG 和 DWG 原样保留，带固定提交和 SHA-256。没有三维标准答案，状态只能是 unscored/manual review，不能加入几何通过率分母。

这些数据是评测资源，不会因为放进仓库就训练或提升模型。外部图可能尺寸不足；正确指出缺失也是需要记录的结果。

## 隔离输入和答案

```powershell
.venv\Scripts\python.exe scripts\benchmark.py prepare data\synthetic\manifest.json --case plate-01 -o work\blind-plate-01
.venv\Scripts\python.exe scripts\package_skill.py -o dist\drawing2sw-0.5.zip
```

prepared 目录只含图纸、任务说明和输入哈希。用干净的新会话，仅授予输入目录和解压后的 skill 访问权，**不要授予整个开发仓库**。文件夹分离本身不是权限隔离；模型仍能读答案时不算盲测。

固定 skill 提交、图纸版本、图片分辨率、工具权限、模型完整版本、允许的重试次数。保留首次输出，再记录最多 3 次修正；记录人工干预、错误类型、总耗时。开发时新增的规则不能在同一测试轮途中更换。

## 离线评分

模型运行结束后，由评测端执行（答案对模型隐藏）：

```powershell
.venv\Scripts\python.exe scripts\benchmark.py score data\synthetic\manifest.json --case plate-01 --table work\model\part.json --observations work\model\observations.json --model "provider/model-version" -o work\score.json
```

验证 schema 和证据来源，比较解析体积/表面积/包围盒；有 STEP 时额外在相同基准下计算两实体的对称差体积。合成图在图纸上明确了基准。更换模型坐标系时应先做有记录的刚体对齐，不能靠任意变换掩盖镜像。

geometry_passed 只代表参考几何在设定容差内一致，不代表特征树设计意图或加工要求一致。脚本评测的是提交的文件；first-pass 或 repaired 必须由运行记录区分，不得把修正后成绩写成首次正确率。

建议后续把真实、有独立答案的图扩展到 20–30 张，并保留按零件族划分的留出集。这里不提供虚构的 Claude、豆包或其他模型成绩。
