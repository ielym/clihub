# =============================================================================
# wireguard-easy :: Windows 一键连接（管理员运行）
# 用法: 右键"以管理员身份运行" onekey-connect.bat
#       或  PowerShell(管理员):  .\onekey-connect.ps1 -ConfigPath .\client.conf
# 功能: ① 检查/安装 WireGuard 客户端  ② 导入隧道  ③ 启动连接
# =============================================================================
[CmdletBinding()]
param(
    [string]$ConfigPath = "",
    [string]$TunnelName = ""
)

$ErrorActionPreference = "Stop"

# --- 自举为管理员 ---------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "需要管理员权限，正在请求提升..." -ForegroundColor Yellow
    $launchArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($ConfigPath) { $launchArgs += " -ConfigPath `"$ConfigPath`"" }
    if ($TunnelName) { $launchArgs += " -TunnelName `"$TunnelName`"" }
    Start-Process powershell -Verb RunAs -ArgumentList $launchArgs
    exit
}

# --- 定位配置文件 ---------------------------------------------------------
if (-not $ConfigPath) {
    $candidates = @(
        (Join-Path $PSScriptRoot "wireguard-client.conf"),
        (Join-Path (Get-Location) "wireguard-client.conf")
    )
    foreach ($c in $candidates) { if (Test-Path $c) { $ConfigPath = $c; break } }
}
if (-not $ConfigPath -or -not (Test-Path $ConfigPath)) {
    Write-Host "❌ 找不到配置文件。用法: .\onekey-connect.ps1 -ConfigPath <client.conf>" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
}
$ConfigPath = (Resolve-Path $ConfigPath).Path

# --- 1. 检查/安装 WireGuard 客户端 ----------------------------------------
$wgExe = "$env:ProgramFiles\WireGuard\WireGuard.exe"
if (-not (Test-Path $wgExe)) {
    Write-Host "未检测到 WireGuard 客户端，尝试安装..." -ForegroundColor Yellow
    # 优先 winget，失败则官方安装包
    $installed = $false
    try {
        winget install --id WireGuard.WireGuard -e --accept-source-agreements --accept-package-agreements --silent | Out-Null
        $installed = $true
    } catch { Write-Host "winget 安装失败，改用官方安装包..." -ForegroundColor Yellow }
    if (-not $installed) {
        $exe = Join-Path $env:TEMP "wireguard-installer.exe"
        Invoke-WebRequest -Uri "https://download.wireguard.com/windows-client/wireguard-installer.exe" -OutFile $exe
        Start-Process -FilePath $exe -ArgumentList "/qn" -Wait
    }
    if (-not (Test-Path $wgExe)) {
        Write-Host "❌ 客户端安装失败，请手动安装后重试" -ForegroundColor Red
        Read-Host "按回车退出"; exit 1
    }
    Write-Host "✅ WireGuard 客户端已安装" -ForegroundColor Green
}

# --- 2. 导入隧道（服务化，免 GUI 手工操作） --------------------------------
if (-not $TunnelName) {
    $TunnelName = [IO.Path]::GetFileNameWithoutExtension($ConfigPath)
    $TunnelName = $TunnelName -replace '[^a-zA-Z0-9_-]', '-'
}
& $wgExe /installtunnelservice $ConfigPath 2>&1 | Out-Null
Start-Sleep -Seconds 2

# --- 3. 启动隧道服务 -------------------------------------------------------
$svc = "WireGuardTunnel`$$TunnelName"
$s = Get-Service -Name $svc -ErrorAction SilentlyContinue
if (-not $s) {
    Write-Host "❌ 隧道服务 $svc 未创建，请检查配置" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
}
if ($s.Status -ne "Running") { Start-Service $svc }
Start-Sleep -Seconds 3
$s = Get-Service -Name $svc

if ($s.Status -eq "Running") {
    Write-Host ""
    Write-Host "✅ 隧道已启动: $TunnelName" -ForegroundColor Green
    Write-Host "   隧道 IP: 10.0.0.2（见配置文件 Address）"
    Write-Host "   验证    : ping 10.0.0.1"
    Write-Host "   停止    : 服务管理器停止 $svc，或 WireGuard App 里关闭"
} else {
    Write-Host "❌ 隧道启动失败，查看事件日志: $svc" -ForegroundColor Red
}
Read-Host "按回车退出"
