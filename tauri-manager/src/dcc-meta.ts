/**
 * DCC application metadata.
 *
 * Central source of truth for how the manager labels and colors
 * instances it discovers in the scan. The manager UI does NOT
 * segregate by DCC — it scans a single shared port range and shows
 * every instance on one dashboard; each entry's `dcc_type` just
 * drives display colour and the appropriate Manual Start snippet.
 *
 * Port range is a single unified pool (see data_model memory).
 * Phase 1e will move the actual value into ~/.dcc-mcp/config.toml.
 */

export type DccKey = "blender" | "houdini" | "ue" | "maya";

export interface DccMeta {
  key: DccKey;
  label: string;
  color: string;
  iconUrl: string;
  /** Python one-liner to paste into the DCC's console; port from unified pool. */
  manualSnippet?: (port: number) => string;
}

export const DCCS: DccMeta[] = [
  {
    key: "blender",
    label: "Blender",
    color: "#E87D0D",
    iconUrl: "/icons/blender_icon_512x512.png",
    manualSnippet: (p) =>
      `from blender_mcp import socket_server; socket_server.start(${p})`,
  },
  {
    key: "houdini",
    label: "Houdini",
    color: "#FF3C00",
    iconUrl: "/icons/Houdini@0.5x.png",
    manualSnippet: (p) => `import hrpyc; hrpyc.start_server(port=${p})`,
  },
  {
    key: "ue",
    label: "Unreal Engine",
    color: "#0D47A1",
    iconUrl: "/icons/UE.png",
    // UE Remote Execution is enabled via plugin settings, not Python.
  },
  {
    key: "maya",
    label: "Maya",
    color: "#2D88D8",
    iconUrl: "/icons/Maya.png",
    // maya-mcp package not implemented yet; metadata kept for future.
  },
];

export const DCC_MAP: Record<string, DccMeta> = Object.fromEntries(
  DCCS.map((d) => [d.key, d])
);

/**
 * Unified port pool for all DCCs.
 * Transitional value 18811-20899 keeps current per-DCC Python MCP
 * servers visible during migration; Phase 1e will narrow to the
 * memory-documented default 18811-18910 once MCP servers read from
 * ~/.dcc-mcp/config.toml.
 */
export const PORT_MIN = 18811;
export const PORT_MAX = 20899;
