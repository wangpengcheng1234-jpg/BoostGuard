# 一键打包 BoostGuard.exe
# 用法：powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$icon = Join-Path $root 'boostguard.ico'

$params = @('--onefile', '--noconsole', '--name', 'BoostGuard',
            '--distpath', (Join-Path $root 'dist'),
            '--workpath', (Join-Path $root 'build'))

if (Test-Path $icon) { $params += @('--icon', $icon) }

pyinstaller @params (Join-Path $root 'src\boost_guard.py')

Write-Host "`n完成：$(Join-Path $root 'dist\BoostGuard.exe')" -ForegroundColor Green
