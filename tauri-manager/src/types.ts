/**
 * Frontend types mirroring the Rust #[derive(Serialize)] structs
 * in src-tauri/src/{scan.rs, install.rs}.
 */

// ── scan.rs ─────────────────────────────────────────────────────────

export interface DccInstance {
  port: number;
  pid: number;
  dcc_type: string;
  exe_path: string;
  window_title: string;
}

// ── install.rs ──────────────────────────────────────────────────────

export interface DccVersion {
  version: string;
  pref_dir: string;
  addons_dir: string;
  installed: boolean;
  /** "symlink" | "copy" | null */
  install_method: string | null;
}

export interface InstallResult {
  ok: boolean;
  /** "symlink" | "copy" | "" on failure */
  method: string;
  path: string;
  error: string | null;
}

export interface UninstallResult {
  ok: boolean;
  was_installed: boolean;
  error: string | null;
}

// ── project.rs ──────────────────────────────────────────────────────

export interface ManagedProject {
  path: string;
  installed_mcps: string[];
  added_at: string;
}

export interface SetupResult {
  ok: boolean;
  project_path: string;
  installed_mcps: string[];
  settings_path: string;
  /** "created" | "merged" */
  settings_op: string;
  error: string | null;
}

export interface RemoveResult {
  ok: boolean;
  removed_keys: string[];
  error: string | null;
}
