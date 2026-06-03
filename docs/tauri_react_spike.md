# Tauri React Spike

This branch contains a side-by-side UI experiment under `frontend/tauri-spike`.

It does not replace the PyQt launcher. The spike reads the same Shutdown Safety Inspector report shape and, when run inside Tauri, calls:

```powershell
python -m launcher.app.shutdown_safety_inspector --print-json
```

Current local status:

- React/Vite can run with Node.js.
- Tauri source files are present.
- Rust/Cargo must be installed before `npm run tauri dev` can compile the desktop shell.

Commands:

```powershell
cd frontend\tauri-spike
npm install
npm run dev
npm run build
npm run tauri dev
```

Browser mode uses `public/sample-shutdown-report.json`. Tauri mode calls the Python backend through a Rust command and renders the live report.
