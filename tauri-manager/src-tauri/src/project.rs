//! Project-level MCP setup.
//!
//! Writes `<project>/.claude/settings.json` with `mcpServers` entries
//! and tracks which projects the manager knows about in
//! `~/.dcc-mcp/manager/projects.json`.
//!
//! Phase 3c-2: in dev mode the `mcpServers.<name>.command` field points
//! at the repo's venv scripts (`.venv/bin/<mcp>`). This works only for
//! the current developer. Phase 5 will bundle PyInstaller-frozen exes
//! into the Tauri app and copy those into `<project>/.claude/dcc-mcp/bin/`
//! instead, producing a fully project-portable setup.

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

// ── Result shapes returned to the frontend ───────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManagedProject {
    pub path: String,
    pub installed_mcps: Vec<String>,
    pub added_at: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SetupResult {
    pub ok: bool,
    pub project_path: String,
    pub installed_mcps: Vec<String>,
    pub settings_path: String,
    /// "created" | "merged"
    pub settings_op: String,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RemoveResult {
    pub ok: bool,
    pub removed_keys: Vec<String>,
    pub error: Option<String>,
}

// ── Path helpers ─────────────────────────────────────────────────────

fn home_dir() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

fn manager_dir() -> Option<PathBuf> {
    Some(home_dir()?.join(".dcc-mcp").join("manager"))
}

fn projects_json_path() -> Option<PathBuf> {
    Some(manager_dir()?.join("projects.json"))
}

/// Compute the absolute path to an MCP server's entry point in dev mode.
///
/// Uses `CARGO_MANIFEST_DIR` (baked in at build time) to locate the repo
/// root, then points at `<repo>/.venv/bin/<name>`. These are the shell
/// scripts `uv sync` installs; they embed the venv Python path.
///
/// Returns absolute path even if the file doesn't exist yet — we want
/// to write the intended path into settings.json regardless; user can
/// run `uv sync` to materialize it.
fn dev_mcp_binary(name: &str) -> PathBuf {
    let manifest = env!("CARGO_MANIFEST_DIR");
    let repo_root = PathBuf::from(manifest)
        .join("../..")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from(manifest).join("../.."));
    let bin_dir = if cfg!(windows) {
        repo_root.join(".venv").join("Scripts")
    } else {
        repo_root.join(".venv").join("bin")
    };
    // Windows venv shims are `.exe`; Claude Code is lenient via PATHEXT,
    // but we write the explicit path for clarity.
    if cfg!(windows) {
        bin_dir.join(format!("{name}.exe"))
    } else {
        bin_dir.join(name)
    }
}

// ── Tracked projects registry ────────────────────────────────────────

fn read_projects() -> Vec<ManagedProject> {
    let Some(p) = projects_json_path() else {
        return vec![];
    };
    let Ok(text) = fs::read_to_string(&p) else {
        return vec![];
    };
    serde_json::from_str(&text).unwrap_or_default()
}

fn write_projects(projects: &[ManagedProject]) -> std::io::Result<()> {
    let Some(dir) = manager_dir() else {
        return Err(std::io::Error::other("no manager dir"));
    };
    fs::create_dir_all(&dir)?;
    let path = dir.join("projects.json");
    let json = serde_json::to_string_pretty(projects)
        .map_err(|e| std::io::Error::other(format!("serialize: {e}")))?;
    fs::write(&path, json)
}

pub fn list_managed_projects() -> Vec<ManagedProject> {
    read_projects()
}

fn upsert_project(path: &Path, mcps: &[String]) -> std::io::Result<()> {
    let path_str = path.to_string_lossy().into_owned();
    let mut projects = read_projects();
    let now = chrono_iso_now();
    if let Some(existing) = projects.iter_mut().find(|p| p.path == path_str) {
        existing.installed_mcps = mcps.to_vec();
        existing.added_at = now;
    } else {
        projects.push(ManagedProject {
            path: path_str,
            installed_mcps: mcps.to_vec(),
            added_at: now,
        });
    }
    write_projects(&projects)
}

fn forget_project(path: &Path) -> std::io::Result<()> {
    let path_str = path.to_string_lossy().into_owned();
    let mut projects = read_projects();
    projects.retain(|p| p.path != path_str);
    write_projects(&projects)
}

/// Tiny ISO-8601 "now" without pulling in the chrono crate.
fn chrono_iso_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    // Return UNIX seconds as a plain integer string — callers treat this
    // as an opaque timestamp for display. Trading ISO niceness for one
    // fewer dep.
    secs.to_string()
}

// ── Settings.json merge ──────────────────────────────────────────────

fn known_mcps() -> &'static [&'static str] {
    &["blender", "houdini", "ue", "maya", "os"]
}

fn settings_path(project_root: &Path) -> PathBuf {
    project_root.join(".claude").join("settings.json")
}

/// Write/merge `<project>/.claude/settings.json`. Returns the operation
/// performed ("created" / "merged") and the final set of MCP keys the
/// manager now owns in that file.
fn merge_settings(
    project_root: &Path,
    selected_mcps: &[String],
) -> std::io::Result<String> {
    let settings = settings_path(project_root);
    if let Some(parent) = settings.parent() {
        fs::create_dir_all(parent)?;
    }

    // Load existing JSON or start fresh.
    let (mut root, op) = match fs::read_to_string(&settings) {
        Ok(text) if !text.trim().is_empty() => {
            let parsed: serde_json::Value = serde_json::from_str(&text)
                .map_err(|e| std::io::Error::other(format!("parse existing settings.json: {e}")))?;
            (parsed, "merged")
        }
        _ => (serde_json::json!({}), "created"),
    };

    // Ensure mcpServers is an object.
    if !root.is_object() {
        return Err(std::io::Error::other(
            ".claude/settings.json is not a JSON object",
        ));
    }
    let obj = root.as_object_mut().unwrap();
    let mcp_servers = obj
        .entry("mcpServers".to_string())
        .or_insert_with(|| serde_json::json!({}));
    if !mcp_servers.is_object() {
        return Err(std::io::Error::other("settings.mcpServers is not an object"));
    }
    let mcp_obj = mcp_servers.as_object_mut().unwrap();

    // Remove stale entries for MCPs we own but the user didn't pick this time.
    for key in known_mcps() {
        if !selected_mcps.iter().any(|s| s == key) {
            mcp_obj.remove(*key);
        }
    }

    // Add/update selected MCP entries with absolute dev-mode binary paths.
    for mcp in selected_mcps {
        let name = format!("{mcp}-mcp");
        let cmd = dev_mcp_binary(&name);
        mcp_obj.insert(
            mcp.clone(),
            serde_json::json!({
                "command": cmd.to_string_lossy().into_owned(),
            }),
        );
    }

    let pretty = serde_json::to_string_pretty(&root)
        .map_err(|e| std::io::Error::other(format!("serialize settings.json: {e}")))?;
    fs::write(&settings, pretty + "\n")?;
    Ok(op.to_string())
}

/// Strip the manager's MCP entries from settings.json. Other entries
/// (hooks, model config, custom MCPs the user added manually under a
/// non-standard key) are preserved. Returns the keys actually removed.
fn unmerge_settings(project_root: &Path) -> std::io::Result<Vec<String>> {
    let settings = settings_path(project_root);
    let text = match fs::read_to_string(&settings) {
        Ok(t) => t,
        Err(_) => return Ok(vec![]),
    };
    if text.trim().is_empty() {
        return Ok(vec![]);
    }
    let mut root: serde_json::Value = serde_json::from_str(&text)
        .map_err(|e| std::io::Error::other(format!("parse settings.json: {e}")))?;
    let Some(obj) = root.as_object_mut() else {
        return Ok(vec![]);
    };
    let mut removed: Vec<String> = vec![];
    if let Some(mcp_val) = obj.get_mut("mcpServers") {
        if let Some(mcp_obj) = mcp_val.as_object_mut() {
            for key in known_mcps() {
                if mcp_obj.remove(*key).is_some() {
                    removed.push(key.to_string());
                }
            }
            if mcp_obj.is_empty() {
                obj.remove("mcpServers");
            }
        }
    }
    // Only write if we changed something.
    if !removed.is_empty() {
        let pretty = serde_json::to_string_pretty(&root)
            .map_err(|e| std::io::Error::other(format!("serialize settings.json: {e}")))?;
        fs::write(&settings, pretty + "\n")?;
    }
    Ok(removed)
}

// ── Public commands ──────────────────────────────────────────────────

pub fn setup_project_mcp(project_path: &str, mcps: Vec<String>) -> SetupResult {
    let project_root = Path::new(project_path);
    let settings = settings_path(project_root);

    // Validate selection against the known set.
    let known = known_mcps();
    let unknown: Vec<_> = mcps
        .iter()
        .filter(|m| !known.contains(&m.as_str()))
        .cloned()
        .collect();
    if !unknown.is_empty() {
        return SetupResult {
            ok: false,
            project_path: project_path.to_string(),
            installed_mcps: vec![],
            settings_path: settings.to_string_lossy().into_owned(),
            settings_op: String::new(),
            error: Some(format!("Unknown MCP key(s): {unknown:?}")),
        };
    }

    let op = match merge_settings(project_root, &mcps) {
        Ok(op) => op,
        Err(e) => {
            return SetupResult {
                ok: false,
                project_path: project_path.to_string(),
                installed_mcps: vec![],
                settings_path: settings.to_string_lossy().into_owned(),
                settings_op: String::new(),
                error: Some(format!("settings merge: {e}")),
            };
        }
    };

    if let Err(e) = upsert_project(project_root, &mcps) {
        return SetupResult {
            ok: false,
            project_path: project_path.to_string(),
            installed_mcps: mcps.clone(),
            settings_path: settings.to_string_lossy().into_owned(),
            settings_op: op,
            error: Some(format!("registry update: {e}")),
        };
    }

    SetupResult {
        ok: true,
        project_path: project_path.to_string(),
        installed_mcps: mcps,
        settings_path: settings.to_string_lossy().into_owned(),
        settings_op: op,
        error: None,
    }
}

pub fn remove_project_mcp(project_path: &str) -> RemoveResult {
    let project_root = Path::new(project_path);
    let removed = match unmerge_settings(project_root) {
        Ok(r) => r,
        Err(e) => {
            return RemoveResult {
                ok: false,
                removed_keys: vec![],
                error: Some(format!("settings unmerge: {e}")),
            };
        }
    };
    if let Err(e) = forget_project(project_root) {
        return RemoveResult {
            ok: false,
            removed_keys: removed,
            error: Some(format!("registry forget: {e}")),
        };
    }
    RemoveResult {
        ok: true,
        removed_keys: removed,
        error: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_mcp_is_rejected() {
        let r = setup_project_mcp("/tmp/x", vec!["nonexistent".to_string()]);
        assert!(!r.ok);
        assert!(r.error.as_ref().unwrap().contains("Unknown"));
    }

    #[test]
    fn dev_mcp_binary_points_at_venv() {
        let p = dev_mcp_binary("blender-mcp");
        let s = p.to_string_lossy();
        assert!(s.contains(".venv"));
        // Unix: .venv/bin/blender-mcp; Windows: .venv\Scripts\blender-mcp.exe
        assert!(
            s.ends_with("blender-mcp") || s.ends_with("blender-mcp.exe"),
            "unexpected path: {s}"
        );
    }
}
