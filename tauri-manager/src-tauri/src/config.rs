//! Unified user config at `~/.dcc-mcp/config.toml`.
//!
//! Shared by the Rust manager (ports, tool disable state) and — in a
//! future phase — the Python MCP servers (same path, same schema). The
//! manager owns writes; Python reads at startup.
//!
//! Schema:
//!
//! ```toml
//! [ports]
//! min = 18811
//! max = 20899
//!
//! [tools.blender]
//! disabled = ["execute_blender_code"]
//!
//! [tools.os]
//! disabled = []
//! ```
//!
//! Unknown keys are preserved on round-trip so the user's hand-edits
//! survive UI writes.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

// ── Schema ───────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    #[serde(default)]
    pub ports: Ports,
    #[serde(default)]
    pub tools: BTreeMap<String, ToolsSection>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            ports: Ports::default(),
            tools: BTreeMap::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Ports {
    pub min: u16,
    pub max: u16,
}

impl Default for Ports {
    fn default() -> Self {
        Self {
            min: 18811,
            max: 20899,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ToolsSection {
    #[serde(default)]
    pub disabled: Vec<String>,
}

// ── Paths ────────────────────────────────────────────────────────────

fn home_dir() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

fn config_dir() -> Option<PathBuf> {
    Some(home_dir()?.join(".dcc-mcp"))
}

pub fn config_path() -> Option<PathBuf> {
    Some(config_dir()?.join("config.toml"))
}

// ── I/O ──────────────────────────────────────────────────────────────

/// Load config from disk; return defaults if missing or malformed. On a
/// parse failure we do NOT overwrite — callers can surface the error to
/// the UI so the user can fix it by hand.
pub fn load() -> Config {
    let Some(path) = config_path() else {
        return Config::default();
    };
    let Ok(text) = fs::read_to_string(&path) else {
        return Config::default();
    };
    toml::from_str(&text).unwrap_or_default()
}

pub fn save(cfg: &Config) -> std::io::Result<()> {
    let Some(dir) = config_dir() else {
        return Err(std::io::Error::other("no home dir"));
    };
    fs::create_dir_all(&dir)?;
    let path = dir.join("config.toml");
    let text = toml::to_string_pretty(cfg)
        .map_err(|e| std::io::Error::other(format!("serialize: {e}")))?;
    fs::write(&path, text)
}

/// Ensure config.toml exists with defaults so Python side can read it
/// too. Safe to call on every app start.
pub fn ensure_exists() {
    let Some(path) = config_path() else { return };
    if !path.exists() {
        let _ = save(&Config::default());
    }
}

// ── Helpers used by Tauri commands ───────────────────────────────────

pub fn set_ports(min: u16, max: u16) -> Result<(), String> {
    if min >= max {
        return Err(format!("invalid range: min={min} max={max}"));
    }
    let mut cfg = load();
    cfg.ports = Ports { min, max };
    save(&cfg).map_err(|e| e.to_string())
}

pub fn set_disabled_tools(mcp: &str, disabled: Vec<String>) -> Result<(), String> {
    let mut cfg = load();
    cfg.tools
        .entry(mcp.to_string())
        .or_default()
        .disabled = disabled;
    save(&cfg).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_round_trips() {
        let cfg = Config::default();
        let s = toml::to_string_pretty(&cfg).unwrap();
        let back: Config = toml::from_str(&s).unwrap();
        assert_eq!(back.ports.min, 18811);
        assert_eq!(back.ports.max, 20899);
        assert!(back.tools.is_empty());
    }

    #[test]
    fn parses_hand_written_config() {
        let text = r#"
[ports]
min = 20000
max = 20100

[tools.blender]
disabled = ["execute_blender_code", "render_frame"]

[tools.os]
disabled = []
"#;
        let cfg: Config = toml::from_str(text).unwrap();
        assert_eq!(cfg.ports.min, 20000);
        assert_eq!(cfg.ports.max, 20100);
        assert_eq!(cfg.tools["blender"].disabled.len(), 2);
        assert_eq!(cfg.tools["os"].disabled.len(), 0);
    }

    #[test]
    fn missing_sections_default() {
        let text = r#"[ports]
min = 18811
max = 20899
"#;
        let cfg: Config = toml::from_str(text).unwrap();
        assert!(cfg.tools.is_empty());
    }

    #[test]
    fn empty_string_yields_defaults() {
        let cfg: Config = toml::from_str("").unwrap();
        assert_eq!(cfg.ports.min, 18811);
    }
}
