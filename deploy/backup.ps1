# LawLens 数据备份：SQLite 在线备份 + 上传件/报告打包，保留最近 N 份
#
# 用法：
#   .\deploy\backup.ps1 -DataDir "D:\lawlens\backend\data" -OutDir "E:\backup\lawlens" -Keep 14
#
# 说明：
#   - 数据库用 SQLite 的 .backup 命令，避免直接拷文件出现半写状态
#   - 上传件与报告是普通文件，直接压缩；体积大时改 Robocopy 增量
#   - 退出码 0 = 成功，非 0 = 失败（任务计划程序据此告警）

param(
  [Parameter(Mandatory = $true)][string]$DataDir,
  [Parameter(Mandatory = $true)][string]$OutDir,
  [int]$Keep = 14
)

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = Join-Path $OutDir $stamp

if (-not (Test-Path $DataDir)) { throw "数据目录不存在：$DataDir" }
New-Item -ItemType Directory -Force -Path $target | Out-Null

$db = Join-Path $DataDir 'app.db'
if (-not (Test-Path $db)) { throw "找不到数据库：$db" }

# 1) 在线备份数据库
$py = Get-Command python -ErrorAction SilentlyContinue
$backupSql = "import sqlite3,sys; src=sqlite3.connect(r'$db'); dst=sqlite3.connect(r'$(Join-Path $target 'app.db')'); src.backup(dst); dst.close(); src.close()"
if ($py) {
  & $py.Source -c $backupSql
} else {
  throw "找不到 python，无法做 SQLite 在线备份"
}
Write-Host "数据库已备份 → $target\app.db"

# 2) 打包上传件与报告
$archive = Join-Path $target 'files.zip'
$toZip = @()
foreach ($sub in @('uploads', 'reports')) {
  $p = Join-Path $DataDir $sub
  if (Test-Path $p) { $toZip += (Get-ChildItem $p -Recurse -File) }
}
if ($toZip.Count -gt 0) {
  Compress-Archive -Path $toZip.FullName -DestinationPath $archive -CompressionLevel Optimal
  Write-Host "文件已打包 $($toZip.Count) 个 → $archive"
} else {
  Write-Host "没有上传件或报告需要打包"
}

# 3) 清理旧备份
$old = Get-ChildItem $OutDir -Directory | Sort-Object Name -Descending | Select-Object -Skip $Keep
foreach ($d in $old) {
  Remove-Item $d.FullName -Recurse -Force
  Write-Host "已清理旧备份 $($d.Name)"
}

$size = (Get-ChildItem $target -File | Measure-Object Length -Sum).Sum
Write-Host ("完成：{0}（{1:N1} MB），保留最近 {2} 份" -f $target, ($size / 1MB), $Keep)
exit 0
