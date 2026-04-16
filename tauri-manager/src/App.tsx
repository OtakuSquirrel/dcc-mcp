import { useState, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { DccInstance } from "./types";
import "./App.css";

// Phase 2a scanning range — covers Houdini/Blender/UE ranges today.
// Phase 1e will unify via ~/.dcc-mcp/config.toml.
const DEFAULT_PORT_MIN = 18811;
const DEFAULT_PORT_MAX = 20899;

// ── Manual Start metadata ──────────────────────────────────────────────
// One row per DCC. Each row shows a one-line Python snippet to paste into
// that DCC's Python console to start its MCP socket server. The port is
// auto-filled from next_free_port() in the DCC's range.

interface ManualStartDcc {
  dccType: "blender" | "houdini" | "maya" | "ue";
  name: string;
  portMin: number;
  portMax: number;
  snippet: (port: number) => string;
}

const MANUAL_START_DCCS: ManualStartDcc[] = [
  {
    dccType: "blender",
    name: "Blender",
    portMin: 19811,
    portMax: 19899,
    snippet: (p) =>
      `from blender_mcp import socket_server; socket_server.start(${p})`,
  },
  {
    dccType: "houdini",
    name: "Houdini",
    portMin: 18811,
    portMax: 18899,
    snippet: (p) => `import hrpyc; hrpyc.start_server(port=${p})`,
  },
];

function ManualStartRow({
  dcc,
  refreshKey,
}: {
  dcc: ManualStartDcc;
  refreshKey: number;
}) {
  const [port, setPort] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    invoke<number | null>("next_free_port", {
      portMin: dcc.portMin,
      portMax: dcc.portMax,
    })
      .then((p) => {
        setPort(p);
        setError(p === null ? "range exhausted" : null);
      })
      .catch((e) => setError(String(e)));
  }, [dcc, refreshKey]);

  const snippet = port !== null ? dcc.snippet(port) : "";

  const copy = async () => {
    if (!snippet) return;
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      setError(`clipboard: ${e}`);
    }
  };

  return (
    <div className={`cmd-row tag-hint-${dcc.dccType}`}>
      <span className="cmd-label">{dcc.name}</span>
      <div
        className="cmd-code"
        onClick={copy}
        title="Click to copy"
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") copy();
        }}
      >
        {snippet || (error ?? "Loading…")}
      </div>
      <span className={`cmd-copied${copied ? " show" : ""}`}>Copied</span>
    </div>
  );
}

function ManualStart({ refreshKey }: { refreshKey: number }) {
  return (
    <section className="manual-start">
      {MANUAL_START_DCCS.map((dcc) => (
        <ManualStartRow key={dcc.dccType} dcc={dcc} refreshKey={refreshKey} />
      ))}
    </section>
  );
}

// ── Main App ───────────────────────────────────────────────────────────

function App() {
  const [instances, setInstances] = useState<DccInstance[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastScan, setLastScan] = useState<Date | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await invoke<DccInstance[]>("list_dcc_instances", {
        portMin: DEFAULT_PORT_MIN,
        portMax: DEFAULT_PORT_MAX,
      });
      setInstances(result);
      setLastScan(new Date());
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <main className="container">
      <header>
        <div className="title-block">
          <h1>DCC MCP Manager</h1>
          <div className="sub">
            Port range {DEFAULT_PORT_MIN}–{DEFAULT_PORT_MAX}
            {lastScan && (
              <span className="timestamp">
                {" · scanned "}
                {lastScan.toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>
        <button onClick={refresh} disabled={loading}>
          {loading ? "Scanning…" : "Refresh"}
        </button>
      </header>

      <ManualStart refreshKey={refreshKey} />

      {error && <div className="error">Error: {error}</div>}

      <h2 className="section-title">Running instances</h2>

      {instances.length === 0 && !loading && !error && (
        <div className="empty">
          <p>No DCC instances detected in range.</p>
          <p className="empty-hint">
            Copy a snippet above and run it in your DCC, or ask Claude to{" "}
            <code>start_blender</code>, then Refresh.
          </p>
        </div>
      )}

      <ul className="instances">
        {instances.map((i) => (
          <li key={i.port} className="instance">
            <div className="head">
              <span className="port">:{i.port}</span>
              <span className={`tag tag-${i.dcc_type}`}>{i.dcc_type}</span>
              <span className="pid">pid {i.pid}</span>
            </div>
            <div className="path">{i.exe_path}</div>
            {i.window_title && <div className="win-title">{i.window_title}</div>}
          </li>
        ))}
      </ul>

      <footer>
        <span>
          {instances.length} instance{instances.length === 1 ? "" : "s"}
        </span>
      </footer>
    </main>
  );
}

export default App;
