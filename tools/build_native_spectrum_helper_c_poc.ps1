param(
    [string]$OutPath = "$env:TEMP\native_spectrum_helper_c_poc.exe",
    [switch]$SkipMsvcBootstrap
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$src = Join-Path $repoRoot "tools\native_spectrum_helper_c_poc.c"
$outDir = Split-Path -Parent $OutPath
if (-not (Test-Path -LiteralPath $outDir)) {
    New-Item -ItemType Directory -Path $outDir | Out-Null
}

function Invoke-Build {
    param(
        [string]$Compiler,
        [string[]]$CompilerArgs
    )
    & $Compiler @CompilerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "build failed via $Compiler (exit=$LASTEXITCODE)"
    }
    if (-not (Test-Path -LiteralPath $OutPath)) {
        throw "compiler exited successfully but output was not created: $OutPath"
    }
}

function Get-VsDevCmdPath {
    $vswhereCandidates = @()
    if (${env:ProgramFiles(x86)}) {
        $vswhereCandidates += Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    }
    if ($env:ProgramFiles) {
        $vswhereCandidates += Join-Path $env:ProgramFiles "Microsoft Visual Studio\Installer\vswhere.exe"
    }
    foreach ($vswhere in $vswhereCandidates) {
        if (-not (Test-Path -LiteralPath $vswhere)) {
            continue
        }
        try {
            $installPath = & $vswhere `
                -latest `
                -products * `
                -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
                -property installationPath 2>$null
            if ($LASTEXITCODE -ne 0) {
                continue
            }
            $installPath = ($installPath | Select-Object -First 1).Trim()
            if (-not $installPath) {
                continue
            }
            $vsDevCmd = Join-Path $installPath "Common7\Tools\VsDevCmd.bat"
            if (Test-Path -LiteralPath $vsDevCmd) {
                return $vsDevCmd
            }
        } catch {
            continue
        }
    }
    return $null
}

function Invoke-MsvcBootstrapReentry {
    param(
        [string]$VsDevCmdPath,
        [string]$OutputPath
    )
    $tempCmd = Join-Path $env:TEMP ("tz_player_build_native_helper_" + [guid]::NewGuid().ToString("N") + ".cmd")
    $scriptPath = $PSCommandPath
    $cmdContents = @(
        "@echo off"
        "call ""$VsDevCmdPath"" -host_arch=x64 -arch=x64 >nul"
        "if errorlevel 1 exit /b %errorlevel%"
        "powershell -NoProfile -ExecutionPolicy Bypass -File ""$scriptPath"" -OutPath ""$OutputPath"" -SkipMsvcBootstrap"
        "exit /b %errorlevel%"
    ) -join [Environment]::NewLine
    Set-Content -LiteralPath $tempCmd -Value $cmdContents -Encoding ASCII
    try {
        $bootstrapOutput = & cmd.exe /d /c $tempCmd
        if ($bootstrapOutput) {
            $bootstrapOutput | ForEach-Object { Write-Host $_ }
        }
        if ($LASTEXITCODE -ne 0) {
            throw "MSVC bootstrap via VsDevCmd failed (exit=$LASTEXITCODE)"
        }
        return $true
    } finally {
        Remove-Item -LiteralPath $tempCmd -Force -ErrorAction SilentlyContinue
    }
}

$cl = Get-Command cl.exe -ErrorAction SilentlyContinue
if ($cl) {
    Invoke-Build -Compiler $cl.Source -CompilerArgs @(
        "/nologo",
        "/O2",
        "/W3",
        "/D_CRT_SECURE_NO_WARNINGS",
        "/Fe:$OutPath",
        $src
    )
    Write-Output "built=$OutPath (compiler=cl.exe)"
    exit 0
}

if (-not $SkipMsvcBootstrap) {
    $vsDevCmd = Get-VsDevCmdPath
    if ($vsDevCmd) {
        if (Invoke-MsvcBootstrapReentry -VsDevCmdPath $vsDevCmd -OutputPath $OutPath) {
            exit 0
        }
    }
}

$gcc = Get-Command gcc.exe -ErrorAction SilentlyContinue
if ($gcc) {
    Invoke-Build -Compiler $gcc.Source -CompilerArgs @(
        "-O2",
        "-Wall",
        "-Wextra",
        "-std=c11",
        "-o",
        $OutPath,
        $src,
        "-lm"
    )
    Write-Output "built=$OutPath (compiler=gcc.exe)"
    exit 0
}

$clang = Get-Command clang.exe -ErrorAction SilentlyContinue
if ($clang) {
    Invoke-Build -Compiler $clang.Source -CompilerArgs @(
        "-O2",
        "-Wall",
        "-Wextra",
        "-std=c11",
        "-o",
        $OutPath,
        $src,
        "-lm"
    )
    Write-Output "built=$OutPath (compiler=clang.exe)"
    exit 0
}

throw "No supported C compiler found (tried cl.exe, gcc.exe, clang.exe). If MSVC Build Tools is installed, try Developer PowerShell for VS or ensure VsDevCmd.bat is present for auto-bootstrap."
