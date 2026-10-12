"""DWG -> DXF 转换。DWG 是私有格式，Python 不能直接读，先转成 DXF 再交给 preprocess_drawing.py。

用法:
  python dwg2dxf.py --check                 看哪种转换方式可用
  python dwg2dxf.py drawing.dwg -o work/    转换，输出 work/drawing.dxf

按顺序尝试，本机有什么用什么：
  1. ODA File Converter（免费，转换最忠实）。需要另装，国外下载慢，见 references/setup.md
  2. 本机 CAD：AutoCAD / 中望 CAD / 浩辰 CAD。打开 DWG 另存为 DXF，和原图一样准。国内用户大多装了其中一个
  3. SolidWorks 自带的 DWG 导入，再另存为 DXF。人人都有，但 SolidWorks 会重新解释一遍图纸，
     尺寸实体可能变成普通文字，转换结果要多核对
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HELP = ("解决办法（任选一个）：\n"
        "  1. 装了 AutoCAD / 中望 / 浩辰：确认能手动打开这个 DWG，关掉弹窗后重新运行\n"
        "  2. 在任意 CAD 软件里把 DWG 另存为 DXF（2013 或 2018 版本），直接用 DXF\n"
        "  3. 安装免费的 ODA File Converter：https://www.opendesign.com/guestfiles/oda_file_converter\n"
        "  4. 确认 SolidWorks 能手动打开这个 DWG")

# AutoCAD 兼容的 COM 接口。名字是注册表里的 ProgID
CAD_PROGIDS = [("AutoCAD", "AutoCAD.Application"), ("中望 CAD", "ZWCAD.Application"),
               ("浩辰 CAD", "GCAD.Application")]
# AcSaveAsType：ac2013_dxf=61, ac2010_dxf=49, ac2007_dxf=37, ac2004_dxf=25。从新到旧试，兼容老版本和国产 CAD
DXF_SAVE_TYPES = [61, 49, 37, 25]

ODA_GLOBS = [
    r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe",
    r"C:\Program Files (x86)\ODA\ODAFileConverter*\ODAFileConverter.exe",
    "/usr/bin/ODAFileConverter",
    "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
]


def find_oda() -> str | None:
    env = os.environ.get("ODAFC_PATH")
    if env and os.path.isfile(env):
        return env
    hits = []
    for g in ODA_GLOBS:
        hits += glob.glob(g)
    return sorted(hits)[-1] if hits else None  # 多个版本取最新


def via_oda(src: Path, out_dir: Path) -> Path:
    exe = find_oda()
    if not exe:
        raise RuntimeError("没有找到 ODA File Converter")
    # ODA 按文件夹转换。复制到纯英文临时目录，避开中文路径和空格的问题
    with tempfile.TemporaryDirectory() as tin, tempfile.TemporaryDirectory() as tout:
        tmp_src = Path(tin) / "input.dwg"
        shutil.copy2(src, tmp_src)
        cmd = [exe, tin, tout, "ACAD2018", "DXF", "0", "1", "input.dwg"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        got = Path(tout) / "input.dxf"
        if not got.exists():
            raise RuntimeError(f"ODA 没有生成 DXF（返回码 {r.returncode}）{r.stderr.strip()[:200]}")
        dst = out_dir / f"{src.stem}.dxf"
        shutil.copy2(got, dst)
        return dst


def installed_cads() -> list[tuple[str, str]]:
    """查注册表，看装了哪些 AutoCAD 兼容软件。不启动它们。"""
    if sys.platform != "win32":
        return []
    import winreg  # noqa: PLC0415

    found = []
    for name, progid in CAD_PROGIDS:
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid))
            found.append((name, progid))
        except OSError:
            pass
    return found


def _retry(fn, tries: int = 30, wait: float = 1.0):
    """CAD 启动或忙的时候会拒绝 COM 调用（RPC_E_CALL_REJECTED），等一下再试。"""
    import time  # noqa: PLC0415

    last = None
    for _ in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            msg = str(e)
            if "-2147418111" in msg or "-2147417846" in msg or "被呼叫方拒绝" in msg or "rejected" in msg.lower():
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"CAD 一直忙，放弃: {last}")


def via_cad(src: Path, out_dir: Path) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("AutoCAD / 中望 / 浩辰 只能在 Windows 上调用")
    import pythoncom  # noqa: PLC0415
    import win32com.client  # noqa: PLC0415

    cads = installed_cads()
    if not cads:
        raise RuntimeError("没有找到 AutoCAD / 中望 CAD / 浩辰 CAD")
    errors = []
    for name, progid in cads:
        app, started_by_us, doc = None, False, None
        try:
            try:
                app = win32com.client.GetActiveObject(progid)  # 已经开着就直接用
            except pythoncom.com_error:
                print(f"启动 {name}（第一次可能要半分钟）...", flush=True)
                app = win32com.client.Dispatch(progid)
                started_by_us = True
            # 复制到纯英文临时路径，避开中文路径和只读问题
            with tempfile.TemporaryDirectory() as tmp:
                tmp_src = Path(tmp) / "input.dwg"
                shutil.copy2(src, tmp_src)
                tmp_dxf = Path(tmp) / "output.dxf"
                docs = _retry(lambda: app.Documents)
                doc = _retry(lambda: docs.Open(str(tmp_src), True))  # 只读打开
                saved = False
                for t in DXF_SAVE_TYPES:
                    try:
                        _retry(lambda t=t: doc.SaveAs(str(tmp_dxf), t))
                        if tmp_dxf.exists():
                            saved = True
                            break
                    except Exception as e:  # noqa: BLE001
                        errors.append(f"{name} SaveAs({t}): {e}")
                try:
                    _retry(lambda: doc.Close(False))
                except Exception:  # noqa: BLE001
                    pass
                doc = None
                if not saved:
                    raise RuntimeError("另存 DXF 没有生成文件")
                dst = out_dir / f"{src.stem}.dxf"
                shutil.copy2(tmp_dxf, dst)
            return dst
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
        finally:
            if doc is not None:
                try:
                    doc.Close(False)
                except Exception:  # noqa: BLE001
                    pass
            if started_by_us and app is not None:
                try:
                    app.Quit()  # 我们开的就关掉；用户自己开着的不动
                except Exception:  # noqa: BLE001
                    pass
    raise RuntimeError(" | ".join(errors))


def dxf_to_dwg(src: Path, dst: Path) -> Path:
    """反向：DXF 另存为 DWG，给合成测试图出 DWG 版本用。只用本机 CAD。"""
    import pythoncom  # noqa: PLC0415
    import win32com.client  # noqa: PLC0415

    cads = installed_cads()
    if not cads:
        raise RuntimeError("没有找到 AutoCAD / 中望 / 浩辰")
    name, progid = cads[0]
    started = False
    try:
        app = win32com.client.GetActiveObject(progid)
    except pythoncom.com_error:
        app = win32com.client.Dispatch(progid)
        started = True
    try:
        with tempfile.TemporaryDirectory() as tmp:
            t_src = Path(tmp) / "in.dxf"
            t_dst = Path(tmp) / "out.dwg"
            shutil.copy2(src, t_src)
            doc = _retry(lambda: app.Documents.Open(str(t_src), True))
            for t in (60, 48, 36, 24):  # ac2013_dwg, ac2010_dwg, ac2007_dwg, ac2004_dwg
                try:
                    _retry(lambda t=t: doc.SaveAs(str(t_dst), t))
                    if t_dst.exists():
                        break
                except Exception:  # noqa: BLE001
                    continue
            _retry(lambda: doc.Close(False))
            if not t_dst.exists():
                raise RuntimeError(f"{name} 另存 DWG 失败")
            shutil.copy2(t_dst, dst)
        return dst
    finally:
        if started:
            try:
                app.Quit()
            except Exception:  # noqa: BLE001
                pass


def via_solidworks(src: Path, out_dir: Path) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("SolidWorks 只能在 Windows 上运行")
    import pythoncom  # noqa: PLC0415
    import win32com.client  # noqa: PLC0415

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import sw_build  # noqa: PLC0415

    app = sw_build.connect()
    path = str(src.resolve())
    doc, errors = None, []
    # 不同版本、不同 pywin32 绑定下签名不一样，逐个试（见 dev/DEVELOPING.md #5 #8）
    try:
        data = app.GetImportFileData(path)
        err = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        doc = app.LoadFile4(path, "", data, err)
    except Exception as e:  # noqa: BLE001
        errors.append(f"LoadFile4: {e}")
    if doc is None:
        try:
            doc = app.LoadFile2(path, "")
        except Exception as e:  # noqa: BLE001
            errors.append(f"LoadFile2: {e}")
    if doc is None:
        raise RuntimeError("SolidWorks 打不开这个 DWG。" + " | ".join(errors))
    dst = (out_dir / f"{src.stem}_sw.dxf").resolve()
    if dst.exists():
        dst.unlink()
    err = doc.SaveAs3(str(dst), 0, 2)
    try:
        app.CloseDoc(sw_build.call(doc, "GetTitle"))
    except Exception:  # noqa: BLE001
        pass
    if err or not dst.exists():
        raise RuntimeError(f"SolidWorks 另存 DXF 失败（错误码 {err}）")
    return dst


def convert(src: Path, out_dir: Path) -> dict:
    src, out_dir = Path(src), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    errors = []
    for name, fn in (("ODA File Converter", via_oda), ("本机 CAD", via_cad), ("SolidWorks", via_solidworks)):
        try:
            dxf = fn(src, out_dir)
            res = {"ok": True, "backend": name, "dxf": str(dxf), "errors": errors}
            if name == "SolidWorks":
                res["warning"] = "SolidWorks 转换会重新解释图纸，尺寸可能变成普通文字。尺寸以图上文字为准并和几何核对"
            return res
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
    return {"ok": False, "errors": errors}


def check() -> dict:
    oda = find_oda()
    sw = None
    if sys.platform == "win32":
        try:
            import win32com.client  # noqa: F401, PLC0415
            sw = "可用（需要 SolidWorks 已安装）"
        except ImportError:
            sw = "缺 pywin32"
    cads = [n for n, _ in installed_cads()]
    return {"oda_file_converter": oda or "未安装",
            "cad": cads or "未找到 AutoCAD / 中望 / 浩辰",
            "solidworks": sw or "不可用（非 Windows）",
            "will_use": "ODA File Converter" if oda else (cads[0] if cads else ("SolidWorks" if sw else None)),
            "ok": bool(oda or cads or sw == "可用（需要 SolidWorks 已安装）")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dwg", nargs="?")
    ap.add_argument("-o", "--out", default="work")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check or not args.dwg:
        print(json.dumps(check(), ensure_ascii=False, indent=2))
        return 0
    res = convert(Path(args.dwg), Path(args.out))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if not res["ok"]:
        print(HELP)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
