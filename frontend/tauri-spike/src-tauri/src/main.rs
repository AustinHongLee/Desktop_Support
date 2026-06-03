use std::path::{Path, PathBuf};
use std::process::Command;
use tauri::Manager;

const PROJECT_ROOT_ENV: &str = "DESKTOP_SUPPORT_PROJECT_ROOT";
const BACKEND_ENV: &str = "DESKTOP_SUPPORT_BACKEND_EXE";
const BACKEND_EXE: &str = "desktop-support-backend.exe";
const BACKEND_SIDECAR_EXE: &str = "desktop-support-backend-x86_64-pc-windows-msvc.exe";

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
        .invoke_handler(tauri::generate_handler![scan_shutdown_safety])
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}
