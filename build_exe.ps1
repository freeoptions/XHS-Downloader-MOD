$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$outputPath = Join-Path $projectRoot "build\cxfreeze\XHS-Downloader"

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到项目虚拟环境：$python"
}

Push-Location $projectRoot
try {
    & $python setup.py build_exe --build-exe $outputPath
} finally {
    Pop-Location
}

if ($LASTEXITCODE -ne 0) {
    throw "cx_Freeze 构建失败，退出码：$LASTEXITCODE"
}

$outputExe = Join-Path $outputPath "XHS-Downloader-MOD.exe"
if (-not (Test-Path -LiteralPath $outputExe)) {
    throw "未找到构建产物：$outputExe"
}

Write-Output $outputExe
