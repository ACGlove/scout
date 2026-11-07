# Scout Windows one-click installer.
# Requires Windows PowerShell 5.1+ and Python 3.12 (py launcher or python on PATH).
# This script only runs on Windows; it does not make Scout Linux-compatible.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail {
    param([string]$Message, [int]$Code = 1)
    Write-Host ""
    Write-Host "错误：$Message" -ForegroundColor Red
    exit $Code
}

function Get-PythonCommand {
    $candidates = @()

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $candidates += [pscustomobject]@{
            Exe   = $py.Source
            Args  = @("-3.12")
            Label = "py -3.12"
        }
    }

    foreach ($name in @("python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            $candidates += [pscustomobject]@{
                Exe   = $cmd.Source
                Args  = @()
                Label = $name
            }
        }
    }

    foreach ($candidate in $candidates) {
        try {
            $exe = $candidate.Exe
            $prefix = $candidate.Args
            & $exe @prefix -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        }
        catch {
            # Try the next candidate.
        }
    }

    return $null
}

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Name
    )

    if (-not (Test-Path $Path)) {
        return $null
    }

    $escaped = [regex]::Escape($Name)
    $line = Get-Content -Path $Path |
        Where-Object { $_ -match "^\s*$escaped\s*=" } |
        Select-Object -Last 1

    if (-not $line) {
        return $null
    }

    $value = ($line -split "=", 2)[1]
    $value = $value.Trim()
    $value = $value.Trim([char]'"')
    $value = $value.Trim([char]"'")
    return $value
}

function Test-Placeholder {
    param([string]$Value)
    return (
        [string]::IsNullOrWhiteSpace($Value) -or
        $Value -eq "sk-your-key-here" -or
        $Value -eq "tvly-your-key-here"
    )
}

function Open-EnvEditor {
    param([string]$Path)
    Write-Host "请在记事本中填写真实的 API_KEY 和 TAVILY_API_KEY，保存并关闭记事本后继续。" -ForegroundColor Yellow
    try {
        Start-Process -FilePath "notepad.exe" -ArgumentList "`"$Path`"" -Wait
    }
    catch {
        Fail "无法打开记事本，请手动编辑 $Path 后重新运行 start.bat。" 2
    }
}

if (-not (Test-Path (Join-Path $RepoRoot "src\__main__.py"))) {
    Fail "未找到 src\__main__.py，请确认脚本位于仓库的 scripts 目录中。"
}

$venvDir = Join-Path $RepoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if ((Test-Path $venvDir) -and -not (Test-Path (Join-Path $venvDir "Lib\site-packages"))) {
    Fail "现有 .venv 不完整。请删除 .venv 后重新运行 start.bat。" 2
}

$python = $null
if (Test-Path $venvPython) {
    & $venvPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
    if ($LASTEXITCODE -eq 0) {
        $python = [pscustomobject]@{
            Exe   = $venvPython
            Args  = @()
            Label = "现有 .venv"
        }
    }
    else {
        Fail "现有 .venv 无法使用或低于 Python 3.12。请删除 .venv 后重新运行 start.bat。" 2
    }
}

if (-not $python) {
    Write-Step "检查 Python 3.12"
    $python = Get-PythonCommand
}
if (-not $python) {
    Fail "未找到 Python 3.12。请从 https://www.python.org/downloads/ 安装，并勾选 Add python.exe to PATH。" 1
}
Write-Host "Python: $($python.Label)" -ForegroundColor Green

if ((Test-Path $venvDir) -and -not (Test-Path $venvPython)) {
    Fail "发现不完整的 .venv。请删除 .venv 后重新运行 start.bat。" 2
}

if (-not (Test-Path $venvPython)) {
    Write-Step "创建虚拟环境 .venv"
    $exe = $python.Exe
    $prefix = $python.Args
    & $exe @prefix -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Fail "创建 .venv 失败。请检查 Python 安装和当前目录权限。"
    }
}

& $venvPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) {
    Fail "无法启动 .venv 中的 Python，或版本低于 3.12。请删除 .venv 后重新运行 start.bat。"
}

& $venvPython -m pip --version
if ($LASTEXITCODE -ne 0) {
    Write-Step "初始化 pip"
    & $venvPython -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) {
        Fail "无法在 .venv 中安装 pip。请删除 .venv 后重新运行 start.bat。"
    }
}

$requirements = Join-Path $RepoRoot "requirements.txt"
if (-not (Test-Path $requirements)) {
    Fail "未找到 requirements.txt。"
}

$reqHash = (Get-FileHash -Path $requirements -Algorithm SHA256).Hash
$marker = Join-Path $venvDir ".requirements.sha256"
$markerHash = ""
if (Test-Path $marker) {
    $markerHash = (Get-Content -Path $marker -Raw).Trim()
}

if ($markerHash -ne $reqHash) {
    Write-Step "安装 Python 依赖"
    & $venvPython -m pip install --upgrade pip --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Fail "升级 pip 失败。请检查网络或代理设置。"
    }

    & $venvPython -m pip install -r $requirements --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Fail "安装依赖失败。请检查网络或代理设置后重试。"
    }

    Set-Content -Path $marker -Value $reqHash -Encoding ASCII
}
else {
    Write-Host "依赖已安装，跳过 pip。" -ForegroundColor Green
}

Write-Step "检查 .env"
$envPath = Join-Path $RepoRoot ".env"
$examplePath = Join-Path $RepoRoot "src\.env.example"

if (-not (Test-Path $envPath)) {
    if (-not (Test-Path $examplePath)) {
        Fail "未找到 src\.env.example。"
    }
    Copy-Item -Path $examplePath -Destination $envPath
    Write-Host "已从 src\.env.example 生成 .env。" -ForegroundColor Green
}

$required = @("API_KEY", "TAVILY_API_KEY", "BASE_URL", "MODEL")
$missing = @()
foreach ($name in $required) {
    $value = Get-EnvValue -Path $envPath -Name $name
    if (Test-Placeholder $value) {
        $missing += $name
    }
}

if ($missing.Count -gt 0) {
    Write-Host "以下配置为空或仍是占位符：$($missing -join ', ')" -ForegroundColor Yellow
    Open-EnvEditor -Path $envPath

    $missing = @()
    foreach ($name in $required) {
        $value = Get-EnvValue -Path $envPath -Name $name
        if (Test-Placeholder $value) {
            $missing += $name
        }
    }
}

if ($missing.Count -gt 0) {
    Fail "以下配置仍未填写：$($missing -join ', ')。请编辑 .env 后重新运行 start.bat。" 2
}

$defaults = @{
    "ROOT"            = "./workspace"
    "LLM_TIMEOUT"     = "60"
    "LLM_MAX_RETRIES" = "2"
}
foreach ($name in $defaults.Keys) {
    $value = Get-EnvValue -Path $envPath -Name $name
    if ([string]::IsNullOrWhiteSpace($value)) {
        Add-Content -Path $envPath -Value "`r`n$name=$($defaults[$name])" -Encoding UTF8
        Write-Host "已补充默认配置 $name=$($defaults[$name])。" -ForegroundColor Yellow
    }
}

foreach ($name in @("LLM_TIMEOUT", "LLM_MAX_RETRIES")) {
    $value = Get-EnvValue -Path $envPath -Name $name
    $number = 0
    if (-not [int]::TryParse($value, [ref]$number)) {
        Fail "$name 必须是整数，当前值无法解析。" 2
    }
    if ($name -eq "LLM_TIMEOUT" -and $number -lt 1) {
        Fail "LLM_TIMEOUT 必须大于 0。" 2
    }
    if ($name -eq "LLM_MAX_RETRIES" -and $number -lt 0) {
        Fail "LLM_MAX_RETRIES 不能小于 0。" 2
    }
}

$rootValue = Get-EnvValue -Path $envPath -Name "ROOT"
if ([string]::IsNullOrWhiteSpace($rootValue)) {
    $rootValue = "./workspace"
}
if ([System.IO.Path]::IsPathRooted($rootValue)) {
    $rootPath = $rootValue
}
else {
    $rootPath = Join-Path $RepoRoot $rootValue
}

Write-Step "准备工作区"
try {
    New-Item -ItemType Directory -Force -Path $rootPath | Out-Null
}
catch {
    Fail "无法创建工作区目录 $rootPath：$($_.Exception.Message)" 2
}
Write-Host "工作区：$rootPath" -ForegroundColor Green

Write-Step "预热 tiktoken 编码"
& $venvPython -c "import tiktoken; tiktoken.get_encoding('o200k_base')"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "tiktoken 预热失败；首次运行仍会尝试下载，但需要网络。"
}

Write-Step "准备完成"
Write-Host "以后双击 start.bat 即可启动 Scout。" -ForegroundColor Green
exit 0