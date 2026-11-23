# Removes a per-user Qwik install. No admin unless Qwik itself is running elevated.
param([switch]$Silent)
$AppName = "Qwik"
$bat = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "Uninstall-Qwik.bat"

function Still-Running {
    Get-Process -Name Qwik -ErrorAction SilentlyContinue | ForEach-Object {
        try { $_.Kill() } catch {}
    }
    Start-Sleep -Milliseconds 400
    return [bool](Get-Process -Name Qwik -ErrorAction SilentlyContinue)
}

if (Still-Running) {
    if ($env:QWIK_UNINSTALL_ELEVATED -eq "1") {
        Write-Host "Qwik is still running. End Qwik.exe in Task Manager, then run this again."
        exit 1
    }
    if (-not $Silent) {
        Write-Host "Qwik is running elevated. Approve the prompt to close it."
        Start-Process -FilePath $env:ComSpec -Verb RunAs -ArgumentList "/c", "set QWIK_UNINSTALL_ELEVATED=1&& `"$bat`""
        exit 0
    }
}

# 1) shortcuts: startup + Start Menu folder (new) + legacy root links (old)
$programs = [Environment]::GetFolderPath("Programs")
$startup = [Environment]::GetFolderPath("Startup")
foreach ($lnk in @(
    (Join-Path $startup "$AppName.lnk"),
    (Join-Path $programs "$AppName.lnk"),
    (Join-Path $programs "Uninstall $AppName.lnk"),
    (Join-Path $programs $AppName),   # the Start Menu\Qwik folder
    (Join-Path $startup "Qwik.lnk"),
    (Join-Path $programs "Qwik.lnk"),
    (Join-Path $programs "Uninstall Qwik.lnk")
)) {
    if (Test-Path $lnk) { Remove-Item $lnk -Force -Recurse -ErrorAction SilentlyContinue }
}

# 2) unregister from Settings > Apps > Installed apps
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
if (Test-Path $reg) { Remove-Item $reg -Force }

function Remove-Tree($path) {
    if (-not (Test-Path $path)) { return }
    $root = [IO.Path]::GetFullPath($path)
    if (-not $root.EndsWith("\")) { $root += "\" }
    $here = [IO.Path]::GetFullPath($PSCommandPath)
    if ($here.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        # This script lives in the folder it is deleting; remove it after we exit.
        Start-Process -WindowStyle Hidden cmd.exe -ArgumentList "/c", "timeout /t 1 /nobreak >nul & rmdir /s /q `"$path`""
        Write-Host "Removing $path"
        return
    }
    Remove-Item $path -Recurse -Force
    Write-Host "Removed $path"
}

Remove-Tree (Join-Path $env:LOCALAPPDATA $AppName)
Write-Host "$AppName is uninstalled."
