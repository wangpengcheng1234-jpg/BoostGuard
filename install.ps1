# BoostGuard 安装脚本
# 用法：右键 install.ps1 -> 使用 PowerShell 运行（或：powershell -ExecutionPolicy Bypass -File install.ps1）
# 需要与 BoostGuard.exe / boostguard.ico / boostguard_red.ico 放在同一目录。

$ErrorActionPreference = 'Stop'
$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $src 'BoostGuard.exe'

if (-not (Test-Path $exe)) {
    [System.Windows.Forms.MessageBox]::Show("未找到 BoostGuard.exe，请把本脚本与程序文件放在同一目录后重试。", "BoostGuard 安装", 'OK', 'Error') | Out-Null
    exit 1
}

$installDir = 'D:\BoostGuard'
New-Item -ItemType Directory -Force -Path $installDir | Out-Null

# 复制程序与图标
Copy-Item $exe $installDir -Force
foreach ($f in 'boostguard.ico', 'boostguard_red.ico') {
    $p = Join-Path $src $f
    if (Test-Path $p) { Copy-Item $p $installDir -Force }
}

$ws = New-Object -ComObject WScript.Shell

# 开始菜单快捷方式（默认总是创建）
$startDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$s = $ws.CreateShortcut((Join-Path $startDir 'BoostGuard.lnk'))
$s.TargetPath = (Join-Path $installDir 'BoostGuard.exe')
$s.WorkingDirectory = $installDir
$s.IconLocation = (Join-Path $installDir 'BoostGuard.exe') + ',0'
$s.Description = '关闭 CPU Boost 降低温度'
$s.Save()

# 询问是否创建桌面快捷方式
$r1 = $ws.Popup('是否在桌面创建快捷方式？', 0, 'BoostGuard 安装', 4)   # 4 = 是/否
if ($r1 -eq 6) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $d = $ws.CreateShortcut((Join-Path $desktop 'BoostGuard.lnk'))
    $d.TargetPath = (Join-Path $installDir 'BoostGuard.exe')
    $d.WorkingDirectory = $installDir
    $d.IconLocation = (Join-Path $installDir 'BoostGuard.exe') + ',0'
    $d.Description = '关闭 CPU Boost 降低温度'
    $d.Save()
}

# 询问是否开机自启
$r2 = $ws.Popup('是否开机自动运行？', 0, 'BoostGuard 安装', 4)
if ($r2 -eq 6) {
    New-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' `
        -Name 'BoostGuard' -Value ('"{0}"' -f (Join-Path $installDir 'BoostGuard.exe')) `
        -PropertyType String -Force | Out-Null
}

# 启动程序
Start-Process (Join-Path $installDir 'BoostGuard.exe')

$ws.Popup('BoostGuard 安装完成，已开始运行。', 0, 'BoostGuard 安装', 0) | Out-Null
