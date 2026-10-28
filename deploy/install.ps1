# LawLens 试用版安装脚本
#
# 在解压后的目录里运行（PowerShell）：
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#
# 会做三件事：建虚拟环境 → 装依赖 → 生成 .env
# 之后用目录里的 start.cmd 启动，或直接：
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Run

param(
  [switch]$Run,
  [switch]$Lite,          # 不装 OCR（省 ~200MB，扫描件将标记为"未识别"）
  [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

Write-Host "== LawLens 试用版安装 ==" -ForegroundColor Cyan

# 1) 找 Python
$py = $null
foreach ($cmd in @('python', 'py')) {
  $found = Get-Command $cmd -ErrorAction SilentlyContinue
  if ($found) { $py = $found.Source; break }
}
if (-not $py) {
  Write-Host "找不到 Python。请先安装 Python 3.11 或 3.12：https://www.python.org/downloads/" -ForegroundColor Red
  Write-Host "（安装时勾选 Add python.exe to PATH）" -ForegroundColor Red
  exit 1
}
$ver = & $py -c "import sys; print('%d.%d' % sys.version_info[:2])"
Write-Host "Python $ver → $py"
if ([version]$ver -lt [version]'3.11') {
  Write-Host "Python 版本过低，建议 3.11 / 3.12" -ForegroundColor Yellow
}
# OCR 引擎（rapidocr-onnxruntime）只支持 Python < 3.13，高版本自动改用精简依赖
if ([version]$ver -ge [version]'3.13') {
  Write-Host "Python $ver 超出 OCR 引擎支持范围（需 < 3.13），自动改用精简依赖：扫描件将无法识别，其余功能正常。" -ForegroundColor Yellow
  Write-Host "如需 OCR，请安装 Python 3.11/3.12 后删除 .venv 重跑本脚本。" -ForegroundColor Yellow
  $Lite = $true
}

# 2) 建虚拟环境
if (-not (Test-Path (Join-Path $root '.venv\Scripts\python.exe'))) {
  Write-Host "创建虚拟环境 .venv ..."
  & $py -m venv (Join-Path $root '.venv')
} else {
  Write-Host "已存在 .venv，跳过创建"
}
$venvPy = Join-Path $root '.venv\Scripts\python.exe'

# 3) 装依赖（有本地 wheels 就离线装，省流量也避免网络问题）
$req = Join-Path $root 'backend\requirements.txt'
$wheels = Join-Path $root 'wheels'
if ($Lite) {
  $reqLite = Join-Path $root 'backend\requirements-lite.txt'
  if (Test-Path $reqLite) { $req = $reqLite } else { Write-Host "缺少 requirements-lite.txt，仍按完整依赖安装" -ForegroundColor Yellow }
}

Write-Host "安装依赖（首次约 3–10 分钟）..."
$pipLog = Join-Path $env:TEMP ("lawlens-pip-{0}.log" -f (Get-Date -Format 'HHmmss'))
& $venvPy -m pip install --upgrade pip --quiet
if (Test-Path $wheels) {
  $pipOut = & $venvPy -m pip install --no-index --find-links $wheels -r $req 2>&1
} else {
  $pipOut = & $venvPy -m pip install -r $req 2>&1
}
$pipOut | Out-String | Set-Content -Path $pipLog -Encoding utf8
if ($LASTEXITCODE -ne 0) {
  Write-Host "依赖安装失败。pip 输出最后几行：" -ForegroundColor Red
  $pipOut | Select-Object -Last 8 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
  $text = ($pipOut | Out-String)
  if ($text -match 'ProxyError|Cannot connect to proxy|Connection aborted|NewConnectionError|Read timed out') {
    Write-Host ""
    Write-Host "判断：网络或代理问题。" -ForegroundColor Yellow
    Write-Host "本机若开着代理（Clash / 公司代理），pip 会走系统代理而失败。可临时设置后重试：" -ForegroundColor Yellow
    Write-Host '  $env:NO_PROXY="pypi.org,files.pythonhosted.org"; $env:no_proxy=$env:NO_PROXY' -ForegroundColor Yellow
    Write-Host '  然后重新运行 install.ps1' -ForegroundColor Yellow
  } elseif ($text -match 'Ignored the following versions that require a different python version|No matching distribution|Requires-Python') {
    Write-Host ""
    Write-Host "判断：Python 版本不兼容（某些依赖不支持当前解释器）。" -ForegroundColor Yellow
    Write-Host "处理：安装 Python 3.11/3.12 后删除 .venv 重跑；或直接运行 install.ps1 -Lite" -ForegroundColor Yellow
  }
  Write-Host ""
  Write-Host "完整日志：$pipLog" -ForegroundColor Yellow
  exit 1
}

# 4) 生成 .env
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
  $secret = -join ((1..48) | ForEach-Object { 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'[(Get-Random -Maximum 56)] })
  @"
# 本机配置，勿外传
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

DILIGENCE_SECRET=$secret
DILIGENCE_ADMIN_EMAIL=admin
DILIGENCE_ADMIN_PASSWORD=

DILIGENCE_CREDITS_PER_RUN=10
DILIGENCE_REGISTER_BONUS=100
"@ | Set-Content -Path $envFile -Encoding utf8
  Write-Host "已生成 .env（管理员初始密码将在首次启动时随机生成并打印）" -ForegroundColor Green
} else {
  Write-Host ".env 已存在，未覆盖"
}

# 5) 检查前端产物
if (-not (Test-Path (Join-Path $root 'frontend\dist\index.html'))) {
  Write-Host "缺少前端产物 frontend\dist。请确认压缩包完整，或让提供方重新打包。" -ForegroundColor Red
  exit 1
}

Write-Host ""
Write-Host "安装完成。" -ForegroundColor Green
Write-Host "下一步："
Write-Host "  1. 用记事本打开 .env，把 DEEPSEEK_API_KEY 填上（不填可跑演示模式）"
Write-Host "  2. 双击 start.cmd 启动，浏览器打开 http://127.0.0.1:$Port"
Write-Host ""

if ($Run) {
  Write-Host "正在启动..." -ForegroundColor Cyan
  & (Join-Path $root 'scripts\start.ps1') -Port $Port
}
exit 0
