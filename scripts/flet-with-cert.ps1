# Run the Flet CLI with SSL_CERT_FILE set from certifi (Windows / PowerShell).
# Usage from project root:
#   .\scripts\flet-with-cert.ps1 build apk
#   .\scripts\flet-with-cert.ps1 build aab
#
# Flutter invokes `git` (e.g. bin\internal\update_engine_version.ps1). If Flutter/Git
# are installed but not on PATH for this shell, prepend standard locations so the
# build does not fail with "Unable to determine engine version".
function Add-DirToPathFront {
    param([string]$Dir)
    if ($Dir -and (Test-Path $Dir)) {
        $env:Path = "$Dir;$env:Path"
    }
}

# Flutter SDK bin (FLUTTER_ROOT or newest version under %USERPROFILE%\flutter\*)
if ($env:FLUTTER_ROOT) {
    Add-DirToPathFront (Join-Path $env:FLUTTER_ROOT 'bin')
} else {
    $flutterBase = Join-Path $env:USERPROFILE 'flutter'
    if (Test-Path $flutterBase) {
        $sdk = Get-ChildItem -Path $flutterBase -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName 'bin\flutter.bat') } |
            Sort-Object { [version]($_.Name -replace '^(\d+\.\d+\.\d+).*$', '$1') } -Descending |
            Select-Object -First 1
        if ($sdk) { Add-DirToPathFront (Join-Path $sdk.FullName 'bin') }
    }
}

# Git (required by Flutter; prefer cmd so git.exe resolves)
$gitDirs = @(
    (Join-Path $env:ProgramFiles 'Git\cmd'),
    (Join-Path $env:ProgramFiles 'Git\bin'),
    (Join-Path ${env:ProgramFiles(x86)} 'Git\cmd'),
    (Join-Path $env:LocalAppData 'Programs\Git\cmd')
)
foreach ($d in $gitDirs) {
    if (Test-Path (Join-Path $d 'git.exe')) {
        Add-DirToPathFront $d
        break
    }
}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$gitOk = $null -ne (Get-Command git -ErrorAction SilentlyContinue)
if (-not $gitOk) {
    Write-Host @"
flet-with-cert: 'git' was not found on PATH after adding common install locations.
Flutter needs Git to resolve the engine version. Install Git for Windows and ensure
'git' is on your PATH, then retry:
  https://git-scm.com/download/win
"@ -ForegroundColor Yellow
}

$VenvActivate = Join-Path $Root '.venv\Scripts\Activate.ps1'
if (Test-Path $VenvActivate) {
    & $VenvActivate
}
# Rich/Flet emoji output fails on cp1252 consoles (UnicodeEncodeError on checkmark U+2705).
$env:PYTHONUTF8 = '1'
# Gradle/JVM: prefer IPv4 when repo.maven.apache.org or Maven Central fail on some networks.
if ($env:GRADLE_OPTS) {
    $env:GRADLE_OPTS = "$env:GRADLE_OPTS -Djava.net.preferIPv4Stack=true"
} else {
    $env:GRADLE_OPTS = '-Djava.net.preferIPv4Stack=true'
}
$env:SSL_CERT_FILE = (python -c "import certifi; print(certifi.where())").Trim()
$env:REQUESTS_CA_BUNDLE = $env:SSL_CERT_FILE
python (Join-Path $PSScriptRoot 'flet_with_ble_gatt.py') @args
exit $LASTEXITCODE
