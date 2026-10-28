# LawLens 临时公网发布（Cloudflare 快速隧道，免备案、免账号）
#
# 用途：让对方先在公网试用；链接是临时的，关掉窗口即失效。
# 用法：
#   powershell -ExecutionPolicy Bypass -File .\deploy\publish.ps1
#   powershell -ExecutionPolicy Bypass -File .\deploy\publish.ps1 -Port 8000
#
# 做三件事：
#   1. 强制安全开关：关闭自助注册、cookie 只走 HTTPS
#   2. 若本机 8000 没有服务，先拉起来
#   3. 起 cloudflared 隧道，打印 https 地址

param(
  [int]$Port = 8000,
  [string]$Cloudflared
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

# 1) 配置
$envFile = Join-Path $root '.env'
if (Test-Path $envFile) {
  Get-Content $envFile -Encoding utf8 | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
    $i = $_.IndexOf('='); if ($i -lt 1) { return }
    [Environment]::SetEnvironmentVariable($_.Substring(0, $i).Trim(), $_.Substring($i + 1).Trim(), 'Process')
  }
}
# 公网必须：关注册、cookie 只走 HTTPS
$env:DILIGENCE_ALLOW_REGISTER = '0'
$env:DILIGENCE_COOKIE_SECURE = '1'
$env:PYTHONIOENCODING = 'utf-8'

# 2) 本地服务
$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
  Write-Host "本地 $Port 未监听，启动服务..." -ForegroundColor Yellow
  $py = Join-Path $root '.venv\Scripts\python.exe'
  if (-not (Test-Path $py)) { throw "找不到 $py，请先运行 install.ps1" }
  Start-Process -FilePath $py -ArgumentList '-m','uvicorn','app.main:app','--app-dir','backend','--host','127.0.0.1','--port',"$Port" `
    -WorkingDirectory $root -WindowStyle Minimized
  Start-Sleep -Seconds 6
} else {
  Write-Host "本地服务已在 $Port 运行" -ForegroundColor Green
}

# 2.1) 校验安全开关是否真的生效（旧进程不会读到新的环境变量）
try {
  $h = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 5
  if ($h.register_open -eq $true) {
    Write-Host "拒绝发布：当前服务仍允许自助注册。" -ForegroundColor Red
    Write-Host "很可能是 $Port 端口上还跑着旧进程。先停掉它，再重新运行本脚本。" -ForegroundColor Red
    exit 1
  }
  Write-Host "安全开关已生效（register_open=false）" -ForegroundColor Green
} catch {
  Write-Host "健康检查失败，继续尝试建隧道：$($_.Exception.Message)" -ForegroundColor Yellow
}

# 3) 隧道
if (-not $Cloudflared) { $Cloudflared = Join-Path $PSScriptRoot 'bin\cloudflared.exe' }
if (-not (Test-Path $Cloudflared)) { throw "找不到 cloudflared：$Cloudflared" }

$log = Join-Path $env:TEMP "lawlens-tunnel-$Port.log"
if (Test-Path $log) { Remove-Item $log -Force }

Write-Host "建立公网隧道..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $Cloudflared `
  -ArgumentList 'tunnel','--url',"http://127.0.0.1:$Port",'--no-autoupdate' `
  -RedirectStandardError $log -RedirectStandardOutput "$log.out" -PassThru -WindowStyle Hidden

$url = $null
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 800
  if (Test-Path $log) {
    $hit = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches -ErrorAction SilentlyContinue
    if ($hit) { $url = $hit.Matches[0].Value; break }
  }
}

if (-not $url) {
  Write-Host "没能拿到公网地址，看日志：$log" -ForegroundColor Red
  Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
  exit 1
}

Write-Host ""
Write-Host "公网地址：$url" -ForegroundColor Green
Write-Host "（临时链接，关掉本窗口或重启电脑即失效；重启后地址会变）" -ForegroundColor DarkGray
Write-Host "安全设置：已关闭自助注册，cookie 仅走 HTTPS"
Write-Host ""
Write-Host "按 Ctrl+C 停止隧道。"

try {
  Wait-Process -Id $proc.Id
} finally {
  Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
