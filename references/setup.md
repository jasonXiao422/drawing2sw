# 环境安装与排查

## 一键安装（推荐）

在 drawing2sw 文件夹里打开终端，运行：

```
powershell -ExecutionPolicy Bypass -File install.ps1
```

脚本会自动：找 Python 3.12/3.11 → 建 `.venv` → 装依赖（默认源失败时自动换清华镜像）→ 运行自检。

## 需要的东西

| 组件 | 版本 | 用途 |
|---|---|---|
| Windows | 10 / 11 | SolidWorks 只能在 Windows 上跑 |
| SolidWorks | 2020 及以上（开发用 2025） | 建模 |
| Python | **3.11 或 3.12** | 运行脚本。3.13、3.14 太新，CadQuery 装不上 |
| pywin32 | 最新 | 通过 COM 调用 SolidWorks |
| jsonschema, pymupdf, ezdxf | 最新 | 校验、读 PDF、读 DXF |
| cadquery | 2.x（可选） | 无 SolidWorks 时预览 |
| matplotlib | 最新（可选） | 把 DXF/DWG 渲染成图片给 AI 看 |
| DWG 转换工具 | 有一个就行 | 按顺序自动找：ODA File Converter（免费，国外下载慢）→ AutoCAD / 中望 CAD / 浩辰 CAD（国内最常见，推荐）→ SolidWorks。运行 `python scripts/dwg2dxf.py --check` 查看 |

电脑上已经有别的 Python 版本不用卸载。用 `winget install Python.Python.3.12` 另装一个，`.venv` 会锁定使用 3.12。

## 手动安装

```
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
.venv\Scripts\python.exe scripts\check_env.py --sw
```

## 排查

| 现象 | 处理 |
|---|---|
| install.ps1 说找不到 Python 3.12 | 运行 `winget install Python.Python.3.12`，关掉终端重开，再运行脚本 |
| "禁止运行脚本" | 用上面带 `-ExecutionPolicy Bypass` 的命令，或运行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| cadquery 装不上 | 确认 `.venv` 用的是 3.12：`.venv\Scripts\python.exe --version`。实在不行可跳过，它只用于预览 |
| check_env 报无法连接 SldWorks.Application | 先手动打开一次 SolidWorks，关掉所有弹窗再试；用管理员终端试一次 |
| 连上了但建模时卡住不动 | SolidWorks 里有对话框没关（更新提示、许可提示） |
| 杀毒软件拦截 | 把 `.venv\Scripts\python.exe` 加入白名单 |
| 学生版 / 教育版 | API 可用，和商业版一样 |
| DWG 转换失败 | 运行 `python scripts/dwg2dxf.py --check` 看哪种方式可用。装 ODA File Converter，或在 CAD 软件里另存为 DXF |

## 国内用户

- GitHub 慢时，用百度网盘或 Gitee 镜像下载。
- install.ps1 会自动在默认源失败时切换清华镜像。
- 所有建模都在本机完成，不需要访问境外服务器。只有读图那一步用的 AI 模型需要联网。
