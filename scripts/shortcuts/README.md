# Shortcut Compatibility Layer

These files are not primary user entry points.

Use the root-level `START_HERE.cmd` first. The scripts in this folder exist so old shortcuts and developer workflows still have stable targets after the root folder was cleaned up.

Primary paths:

- Start / menu: `..\..\START_HERE.cmd`
- Test runner: `..\test.ps1`
- Launcher internals: `..\launcher\`

`test_tauri_ui.cmd` starts the Tauri dev/test UI for PyQt-to-Tauri migration work. It prefers the native Tauri window, but falls back to the browser React UI when the local MSVC/Windows SDK toolchain is not ready. The browser fallback opens automatically.

Release builds still require a working Rust/Tauri toolchain, MSVC `link.exe`, and Windows SDK `RC.EXE`.
