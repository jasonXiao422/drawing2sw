"""环境自检：Python 版本、依赖库、操作系统、SolidWorks 连接。

用法: python check_env.py [--sw]     加 --sw 时额外检查 SolidWorks
每一项给出 ok / missing，以及缺了怎么办。SKILL.md 第 0 步调用。
"""
from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys

LIBS = {
    "jsonschema": ("必需", "校验特征表"),
    "pymupdf": ("必需", "读 PDF 图纸"),
    "ezdxf": ("必需", "读 DXF 图纸"),
    "cadquery": ("可选", "无 SolidWorks 时预览"),
    "matplotlib": ("可选", "DXF/DWG 渲染成图片"),
}
if sys.platform == "win32":
    LIBS["win32com.client"] = ("SolidWorks 必需", "连接 SolidWorks（pywin32）")

FIX = "在 drawing2sw 文件夹运行: powershell -ExecutionPolicy Bypass -File install.ps1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sw", action="store_true", help="同时检查 SolidWorks 连接")
    args = ap.parse_args()

    res = {"python": platform.python_version(), "os": platform.platform(), "libs": {}, "problems": []}
    for mod, (level, use) in LIBS.items():
        try:
            importlib.import_module(mod)
            res["libs"][mod] = "ok"
        except Exception:  # noqa: BLE001
            res["libs"][mod] = "missing"
            if level != "可选":
                res["problems"].append(f"缺少 {mod}（{level}，用于{use}）。{FIX}")
            elif sys.version_info >= (3, 13):
                res.setdefault("notes", []).append(
                    f"cadquery 未安装：Python {res['python']} 太新。预览功能不可用，其他功能不受影响。要预览请用 3.12：{FIX}")

    if args.sw:
        if sys.platform != "win32":
            res["problems"].append("SolidWorks 只能在 Windows 上运行。")
        elif res["libs"].get("win32com.client") == "ok":
            import sw_build  # noqa: PLC0415
            res["solidworks"] = sw_build.env_check()
            if not res["solidworks"].get("ok"):
                res["problems"].append(res["solidworks"].get("error", "SolidWorks 检查失败"))

    try:
        import dwg2dxf  # noqa: PLC0415
        res["dwg"] = dwg2dxf.check()
    except Exception as e:  # noqa: BLE001
        res["dwg"] = {"error": str(e)}

    res["ok"] = not res["problems"]
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
