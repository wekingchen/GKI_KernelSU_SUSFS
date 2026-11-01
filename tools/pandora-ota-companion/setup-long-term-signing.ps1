#Requires -Version 5.1
<#
在本地解压签名私钥备份后，从该解压目录运行此脚本。
仅将四项 GitHub Actions Secrets 发送给指定私有/公共仓库，不上传文件到代码分支。
必须先安装 GitHub CLI 并使用本人 GitHub 账户 gh auth login。
#>
param(
    [string]$Repo = "wekingchen/GKI_KernelSU_SUSFS"
)
$ErrorActionPreference = "Stop"
if ($Repo -ne "wekingchen/GKI_KernelSU_SUSFS") {
    throw "为避免错误授权，本脚本仅支持 wekingchen/GKI_KernelSU_SUSFS"
}
$ghCommand = Get-Command gh -ErrorAction SilentlyContinue
if (-not $ghCommand) {
    throw "缺少 GitHub CLI。请先安装 gh，再运行 gh auth login。"
}
& $ghCommand.Source auth status 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "当前没有可用的 GitHub CLI 授权。请先执行 gh auth login。"
}
$workdir = Split-Path -Parent $MyInvocation.MyCommand.Path
$keyFile = Join-Path $workdir "pandora-ota-companion-signing.p12"
$base64File = Join-Path $workdir "PANDORA_OTA_SIGNING_KEYSTORE_B64.txt"
if (-not (Test-Path -LiteralPath $keyFile) -or -not (Test-Path -LiteralPath $base64File)) {
    throw "签名备份不完整：请直接从私密签名备份 ZIP 解压全套文件。"
}
$expectedBytes = [System.Convert]::FromBase64String(
    [System.IO.File]::ReadAllText($base64File).Trim()
)
$actualBytes = [System.IO.File]::ReadAllBytes($keyFile)
if ($actualBytes.Length -lt 1024 -or $expectedBytes.Length -ne $actualBytes.Length) {
    throw "本地签名密钥文件与备份 Base64 数据不一致"
}
for ($i = 0; $i -lt $actualBytes.Length; $i++) {
    if ($actualBytes[$i] -ne $expectedBytes[$i]) {
        throw "本地签名密钥文件与备份 Base64 数据不一致"
    }
}

$names = @(
    "PANDORA_OTA_SIGNING_KEYSTORE_B64",
    "PANDORA_OTA_STORE_PASSWORD",
    "PANDORA_OTA_KEY_ALIAS",
    "PANDORA_OTA_KEY_PASSWORD"
)
foreach ($name in $names) {
    $file = Join-Path $workdir ($name + ".txt")
    if (-not (Test-Path -LiteralPath $file)) {
        throw "备份缺少文件：$name.txt"
    }
    $value = [System.IO.File]::ReadAllText($file).TrimEnd([char]13, [char]10)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "备份密钥值为空：$name"
    }
    # Send from stdin to avoid exposing credentials in command-line arguments, output or shell history.
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $ghCommand.Source
    $start.Arguments = "secret set $name --repo $Repo --app actions"
    $start.UseShellExecute = $false
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.CreateNoWindow = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw "无法启动 gh" }
        $process.StandardInput.Write($value)
        $process.StandardInput.Close()
        $null = $process.StandardOutput.ReadToEnd()
        $null = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "设置 $name 失败（exit=$($process.ExitCode)），请检查 gh auth 权限"
        }
        Write-Host "[成功] 已配置 $name（内容不显示）"
    } finally {
        $process.Dispose()
        $value = $null
    }
}
$namesFound = & $ghCommand.Source secret list --repo $Repo --app actions --json name |
    ConvertFrom-Json
foreach ($name in $names) {
    if (@($namesFound | Where-Object { $_.name -eq $name }).Count -ne 1) {
        throw "GitHub 没有确认该 Secret：$name"
    }
}
Write-Host ""
Write-Host "[完成] 4 个 Actions Secrets 均已在 GitHub 确认存在。"
Write-Host "私钥未写入仓库代码、Release 或 Actions 日志。"
Write-Host "请妥善离线保管本目录；不要删除唯一的 p12/密码备份。"
Write-Host "告知 ChatGPT '四项 signing secrets 已配置'，即可触发独立 APK 工作流验证正式签名。"
