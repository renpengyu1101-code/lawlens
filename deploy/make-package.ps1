# 打包「试用版」压缩包：解压 → 运行 install.ps1 即可
#
# 用法（在 diligence-platform 目录）：
#   powershell -ExecutionPolicy Bypass -File .\deploy\make-package.ps1
#
# 产物：dist-packages\lawlens-trial-<日期>.zip
#
# 包含：后端代码、前端构建产物、启动/运维脚本、脱敏样例、安装脚本
# 排除：.venv、node_modules、backend/data（含真实数据）、.env（含密钥）

param(
  [string]$OutDir = 'dist-packages',
  [switch]$WithWheels      # 附带离线依赖（体积增大，目标机无需外网）
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$stamp = Get-Date -Format 'yyyyMMdd'
$stage = Join-Path $env:TEMP "lawlens-pack-$stamp"
$pkg = Join-Path $stage 'lawlens-trial'

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $pkg | Out-Null

function Copy-Tree([string]$from, [string]$to, [string[]]$excludeDirs = @(), [string[]]$excludeFiles = @()) {
  New-Item -ItemType Directory -Force -Path $to | Out-Null
  Get-ChildItem $from -Force | ForEach-Object {
    if ($_.PSIsContainer) {
      if ($excludeDirs -contains $_.Name) { return }
      Copy-Tree $_.FullName (Join-Path $to $_.Name) $excludeDirs $excludeFiles
    } else {
      if ($excludeFiles -contains $_.Name) { return }
      if ($_.Extension -in @('.pyc')) { return }
      Copy-Item $_.FullName (Join-Path $to $_.Name)
    }
  }
}

Write-Host "收集文件..."
# 后端（去掉 data / 缓存）
Copy-Tree (Join-Path $root 'backend') (Join-Path $pkg 'backend') @('data', '__pycache__') @()
# 前端只带 dist
Copy-Tree (Join-Path $root 'frontend\dist') (Join-Path $pkg 'frontend\dist')
# 运维脚本
Copy-Tree (Join-Path $root 'scripts') (Join-Path $pkg 'scripts') @('__pycache__') @('ui_check.mjs','ui_account_check.mjs','ui_progress_check.mjs','ui_review_jump_check.mjs','ui_workbench_check.mjs','ui_dialog_check.mjs','ui_composer_check.mjs','ui_footer_check.mjs','shot_versions.mjs','check_score.py','find_demo_group.py','fix_escapes.py','rename_issue_term.py','seed_case_demo.py','smoke_test.py','test_external.py','test_scoring.py','make_case.py','make_samples.py')
# 样例材料
foreach ($s in @('脱敏样例-澄海精工-2026-10', '虚构材料-澜川精密-2026-10', '虚构测试样本')) {
  $src = Join-Path $root "samples\$s"
  if (Test-Path $src) { Copy-Tree $src (Join-Path $pkg "samples\$s") }
}
# 根目录文件
foreach ($f in @('start.cmd', 'README.md', '.env.example')) {
  if (Test-Path (Join-Path $root $f)) { Copy-Item (Join-Path $root $f) (Join-Path $pkg $f) }
}
# 安装脚本与精简依赖
Copy-Item (Join-Path $root 'deploy\install.ps1') (Join-Path $pkg 'install.ps1')
Copy-Item (Join-Path $root 'deploy\requirements-lite.txt') (Join-Path $pkg 'backend\requirements-lite.txt')

# 可选：离线依赖
if ($WithWheels) {
  Write-Host "下载离线依赖（较慢）..."
  $wh = Join-Path $pkg 'wheels'
  New-Item -ItemType Directory -Force -Path $wh | Out-Null
  & (Join-Path $root '.venv\Scripts\python.exe') -m pip download -r (Join-Path $root 'backend\requirements.txt') -d $wh --quiet
}

# 试用说明
$trialReadme = @"
# LawLens 试用版

## 三步跑起来

1. 装 Python 3.11/3.12（安装时勾选 Add to PATH）：https://www.python.org/downloads/
2. 在解压目录里打开 PowerShell，执行：
   `powershell -ExecutionPolicy Bypass -File .\install.ps1`
   （想省 200MB、不要 OCR：加 -Lite）
3. 用记事本打开生成的 .env，填 DEEPSEEK_API_KEY；然后双击 start.cmd

浏览器打开 http://127.0.0.1:8000

## 第一次进来

- 管理员账号在**启动窗口**里打印（随机密码，只显示一次）
- 上传 samples\脱敏样例-澄海精工-2026-10 整个目录，点「开始核查」
- 跑完对照该目录下 README.md 的 12 条埋点，看命中了几条

## 说明

- 数据只存在本机 `backend\data\`，删除整个目录即清空
- 没填 API Key 也能跑，但那是规则引擎（演示模式），结论不代表模型效果
- 正文会发给 DeepSeek；真实客户材料请先脱敏
"@
$trialReadme | Set-Content -Path (Join-Path $pkg 'README-试用.md') -Encoding utf8

# 压缩
$zip = Join-Path $root "$OutDir\lawlens-trial-$stamp.zip"
New-Item -ItemType Directory -Force -Path (Join-Path $root $OutDir) | Out-Null
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $pkg -DestinationPath $zip -CompressionLevel Optimal

$size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
$files = (Get-ChildItem $pkg -Recurse -File | Measure-Object).Count
Write-Host ""
Write-Host "打包完成：$zip（$size MB，$files 个文件）" -ForegroundColor Green
Write-Host "对方需要：Windows + Python 3.11/3.12；解压后运行 install.ps1"
Remove-Item $stage -Recurse -Force
