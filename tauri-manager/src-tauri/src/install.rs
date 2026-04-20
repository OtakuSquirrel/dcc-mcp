//! DCC plugin installation.
//!
//! Phase 3c-1 implements Blender only. Other DCCs (Houdini / UE / Maya)
//! return empty version lists for now; their install flows will follow
//! when user has access to those tools.

use serde::Serialize;
use std::fs;
use std::path::{Path, PathBuf};

// ── Results returned to the frontend ───────────────────────────────────

#[derive(Debug, Clone, Serialize)]
pub struct DccVersion {
    pub version: String,
    pub pref_dir: String,
    pub addons_dir: String,
    pub installed: bool,
    /// "symlink" | "copy" | null when not installed
    pub install_method: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct InstallResult {
    pub ok: bool,
    /// "symlink" | "copy" | "" on failure
    pub method: String,
    pub path: String,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct UninstallResult {
    pub ok: bool,
    pub was_installed: bool,
    pub error: Option<String>,
}

// ── Path helpers ───────────────────────────────────────────────────────

/// Root of the repository's `plugins/` directory (where the addon source
/// lives). In dev mode, this resolves via `CARGO_MANIFEST_DIR` which is
/// baked in at compile time — pointing at `tauri-manager/src-tauri/`.
/// Climbing `../../plugins` lands on `<repo>/plugins/`.
///
/// Phase 5 (bundled build): switch to `tauri::AppHandle::path().resource_dir()
/// + "plugins"` so the addon source ships inside the app bundle.
fn plugins_dir() -> PathBuf {
    let manifest = env!("CARGO_MANIFEST_DIR");
    PathBuf::from(manifest).join("../../plugins")
}

fn blender_base_dir() -> Option<PathBuf> {
    #[cfg(target_os = "macos")]
    {
        let home = std::env::var_os("HOME")?;
        Some(PathBuf::from(home).join("Library/Application Support/Blender"))
    }
    #[cfg(target_os = "windows")]
    {
        let appdata = std::env::var_os("APPDATA")?;
        Some(PathBuf::from(appdata).join("Blender Foundation/Blender"))
    }
    #[cfg(target_os = "linux")]
    {
        let home = std::env::var_os("HOME")?;
        Some(PathBuf::from(home).join(".config/blender"))
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    None
}

/// True when `target` is a symlink (not a real file / dir).
fn is_symlink(target: &Path) -> bool {
    fs::symlink_metadata(target)
        .map(|m| m.file_type().is_symlink())
        .unwrap_or(false)
}

// ── Detection ──────────────────────────────────────────────────────────

pub fn detect_dcc_versions(dcc: &str) -> Vec<DccVersion> {
    match dcc {
        "blender" => detect_blender(),
        // Other DCCs not yet implemented; empty list signals "no versions
        // detected" in the UI.
        _ => vec![],
    }
}

fn detect_blender() -> Vec<DccVersion> {
    let Some(base) = blender_base_dir() else {
        return vec![];
    };
    if !base.exists() {
        return vec![];
    }

    let entries = match fs::read_dir(&base) {
        Ok(e) => e,
        Err(_) => return vec![],
    };

    let mut versions: Vec<DccVersion> = vec![];

    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let name = match path.file_name().and_then(|s| s.to_str()) {
            Some(n) => n.to_string(),
            None => continue,
        };
        // Skip non-version directories like "Config" or hidden dotfiles.
        let first = name.chars().next();
        if !first.map(|c| c.is_ascii_digit()).unwrap_or(false) {
            continue;
        }

        let addons_dir = path.join("scripts").join("addons");
        let target = addons_dir.join("blender_mcp");
        let installed = target.exists() || is_symlink(&target);
        let install_method = if installed {
            Some(
                if is_symlink(&target) {
                    "symlink"
                } else {
                    "copy"
                }
                .to_string(),
            )
        } else {
            None
        };

        versions.push(DccVersion {
            version: name,
            pref_dir: path.to_string_lossy().into_owned(),
            addons_dir: addons_dir.to_string_lossy().into_owned(),
            installed,
            install_method,
        });
    }

    // Newest version first.
    versions.sort_by(|a, b| b.version.cmp(&a.version));
    versions
}

// ── Install / Uninstall ────────────────────────────────────────────────

fn copy_dir_all(src: &Path, dst: &Path) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let ty = entry.file_type()?;
        let src_path = entry.path();
        let dst_path = dst.join(entry.file_name());
        if ty.is_dir() {
            copy_dir_all(&src_path, &dst_path)?;
        } else {
            fs::copy(&src_path, &dst_path)?;
        }
    }
    Ok(())
}

fn remove_install(target: &Path) -> std::io::Result<()> {
    if is_symlink(target) {
        fs::remove_file(target)
    } else if target.exists() {
        fs::remove_dir_all(target)
    } else {
        Ok(())
    }
}

pub fn install_plugin(dcc: &str, version: &str) -> InstallResult {
    match dcc {
        "blender" => install_blender(version),
        _ => InstallResult {
            ok: false,
            method: String::new(),
            path: String::new(),
            error: Some(format!("Install not implemented for {dcc} yet")),
        },
    }
}

fn install_blender(version: &str) -> InstallResult {
    let Some(base) = blender_base_dir() else {
        return InstallResult {
            ok: false,
            method: String::new(),
            path: String::new(),
            error: Some("Could not locate Blender pref directory on this platform".into()),
        };
    };

    let addons_dir = base.join(version).join("scripts").join("addons");
    if let Err(e) = fs::create_dir_all(&addons_dir) {
        return InstallResult {
            ok: false,
            method: String::new(),
            path: addons_dir.to_string_lossy().into_owned(),
            error: Some(format!("create addons dir: {e}")),
        };
    }

    let target = addons_dir.join("blender_mcp");
    let source = match plugins_dir().join("blender").canonicalize() {
        Ok(p) => p,
        Err(e) => {
            return InstallResult {
                ok: false,
                method: String::new(),
                path: target.to_string_lossy().into_owned(),
                error: Some(format!("plugin source not found: {e}")),
            };
        }
    };

    // Wipe any previous install (symlink or copy).
    if let Err(e) = remove_install(&target) {
        return InstallResult {
            ok: false,
            method: String::new(),
            path: target.to_string_lossy().into_owned(),
            error: Some(format!("remove previous install: {e}")),
        };
    }

    // Try symlink first — avoids copying and keeps the addon source live.
    #[cfg(unix)]
    let symlink_result = std::os::unix::fs::symlink(&source, &target);
    #[cfg(windows)]
    let symlink_result = std::os::windows::fs::symlink_dir(&source, &target);

    if symlink_result.is_ok() {
        return InstallResult {
            ok: true,
            method: "symlink".into(),
            path: target.to_string_lossy().into_owned(),
            error: None,
        };
    }

    // Fallback: deep copy. Happens on Windows without symlink privilege
    // or on filesystems that refuse symlinks.
    match copy_dir_all(&source, &target) {
        Ok(()) => InstallResult {
            ok: true,
            method: "copy".into(),
            path: target.to_string_lossy().into_owned(),
            error: None,
        },
        Err(e) => InstallResult {
            ok: false,
            method: String::new(),
            path: target.to_string_lossy().into_owned(),
            error: Some(format!("copy failed: {e}")),
        },
    }
}

pub fn uninstall_plugin(dcc: &str, version: &str) -> UninstallResult {
    match dcc {
        "blender" => uninstall_blender(version),
        _ => UninstallResult {
            ok: false,
            was_installed: false,
            error: Some(format!("Uninstall not implemented for {dcc} yet")),
        },
    }
}

fn uninstall_blender(version: &str) -> UninstallResult {
    let Some(base) = blender_base_dir() else {
        return UninstallResult {
            ok: false,
            was_installed: false,
            error: Some("Could not locate Blender pref directory on this platform".into()),
        };
    };
    let target = base.join(version).join("scripts").join("addons").join("blender_mcp");

    let was_installed = target.exists() || is_symlink(&target);
    if !was_installed {
        return UninstallResult {
            ok: true,
            was_installed: false,
            error: None,
        };
    }

    match remove_install(&target) {
        Ok(()) => UninstallResult {
            ok: true,
            was_installed: true,
            error: None,
        },
        Err(e) => UninstallResult {
            ok: false,
            was_installed: true,
            error: Some(e.to_string()),
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_dcc_returns_empty() {
        assert!(detect_dcc_versions("nonexistent").is_empty());
    }

    #[test]
    fn install_unknown_dcc_reports_error() {
        let r = install_plugin("nonexistent", "1.0");
        assert!(!r.ok);
        assert!(r.error.is_some());
    }
}
