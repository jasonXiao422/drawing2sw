# drawing2sw 一键安装（Windows PowerShell）
# 用法：在 drawing2sw 文件夹里右键"在终端中打开"，运行：
#   powershell -ExecutionPolicy Bypass -File install.ps1
# 做的事：找到 Python 3.12/3.11 -> 建 .venv -> 装依赖（失败自动换清华镜像）-> 环境自检

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

Write-Host "[1/4] 查找 Python 3.12 或 3.11 ..."
$pyver = $null
foreach ($v in @("3.12", "3.11")) {
    try {
        & py "-$v" --version *> $null
        if ($LASTEXITCODE -eq 0) { $pyver = $v; break }
    } catch {}
}
if (-not $pyver) {
    Write-Host ""
    Write-Host "没有找到 Python 3.12 / 3.11。CadQuery 不支持太新的版本（例如 3.13、3.14）。" -ForegroundColor Red
    Write-Host "请运行下面这条命令安装，然后关掉终端重新打开，再运行本脚本："
    Write-Host "    winget install Python.Python.3.12" -ForegroundColor Yellow
    Write-Host "（没有 winget 就去 python.org 下载 3.12。已有的其他版本不用卸载。）"
    exit 1
}
Write-Host "    使用 Python $pyver"

Write-Host "[2/4] 创建项目专用环境 .venv ..."
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & py "-$pyver" -m venv .venv
}
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip -q

Write-Host "[3/4] 安装依赖（CadQuery 较大，需要几分钟）..."
& $py -m pip install -r requirements.txt --timeout 30
if ($LASTEXITCODE -ne 0) {
    Write-Host "    默认源失败，换清华镜像重试 ..." -ForegroundColor Yellow
    & $py -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
}

Write-Host "[4/4] 环境自检 ..."
& $py scripts\check_env.py
Write-Host ""
Write-Host "完成。以后运行脚本用：.venv\Scripts\python.exe scripts\xxx.py" -ForegroundColor Green
