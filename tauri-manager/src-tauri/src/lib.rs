//! DCC MCP Manager — Tauri backend.
//!
//! Phase 1e: unified `~/.dcc-mcp/config.toml` backs port range and
//! per-server tool-disable state. Phase 3c-3 ships multi-DCC plugin
//! install (Blender, Houdini, Maya). Phase 3d wires the Tools tab.

mod config;
mod install;
mod project;
mod scan;

use config::Config;
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

// ── Config (Phase 1e) ─────────────────────────────────────────────────

#[tauri::command]
fn get_config() -> Config {
    config::load()
}

#[tauri::command]
fn set_config_ports(min: u16, max: u16) -> Result<(), String> {
    config::set_ports(min, max)
}

#[tauri::command]
fn set_config_disabled_tools(mcp: String, disabled: Vec<String>) -> Result<(), String> {
    config::set_disabled_tools(&mcp, disabled)
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
    // Materialize the config file on first launch so Python-side readers
    // don't have to guess defaults.
    config::ensure_exists();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            list_dcc_instances,
            next_free_port,
            get_config,
            set_config_ports,
            set_config_disabled_tools,
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
