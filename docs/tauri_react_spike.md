# Tauri React Spike

This branch contains a side-by-side UI experiment under `frontend/tauri-spike`.

It does not replace the PyQt launcher yet. The intended migration shape is:

- `dock` surface: the resident edge dock / tail that stays small on the desktop.
- `cockpit` surface: the full futuristic command center for workbenches.
- Python backend: still owned by the existing project modules.

## Current Status

- React/Vite frontend builds.
- Rust/Cargo and Visual Studio Build Tools are installed locally.
- Tauri debug exe builds successfully.
- The Tauri app starts as a small right-edge dock tail, expands into a compact dock panel, then opens the full cockpit on demand.
- Shutdown Safety Inspector is backend-connected through a Rust command that calls:

```powershell
python -m launcher.app.shutdown_safety_inspector --print-json
```

ISO PDF, Cleanup, and Locks are cockpit UI prototypes only; their Python workflows are not connected to Tauri commands yet.

## Build

Use the project build script so Cargo is added to `PATH` consistently:

```powershell
.\scripts\tauri\build_desktop_app.ps1 -Configuration Debug
```

Debug output:

```text
frontend\tauri-spike\src-tauri\target\debug\desktop-support-tauri-spike.exe
```

Release output:

```powershell
.\scripts\tauri\build_desktop_app.ps1 -Configuration Release
```

## Runtime Model

Browser preview uses `public/sample-shutdown-report.json`.

Tauri mode calls the Python backend through Rust and renders the live Shutdown Safety Inspector report. The current exe is runnable, but it is not a fully standalone product yet because it expects the project folder and Python environment to exist.

For a true standalone installer/exe, package the Python backend as a sidecar, then have Rust call that sidecar instead of `python -m ...`.

## Tail Safety

There are two different "tail" ideas:

- Dock tail: the resident edge UI surface. This is production behavior.
- Log tail: `Get-Content -Wait -Tail`, which is debug-only and intentionally never exits.

Production Tauri commands must return bounded JSON or spawn tracked jobs. They must not call an infinite log tail, otherwise app close / shutdown safety flows can appear stuck.

The debug launcher now keeps log tail disabled by default:

```powershell
.\scripts\launcher\run_launcher_debug.ps1 -Restart
```

Enable it only when intentionally watching logs:

```powershell
.\scripts\launcher\run_launcher_debug.ps1 -Restart -Tail
```
