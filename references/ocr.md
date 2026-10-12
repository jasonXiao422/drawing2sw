# 可选 OCR：PaddleOCR 3.x

本项目调用 PaddleOCR 的公开 Python API，或导入它导出的单张图结果。原环境不需要安装 PaddleOCR。

## 离线导入（已做格式与坐标测试）

先运行 preprocess_drawing.py。对它输出的**整页原尺寸图片**运行 PaddleOCR 3.x，将该页结果保存为 JSON（含 rec_texts、rec_scores、rec_polys 或 rec_boxes；支持外层 res）。

```powershell
.venv\Scripts\python.exe scripts\ocr_drawing.py work\extract_observations.json --page 1 --paddle-json work\paddle_page1.json -o work\ocr_observations.json
```

之后 validate 的 --observations 使用新的文件。多页依次导入各页；同页重复导入会拒绝，避免旧引用误指向新结果。

## 本地 CPU 推理（可选依赖）

单独建立环境，先按 [PaddleOCR 官方安装说明](https://www.paddleocr.ai/latest/en/quick_start.html) 安装适合系统的 PaddlePaddle/PaddleOCR 3.x，再装 jsonschema、Pillow。不要改现有 CAD 环境的 numpy。

```powershell
py -3.12 -m venv .venv-ocr
.venv-ocr\Scripts\python.exe -m pip install "paddlepaddle>=3,<4" "paddleocr>=3,<4" jsonschema Pillow
.venv-ocr\Scripts\python.exe scripts\ocr_drawing.py work\extract_observations.json --engine paddleocr --lang ch -o work\ocr_observations.json
```

首次推理可能下载模型。CPU 和系统兼容性取决于上游安装包。这一可选推理路径需要在装有对应依赖的环境验证；仅导入测试通过不代表 OCR 准确率已经验证。

关闭页面方向分类、文档矫正，保持坐标对应原页。不要把经过旋转、透视变换或裁剪的外部 OCR 结果直接导入；先把框映射回原图。OCR 的 0/O、1/7、R/Ø、上下偏差、±、深度符号需对原图复核。

eDOCr2 的机械工程图分割/OCR 方案列在 THIRD_PARTY_NOTICES；目前未嵌入其运行时、训练权重或未单独核实权利的论文测试图。
