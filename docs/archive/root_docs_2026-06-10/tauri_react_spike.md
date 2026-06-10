# Tauri React Spike

This branch contains a side-by-side UI experiment under `frontend/tauri-spike`.

It does not replace the PyQt launcher yet. The intended migration shape is:

- `dock` surface: the resident edge dock / tail that stays small on the desktop.
- `cockpit` surface: the full futuristic command center for workbenches.
- Python backend: still owned by the existing project modules.

## Current Status

- React/Vite frontend builds.
- Rust/Cargo and Visual Studio Build Tools are installed locally.
- Tauri debug/release exe builds successfully.
- Python backend is packaged as a PyInstaller sidecar.
- The Tauri app starts as a small right-edge dock tail, expands into a compact dock panel, then opens the full cockpit on demand.
- ISO PDF is backend-connected and the Pilot uplift is complete. See `docs/iso_pdf_current_status.md`.
- Shutdown Safety Inspector is backend-connected through a Rust command that calls:

```powershell
python -m launcher.app.shutdown_safety_inspector --print-json
```

Cleanup and Locks are cockpit UI prototypes only; their Python workflows are not connected to Tauri commands yet.

## Build

Use the project build script so Cargo is added to `PATH` consistently and the Python backend sidecar is rebuilt:

```powershell
.\scripts\tauri\build_desktop_app.ps1 -Configuration Debug
```

Debug output:

```text
frontend\tauri-spike\src-tauri\target\debug\desktop-support-tauri-spike.exe
frontend\tauri-spike\src-tauri\target\debug\desktop-support-backend.exe
```

Release build:

```powershell
.\scripts\tauri\build_desktop_app.ps1 -Configuration Release
```

Release output:

```text
frontend\tauri-spike\src-tauri\target\release\desktop-support-tauri-spike.exe
frontend\tauri-spike\src-tauri\target\release\desktop-support-backend.exe
```

## Runtime Model

Browser preview uses `public/sample-shutdown-report.json`.

Tauri mode calls the backend through Rust and renders the live Shutdown Safety Inspector report.

Runtime lookup order:

1. `DESKTOP_SUPPORT_BACKEND_EXE`, when explicitly set.
2. `desktop-support-backend.exe` beside the Tauri exe.
3. Tauri resource / `binaries` locations.
4. Development fallback: `.venv\Scripts\python.exe` or `python` with `python -m launcher.app.shutdown_safety_inspector`.

Project root lookup order:

1. `DESKTOP_SUPPORT_PROJECT_ROOT`, when explicitly set.
2. The local repository root, when running from the checked-out project.
3. The Tauri exe folder, for portable standalone runtime.

The bundled sidecar removes the need for a local Python install for connected workbenches such as Shutdown Safety Inspector and ISO PDF. Cleanup and Locks still need their backend commands connected before those workbenches are complete.

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
