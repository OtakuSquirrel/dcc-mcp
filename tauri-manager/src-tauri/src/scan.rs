//! DCC instance scanning.
//!
//! Phase 2a: macOS-only. Uses `lsof` subprocess to find listening TCP
//! sockets in the configured port range, filters them to processes whose
//! command name matches a known DCC executable.
//!
//! Phase 2b will add a Windows backend using `GetExtendedTcpTable` (via
//! the `windows` crate or `netstat -ano` subprocess).

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
    let lower = command_name.to_lowercase();
    // Exact match first
    for (pattern, dcc) in DCC_EXE_PATTERNS {
        if lower == *pattern {
            return Some(dcc);
        }
    }
    // Partial match (e.g. "Blender" process on macOS shows up as "Blender")
    for (pattern, dcc) in DCC_EXE_PATTERNS {
        if lower.contains(pattern) {
            return Some(dcc);
        }
    }
    None
}

/// Get the full executable path of a process on macOS.
/// Uses `ps -p <pid> -o comm=` which prints just the exe path, no header.
fn get_exe_path(pid: u32) -> Option<String> {
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

/// Scan a port range and return all listening DCC instances.
///
/// macOS implementation: spawns `lsof -iTCP:<min>-<max> -sTCP:LISTEN -P -n -F pPcn`.
/// The `-F pPcn` flag requests a machine-readable output format where each
/// field is on its own line with a single-letter prefix:
///   p<pid>         process id (starts a new record)
///   c<command>     command name
///   P<protocol>    protocol (TCP/UDP)
///   n<addr>:<port> network endpoint
///
/// We parse this into (pid, cmd, port) triples and filter by DCC pattern.
pub fn list_dcc_instances(port_min: u16, port_max: u16) -> Vec<DccInstance> {
    if port_min > port_max {
        return vec![];
    }

    let range_arg = format!("-iTCP:{}-{}", port_min, port_max);
    let output = match Command::new("lsof")
        .args([&range_arg, "-sTCP:LISTEN", "-P", "-n", "-F", "pPcn"])
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            eprintln!("scan: lsof spawn failed: {}", e);
            return vec![];
        }
    };

    // lsof exits 1 when no matches found — that is expected, not an error.
    let text = String::from_utf8_lossy(&output.stdout);

    let mut instances: Vec<DccInstance> = vec![];
    let mut cur_pid: Option<u32> = None;
    let mut cur_cmd: Option<String> = None;

    for line in text.lines() {
        if line.is_empty() {
            continue;
        }
        let (prefix, rest) = line.split_at(1);
        match prefix {
            "p" => {
                // New record — reset command
                cur_pid = rest.parse().ok();
                cur_cmd = None;
            }
            "c" => {
                cur_cmd = Some(rest.to_string());
            }
            "n" => {
                // rest looks like "*:19811", "127.0.0.1:19811", "[::1]:19811"
                let port_str = rest.rsplit(':').next().unwrap_or("");
                if let Ok(port) = port_str.parse::<u16>() {
                    if port >= port_min && port <= port_max {
                        if let (Some(pid), Some(cmd)) = (cur_pid, cur_cmd.as_ref()) {
                            if let Some(dcc) = identify_dcc(cmd) {
                                let exe =
                                    get_exe_path(pid).unwrap_or_else(|| cmd.clone());
                                instances.push(DccInstance {
                                    port,
                                    pid,
                                    dcc_type: dcc.to_string(),
                                    exe_path: exe,
                                    window_title: String::new(),
                                });
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }

    // lsof may emit both IPv4 and IPv6 entries for the same listener.
    instances.sort_by_key(|i| i.port);
    instances.dedup_by_key(|i| i.port);
    instances
}

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
    fn scan_empty_range_is_fine() {
        let r = list_dcc_instances(65530, 65535);
        assert!(r.is_empty());
    }

    #[test]
    fn scan_reversed_range_returns_empty() {
        let r = list_dcc_instances(20000, 19000);
        assert!(r.is_empty());
    }
}
