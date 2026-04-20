import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  FolderPlus,
  Package,
  Puzzle,
  Info,
  RefreshCw,
  CheckCircle2,
  Circle,
  Trash2,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

import { DCCS, type DccMeta } from "@/dcc-meta";
import type { DccVersion, InstallResult, UninstallResult } from "@/types";
import { invoke, isTauri } from "@/lib/tauri";

/**
 * Install tab.
 *   Sub-section 1: per-DCC plugin install (Blender works; others are
 *                  placeholders in Phase 3c-1).
 *   Sub-section 2: Project MCP setup — still a placeholder (Phase 3c-2).
 */

// ── Plugin install ─────────────────────────────────────────────────

type VersionState = {
  versions: DccVersion[];
  loading: boolean;
  error: string | null;
};

function useDccVersions(dcc: DccMeta): VersionState & { refresh: () => void } {
  const [versions, setVersions] = useState<DccVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await invoke<DccVersion[]>(
        "detect_dcc_versions",
        { dcc: dcc.key },
        [],
      );
      setVersions(list);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [dcc.key]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { versions, loading, error, refresh };
}

function VersionRow({
  dcc,
  version,
  onChange,
}: {
  dcc: DccMeta;
  version: DccVersion;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState<"install" | "uninstall" | null>(null);

  const install = async () => {
    setBusy("install");
    try {
      const r = await invoke<InstallResult>(
        "install_plugin",
        { dcc: dcc.key, version: version.version },
        { ok: false, method: "", path: "", error: "Not in Tauri" },
      );
      if (r.ok) {
        toast.success(
          `${dcc.label} ${version.version} installed (${r.method})`,
        );
        onChange();
      } else {
        toast.error(`Install failed: ${r.error ?? "unknown"}`);
      }
    } catch (e) {
      toast.error(`Install failed: ${e}`);
    } finally {
      setBusy(null);
    }
  };

  const uninstall = async () => {
    setBusy("uninstall");
    try {
      const r = await invoke<UninstallResult>(
        "uninstall_plugin",
        { dcc: dcc.key, version: version.version },
        { ok: false, was_installed: false, error: "Not in Tauri" },
      );
      if (r.ok) {
        if (r.was_installed) {
          toast.success(`${dcc.label} ${version.version} uninstalled`);
        } else {
          toast.info(`${dcc.label} ${version.version} was already uninstalled`);
        }
        onChange();
      } else {
        toast.error(`Uninstall failed: ${r.error ?? "unknown"}`);
      }
    } catch (e) {
      toast.error(`Uninstall failed: ${e}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex items-center gap-3 px-5 py-3">
      {version.installed ? (
        <CheckCircle2 className="size-4 shrink-0 text-success" />
      ) : (
        <Circle className="size-4 shrink-0 text-muted-foreground/40" />
      )}
      <span className="w-16 shrink-0 font-mono text-sm font-bold tabular-nums text-text-bright">
        {version.version}
      </span>
      <span
        className="min-w-0 flex-1 truncate font-mono text-[10px] text-muted-foreground"
        title={version.pref_dir}
      >
        {version.pref_dir}
      </span>
      {version.installed ? (
        <Badge
          variant="outline"
          className="shrink-0 border-success/40 text-success"
        >
          Installed{version.install_method ? ` (${version.install_method})` : ""}
        </Badge>
      ) : (
        <Badge
          variant="outline"
          className="shrink-0 border-border text-muted-foreground"
        >
          Not installed
        </Badge>
      )}
      {version.installed ? (
        <div className="flex shrink-0 gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={install}
            disabled={busy !== null}
            className="min-w-[96px] gap-1.5"
          >
            <RefreshCw
              className={`size-3.5 ${busy === "install" ? "animate-spin" : ""}`}
            />
            Reinstall
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={uninstall}
            disabled={busy !== null}
            className="min-w-[96px] gap-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="size-3.5" />
            Uninstall
          </Button>
        </div>
      ) : (
        <Button
          size="sm"
          onClick={install}
          disabled={busy !== null}
          className="min-w-[96px] gap-1.5"
        >
          <Package
            className={`size-3.5 ${busy === "install" ? "animate-pulse" : ""}`}
          />
          Install
        </Button>
      )}
    </div>
  );
}

function DccInstallBlock({ dcc }: { dcc: DccMeta }) {
  const { versions, loading, error, refresh } = useDccVersions(dcc);
  const supported = dcc.key === "blender"; // Phase 3c-1: Blender only

  return (
    <div className="divide-y divide-border">
      {/* DCC group header */}
      <div className="flex items-center gap-3 px-5 py-3 bg-surface2/40">
        <img src={dcc.iconUrl} alt="" className="size-6 shrink-0 object-contain" />
        <span className="font-semibold text-text-bright" style={{ color: dcc.color }}>
          {dcc.label}
        </span>
        {!supported && (
          <Badge variant="outline" className="border-border text-muted-foreground">
            Phase 3c-1: not yet wired
          </Badge>
        )}
        <div className="ml-auto">
          {supported && (
            <Button
              size="sm"
              variant="ghost"
              onClick={refresh}
              disabled={loading}
              className="gap-1.5"
            >
              <RefreshCw
                className={`size-3.5 ${loading ? "animate-spin" : ""}`}
              />
              Rescan
            </Button>
          )}
        </div>
      </div>

      {/* Rows */}
      {loading ? (
        <div className="space-y-2 px-5 py-3">
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-3/4" />
        </div>
      ) : error ? (
        <div className="px-5 py-6 text-center text-sm text-destructive">
          {error}
        </div>
      ) : versions.length === 0 ? (
        <div className="px-5 py-6 text-center text-[12px] text-muted-foreground">
          {supported
            ? `No ${dcc.label} installations detected`
            : `Install flow coming in a later phase`}
        </div>
      ) : (
        versions.map((v) => (
          <VersionRow
            key={v.version}
            dcc={dcc}
            version={v}
            onChange={refresh}
          />
        ))
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────

function Install() {
  const dccs = useMemo(() => DCCS, []);

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6">
      {/* Sub-section 1 — Plugin install */}
      <Card className="overflow-hidden">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-border py-3">
          <div className="flex items-center gap-2">
            <Puzzle className="size-4 text-muted-foreground" />
            <CardTitle className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Install Plugin into DCC
            </CardTitle>
          </div>
          {!isTauri() && (
            <Badge variant="outline" className="border-warning/40 text-warning">
              Preview mode — detection disabled
            </Badge>
          )}
        </CardHeader>
        <CardContent className="p-0">
          <p className="px-5 py-3 text-[12px] text-muted-foreground border-b border-border">
            Installs the DCC-specific MCP plugin into each detected version's
            user pref directory. Symlink is preferred (auto-updates with repo
            changes) and falls back to a deep copy when symlinks are not
            permitted.
          </p>
          {dccs.map((d) => (
            <div
              key={d.key}
              className="border-b border-border last:border-b-0"
            >
              <DccInstallBlock dcc={d} />
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Sub-section 2 — Project MCP setup (still placeholder) */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-border py-3">
          <div className="flex items-center gap-2">
            <FolderPlus className="size-4 text-muted-foreground" />
            <CardTitle className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Set up MCP for Project
            </CardTitle>
          </div>
          <Badge variant="outline" className="border-border text-muted-foreground">
            Coming in Phase 3c-2
          </Badge>
        </CardHeader>
        <CardContent className="space-y-4 p-5">
          <div className="flex items-start gap-2 rounded-md border border-border bg-surface2/50 p-3">
            <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <p className="text-[12px] leading-relaxed text-muted-foreground">
              Project-scoped install only. MCP binaries go into{" "}
              <code className="rounded bg-background px-1 py-0.5 font-mono text-[11px] text-code-text">
                &lt;project&gt;/.claude/dcc-mcp/bin/
              </code>{" "}
              and the registration is written to{" "}
              <code className="rounded bg-background px-1 py-0.5 font-mono text-[11px] text-code-text">
                .claude/settings.json
              </code>
              . No global install is supported.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button disabled className="gap-2">
              <Package className="size-4" />
              Add MCP to a project…
            </Button>
            <span className="text-[11px] text-muted-foreground">
              Opens a folder picker, then lets you select which MCP servers to
              include.
            </span>
          </div>

          <Separator />

          <div>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Managed projects
            </div>
            <div className="flex min-h-[80px] items-center justify-center rounded-md border border-dashed border-border text-[12px] text-muted-foreground">
              No projects registered yet
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default Install;
