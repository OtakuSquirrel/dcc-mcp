/**
 * Frontend binding for the unified `~/.dcc-mcp/config.toml`.
 *
 * Mirrors src-tauri/src/config.rs. The manager writes; Python MCP
 * servers read the same file at startup.
 */

import { useCallback, useEffect, useState } from "react";
import { invoke } from "./tauri";

export interface ConfigPorts {
  min: number;
  max: number;
}

export interface ConfigTools {
  disabled: string[];
}

export interface Config {
  ports: ConfigPorts;
  tools: Record<string, ConfigTools>;
}

/** Defaults mirror src-tauri/src/config.rs — keep in sync. */
export const DEFAULT_CONFIG: Config = {
  ports: { min: 18811, max: 20899 },
  tools: {},
};

/**
 * Hook that loads config on mount and re-fetches on demand. Returns the
 * hardcoded default while the Tauri round-trip resolves or in browser
 * preview mode, so callers don't need to handle a loading state.
 */
export function useConfig() {
  const [config, setConfig] = useState<Config>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const cfg = await invoke<Config>("get_config", undefined, DEFAULT_CONFIG);
      setConfig(cfg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { config, loading, refresh };
}

export async function setPorts(min: number, max: number): Promise<void> {
  await invoke<void>("set_config_ports", { min, max }, undefined);
}

export async function setDisabledTools(
  mcp: string,
  disabled: string[],
): Promise<void> {
  await invoke<void>(
    "set_config_disabled_tools",
    { mcp, disabled },
    undefined,
  );
}

/** Look up disabled tools for an MCP server, defaulting to empty. */
export function disabledTools(cfg: Config, mcp: string): string[] {
  return cfg.tools[mcp]?.disabled ?? [];
}
