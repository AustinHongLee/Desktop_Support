#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::{Path, PathBuf};
use std::process::Command;
use tauri::image::Image;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Manager, WindowEvent};

const MAIN_WINDOW_LABEL: &str = "main";
const TRAY_SHOW_DOCK: &str = "show_dock";
const TRAY_HIDE_DOCK: &str = "hide_dock";
const TRAY_SHOW_COCKPIT: &str = "show_cockpit";
const TRAY_QUIT: &str = "quit";

const PROJECT_ROOT_ENV: &str = "DESKTOP_SUPPORT_PROJECT_ROOT";
const BACKEND_ENV: &str = "DESKTOP_SUPPORT_BACKEND_EXE";
const BACKEND_EXE: &str = "desktop-support-backend.exe";
const BACKEND_SIDECAR_EXE: &str = "desktop-support-backend-x86_64-pc-windows-msvc.exe";
const TRAY_ICON_BYTES: &[u8] = include_bytes!("../icons/icon.ico");

#[tauri::command]
fn scan_shutdown_safety(app: tauri::AppHandle) -> Result<String, String> {
    let project_root = runtime_root()?;
    let mut failures = Vec::new();

    if let Some(backend) = sidecar_executable(&app) {
        match run_backend(&backend, &project_root) {
            Ok(payload) => return Ok(payload),
            Err(error) => failures.push(error),
        }
    }

    match run_python_backend(&project_root) {
        Ok(payload) => Ok(payload),
        Err(error) => {
            failures.push(error);
            Err(failures.join("\n\n"))
        }
    }
}

fn run_backend(backend: &Path, project_root: &Path) -> Result<String, String> {
    run_json_command(
        Command::new(backend)
            .arg("--print-json")
            .arg("--project-root")
            .arg(project_root)
            .current_dir(project_root)
            .env(PROJECT_ROOT_ENV, project_root),
        &format!("backend sidecar {}", backend.display()),
    )
}

fn run_python_backend(project_root: &Path) -> Result<String, String> {
    let python = python_executable(project_root);
    run_json_command(
        Command::new(&python)
            .args(["-m", "launcher.app.shutdown_safety_inspector", "--print-json", "--project-root"])
            .arg(project_root)
            .current_dir(project_root)
            .env(PROJECT_ROOT_ENV, project_root),
        &format!("Python backend {}", python.display()),
    )
}

fn run_json_command(command: &mut Command, label: &str) -> Result<String, String> {
    let output = command
        .output()
        .map_err(|error| format!("failed to run {label}: {error}"))?;

    if output.status.success() {
        return Ok(String::from_utf8_lossy(&output.stdout).trim().to_string());
    }

    let stderr = String::from_utf8_lossy(&output.stderr);
    let stdout = String::from_utf8_lossy(&output.stdout);
    Err(format!(
        "{label} failed with status {:?}\n{}\n{}",
        output.status.code(),
        stderr.trim(),
        stdout.trim()
    ))
}

fn runtime_root() -> Result<PathBuf, String> {
    if let Ok(value) = std::env::var(PROJECT_ROOT_ENV) {
        let path = PathBuf::from(value);
        if !path.as_os_str().is_empty() {
            return Ok(path);
        }
    }

    if let Some(root) = project_root_from_process_context() {
        return Ok(root);
    }

    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            return Ok(parent.to_path_buf());
        }
    }

    std::env::current_dir().map_err(|error| format!("cannot read runtime root: {error}"))
}

fn project_root_from_process_context() -> Option<PathBuf> {
    let mut starts = Vec::new();
    if let Ok(current) = std::env::current_dir() {
        starts.push(current);
    }
    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            starts.push(parent.to_path_buf());
        }
    }

    for start in starts {
        for candidate in start.ancestors() {
            if is_project_root(candidate) {
                return Some(candidate.to_path_buf());
            }
        }
        if let Ok(from_tauri) = start.join("..").join("..").canonicalize() {
            if is_project_root(&from_tauri) {
                return Some(from_tauri);
            }
        }
    }

    None
}

fn sidecar_executable(app: &tauri::AppHandle) -> Option<PathBuf> {
    let names = [BACKEND_EXE, BACKEND_SIDECAR_EXE];

    if let Ok(value) = std::env::var(BACKEND_ENV) {
        let path = PathBuf::from(value);
        if path.exists() {
            return Some(path);
        }
    }

    let mut folders = Vec::new();
    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            folders.push(parent.to_path_buf());
        }
    }
    if let Ok(resource_dir) = app.path().resource_dir() {
        folders.push(resource_dir.clone());
        folders.push(resource_dir.join("binaries"));
    }
    if let Ok(current) = std::env::current_dir() {
        folders.push(current.join("src-tauri").join("binaries"));
        folders.push(current.join("binaries"));
    }

    for folder in folders {
        for name in names {
            let candidate = folder.join(name);
            if candidate.exists() {
                return Some(candidate);
            }
        }
    }

    None
}

fn is_project_root(path: &Path) -> bool {
    path.join("launcher").join("app").join("main.py").exists() && path.join("pyproject.toml").exists()
}

fn python_executable(project_root: &Path) -> PathBuf {
    let venv_python = project_root.join(".venv").join("Scripts").join("python.exe");
    if venv_python.exists() {
        return venv_python;
    }
    PathBuf::from("python")
}

fn main() {
    tauri::Builder::default()
        .on_window_event(|window, event| {
            if window.label() == MAIN_WINDOW_LABEL {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .setup(|app| {
            setup_tray(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![scan_shutdown_safety])
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}

fn setup_tray(app: &mut tauri::App) -> tauri::Result<()> {
    let show_dock = MenuItem::with_id(app, TRAY_SHOW_DOCK, "顯示工具列", true, None::<&str>)?;
    let show_cockpit = MenuItem::with_id(app, TRAY_SHOW_COCKPIT, "開啟 Cockpit", true, None::<&str>)?;
    let hide_dock = MenuItem::with_id(app, TRAY_HIDE_DOCK, "隱藏到系統匣", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, TRAY_QUIT, "離開", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let menu = Menu::new(app)?;
    menu.append_items(&[&show_dock, &show_cockpit, &hide_dock, &separator, &quit])?;

    let icon = Image::from_bytes(TRAY_ICON_BYTES)?;
    TrayIconBuilder::with_id("desktop-support-tray")
        .icon(icon)
        .tooltip("Desktop Support")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            TRAY_SHOW_DOCK => show_main_window(app, false),
            TRAY_SHOW_COCKPIT => show_main_window(app, true),
            TRAY_HIDE_DOCK => hide_main_window(app),
            TRAY_QUIT => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(&tray.app_handle(), false);
            }
        })
        .build(app)?;

    Ok(())
}

fn show_main_window(app: &tauri::AppHandle, cockpit: bool) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
        if cockpit {
            let _ = window.eval(
                "window.dispatchEvent(new CustomEvent('desktop-support:set-surface', { detail: { surface: 'cockpit' } }));",
            );
        } else {
            let _ = window.eval(
                "window.dispatchEvent(new CustomEvent('desktop-support:set-surface', { detail: { surface: 'dock', collapsed: true } }));",
            );
        }
    }
}

fn hide_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
        let _ = window.hide();
    }
}
