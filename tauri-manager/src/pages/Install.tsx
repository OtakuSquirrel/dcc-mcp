import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { open as openFolder } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";
import {
  FolderPlus,
  Package,
  Puzzle,
  Info,
  RefreshCw,
  CheckCircle2,
  Circle,
  Trash2,
  FolderOpen,
  X,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { DCCS, type DccMeta } from "@/dcc-meta";
import type {
  DccVersion,
  InstallResult,
  ManagedProject,
  RemoveResult,
  SetupResult,
  UninstallResult,
} from "@/types";
import { invoke, isTauri } from "@/lib/tauri";

// ─── Sub-section 1: Plugin install ────────────────────────────────────

function useDccVersions(dcc: DccMeta) {
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

// DCCs for which detection + install is wired in src-tauri/src/install.rs.
// Keep in sync with `SPECS` there. UE remains deferred — its plugin
// model (engine-scoped Plugins folder, .uplugin manifests, editor
// restart) doesn't fit the shared flow.
const SUPPORTED_INSTALL: readonly string[] = ["blender", "houdini", "maya"];

function DccInstallBlock({ dcc }: { dcc: DccMeta }) {
  const { versions, loading, error, refresh } = useDccVersions(dcc);
  const supported = SUPPORTED_INSTALL.includes(dcc.key);

  return (
    <div className="divide-y divide-border">
      <div className="flex items-center gap-3 px-5 py-3 bg-surface2/40">
        <img src={dcc.iconUrl} alt="" className="size-6 shrink-0 object-contain" />
        <span className="font-semibold" style={{ color: dcc.color }}>
          {dcc.label}
        </span>
        {!supported && (
          <Badge variant="outline" className="border-border text-muted-foreground">
            Not yet wired
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
              <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
              Rescan
            </Button>
          )}
        </div>
      </div>

      {!supported ? (
        <div className="px-5 py-6 text-center text-[12px] text-muted-foreground">
          Install flow coming in a later phase
        </div>
      ) : loading ? (
        <div className="space-y-2 px-5 py-3">
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-3/4" />
        </div>
      ) : error ? (
        <div className="px-5 py-6 text-center text-sm text-destructive">{error}</div>
      ) : versions.length === 0 ? (
        <div className="px-5 py-6 text-center text-[12px] text-muted-foreground">
          No {dcc.label} installations detected
        </div>
      ) : (
        versions.map((v) => (
          <VersionRow key={v.version} dcc={dcc} version={v} onChange={refresh} />
        ))
      )}
    </div>
  );
}

// ─── Sub-section 2: Project MCP setup ─────────────────────────────────

type McpChoice = {
  key: "blender" | "houdini" | "ue" | "maya" | "os";
  label: string;
  description: string;
  color: string;
};

const MCP_CHOICES: McpChoice[] = [
  {
    key: "blender",
    label: "blender-mcp",
    description: "Control Blender via MCP",
    color: "var(--dcc-blender)",
  },
  {
    key: "houdini",
    label: "houdini-mcp",
    description: "Control Houdini via MCP",
    color: "var(--dcc-houdini)",
  },
  {
    key: "ue",
    label: "ue-mcp",
    description: "Control Unreal Engine via MCP",
    color: "var(--dcc-ue)",
  },
  {
    key: "maya",
    label: "maya-mcp",
    description: "Control Maya via MCP",
    color: "var(--dcc-maya)",
  },
  {
    key: "os",
    label: "os-mcp",
    description: "OS-level tools (health, kill, screenshot)",
    color: "var(--dcc-os)",
  },
];

function ProjectSetupDialog({
  projectPath,
  initialSelection,
  onClose,
  onDone,
}: {
  projectPath: string;
  initialSelection?: Set<McpChoice["key"]>;
  onClose: () => void;
  onDone: () => void;
}) {
  const [selected, setSelected] = useState<Set<McpChoice["key"]>>(
    () => initialSelection ?? new Set(["os"]),
  );
  const [busy, setBusy] = useState(false);

  const toggle = (key: McpChoice["key"]) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const confirm = async () => {
    setBusy(true);
    try {
      const r = await invoke<SetupResult>(
        "setup_project_mcp",
        { projectPath, mcps: [...selected] },
        {
          ok: false,
          project_path: projectPath,
          installed_mcps: [],
          settings_path: "",
          settings_op: "",
          error: "Not in Tauri",
        },
      );
      if (r.ok) {
        toast.success(
          `Set up ${r.installed_mcps.length} MCP server${
            r.installed_mcps.length === 1 ? "" : "s"
          } for this project`,
          { description: `${r.settings_op} ${r.settings_path}` },
        );
        onDone();
      } else {
        toast.error(`Setup failed: ${r.error ?? "unknown"}`);
      }
    } catch (e) {
      toast.error(`Setup failed: ${e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package className="size-4 text-primary" />
            Set up MCP for project
          </DialogTitle>
          <DialogDescription>
            The selected MCP servers will be registered in this project's{" "}
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px] text-code-text">
              .claude/settings.json
            </code>
            .
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-md border border-border bg-surface2/60 px-3 py-2 font-mono text-[11px] text-muted-foreground">
          {projectPath}
        </div>

        <div className="space-y-1">
          {MCP_CHOICES.map((choice) => {
            const checked = selected.has(choice.key);
            return (
              <label
                key={choice.key}
                className={`flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2 transition-colors ${
                  checked
                    ? "border-primary/50 bg-primary/5"
                    : "border-border hover:bg-surface2/60"
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(choice.key)}
                  className="mt-1 size-4 cursor-pointer accent-[color:var(--primary)]"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className="font-mono text-sm font-bold"
                      style={{ color: choice.color }}
                    >
                      {choice.label}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    {choice.description}
                  </div>
                </div>
              </label>
            );
          })}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            onClick={confirm}
            disabled={busy || selected.size === 0}
            className="min-w-[120px] gap-1.5"
          >
            {busy ? (
              <RefreshCw className="size-3.5 animate-spin" />
            ) : (
              <Package className="size-3.5" />
            )}
            {busy ? "Setting up…" : "Confirm"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ManagedProjectRow({
  proj,
  onChange,
}: {
  proj: ManagedProject;
  onChange: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState(false);

  const remove = async () => {
    setRemoving(true);
    try {
      const r = await invoke<RemoveResult>(
        "remove_project_mcp",
        { projectPath: proj.path },
        { ok: false, removed_keys: [], error: "Not in Tauri" },
      );
      if (r.ok) {
        toast.success(
          `Removed ${r.removed_keys.length} MCP entr${
            r.removed_keys.length === 1 ? "y" : "ies"
          } from ${proj.path}`,
        );
        onChange();
      } else {
        toast.error(`Remove failed: ${r.error ?? "unknown"}`);
      }
    } catch (e) {
      toast.error(`Remove failed: ${e}`);
    } finally {
      setRemoving(false);
    }
  };

  const revealInFinder = async () => {
    try {
      await openPath(proj.path);
    } catch (e) {
      toast.error(`Open failed: ${e}`);
    }
  };

  return (
    <>
      <div className="flex items-center gap-3 px-3 py-3 hover:bg-surface2/40">
        <FolderOpen className="size-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <div
            className="truncate font-mono text-[12px] text-text-bright"
            title={proj.path}
          >
            {proj.path}
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {proj.installed_mcps.map((m) => {
              const choice = MCP_CHOICES.find((c) => c.key === m);
              return (
                <span
                  key={m}
                  className="rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider"
                  style={{
                    color: choice?.color ?? "var(--text-dim)",
                    borderColor: choice?.color ?? "var(--border)",
                  }}
                >
                  {m}
                </span>
              );
            })}
          </div>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={revealInFinder}
            className="gap-1.5"
            title="Open in Finder"
          >
            <FolderOpen className="size-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setEditing(true)}
            disabled={removing}
            className="gap-1.5"
            title="Change selected MCPs"
          >
            Edit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={remove}
            disabled={removing}
            className="gap-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive"
            title="Remove MCP entries from settings.json"
          >
            {removing ? (
              <RefreshCw className="size-3.5 animate-spin" />
            ) : (
              <X className="size-3.5" />
            )}
          </Button>
        </div>
      </div>
      {editing && (
        <ProjectSetupDialog
          projectPath={proj.path}
          initialSelection={new Set(proj.installed_mcps as McpChoice["key"][])}
          onClose={() => setEditing(false)}
          onDone={() => {
            setEditing(false);
            onChange();
          }}
        />
      )}
    </>
  );
}

function ProjectsSection() {
  const [projects, setProjects] = useState<ManagedProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogPath, setDialogPath] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const list = await invoke<ManagedProject[]>(
        "list_managed_projects",
        undefined,
        [],
      );
      setProjects(list);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const startAdd = async () => {
    if (!isTauri()) {
      toast.info(
        "Folder picker only works in the native window — start via `npm run tauri dev`.",
      );
      return;
    }
    try {
      const picked = await openFolder({
        directory: true,
        multiple: false,
        title: "Choose a project folder",
      });
      if (typeof picked === "string") {
        setDialogPath(picked);
      }
    } catch (e) {
      toast.error(`Folder picker failed: ${e}`);
    }
  };

  return (
    <>
      <div className="flex items-start gap-2 rounded-md border border-border bg-surface2/50 p-3">
        <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          Project-scoped install only. MCP servers are registered in{" "}
          <code className="rounded bg-background px-1 py-0.5 font-mono text-[11px] text-code-text">
            &lt;project&gt;/.claude/settings.json
          </code>
          . In dev mode the <code className="rounded bg-background px-1 py-0.5 font-mono text-[11px] text-code-text">command</code>
          {" "}field points at the repo's <code className="rounded bg-background px-1 py-0.5 font-mono text-[11px] text-code-text">.venv/bin/</code>{" "}
          scripts; Phase 5 will switch to bundled frozen binaries.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={startAdd} className="gap-2">
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
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Managed projects
          </span>
          <span className="tabular-nums font-mono text-[11px] text-muted-foreground">
            {loading ? "—" : `${projects.length} total`}
          </span>
        </div>
        <div className="divide-y divide-border overflow-hidden rounded-md border border-border">
          {loading ? (
            <div className="p-3">
              <Skeleton className="h-8 w-full" />
            </div>
          ) : projects.length === 0 ? (
            <div className="flex min-h-[80px] items-center justify-center text-[12px] text-muted-foreground">
              No projects registered yet
            </div>
          ) : (
            projects.map((p) => (
              <ManagedProjectRow key={p.path} proj={p} onChange={refresh} />
            ))
          )}
        </div>
      </div>

      {dialogPath && (
        <ProjectSetupDialog
          projectPath={dialogPath}
          onClose={() => setDialogPath(null)}
          onDone={() => {
            setDialogPath(null);
            refresh();
          }}
        />
      )}
    </>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────

function Install() {
  const dccs = useMemo(() => DCCS, []);

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6">
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
          <p className="border-b border-border px-5 py-3 text-[12px] text-muted-foreground">
            Installs the DCC-specific MCP plugin into each detected version's
            user pref directory. Symlink is preferred (auto-updates with repo
            changes) and falls back to a deep copy when symlinks are not
            permitted.
          </p>
          {dccs.map((d) => (
            <div key={d.key} className="border-b border-border last:border-b-0">
              <DccInstallBlock dcc={d} />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-border py-3">
          <div className="flex items-center gap-2">
            <FolderPlus className="size-4 text-muted-foreground" />
            <CardTitle className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Set up MCP for Project
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-5">
          <ProjectsSection />
        </CardContent>
      </Card>
    </div>
  );
}

export default Install;
