# Qwik — floating shortcut dot (Windows)

A tiny always-on-top dot that fans out your 5 favorite apps/folders in a
transparent half-circle. Hover to open, auto-collapses 3s after the mouse
leaves, or press **Ctrl+Q** anywhere to toggle it.

![Python](https://img.shields.io/badge/python-3.14-blue) ![Windows](https://img.shields.io/badge/windows-10%2B-blue)

## Features

- Transparent half-circle fan: hub + up to 5 black shortcut circles
- Real Windows icons (exe + folder), per-item right-click menu (open / move / delete)
- Position + use-count persist in `shortcuts.toml` (most-used floats first)
- Global **Ctrl+Q** hotkey — show the list without touching the mouse
- Per-user install, no admin: `%LOCALAPPDATA%\Qwik`, Start Menu entry,
  registered in *Settings > Apps > Installed apps*, autostart, uninstaller

## Install

1. Download `Qwik-install-v1.1.0.zip` from [Releases](../../releases)
2. Extract it, double-click **`Install-Qwik.bat`**
3. Done — the dot starts, and lives in `Start Menu > Qwik`

To remove: `Start Menu > Qwik > Uninstall Qwik` (or run `Uninstall-Qwik.bat`).

## Run from source

```powershell
python float_shortcut.py
```

Needs Python 3.14 with `tcl/tk` + Pillow (`pip install pillow`).

## Build the exe

```powershell
python -m PyInstaller Qwik.spec --noconfirm --clean
# output: dist\Qwik\Qwik.exe (+ _internal\)
```

## Files

| File | What |
|---|---|
| `float_shortcut.py` | the app (Tkinter, stdlib + Pillow) |
| `Qwik.spec` | PyInstaller one-dir spec |
| `Install-Qwik.ps1` / `.bat` | per-user installer + Apps registration |
| `Uninstall-Qwik.ps1` / `.bat` | clean uninstaller |
| `shortcuts.toml` | example config (copied on first install) |
| `logo.png` / `logo.ico` | app icon |
| `src/` | legacy Rust MVP (superseded by the Python build) |
