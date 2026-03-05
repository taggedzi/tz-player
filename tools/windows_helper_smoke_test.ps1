param(
    [string]$TrackPath = "E:\Home\Documents\Programming\tz-player\.local\perf_media\Feast Of Foes 2.mp3",
    [string]$HelperPath = "$env:TEMP\native_spectrum_helper_c_poc.exe",
    [switch]$BuildIfMissing = $true,
    [switch]$ForceBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$buildScript = Join-Path $PSScriptRoot "build_native_spectrum_helper_c_poc.ps1"
$helperSource = Join-Path $PSScriptRoot "native_spectrum_helper_c_poc.c"

if (-not (Test-Path -LiteralPath $TrackPath)) {
    throw "Track not found: $TrackPath"
}

function Invoke-HelperBuild {
    param([string]$Reason)
    Write-Host "$Reason -> building: $HelperPath"
    & $buildScript -OutPath $HelperPath
    if ($LASTEXITCODE -ne 0) {
        throw "Helper build failed (exit=$LASTEXITCODE)"
    }
}

if ($ForceBuild) {
    Invoke-HelperBuild -Reason "helper_rebuild_forced"
}
elseif ((-not (Test-Path -LiteralPath $HelperPath)) -and $BuildIfMissing) {
    Invoke-HelperBuild -Reason "helper_missing"
}
elseif ((Test-Path -LiteralPath $HelperPath) -and $BuildIfMissing) {
    $helperMtime = (Get-Item -LiteralPath $HelperPath).LastWriteTimeUtc
    $sourceMtime = (Get-Item -LiteralPath $helperSource).LastWriteTimeUtc
    $buildScriptMtime = (Get-Item -LiteralPath $buildScript).LastWriteTimeUtc
    if (($sourceMtime -gt $helperMtime) -or ($buildScriptMtime -gt $helperMtime)) {
        Invoke-HelperBuild -Reason "helper_stale"
    }
}

if (-not (Test-Path -LiteralPath $HelperPath)) {
    throw "Helper not found: $HelperPath"
}

$request = @{
    schema = "tz_player.native_spectrum_helper_request.v1"
    track_path = $TrackPath
    spectrum = @{
        mono_target_rate_hz = 11025
        hop_ms = 40
        band_count = 8
        max_frames = 64
    }
    beat = @{
        hop_ms = 40
        max_frames = 64
    }
    waveform_proxy = @{
        hop_ms = 20
        max_frames = 128
    }
} | ConvertTo-Json -Depth 4 -Compress

Write-Host "helper=$HelperPath"
Write-Host "track=$TrackPath"

$stdinFile = Join-Path $env:TEMP ("tz_player_helper_stdin_" + [guid]::NewGuid().ToString("N") + ".json")
$stdoutFile = Join-Path $env:TEMP ("tz_player_helper_stdout_" + [guid]::NewGuid().ToString("N") + ".txt")
$stderrFile = Join-Path $env:TEMP ("tz_player_helper_stderr_" + [guid]::NewGuid().ToString("N") + ".txt")

try {
    $request | Set-Content -LiteralPath $stdinFile -Encoding UTF8

    $proc = Start-Process `
        -FilePath $HelperPath `
        -NoNewWindow `
        -PassThru `
        -Wait `
        -RedirectStandardInput $stdinFile `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile

    $exitCode = $proc.ExitCode
    $raw = if (Test-Path -LiteralPath $stdoutFile) {
        Get-Content -LiteralPath $stdoutFile -Raw
    } else {
        ""
    }
    $stderrText = if (Test-Path -LiteralPath $stderrFile) {
        Get-Content -LiteralPath $stderrFile -Raw
    } else {
        ""
    }

    if ($exitCode -ne 0) {
        if ($stderrText) {
            Write-Host ""
            Write-Host "Helper stderr:" -ForegroundColor Yellow
            Write-Host $stderrText
        }
        throw "Helper exited with code $exitCode"
    }
    if (-not $raw) {
        if ($stderrText) {
            Write-Host ""
            Write-Host "Helper stderr:" -ForegroundColor Yellow
            Write-Host $stderrText
        }
        throw "Helper returned empty output"
    }
} finally {
    Remove-Item -LiteralPath $stdinFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stdoutFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stderrFile -Force -ErrorAction SilentlyContinue
}

if (-not $raw) {
    throw "Helper returned empty output"
}

$payload = $raw | ConvertFrom-Json

Write-Host ""
Write-Host "Smoke Test Summary"
Write-Host "schema=$($payload.schema)"
Write-Host "helper_version=$($payload.helper_version)"
Write-Host "duration_ms=$($payload.duration_ms)"
Write-Host "spectrum_frames=$($payload.frames.Count)"
Write-Host "beat_frames=$($payload.beat.frames.Count)"
Write-Host "waveform_frames=$($payload.waveform_proxy.frames.Count)"
Write-Host ("timings_ms decode={0} spectrum={1} beat={2} waveform={3} total={4}" -f `
    $payload.timings.decode_ms,
    $payload.timings.spectrum_ms,
    $payload.timings.beat_ms,
    $payload.timings.waveform_proxy_ms,
    $payload.timings.total_ms)

Write-Host ""
Write-Host "First frame samples:"
Write-Host ("spectrum={0}" -f (($payload.frames | Select-Object -First 1) | ConvertTo-Json -Compress))
Write-Host ("beat={0}" -f (($payload.beat.frames | Select-Object -First 1) | ConvertTo-Json -Compress))
Write-Host ("waveform={0}" -f (($payload.waveform_proxy.frames | Select-Object -First 1) | ConvertTo-Json -Compress))
