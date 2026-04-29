//! DCC plugin installation.
//!
//! Phase 3c-3: table-driven across Blender, Houdini, and Maya. UE
//! remains deferred — its plugin model (engine- vs project-scoped
//! Plugins folders, .uplugin manifests, editor restart) is different
//! enough that bolting it into the shared flow would regress the others.
//! UE returns an empty version list; the UI surfaces it as "not yet
//! wired".
//!
//! Each DCC's detection logic returns the set of versions found on the
//! local machine, plus the `addons_dir` into which the plugin is
//! installed. The common install/uninstall machinery (symlink-first with
//! a deep-copy fallback, re-install wipes a stale directory) is then
//! shared via a single code path parameterised by `DccSpec`.

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

// ── Internal: per-DCC detected version ─────────────────────────────────

#[derive(Debug, Clone)]
struct DetectedVersion {
    version: String,
    pref_dir: PathBuf,
    addons_dir: PathBuf,
}

// ── Per-DCC spec + detection implementations ───────────────────────────

/// Static metadata + detection function for one DCC. The detect fn
/// returns every version it finds on the current OS; the common install
/// code handles everything else.
struct DccSpec {
    key: &'static str,
    /// Directory under `<repo>/plugins/` holding the addon source.
    source_subdir: &'static str,
    /// Final directory name inside `addons_dir`. For Blender this is the
    /// addon package name; for Houdini/Maya it's the folder the DCC will
    /// import from a scripts path on startup.
    target_name: &'static str,
    detect: fn() -> Vec<DetectedVersion>,
}

const SPECS: &[DccSpec] = &[
    DccSpec {
        key: "blender",
        source_subdir: "blender",
        target_name: "blender_mcp",
        detect: detect_blender,
    },
    DccSpec {
        key: "houdini",
        source_subdir: "houdini",
        target_name: "houdini_mcp",
        detect: detect_houdini,
    },
    DccSpec {
        key: "maya",
        source_subdir: "maya",
        target_name: "maya_mcp",
        detect: detect_maya,
    },
    // UE intentionally absent — unsupported path returns an empty list.
];

fn spec_for(dcc: &str) -> Option<&'static DccSpec> {
    SPECS.iter().find(|s| s.key == dcc)
}

// ── Path helpers ───────────────────────────────────────────────────────

/// Root of the repository's `plugins/` directory (where the addon source
/// lives). In dev mode this resolves via `CARGO_MANIFEST_DIR` which is
/// baked in at compile time — pointing at `tauri-manager/src-tauri/`.
/// Climbing `../../plugins` lands on `<repo>/plugins/`.
///
/// Phase 5 (bundled build): switch to `tauri::AppHandle::path().resource_dir()
/// + "plugins"` so the addon source ships inside the app bundle.
fn plugins_dir() -> PathBuf {
    let manifest = env!("CARGO_MANIFEST_DIR");
    PathBuf::from(manifest).join("../../plugins")
}

fn home_dir() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

/// True when `target` is a symlink (not a real file / dir).
fn is_symlink(target: &Path) -> bool {
    fs::symlink_metadata(target)
        .map(|m| m.file_type().is_symlink())
        .unwrap_or(false)
}

/// Iterate direct child directories of `base`, yielding `(name, path)`
/// for each. Empty vec on missing dir / read error.
fn list_subdirs(base: &Path) -> Vec<(String, PathBuf)> {
    let Ok(entries) = fs::read_dir(base) else {
        return vec![];
    };
    let mut out = vec![];
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let Some(name) = path.file_name().and_then(|s| s.to_str()) else {
            continue;
        };
        out.push((name.to_string(), path));
    }
    out
}

// ── Blender detection ──────────────────────────────────────────────────

fn blender_base_dir() -> Option<PathBuf> {
    #[cfg(target_os = "macos")]
    {
        Some(home_dir()?.join("Library/Application Support/Blender"))
    }
    #[cfg(target_os = "windows")]
    {
        let appdata = std::env::var_os("APPDATA")?;
        Some(PathBuf::from(appdata).join("Blender Foundation/Blender"))
    }
    #[cfg(target_os = "linux")]
    {
        Some(home_dir()?.join(".config/blender"))
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    None
}

fn detect_blender() -> Vec<DetectedVersion> {
    let Some(base) = blender_base_dir() else {
        return vec![];
    };
    let mut out = vec![];
    for (name, path) in list_subdirs(&base) {
        // Skip non-version directories like "Config" or hidden dotfiles.
        if !name
            .chars()
            .next()
            .map(|c| c.is_ascii_digit())
            .unwrap_or(false)
        {
            continue;
        }
        let addons_dir = path.join("scripts").join("addons");
        out.push(DetectedVersion {
            version: name,
            pref_dir: path,
            addons_dir,
        });
    }
    out
}

// ── Houdini detection ──────────────────────────────────────────────────
//
// Houdini's user pref dir is `houdiniXX.X` under the platform-specific
// parent. We strip the "houdini" prefix for display.

fn houdini_parent_dir() -> Option<PathBuf> {
    #[cfg(target_os = "macos")]
    {
        Some(home_dir()?.join("Library/Preferences/houdini"))
    }
    #[cfg(target_os = "windows")]
    {
        // Houdini on Windows drops its user prefs into `Documents/houdiniXX.X`.
        Some(home_dir()?.join("Documents"))
    }
    #[cfg(target_os = "linux")]
    {
        home_dir()
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    None
}

fn detect_houdini() -> Vec<DetectedVersion> {
    let Some(parent) = houdini_parent_dir() else {
        return vec![];
    };

    // On macOS the parent already IS `houdini/`; versions are `20.5/`,
    // `19.5/` etc. On Windows / Linux the parent contains dirs named
    // `houdiniXX.X` directly.
    #[cfg(target_os = "macos")]
    let (uses_prefix, prefix) = (false, "");
    #[cfg(any(target_os = "windows", target_os = "linux"))]
    let (uses_prefix, prefix) = (true, "houdini");
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    let (uses_prefix, prefix) = (false, "");

    let mut out = vec![];
    for (name, path) in list_subdirs(&parent) {
        let version = if uses_prefix {
            match name.strip_prefix(prefix) {
                Some(rest) if !rest.is_empty() => rest.to_string(),
                _ => continue,
            }
        } else {
            // macOS: only accept directories starting with a digit.
            if !name
                .chars()
                .next()
                .map(|c| c.is_ascii_digit())
                .unwrap_or(false)
            {
                continue;
            }
            name.clone()
        };
        // Addon target: `<prefs>/python3.X/houdini_mcp/` would require
        // knowing the Python version. Simpler: drop it next to the other
        // per-user scripts at `<prefs>/python/houdini_mcp/`, which is on
        // HOUDINI_PATH via the default `scripts/python` entry.
        let addons_dir = path.join("scripts").join("python");
        out.push(DetectedVersion {
            version,
            pref_dir: path,
            addons_dir,
        });
    }
    out
}

// ── Maya detection ─────────────────────────────────────────────────────

fn maya_parent_dir() -> Option<PathBuf> {
    #[cfg(target_os = "macos")]
    {
        Some(home_dir()?.join("Library/Preferences/Autodesk/maya"))
    }
    #[cfg(target_os = "windows")]
    {
        Some(home_dir()?.join("Documents/maya"))
    }
    #[cfg(target_os = "linux")]
    {
        Some(home_dir()?.join("maya"))
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    None
}

fn detect_maya() -> Vec<DetectedVersion> {
    let Some(parent) = maya_parent_dir() else {
        return vec![];
    };
    let mut out = vec![];
    for (name, path) in list_subdirs(&parent) {
        // Maya version dirs are 4-digit years: "2023", "2024", "2025".
        if name.len() != 4 || !name.chars().all(|c| c.is_ascii_digit()) {
            continue;
        }
        let addons_dir = path.join("scripts");
        out.push(DetectedVersion {
            version: name,
            pref_dir: path,
            addons_dir,
        });
    }
    out
}

// ── Shared install / uninstall ─────────────────────────────────────────

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

fn sorted_desc(mut versions: Vec<DccVersion>) -> Vec<DccVersion> {
    versions.sort_by(|a, b| b.version.cmp(&a.version));
    versions
}

// ── Public API ─────────────────────────────────────────────────────────

pub fn detect_dcc_versions(dcc: &str) -> Vec<DccVersion> {
    let Some(spec) = spec_for(dcc) else {
        return vec![];
    };
    let detected = (spec.detect)();
    let rows = detected
        .into_iter()
        .map(|d| {
            let target = d.addons_dir.join(spec.target_name);
            let sym = is_symlink(&target);
            let installed = sym || target.exists();
            let install_method = if installed {
                Some(if sym { "symlink" } else { "copy" }.to_string())
            } else {
                None
            };
            DccVersion {
                version: d.version,
                pref_dir: d.pref_dir.to_string_lossy().into_owned(),
                addons_dir: d.addons_dir.to_string_lossy().into_owned(),
                installed,
                install_method,
            }
        })
        .collect();
    sorted_desc(rows)
}

pub fn install_plugin(dcc: &str, version: &str) -> InstallResult {
    let Some(spec) = spec_for(dcc) else {
        return InstallResult {
            ok: false,
            method: String::new(),
            path: String::new(),
            error: Some(format!("Install not implemented for {dcc} yet")),
        };
    };

    // Re-run detect and match by version — avoids re-deriving paths in a
    // second place (single source of truth for "where does this addon go").
    let detected = (spec.detect)();
    let Some(v) = detected.into_iter().find(|d| d.version == version) else {
        return InstallResult {
            ok: false,
            method: String::new(),
            path: String::new(),
            error: Some(format!("{dcc} version '{version}' not detected")),
        };
    };

    if let Err(e) = fs::create_dir_all(&v.addons_dir) {
        return InstallResult {
            ok: false,
            method: String::new(),
            path: v.addons_dir.to_string_lossy().into_owned(),
            error: Some(format!("create addons dir: {e}")),
        };
    }

    let target = v.addons_dir.join(spec.target_name);
    let source = match plugins_dir().join(spec.source_subdir).canonicalize() {
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

    if let Err(e) = remove_install(&target) {
        return InstallResult {
            ok: false,
            method: String::new(),
            path: target.to_string_lossy().into_owned(),
            error: Some(format!("remove previous install: {e}")),
        };
    }

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
    let Some(spec) = spec_for(dcc) else {
        return UninstallResult {
            ok: false,
            was_installed: false,
            error: Some(format!("Uninstall not implemented for {dcc} yet")),
        };
    };

    let detected = (spec.detect)();
    let Some(v) = detected.into_iter().find(|d| d.version == version) else {
        return UninstallResult {
            ok: true,
            was_installed: false,
            error: None,
        };
    };
    let target = v.addons_dir.join(spec.target_name);

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
    fn ue_is_unsupported() {
        // UE is intentionally not in SPECS yet.
        assert!(detect_dcc_versions("ue").is_empty());
        let r = install_plugin("ue", "5.4");
        assert!(!r.ok);
        assert!(r.error.is_some());
    }

    #[test]
    fn install_unknown_dcc_reports_error() {
        let r = install_plugin("nonexistent", "1.0");
        assert!(!r.ok);
        assert!(r.error.is_some());
    }

    #[test]
    fn install_unknown_version_reports_error() {
        // Even if the DCC key is known, a version that doesn't exist on
        // this machine should surface a clear error rather than silently
        // creating directories.
        let r = install_plugin("blender", "9999.9999");
        assert!(!r.ok);
        assert!(r.error.as_ref().unwrap().contains("not detected"));
    }

    #[test]
    fn uninstall_unknown_version_is_noop() {
        let r = uninstall_plugin("blender", "9999.9999");
        assert!(r.ok);
        assert!(!r.was_installed);
    }

    #[test]
    fn known_specs_are_wired() {
        assert!(spec_for("blender").is_some());
        assert!(spec_for("houdini").is_some());
        assert!(spec_for("maya").is_some());
        assert!(spec_for("ue").is_none());
    }
}
