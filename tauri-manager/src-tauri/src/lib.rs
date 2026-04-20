//! DCC MCP Manager — Tauri backend.
//!
//! Phase 2a: exposes a single command `list_dcc_instances` that scans the
//! local machine for listening DCC processes in a port range and returns
//! them to the React frontend.

mod install;
mod project;
mod scan;

use install::{DccVersion, InstallResult, UninstallResult};
use project::{ManagedProject, RemoveResult, SetupResult};
use scan::DccInstance;

// ── Scan (Dashboard tab) ──────────────────────────────────────────────

#[tauri::command]
fn list_dcc_instances(port_min: u16, port_max: u16) -> Vec<DccInstance> {
    scan::list_dcc_instances(port_min, port_max)
}

#[tauri::command]
fn next_free_port(port_min: u16, port_max: u16) -> Option<u16> {
    scan::next_free_port(port_min, port_max)
}

// ── Install (Install tab) ─────────────────────────────────────────────

#[tauri::command]
fn detect_dcc_versions(dcc: String) -> Vec<DccVersion> {
    install::detect_dcc_versions(&dcc)
}

#[tauri::command]
fn install_plugin(dcc: String, version: String) -> InstallResult {
    install::install_plugin(&dcc, &version)
}

#[tauri::command]
fn uninstall_plugin(dcc: String, version: String) -> UninstallResult {
    install::uninstall_plugin(&dcc, &version)
}

// ── Project MCP setup (Install tab, sub-section 2) ────────────────────

#[tauri::command]
fn list_managed_projects() -> Vec<ManagedProject> {
    project::list_managed_projects()
}

#[tauri::command]
fn setup_project_mcp(project_path: String, mcps: Vec<String>) -> SetupResult {
    project::setup_project_mcp(&project_path, mcps)
}

#[tauri::command]
fn remove_project_mcp(project_path: String) -> RemoveResult {
    project::remove_project_mcp(&project_path)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            list_dcc_instances,
            next_free_port,
            detect_dcc_versions,
            install_plugin,
            uninstall_plugin,
            list_managed_projects,
            setup_project_mcp,
            remove_project_mcp,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
