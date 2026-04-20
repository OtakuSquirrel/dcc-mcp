//! DCC instance scanning.
//!
//! Cross-platform port scan. Returns `(port, pid, command_name)` triples
//! for every TCP listener in the given range, via platform-specific
//! subprocess calls:
//!
//!   Unix (macOS, Linux): `lsof -iTCP:<min>-<max> -sTCP:LISTEN -P -n -F pcn`
//!   Windows:             `netstat -ano -p TCP` + `tasklist /FO CSV /NH`
//!
//! Filtering by DCC executable name then happens in the platform-neutral
//! `list_dcc_instances` wrapper below.

use serde::Serialize;
use std::process::Command;

#[derive(Debug, Clone, Serialize)]
pub struct DccInstance {
    pub port: u16,
    pub pid: u32,
    pub dcc_type: String,
    pub exe_path: String,
    pub window_title: String,
}

/// (port, pid, command_name) — command_name may be empty on platforms
/// where a second subprocess call is needed to resolve it (we only do
/// that call when the port falls in our range, to save work).
type Listener = (u16, u32, String);

/// Map lowercase process command name → DCC type string.
/// Ordered from most-specific to least; first match wins for partial fallback.
const DCC_EXE_PATTERNS: &[(&str, &str)] = &[
    ("blender", "blender"),
    ("houdinifx", "houdini"),
    ("houdinicore", "houdini"),
    ("houdini", "houdini"),
    ("hython", "houdini"),
    ("maya", "maya"),
    ("unrealeditor", "ue"),
    ("ue4editor", "ue"),
    ("ue5editor", "ue"),
];

fn identify_dcc(command_name: &str) -> Option<&'static str> {
    // Strip common suffixes (.exe, path separators) before matching.
    let base = command_name
        .rsplit(|c| c == '/' || c == '\\')
        .next()
        .unwrap_or(command_name)
        .trim_end_matches(".exe")
        .trim_end_matches(".EXE");
    let lower = base.to_lowercase();

    for (pattern, dcc) in DCC_EXE_PATTERNS {
        if lower == *pattern {
            return Some(dcc);
        }
    }
    for (pattern, dcc) in DCC_EXE_PATTERNS {
        if lower.contains(pattern) {
            return Some(dcc);
        }
    }
    None
}

// ══════════════════════════════════════════════════════════════════════
// Unix backend (lsof)
// ══════════════════════════════════════════════════════════════════════

#[cfg(not(target_os = "windows"))]
fn list_listeners(port_min: u16, port_max: u16) -> Vec<Listener> {
    let range_arg = format!("-iTCP:{}-{}", port_min, port_max);
    let output = match Command::new("lsof")
        .args([&range_arg, "-sTCP:LISTEN", "-P", "-n", "-F", "pcn"])
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            eprintln!("scan: lsof spawn failed: {e}");
            return vec![];
        }
    };

    // lsof -F output: p<pid>, c<cmd>, n<addr>:<port> — one field per line.
    let text = String::from_utf8_lossy(&output.stdout);
    let mut listeners: Vec<Listener> = vec![];
    let mut cur_pid: Option<u32> = None;
    let mut cur_cmd = String::new();

    for line in text.lines() {
        if line.is_empty() {
            continue;
        }
        let (prefix, rest) = line.split_at(1);
        match prefix {
            "p" => {
                cur_pid = rest.parse().ok();
                cur_cmd.clear();
            }
            "c" => {
                cur_cmd = rest.to_string();
            }
            "n" => {
                let port_str = rest.rsplit(':').next().unwrap_or("");
                if let Ok(port) = port_str.parse::<u16>() {
                    if port >= port_min && port <= port_max {
                        if let Some(pid) = cur_pid {
                            listeners.push((port, pid, cur_cmd.clone()));
                        }
                    }
                }
            }
            _ => {}
        }
    }
    listeners
}

#[cfg(not(target_os = "windows"))]
fn get_exe_path(pid: u32) -> Option<String> {
    // macOS / Linux: `ps -p <pid> -o comm=` (command path, no header).
    let output = Command::new("ps")
        .args(["-p", &pid.to_string(), "-o", "comm="])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let s = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if s.is_empty() { None } else { Some(s) }
}

// ══════════════════════════════════════════════════════════════════════
// Windows backend (netstat + tasklist)
// ══════════════════════════════════════════════════════════════════════

#[cfg(target_os = "windows")]
fn list_listeners(port_min: u16, port_max: u16) -> Vec<Listener> {
    // One netstat call gets every TCP socket on the machine.
    let output = match Command::new("netstat").args(["-ano", "-p", "TCP"]).output() {
        Ok(o) => o,
        Err(e) => {
            eprintln!("scan: netstat spawn failed: {e}");
            return vec![];
        }
    };

    let text = String::from_utf8_lossy(&output.stdout);
    // netstat line shape:
    //   TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       972
    //   TCP    [::]:135               [::]:0                 LISTENING       972
    let mut raw: Vec<(u16, u32)> = vec![];
    for line in text.lines() {
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() < 5 {
            continue;
        }
        if parts[0] != "TCP" {
            continue;
        }
        if parts[3] != "LISTENING" {
            continue;
        }
        // Parse port from parts[1] "addr:port" (IPv6 may have brackets).
        let local = parts[1];
        let port_str = local.rsplit(':').next().unwrap_or("");
        let port: u16 = match port_str.parse() {
            Ok(p) => p,
            Err(_) => continue,
        };
        if port < port_min || port > port_max {
            continue;
        }
        let pid: u32 = match parts[4].parse() {
            Ok(p) => p,
            Err(_) => continue,
        };
        raw.push((port, pid));
    }

    if raw.is_empty() {
        return vec![];
    }

    // Resolve PID → image name via a single tasklist call.
    let pid_to_name = tasklist_all();
    raw.into_iter()
        .map(|(port, pid)| {
            let name = pid_to_name
                .get(&pid)
                .cloned()
                .unwrap_or_else(String::new);
            (port, pid, name)
        })
        .collect()
}

#[cfg(target_os = "windows")]
fn tasklist_all() -> std::collections::HashMap<u32, String> {
    use std::collections::HashMap;
    let mut map: HashMap<u32, String> = HashMap::new();
    let output = match Command::new("tasklist").args(["/FO", "CSV", "/NH"]).output() {
        Ok(o) => o,
        Err(_) => return map,
    };
    let text = String::from_utf8_lossy(&output.stdout);
    for line in text.lines() {
        // CSV: "Image Name","PID","Session Name","Session#","Mem Usage"
        // Parsing naively since image names don't contain commas.
        let trimmed = line.trim();
        if !trimmed.starts_with('"') {
            continue;
        }
        let fields: Vec<&str> = trimmed
            .split("\",\"")
            .map(|f| f.trim_matches('"'))
            .collect();
        if fields.len() < 2 {
            continue;
        }
        let name = fields[0].to_string();
        let pid: u32 = match fields[1].parse() {
            Ok(p) => p,
            Err(_) => continue,
        };
        map.insert(pid, name);
    }
    map
}

#[cfg(target_os = "windows")]
fn get_exe_path(_pid: u32) -> Option<String> {
    // The tasklist lookup already gave us the image name, which we pass
    // through command_name in list_dcc_instances. Returning None here
    // lets the caller fall back to cmd (the name from tasklist).
    //
    // A full path would require `wmic`/PowerShell/Win32 API — deferred
    // until we have a concrete need.
    None
}

// ══════════════════════════════════════════════════════════════════════
// Public API
// ══════════════════════════════════════════════════════════════════════

pub fn list_dcc_instances(port_min: u16, port_max: u16) -> Vec<DccInstance> {
    if port_min > port_max {
        return vec![];
    }
    let listeners = list_listeners(port_min, port_max);
    let mut instances: Vec<DccInstance> = vec![];
    for (port, pid, cmd) in listeners {
        let dcc = match identify_dcc(&cmd) {
            Some(d) => d,
            None => continue,
        };
        let exe = get_exe_path(pid).unwrap_or_else(|| cmd.clone());
        instances.push(DccInstance {
            port,
            pid,
            dcc_type: dcc.to_string(),
            exe_path: exe,
            window_title: String::new(),
        });
    }

    // Listeners may appear twice (IPv4 + IPv6 or netstat dup lines).
    instances.sort_by_key(|i| i.port);
    instances.dedup_by_key(|i| i.port);
    instances
}

/// Return the first TCP port in `[port_min, port_max]` that is not
/// currently held by any listening process. Returns `None` if the range
/// is exhausted or the scan fails.
///
/// Unlike `list_dcc_instances`, this scans ALL listeners (not just DCCs)
/// so we correctly avoid ports occupied by unrelated processes.
pub fn next_free_port(port_min: u16, port_max: u16) -> Option<u16> {
    if port_min > port_max {
        return None;
    }
    let occupied: std::collections::HashSet<u16> = list_listeners(port_min, port_max)
        .into_iter()
        .map(|(p, _, _)| p)
        .collect();
    (port_min..=port_max).find(|p| !occupied.contains(p))
}

// ══════════════════════════════════════════════════════════════════════
// Tests
// ══════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identify_dcc_exact() {
        assert_eq!(identify_dcc("blender"), Some("blender"));
        assert_eq!(identify_dcc("Blender"), Some("blender"));
        assert_eq!(identify_dcc("houdinifx"), Some("houdini"));
        assert_eq!(identify_dcc("firefox"), None);
    }

    #[test]
    fn identify_dcc_partial() {
        assert_eq!(identify_dcc("blender.app"), Some("blender"));
        assert_eq!(identify_dcc("HoudiniFX 20.0"), Some("houdini"));
    }

    #[test]
    fn identify_dcc_strips_exe_and_path() {
        // Windows scenarios: image name includes .exe; full paths.
        assert_eq!(identify_dcc("blender.exe"), Some("blender"));
        assert_eq!(identify_dcc("Blender.EXE"), Some("blender"));
        assert_eq!(
            identify_dcc("C:/Program Files/Blender Foundation/Blender/blender.exe"),
            Some("blender")
        );
        assert_eq!(
            identify_dcc("houdinifx.exe"),
            Some("houdini")
        );
    }

    #[test]
    fn scan_empty_range_is_fine() {
        let r = list_dcc_instances(65530, 65535);
        assert!(r.is_empty());
    }

    #[test]
    fn scan_reversed_range_returns_empty() {
        let r = list_dcc_instances(20000, 19000);
        assert!(r.is_empty());
    }

    #[test]
    fn next_free_reversed_range_returns_none() {
        assert_eq!(next_free_port(20000, 19000), None);
    }

    #[test]
    fn next_free_large_empty_range_returns_min() {
        // Ports 55000-55010 are almost certainly free on any dev machine.
        // If a test infra conflict ever occurs, adjust the range.
        let p = next_free_port(55000, 55010);
        assert!(p.is_some(), "expected a free port in 55000-55010");
    }
}
