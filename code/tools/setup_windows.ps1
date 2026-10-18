#Requires -Version 5.1
<#
Prepare the Windows P0 toolchain without running installers or changing PATH.
All downloads and extracted files stay in the project's ignored .tools directory.
Run from any working directory: powershell -File tools/setup_windows.ps1

Sources are the NASM release server, the QEMU Windows publisher linked by qemu.org,
and the official 7-Zip site. SHA-256 pins record the downloaded release bytes;
QEMU's SHA-512 pin also matches the publisher's 20260422.sha512 sidecar:
https://qemu.weilnetz.de/w64/2026/qemu-w64-setup-20260422.sha512
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'This setup script requires 64-bit Windows.'
}

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$toolsRoot = Join-Path $projectRoot '.tools'
$downloadRoot = Join-Path $toolsRoot 'downloads'

function Ensure-LocalDirectory {
    param([Parameter(Mandatory = $true)][string]$Directory)
    $resolved = [IO.Path]::GetFullPath($Directory)
    if ($resolved -ne $toolsRoot -and -not $resolved.StartsWith($toolsRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to write outside $toolsRoot : $resolved"
    }
    # A redirected tools directory would violate the local-only write contract.
    $cursor = $resolved
    while ($cursor.Length -ge $toolsRoot.Length) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Expected an ordinary local directory: $cursor"
            }
        }
        if ($cursor -eq $toolsRoot) { break }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
    New-Item -ItemType Directory -Path $resolved -Force | Out-Null
}

function Get-VerifiedDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string]$Hash,
        [ValidateSet('SHA256', 'SHA512')][string]$Algorithm = 'SHA256'
    )
    $destination = Join-Path $downloadRoot $FileName
    if (Test-Path -LiteralPath $destination) {
        if ((Get-FileHash -LiteralPath $destination -Algorithm $Algorithm).Hash -eq $Hash) {
            Write-Host "Verified cached $FileName ($Algorithm)"
            return $destination
        }
        Write-Warning "Cached $FileName has a different hash; downloading a verified replacement."
    }
    $partial = $destination + '.part'
    Write-Host "Downloading $Url"
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $partial
    $actual = (Get-FileHash -LiteralPath $partial -Algorithm $Algorithm).Hash
    if ($actual -ne $Hash) {
        throw "$Algorithm mismatch for $FileName. Expected $Hash; received $actual. The downloaded file was not executed or extracted."
    }
    Move-Item -LiteralPath $partial -Destination $destination -Force
    Write-Host "Verified $FileName ($Algorithm)"
    return $destination
}

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$NativeArguments = @(),
        [int]$MaximumExitCode = 0
    )
    & $Executable @NativeArguments
    if ($LASTEXITCODE -lt 0 -or $LASTEXITCODE -gt $MaximumExitCode) {
        throw "$Executable exited with code $LASTEXITCODE."
    }
}

Ensure-LocalDirectory $toolsRoot
Ensure-LocalDirectory $downloadRoot
# Windows PowerShell 5.1 may otherwise negotiate an obsolete TLS version.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$nasmArchive = Get-VerifiedDownload `
    -Url 'https://www.nasm.us/pub/nasm/releasebuilds/3.02/win64/nasm-3.02-win64.zip' `
    -FileName 'nasm-3.02-win64.zip' `
    -Hash '161D0BFAFF53C2F9E9F3E69FD0672323EBABAFD1268976A5CEC11BE92A19AEE7'
$qemuArchive = Get-VerifiedDownload `
    -Url 'https://qemu.weilnetz.de/w64/2026/qemu-w64-setup-20260422.exe' `
    -FileName 'qemu-w64-setup-20260422.exe' -Algorithm SHA512 `
    -Hash '64A43C0D39ACDDC9D30D290935A312A2B5C4FA62CFFE6C27090F2A45CA6C8DE0F0E8673E1E5117FB116A8742F86DF92163531AFC23F34758AADFC6D82C1F41A5'
# The small standalone 7zr reader opens 7-Zip's own self-extracting archive.
# Its fixed hash deliberately rejects a future replacement at this mutable URL.
$bootstrap = Get-VerifiedDownload `
    -Url 'https://www.7-zip.org/a/7zr.exe' -FileName '7zr.exe' `
    -Hash '256FECA8E274E5DA655E2A284FABAFD9F554365EB164862089DACD4E8276D282'
$sevenZipArchive = Get-VerifiedDownload `
    -Url 'https://www.7-zip.org/a/7z2604-x64.exe' -FileName '7z2604-x64.exe' `
    -Hash 'D54BF805F9F3704D1E8DB2FA3498AE7EF2DF0312B40B558E7C71C734430A665D'

$sevenZipRoot = Join-Path $toolsRoot '7zip'
$nasmRoot = Join-Path $toolsRoot 'nasm'
$qemuRoot = Join-Path $toolsRoot 'qemu'
Ensure-LocalDirectory $sevenZipRoot
Ensure-LocalDirectory $nasmRoot
Ensure-LocalDirectory $qemuRoot

Write-Host 'Extracting 7-Zip 26.04 (the installer is read as an archive).'
Invoke-CheckedNative -Executable $bootstrap -NativeArguments @('x', $sevenZipArchive, "-o$sevenZipRoot", '-y')
$sevenZip = Join-Path $sevenZipRoot '7z.exe'
Write-Host 'Extracting NASM 3.02.'
Expand-Archive -LiteralPath $nasmArchive -DestinationPath $nasmRoot -Force
Write-Host 'Extracting QEMU 11.0.0 and bundled EDK II firmware (about 1.2 GB).'
# The signed NSIS executable has trailing signature data, which 7-Zip reports
# as warning/exit code 1. Errors (2 or above) are still fatal.
Invoke-CheckedNative -Executable $sevenZip -MaximumExitCode 1 `
    -NativeArguments @('x', '-tNSIS', $qemuArchive, "-o$qemuRoot", '-y', '-x!$PLUGINSDIR')

$nasm = Join-Path $nasmRoot 'nasm-3.02/nasm.exe'
$qemu = Join-Path $qemuRoot 'qemu-system-x86_64.exe'
$firmwareCode = Join-Path $qemuRoot 'share/edk2-x86_64-code.fd'
$firmwareVars = Join-Path $qemuRoot 'share/edk2-i386-vars.fd'
foreach ($requiredFile in @($nasm, $qemu, $firmwareCode, $firmwareVars)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Extraction did not produce the required file: $requiredFile"
    }
}
Invoke-CheckedNative -Executable $nasm -NativeArguments @('--version')
Invoke-CheckedNative -Executable $qemu -NativeArguments @('--version')
Write-Host "NASM: $nasm"
Write-Host "QEMU: $qemu"
Write-Host "UEFI code: $firmwareCode"
Write-Host "UEFI variables template: $firmwareVars"

$linker = $null
if ($env:LLD_LINK) {
    $linkerCommand = Get-Command -Name $env:LLD_LINK -CommandType Application -ErrorAction SilentlyContinue
    if (-not $linkerCommand) { throw 'LLD_LINK points to an unavailable executable.' }
    $linker = $linkerCommand.Source
} else {
    $linkerCommand = Get-Command lld-link.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($linkerCommand) { $linker = $linkerCommand.Source }
    if (-not $linker) {
        $programs = [Environment]::GetFolderPath('ProgramFiles')
        $candidates = @((Join-Path $programs 'LLVM/bin/lld-link.exe'))
        $vsPattern = Join-Path $programs 'Microsoft Visual Studio/*/*/VC/Tools/Llvm/x64/bin/lld-link.exe'
        $candidates += @(Get-ChildItem -Path $vsPattern -File -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -ExpandProperty FullName)
        foreach ($candidate in $candidates) {
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { $linker = $candidate; break }
        }
    }
}
if (-not $linker) {
    throw 'NASM and QEMU are ready. Install official LLVM with LLD from https://github.com/llvm/llvm-project/releases , then set LLD_LINK to its bin/lld-link.exe path in the current shell and rerun this script.'
}
Invoke-CheckedNative -Executable $linker -NativeArguments @('--version')
Write-Host "LLD linker: $linker"
Write-Host 'If the linker is not found by doctor, set it in your current PowerShell session:'
Write-Host ('$env:LLD_LINK = ''' + $linker.Replace("'", "''") + '''')
Write-Host 'Toolchain ready. Run: python tools/build.py doctor; python tools/build.py test'
