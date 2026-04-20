import { useState, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { DCCS, DCC_MAP, PORT_MIN, PORT_MAX } from "../dcc-meta";
import type { DccMeta } from "../dcc-meta";
import type { DccInstance } from "../types";
import { useToast } from "../layout/Toast";

/**
 * Unified Dashboard — one page, one port pool, all DCCs.
 *
 * - Single scan over the whole port range.
 * - All discovered instances listed together, tag-coloured by dcc_type.
 * - One Manual Start row per DCC that supports a one-liner, each row
 *   shows the same `nextPort` from the unified pool. User is expected
 *   to refresh after starting one before copying another.
 */

function dccWithSnippets(): DccMeta[] {
  return DCCS.filter((d) => d.manualSnippet);
}

function ManualStartRow({
  dcc,
  nextPort,
}: {
  dcc: DccMeta;
  nextPort: number | null;
}) {
  const toast = useToast();
  const snippet =
    nextPort !== null && dcc.manualSnippet ? dcc.manualSnippet(nextPort) : "";

  const copy = async () => {
    if (!snippet) return;
    try {
      await navigator.clipboard.writeText(snippet);
      toast.show(`Copied: ${dcc.label} start (port ${nextPort})`);
    } catch (e) {
      toast.show(`Copy failed: ${e}`);
    }
  };

  return (
    <div className="cmd-row">
      <span
        className="cmd-label"
        style={{ color: dcc.color }}
        title={dcc.label}
      >
        {dcc.label}
      </span>
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
        {snippet || "…"}
      </div>
    </div>
  );
}

function Dashboard() {
  const toast = useToast();
  const [instances, setInstances] = useState<DccInstance[]>([]);
  const [nextPort, setNextPort] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastScan, setLastScan] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, freePort] = await Promise.all([
        invoke<DccInstance[]>("list_dcc_instances", {
          portMin: PORT_MIN,
          portMax: PORT_MAX,
        }),
        invoke<number | null>("next_free_port", {
          portMin: PORT_MIN,
          portMax: PORT_MAX,
        }),
      ]);
      setInstances(list);
      setNextPort(freePort);
      setLastScan(new Date());
    } catch (e) {
      setError(String(e));
      toast.show(`Scan failed: ${e}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const manualDccs = dccWithSnippets();

  return (
    <div className="container">
      {/* Action bar */}
      <div className="action-bar">
        <button
          className="btn btn-accent btn-sm"
          onClick={refresh}
          disabled={loading}
        >
          {loading ? "Scanning…" : "Refresh"}
        </button>
        <div className="action-bar-sep" />
        <span>
          <span className="stat-label">Instances</span>
          <span className="stat-value">{instances.length}</span>
        </span>
        <span>
          <span className="stat-label">Range</span>
          <span className="stat-value">
            {PORT_MIN}&ndash;{PORT_MAX}
          </span>
        </span>
        <span>
          <span className="stat-label">Next Free</span>
          <span className="stat-value">
            {nextPort !== null ? `:${nextPort}` : "—"}
          </span>
        </span>
        {lastScan && (
          <span style={{ marginLeft: "auto", fontSize: 11 }}>
            scanned {lastScan.toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Manual Start rows */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Manual Start</span>
          <span className="section-desc" style={{ marginBottom: 0 }}>
            Paste into the DCC's Python console · refresh after each use
          </span>
        </div>
        <div className="card-body cmd-rows">
          {manualDccs.map((d) => (
            <ManualStartRow key={d.key} dcc={d} nextPort={nextPort} />
          ))}
        </div>
      </div>

      {/* Instances list */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Running Instances</span>
        </div>
        <div className="instance-list">
          {error && (
            <div className="empty-state" style={{ color: "var(--red)" }}>
              {error}
            </div>
          )}
          {!error && instances.length === 0 && (
            <div className="empty-state">
              No DCC instances detected on ports {PORT_MIN}–{PORT_MAX}
            </div>
          )}
          {instances.map((i) => {
            const meta = DCC_MAP[i.dcc_type];
            return (
              <div key={i.port} className="instance-item">
                <div className="instance-row">
                  <span
                    className="instance-dot"
                    style={{ background: meta?.color ?? "var(--accent)" }}
                  />
                  <span className="instance-port">{i.port}</span>
                  <span
                    className="port-badge"
                    style={{
                      color: meta?.color ?? "var(--text-dim)",
                      borderColor: meta?.color ?? "var(--border)",
                    }}
                  >
                    {i.dcc_type}
                  </span>
                  <span className="instance-meta">
                    <span>PID {i.pid}</span>
                    {i.window_title && <span>{i.window_title}</span>}
                  </span>
                </div>
                {i.exe_path && (
                  <div className="instance-exe">{i.exe_path}</div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
