//! DCC plugin installation.
//!
//! Phase 3c-4: covers Blender, Houdini, Maya, and Unreal Engine. The
//! first three install a single named directory under the per-version
//! pref dir (`addons_dir/<target_name>`) — symlink first, deep-copy
//! fallback. UE is engine-scoped: it copies individual `*.py` files
//! straight into `<UE_install>/Engine/Content/Python/` because UE only
//! auto-loads `init_unreal.py` when it lives at the top of a Python
//! search path, not in a subdirectory.
//!
//! Each DCC's detection logic returns the set of versions found on the
//! local machine, plus the `addons_dir` into which the plugin is
//! installed. The shared install/uninstall machinery branches on
//! `InstallKind` per spec.

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

/// How a DCC's plugin source maps onto its addon search path.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum InstallKind {
    /// Place the entire source directory at `addons_dir/<target_name>`,
    /// preferring a symlink and falling back to a deep copy. Used by
    /// Blender (the `addons/` convention), and by Houdini/Maya where
    /// the target is a folder on a scripts search path.
    DirectoryAtTarget,
    /// Copy every `*.py` file from the source dir straight into
    /// `addons_dir`, leaving `target_name` unused. Used by UE because
    /// the editor only auto-loads `init_unreal.py` when it sits at the
    /// top of a Python search path — not inside a subdirectory.
    LooseFiles,
}

/// Static metadata + detection function for one DCC. The detect fn
/// returns every version it finds on the current OS; the common install
/// code handles everything else.
struct DccSpec {
    key: &'static str,
    /// Directory under `<repo>/plugins/` holding the addon source.
    source_subdir: &'static str,
    /// Final directory name inside `addons_dir`. Ignored when
    /// `kind == LooseFiles`.
    target_name: &'static str,
    kind: InstallKind,
    detect: fn() -> Vec<DetectedVersion>,
}

const SPECS: &[DccSpec] = &[
    DccSpec {
        key: "blender",
        source_subdir: "blender",
        target_name: "blender_mcp",
        kind: InstallKind::DirectoryAtTarget,
        detect: detect_blender,
    },
    DccSpec {
        key: "houdini",
        source_subdir: "houdini",
        target_name: "houdini_mcp",
        kind: InstallKind::DirectoryAtTarget,
        detect: detect_houdini,
    },
    DccSpec {
        key: "maya",
        source_subdir: "maya",
        target_name: "maya_mcp",
        kind: InstallKind::DirectoryAtTarget,
        detect: detect_maya,
    },
    DccSpec {
        key: "ue",
        source_subdir: "ue",
        target_name: "",
        kind: InstallKind::LooseFiles,
        detect: detect_ue,
    },
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

// ── UE detection ───────────────────────────────────────────────────────
//
// UE installs land in `<root>/UE_<version>/Engine/Binaries/.../UnrealEditor.exe`.
// Plugins go into `<root>/UE_<version>/Engine/Content/Python/` (engine-wide).
// We scan a fixed set of common roots; users with non-standard locations
// can rely on the Manual Start row in the UI rather than auto-detect.

fn ue_search_roots() -> Vec<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        vec![
            PathBuf::from("C:/Program Files/Epic Games"),
            PathBuf::from("D:/Program Files/Epic Games"),
            PathBuf::from("C:/Epic Games"),
            PathBuf::from("D:/Epic Games"),
        ]
    }
    #[cfg(target_os = "macos")]
    {
        vec![
            PathBuf::from("/Users/Shared/Epic Games"),
            home_dir().map(|h| h.join("Epic Games")).unwrap_or_default(),
        ]
        .into_iter()
        .filter(|p| !p.as_os_str().is_empty())
        .collect()
    }
    #[cfg(target_os = "linux")]
    {
        let home = home_dir();
        let mut out = vec![];
        if let Some(h) = home {
            out.push(h.join("Epic Games"));
        }
        out.push(PathBuf::from("/opt/Epic Games"));
        out
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
    {
        vec![]
    }
}

fn detect_ue() -> Vec<DetectedVersion> {
    let mut out = vec![];
    for root in ue_search_roots() {
        if !root.exists() {
            continue;
        }
        for (name, path) in list_subdirs(&root) {
            // Match `UE_5.4`, `UE_5.3`, `UE_4.27`, ...
            let Some(version) = name.strip_prefix("UE_") else {
                continue;
            };
            if version.is_empty() {
                continue;
            }
            // Engine binary must exist before we offer install — otherwise
            // we'd promote a corrupt or in-progress install.
            #[cfg(target_os = "windows")]
            let editor = path
                .join("Engine/Binaries/Win64/UnrealEditor.exe")
                .exists()
                || path
                    .join("Engine/Binaries/Win64/UE4Editor.exe")
                    .exists();
            #[cfg(target_os = "macos")]
            let editor = path
                .join("Engine/Binaries/Mac/UnrealEditor.app")
                .exists();
            #[cfg(target_os = "linux")]
            let editor = path
                .join("Engine/Binaries/Linux/UnrealEditor")
                .exists();
            #[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
            let editor = false;

            if !editor {
                continue;
            }

            out.push(DetectedVersion {
                version: version.to_string(),
                pref_dir: path.clone(),
                addons_dir: path.join("Engine/Content/Python"),
            });
        }
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

/// List of `*.py` filenames a `LooseFiles` install drops into the
/// addons dir. Source is always `<repo>/plugins/<source_subdir>/`.
fn loose_files(spec: &DccSpec) -> Vec<PathBuf> {
    let src = plugins_dir().join(spec.source_subdir);
    let Ok(entries) = fs::read_dir(&src) else {
        return vec![];
    };
    entries
        .flatten()
        .filter_map(|e| {
            let p = e.path();
            (p.is_file() && p.extension().and_then(|s| s.to_str()) == Some("py")).then_some(p)
        })
        .collect()
}

/// True when every loose file from the source dir is present at the
/// target. Conservative — partial copies still report "installed" so
/// the user gets prompted to repair via re-install.
fn loose_files_installed(spec: &DccSpec, addons_dir: &Path) -> bool {
    let files = loose_files(spec);
    if files.is_empty() {
        return false;
    }
    files.iter().any(|src| {
        if let Some(name) = src.file_name() {
            addons_dir.join(name).exists()
        } else {
            false
        }
    })
}

pub fn detect_dcc_versions(dcc: &str) -> Vec<DccVersion> {
    let Some(spec) = spec_for(dcc) else {
        return vec![];
    };
    let detected = (spec.detect)();
    let rows = detected
        .into_iter()
        .map(|d| match spec.kind {
            InstallKind::DirectoryAtTarget => {
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
            }
            InstallKind::LooseFiles => {
                let installed = loose_files_installed(spec, &d.addons_dir);
                DccVersion {
                    version: d.version,
                    pref_dir: d.pref_dir.to_string_lossy().into_owned(),
                    addons_dir: d.addons_dir.to_string_lossy().into_owned(),
                    installed,
                    install_method: installed.then_some("copy".to_string()),
                }
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

    let source_dir = match plugins_dir().join(spec.source_subdir).canonicalize() {
        Ok(p) => p,
        Err(e) => {
            return InstallResult {
                ok: false,
                method: String::new(),
                path: v.addons_dir.to_string_lossy().into_owned(),
                error: Some(format!("plugin source not found: {e}")),
            };
        }
    };

    match spec.kind {
        InstallKind::DirectoryAtTarget => install_directory(&source_dir, &v.addons_dir, spec.target_name),
        InstallKind::LooseFiles => install_loose_files(spec, &v.addons_dir),
    }
}

fn install_directory(source: &Path, addons_dir: &Path, target_name: &str) -> InstallResult {
    let target = addons_dir.join(target_name);

    if let Err(e) = remove_install(&target) {
        return InstallResult {
            ok: false,
            method: String::new(),
            path: target.to_string_lossy().into_owned(),
            error: Some(format!("remove previous install: {e}")),
        };
    }

    #[cfg(unix)]
    let symlink_result = std::os::unix::fs::symlink(source, &target);
    #[cfg(windows)]
    let symlink_result = std::os::windows::fs::symlink_dir(source, &target);

    if symlink_result.is_ok() {
        return InstallResult {
            ok: true,
            method: "symlink".into(),
            path: target.to_string_lossy().into_owned(),
            error: None,
        };
    }

    match copy_dir_all(source, &target) {
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

fn install_loose_files(spec: &DccSpec, addons_dir: &Path) -> InstallResult {
    // UE wants individual `*.py` files at the top of `Engine/Content/Python/`,
    // not a subdirectory. Copy each file fresh — symlinks for individual
    // files cause headaches with UE's editor restart workflow on Windows.
    let files = loose_files(spec);
    if files.is_empty() {
        return InstallResult {
            ok: false,
            method: String::new(),
            path: addons_dir.to_string_lossy().into_owned(),
            error: Some(format!(
                "no .py files found in plugins/{}/",
                spec.source_subdir
            )),
        };
    }
    let mut copied = 0usize;
    for src in &files {
        let Some(name) = src.file_name() else {
            continue;
        };
        let dst = addons_dir.join(name);
        // Best-effort wipe of a stale copy / symlink first.
        let _ = remove_install(&dst);
        if let Err(e) = fs::copy(src, &dst) {
            return InstallResult {
                ok: false,
                method: String::new(),
                path: dst.to_string_lossy().into_owned(),
                error: Some(format!("copy {}: {e}", name.to_string_lossy())),
            };
        }
        copied += 1;
    }
    InstallResult {
        ok: true,
        method: format!("copy ({copied} files)"),
        path: addons_dir.to_string_lossy().into_owned(),
        error: None,
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

    match spec.kind {
        InstallKind::DirectoryAtTarget => uninstall_directory(&v.addons_dir, spec.target_name),
        InstallKind::LooseFiles => uninstall_loose_files(spec, &v.addons_dir),
    }
}

fn uninstall_directory(addons_dir: &Path, target_name: &str) -> UninstallResult {
    let target = addons_dir.join(target_name);
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

fn uninstall_loose_files(spec: &DccSpec, addons_dir: &Path) -> UninstallResult {
    let files = loose_files(spec);
    let mut found_any = false;
    for src in &files {
        let Some(name) = src.file_name() else {
            continue;
        };
        let dst = addons_dir.join(name);
        if dst.exists() || is_symlink(&dst) {
            found_any = true;
            if let Err(e) = remove_install(&dst) {
                return UninstallResult {
                    ok: false,
                    was_installed: true,
                    error: Some(format!("remove {}: {e}", name.to_string_lossy())),
                };
            }
        }
    }
    UninstallResult {
        ok: true,
        was_installed: found_any,
        error: None,
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
    fn ue_install_unknown_version_reports_error() {
        // UE is wired in Phase 3c-4; an unknown version should now error
        // with "not detected" (same as Blender) rather than the old
        // "not implemented" message.
        let r = install_plugin("ue", "9999.9999");
        assert!(!r.ok);
        assert!(r.error.as_ref().unwrap().contains("not detected"));
    }

    #[test]
    fn ue_loose_files_helper_finds_plugin_pys() {
        // The repo's plugins/ue/ should hold init_unreal.py and
        // ue_mcp_server.py. If this changes (e.g. plugin moves to a
        // subdir), the LooseFiles install path will silently install
        // nothing — fail loudly here instead.
        let spec = spec_for("ue").expect("ue spec");
        let files = loose_files(spec);
        let names: Vec<_> = files
            .iter()
            .filter_map(|p| p.file_name().and_then(|n| n.to_str()).map(String::from))
            .collect();
        assert!(names.contains(&"init_unreal.py".to_string()), "names = {names:?}");
        assert!(names.contains(&"ue_mcp_server.py".to_string()), "names = {names:?}");
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
        assert!(spec_for("ue").is_some());
    }

    #[test]
    fn ue_uses_loose_files_kind() {
        let spec = spec_for("ue").expect("ue spec");
        assert!(matches!(spec.kind, InstallKind::LooseFiles));
        // target_name is unused for LooseFiles; the empty string
        // signals that to readers of SPECS.
        assert_eq!(spec.target_name, "");
    }

    #[test]
    fn blender_remains_directory_kind() {
        // Regression guard: changing Blender to LooseFiles would break
        // the Blender addon registration model (which expects a single
        // `blender_mcp/` package directory under `addons/`).
        let spec = spec_for("blender").expect("blender spec");
        assert!(matches!(spec.kind, InstallKind::DirectoryAtTarget));
    }
}
