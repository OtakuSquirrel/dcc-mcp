import { useState, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { DccInstance } from "./types";
import "./App.css";

// Covers current DCC ranges: Houdini 18811-18899,
// Blender 19811-19899, UE 20811-20899.
// Phase 1e will unify into a single shared range read from
// ~/.dcc-mcp/config.toml.
const DEFAULT_PORT_MIN = 18811;
const DEFAULT_PORT_MAX = 20899;

function App() {
  const [instances, setInstances] = useState<DccInstance[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastScan, setLastScan] = useState<Date | null>(null);

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

      {error && <div className="error">Error: {error}</div>}

      {instances.length === 0 && !loading && !error && (
        <div className="empty">
          <p>No DCC instances detected in range.</p>
          <p className="empty-hint">
            Ask Claude to <code>start_blender</code> from the Blender MCP server,
            then click Refresh.
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
