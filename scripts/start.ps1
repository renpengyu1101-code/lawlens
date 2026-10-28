# LawLens 启动器（内网试用版）
#
#   .\scripts\start.ps1 -Init          # 首次：生成 .env（随机 SECRET 与管理员密码），打印后退出
#   .\scripts\start.ps1                # 启动，绑定 0.0.0.0，打印内网地址
#   .\scripts\start.ps1 -Port 8080     # 换端口
#   .\scripts\start.ps1 -Mock          # 无 Key 时强制以演示模式启动
#
# 约定：密钥只放 .env，不进代码、不进日志。本脚本只把 .env 读进当前进程的环境变量。

param(
  [int]$Port = 8000,
  [string]$Bind = '0.0.0.0',
  [switch]$Init,
  [switch]$Mock
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $root '.env'

function New-RandomString([int]$len) {
  $bytes = New-Object byte[] $len
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $alphabet = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}

if ($Init -or -not (Test-Path $envFile)) {
  if (Test-Path $envFile) { throw ".env 已存在：要重建请先备份并手动删除 $envFile" }
  $secret = New-RandomString 48
  $content = @"
# 由 scripts/start.ps1 -Init 生成于 $(Get-Date -Format 'yyyy-MM-dd HH:mm')
# 不要提交到版本库
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

DILIGENCE_SECRET=$secret

# 留空：全新数据库首次启动时会随机生成管理员密码并打印一次；
# 已有数据库请用 scripts/set_admin.py 重设，这里的值对已存在的账号无效。
DILIGENCE_ADMIN_EMAIL=admin
DILIGENCE_ADMIN_PASSWORD=

DILIGENCE_CREDITS_PER_RUN=10
DILIGENCE_REGISTER_BONUS=100
"@
  Set-Content -Path $envFile -Value $content -Encoding utf8
  Write-Host "已生成 $envFile（SECRET 已随机化）" -ForegroundColor Green
  Write-Host ""
  Write-Host "还需要两步：" -ForegroundColor Yellow
  Write-Host "  1) 把 DEEPSEEK_API_KEY 填进 .env"
  Write-Host "  2) 已有数据库的话，用 scripts/set_admin.py 重设管理员密码"
  Write-Host "然后运行 .\scripts\start.ps1" -ForegroundColor Yellow
  exit 0
}

Get-Content $envFile -Encoding utf8 | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
  $i = $_.IndexOf('=')
  if ($i -lt 1) { return }
  $k = $_.Substring(0, $i).Trim()
  $v = $_.Substring($i + 1).Trim().Trim('"')
  [Environment]::SetEnvironmentVariable($k, $v, 'Process')
}

if (-not $env:DEEPSEEK_API_KEY -and -not $Mock) {
  throw "DEEPSEEK_API_KEY 为空：要么填进 .env，要么加 -Mock 以演示模式启动（演示模式是规则引擎，不是模型分析）"
}
if ($env:DILIGENCE_SECRET -eq 'please-change-this-in-production' -or -not $env:DILIGENCE_SECRET) {
  Write-Host "警告：DILIGENCE_SECRET 仍是默认值。删掉 .env 重跑 -Init 可重新生成。" -ForegroundColor Yellow
}

$dist = Join-Path $root 'frontend\dist\index.html'
if (-not (Test-Path $dist)) {
  throw "前端未构建：先在 frontend 目录执行 node node_modules/vite/bin/vite.js build（或 pnpm build）"
}

$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "找不到 $py：先按 README 第 2 节建虚拟环境" }

# 优先取有默认网关的网卡（避免报到 VMware/Hyper-V 虚拟网卡上）
$lan = (Get-NetIPConfiguration -ErrorAction SilentlyContinue |
  Where-Object { $_.IPv4DefaultGateway -and $_.IPv4Address } |
  Select-Object -First 1 -ExpandProperty IPv4Address).IPAddress
if (-not $lan) {
  $lan = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -First 1 -ExpandProperty IPAddress
}

$mode = if ($env:DEEPSEEK_API_KEY) { '模型模式（DeepSeek）' } else { '演示模式（规则引擎）' }
Write-Host "LawLens 启动" -ForegroundColor Green
Write-Host "  模式：$mode"
Write-Host "  本机：http://127.0.0.1:$Port"
if ($lan -and $Bind -eq '0.0.0.0') { Write-Host "  内网：http://${lan}:$Port" -ForegroundColor Cyan }
Write-Host "  日志里的 '!' 开头是安全提示，务必看一眼" -ForegroundColor DarkGray
Write-Host ""

$env:PYTHONIOENCODING = 'utf-8'
Push-Location (Join-Path $root 'backend')
try {
  & $py -m uvicorn app.main:app --host $Bind --port $Port
} finally {
  Pop-Location
}
