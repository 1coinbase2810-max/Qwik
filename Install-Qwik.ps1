# Qwik installer - per-user install, no admin needed.
# Installs into %LOCALAPPDATA%\Qwik, adds Start Menu shortcuts,
# registers in "Installed apps" ( Programs and Features ), enables autostart.
$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppName = "Qwik"
$AppVersion = "1.1.0"
$Publisher = "Qwik"
$dest = Join-Path $env:LOCALAPPDATA $AppName
$exe = Join-Path $dest "Qwik.exe"

Write-Host "== Installing $AppName $AppVersion =="

# 1) close a running copy so files can be replaced
Get-Process -Name Qwik -ErrorAction SilentlyContinue | ForEach-Object {
    try { $_.CloseMainWindow() | Out-Null } catch {}
}
Start-Sleep -Milliseconds 300
Get-Process -Name Qwik -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 300

# 2) copy program files
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item (Join-Path $here "Qwik\*") $dest -Recurse -Force
Copy-Item (Join-Path $here "Uninstall-Qwik.bat") $dest -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $here "Uninstall-Qwik.ps1") $dest -Force -ErrorAction SilentlyContinue

# 3) default shortcuts.toml (only on first install)
$toml = Join-Path $dest "shortcuts.toml"
if (-not (Test-Path $toml)) {
    @"
[[shortcut]]
name = "Downloads"
path = "$env:USERPROFILE\Downloads"
uses = 0

[[shortcut]]
name = "Screenshots"
path = "$env:USERPROFILE\Pictures\Screenshots"
uses = 0
"@ | Set-Content $toml -Encoding UTF8
}

# 4) Start Menu entries with clean display names (Qwik = the app, NOT the exe path)
$ws = New-Object -ComObject WScript.Shell
$programs = [Environment]::GetFolderPath("Programs")
$qwikDir = Join-Path $programs $AppName
New-Item -ItemType Directory -Force -Path $qwikDir | Out-Null
$sm = $ws.CreateShortcut((Join-Path $qwikDir "$AppName.lnk"))
$sm.TargetPath = $exe; $sm.WorkingDirectory = $dest
$sm.Description = "$AppName - floating shortcut dot"
$sm.IconLocation = "$exe,0"; $sm.Save()
$un = $ws.CreateShortcut((Join-Path $qwikDir "Uninstall $AppName.lnk"))
$un.TargetPath = Join-Path $dest "Uninstall-Qwik.bat"; $un.WorkingDirectory = $dest
$un.Description = "Remove $AppName"; $un.Save()
# legacy root-level links from older installs are removed (no more "Qwik.lnk" clutter)
foreach ($old in @((Join-Path $programs "Qwik.lnk"), (Join-Path $programs "Uninstall Qwik.lnk"))) {
    if (Test-Path $old) { Remove-Item $old -Force }
}

# 5) register in "Installed apps" (per-user uninstall key -> Settings > Apps > Installed apps)
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
New-Item -Path $reg -Force | Out-Null
Set-ItemProperty $reg -Name "DisplayName" -Value $AppName
Set-ItemProperty $reg -Name "DisplayVersion" -Value $AppVersion
Set-ItemProperty $reg -Name "Publisher" -Value $Publisher
Set-ItemProperty $reg -Name "InstallLocation" -Value $dest
Set-ItemProperty $reg -Name "DisplayIcon" -Value "`"$exe`",0"
Set-ItemProperty $reg -Name "UninstallString" -Value "powershell -NoProfile -ExecutionPolicy Bypass -File `"$dest\Uninstall-Qwik.ps1`""
Set-ItemProperty $reg -Name "QuietUninstallString" -Value "powershell -NoProfile -ExecutionPolicy Bypass -File `"$dest\Uninstall-Qwik.ps1`" -Silent"
Set-ItemProperty $reg -Name "NoModify" -Value 1 -Type DWord
Set-ItemProperty $reg -Name "NoRepair" -Value 1 -Type DWord
Set-ItemProperty $reg -Name "EstimatedSize" -Value 15000 -Type DWord

# 6) autostart (per-user, no admin): comment out the next 3 lines to skip
$lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "$AppName.lnk"
$sc = $ws.CreateShortcut($lnk); $sc.TargetPath = $exe; $sc.WorkingDirectory = $dest
$sc.Description = "$AppName - floating shortcut dot"; $sc.Save()

Start-Process $exe
Write-Host "Installed $AppName $AppVersion to $dest and started."
Write-Host "Find it in: Start Menu > $AppName, and Settings > Apps > Installed apps > $AppName."
