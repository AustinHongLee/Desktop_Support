# Scripts Index

Root-level human entry point:

- `..\START_HERE.cmd`

Common developer commands:

- `test.ps1`: unified test runner (`env`, `smoke`, `shutdown`, `unit`, `frontend`, `tauri-ui`, `all`)
- `dev\prepare_dev_environment.ps1`: Windows/Tauri development environment check and optional install
- `tauri\run_dev_app.ps1`: Tauri dev/test UI with browser fallback
- `tauri\build_desktop_app.ps1`: native Tauri build and Python sidecar packaging

Launcher internals:

- `launcher\run_launcher.ps1`: start the PyQt launcher
- `launcher\run_launcher_debug.ps1`: debug launcher start
- `launcher\run_self_test.ps1`: launcher self-test
- `launcher\start_hidden.vbs`: hidden compatibility start
- `launcher\restart_show.vbs`: restart/show compatibility helper

Explorer context menu:

- `install_explorer_context_menu.ps1`
- `uninstall_explorer_context_menu.ps1`
- `shutdown_safety_inspector.ps1`

Compatibility shortcuts:

- `shortcuts\README.md`

Shared helper modules:

- `_shared\path_utils.ps1`
- `_shared\vs_env.ps1`
