#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use rfd::{MessageButtons, MessageDialog, MessageLevel};
use std::io::Write;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::{env, fs};
use tauri::image::Image;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Manager, WindowEvent};

const MAIN_WINDOW_LABEL: &str = "main";
const TRAY_SHOW_DOCK: &str = "show_dock";
const TRAY_HIDE_DOCK: &str = "hide_dock";
const TRAY_SHOW_COCKPIT: &str = "show_cockpit";
const TRAY_QUIT: &str = "quit";

const APP_DIR_NAME: &str = "EngineeringLauncher";
const DATA_ROOT_ENV: &str = "DESKTOP_SUPPORT_DATA_ROOT";
const PROJECT_ROOT_ENV: &str = "DESKTOP_SUPPORT_PROJECT_ROOT";
const BACKEND_ENV: &str = "DESKTOP_SUPPORT_BACKEND_EXE";
const BACKEND_EXE: &str = "desktop-support-backend.exe";
const BACKEND_SIDECAR_EXE: &str = "desktop-support-backend-x86_64-pc-windows-msvc.exe";
const TRAY_ICON_BYTES: &[u8] = include_bytes!("../icons/icon.ico");
const HIDE_TO_TRAY_NOTICE_FLAG: &str = "hide-to-tray-notified";
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

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

#[tauri::command]
fn open_legacy_workbench(workbench: String) -> Result<String, String> {
    let project_root = runtime_root()?;
    let args = legacy_workbench_args(&workbench, &project_root)?;
    let mut failures = Vec::new();

    for python in gui_python_candidates(&project_root) {
        match spawn_legacy_launcher(&python, &project_root, &args) {
            Ok(()) => return Ok(format!("opened {workbench} via {}", python.display())),
            Err(error) => failures.push(error),
        }
    }

    Err(failures.join("\n"))
}

#[tauri::command]
fn pick_iso_combine_pdf() -> Option<String> {
    rfd::FileDialog::new()
        .set_title("選擇 combine PDF")
        .add_filter("PDF", &["pdf"])
        .pick_file()
        .map(|path| path.to_string_lossy().to_string())
}

#[tauri::command]
fn pick_iso_work_folder() -> Option<String> {
    rfd::FileDialog::new()
        .set_title("選擇 ISO PDF 工作資料夾")
        .pick_folder()
        .map(|path| path.to_string_lossy().to_string())
}

#[tauri::command]
fn pick_iso_list_file() -> Option<String> {
    rfd::FileDialog::new()
        .set_title("選擇 ISO List")
        .add_filter("ISO List", &["xlsx", "xlsm", "csv"])
        .pick_file()
        .map(|path| path.to_string_lossy().to_string())
}

#[tauri::command]
fn pick_iso_page_folder() -> Option<String> {
    rfd::FileDialog::new()
        .set_title("選擇頁面 PDF 資料夾")
        .pick_folder()
        .map(|path| path.to_string_lossy().to_string())
}

#[tauri::command]
fn run_iso_workflow(request: String) -> Result<String, String> {
    let project_root = runtime_root()?;
    let python = python_executable(&project_root);
    let mut command = Command::new(&python);
    command
        .args(["-m", "launcher.app.tauri_iso_workflow"])
        .current_dir(&project_root)
        .env(PROJECT_ROOT_ENV, &project_root)
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8");
    run_json_stdin_command(
        &mut command,
        &request,
        &format!("ISO workflow backend {}", python.display()),
    )
}

#[tauri::command]
fn preview_iso_pdf_page(request: String) -> Result<String, String> {
    let project_root = runtime_root()?;
    let python = python_executable(&project_root);
    let mut command = Command::new(&python);
    command
        .args(["-m", "launcher.app.tauri_iso_preview"])
        .current_dir(&project_root)
        .env(PROJECT_ROOT_ENV, &project_root)
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8");
    run_json_stdin_command(
        &mut command,
        &request,
        &format!("ISO PDF preview backend {}", python.display()),
    )
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
            .args([
                "-m",
                "launcher.app.shutdown_safety_inspector",
                "--print-json",
                "--project-root",
            ])
            .arg(project_root)
            .current_dir(project_root)
            .env(PROJECT_ROOT_ENV, project_root),
        &format!("Python backend {}", python.display()),
    )
}

fn legacy_workbench_args(workbench: &str, project_root: &Path) -> Result<Vec<String>, String> {
    let flag = match workbench {
        "iso" => "--open-iso-workbench",
        "cleanup" => "--open-safe-cleanup",
        "locks" => "--open-file-lock-checker",
        "shutdown" => "--open-shutdown-safety-inspector",
        _ => return Err(format!("unknown legacy workbench: {workbench}")),
    };

    Ok(vec![
        "-m".to_string(),
        "launcher.app.main".to_string(),
        "--start-hidden".to_string(),
        "--show-existing".to_string(),
        flag.to_string(),
        "--context-source".to_string(),
        "tauri.bridge".to_string(),
        "--set-context".to_string(),
        project_root.to_string_lossy().to_string(),
    ])
}

fn spawn_legacy_launcher(
    python: &Path,
    project_root: &Path,
    args: &[String],
) -> Result<(), String> {
    let mut command = Command::new(python);
    command
        .args(args)
        .current_dir(project_root)
        .env(PROJECT_ROOT_ENV, project_root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    command
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("failed to launch {}: {error}", python.display()))
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

fn run_json_stdin_command(
    command: &mut Command,
    input: &str,
    label: &str,
) -> Result<String, String> {
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    let mut child = command
        .spawn()
        .map_err(|error| format!("failed to run {label}: {error}"))?;
    if let Some(stdin) = child.stdin.as_mut() {
        stdin
            .write_all(input.as_bytes())
            .map_err(|error| format!("failed to write request to {label}: {error}"))?;
    }
    let output = child
        .wait_with_output()
        .map_err(|error| format!("failed to read {label}: {error}"))?;

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
    if let Ok(value) = env::var(PROJECT_ROOT_ENV) {
        let path = PathBuf::from(value);
        if !path.as_os_str().is_empty() {
            return Ok(path);
        }
    }

    if let Some(root) = project_root_from_process_context() {
        return Ok(root);
    }

    if let Some(root) = local_app_data_root() {
        let _ = fs::create_dir_all(&root);
        return Ok(root);
    }

    if let Ok(current_exe) = env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            return Ok(parent.to_path_buf());
        }
    }

    env::current_dir().map_err(|error| format!("cannot read runtime root: {error}"))
}

fn local_app_data_root() -> Option<PathBuf> {
    if let Ok(value) = env::var(DATA_ROOT_ENV) {
        let path = PathBuf::from(value);
        if !path.as_os_str().is_empty() {
            return Some(path);
        }
    }
    env::var("LOCALAPPDATA")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map(|value| PathBuf::from(value).join(APP_DIR_NAME))
}

fn project_root_from_process_context() -> Option<PathBuf> {
    let mut starts = Vec::new();
    if let Ok(current) = env::current_dir() {
        starts.push(current);
    }
    if let Ok(current_exe) = env::current_exe() {
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

    if let Ok(value) = env::var(BACKEND_ENV) {
        let path = PathBuf::from(value);
        if path.exists() {
            return Some(path);
        }
    }

    let mut folders = Vec::new();
    if let Ok(current_exe) = env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            folders.push(parent.to_path_buf());
        }
    }
    if let Ok(resource_dir) = app.path().resource_dir() {
        folders.push(resource_dir.clone());
        folders.push(resource_dir.join("binaries"));
    }
    if let Ok(current) = env::current_dir() {
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
    path.join("launcher").join("app").join("main.py").exists()
        && path.join("pyproject.toml").exists()
}

fn python_executable(project_root: &Path) -> PathBuf {
    let venv_python = project_root
        .join(".venv")
        .join("Scripts")
        .join("python.exe");
    if venv_python.exists() {
        return venv_python;
    }
    PathBuf::from("python")
}

fn gui_python_candidates(project_root: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    let venv_scripts = project_root.join(".venv").join("Scripts");
    for candidate in [
        venv_scripts.join("pythonw.exe"),
        venv_scripts.join("python.exe"),
        PathBuf::from("pythonw"),
        PathBuf::from("python"),
    ] {
        if !candidates.contains(&candidate) {
            candidates.push(candidate);
        }
    }
    candidates
}

fn main() {
    tauri::Builder::default()
        .on_window_event(|window, event| {
            if window.label() == MAIN_WINDOW_LABEL {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    maybe_show_hide_to_tray_notice();
                    let _ = window.hide();
                }
            }
        })
        .setup(|app| {
            setup_tray(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            scan_shutdown_safety,
            open_legacy_workbench,
            pick_iso_combine_pdf,
            pick_iso_work_folder,
            pick_iso_list_file,
            pick_iso_page_folder,
            preview_iso_pdf_page,
            run_iso_workflow
        ])
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}

fn setup_tray(app: &mut tauri::App) -> tauri::Result<()> {
    let show_dock = MenuItem::with_id(app, TRAY_SHOW_DOCK, "顯示工具列", true, None::<&str>)?;
    let show_cockpit =
        MenuItem::with_id(app, TRAY_SHOW_COCKPIT, "開啟 Cockpit", true, None::<&str>)?;
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
            TRAY_QUIT => request_shutdown_safe_quit(app),
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

fn maybe_show_hide_to_tray_notice() {
    let Some(flag_path) = hide_to_tray_notice_flag_path() else {
        return;
    };
    if flag_path.exists() {
        return;
    }

    let _ = MessageDialog::new()
        .set_level(MessageLevel::Info)
        .set_title("Desktop Support")
        .set_description(
            "關閉視窗會隱藏到系統匣，程式仍會常駐。若要結束程式，請從 tray 右鍵選單選「離開」。",
        )
        .set_buttons(MessageButtons::Ok)
        .show();

    if let Some(parent) = flag_path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let _ = fs::write(flag_path, "shown\n");
}

fn hide_to_tray_notice_flag_path() -> Option<PathBuf> {
    runtime_root().ok().map(|root| {
        root.join(".runtime")
            .join("flags")
            .join(HIDE_TO_TRAY_NOTICE_FLAG)
    })
}

fn request_shutdown_safe_quit(app: &tauri::AppHandle) {
    match scan_shutdown_safety(app.clone()) {
        Ok(payload) if !shutdown_report_has_blockers(&payload) => app.exit(0),
        Ok(_) => show_shutdown_cockpit_for_quit(app, "blocked"),
        Err(_) => show_shutdown_cockpit_for_quit(app, "scan_failed"),
    }
}

fn shutdown_report_has_blockers(payload: &str) -> bool {
    match serde_json::from_str::<serde_json::Value>(payload) {
        Ok(value) => value
            .get("blockers")
            .and_then(|blockers| blockers.as_array())
            .map(|blockers| !blockers.is_empty())
            .unwrap_or_else(|| {
                value
                    .get("blocker_count")
                    .and_then(|count| count.as_u64())
                    .unwrap_or(0)
                    > 0
            }),
        Err(_) => true,
    }
}

fn show_shutdown_cockpit_for_quit(app: &tauri::AppHandle, reason: &str) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
        let script = format!(
            "window.dispatchEvent(new CustomEvent('desktop-support:set-surface', {{ detail: {{ surface: 'cockpit', mode: 'shutdown', refresh: true, quitReason: '{}' }} }}));",
            reason
        );
        let _ = window.eval(&script);
    }
}
