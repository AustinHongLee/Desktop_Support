use std::path::{Path, PathBuf};
use std::process::Command;

#[tauri::command]
fn scan_shutdown_safety() -> Result<String, String> {
    let project_root = project_root()?;
    let python = python_executable(&project_root);
    let output = Command::new(&python)
        .args(["-m", "launcher.app.shutdown_safety_inspector", "--print-json"])
        .current_dir(&project_root)
        .output()
        .map_err(|error| format!("failed to run Python: {error}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        return Err(format!(
            "shutdown safety scan failed with status {:?}\n{}\n{}",
            output.status.code(),
            stderr.trim(),
            stdout.trim()
        ));
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn project_root() -> Result<PathBuf, String> {
    let current = std::env::current_dir().map_err(|error| format!("cannot read current dir: {error}"))?;
    for candidate in current.ancestors() {
        if is_project_root(candidate) {
            return Ok(candidate.to_path_buf());
        }
    }

    let from_tauri = current
        .join("..")
        .join("..")
        .canonicalize()
        .map_err(|error| format!("cannot resolve project root: {error}"))?;
    if is_project_root(&from_tauri) {
        return Ok(from_tauri);
    }

    Err("could not find launcher project root".to_string())
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
