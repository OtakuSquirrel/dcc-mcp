import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  ChevronDown,
  ChevronRight,
  Info,
  RefreshCw,
  Server,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

import { DCCS } from "@/dcc-meta";
import { setDisabledTools, useConfig } from "@/lib/config";
import toolDefsBundle from "@/tool-defs.generated.json";

// ── Types mirroring the JSON bundle ──────────────────────────────────

interface ToolDefs {
  categories: Record<string, { desc: string; tools: Record<string, string> }>;
  default_disabled: string[];
}
type Bundle = Record<string, ToolDefs>;

const BUNDLE = toolDefsBundle as unknown as Bundle;

// ── Per-MCP metadata (name, colour, icon) ────────────────────────────

interface McpMeta {
  key: string;
  name: string; // "blender-mcp", "os-mcp", etc.
  label: string;
  color: string;
  iconUrl: string;
  isOs: boolean;
}

const MCP_META: McpMeta[] = [
  ...DCCS.map((d) => ({
    key: d.key,
    name: `${d.key}-mcp`,
    label: d.label,
    color: d.color,
    iconUrl: d.iconUrl,
    isOs: false,
  })),
  {
    key: "os",
    name: "os-mcp",
    label: "OS Tools",
    color: "#6366f1",
    iconUrl: "",
    isOs: true,
  },
];

// ── Helpers ──────────────────────────────────────────────────────────

function allToolNames(defs: ToolDefs): string[] {
  return Object.values(defs.categories).flatMap((c) => Object.keys(c.tools));
}

// ── Per-tool row ─────────────────────────────────────────────────────

function ToolRow({
  name,
  desc,
  enabled,
  onToggle,
}: {
  name: string;
  desc: string;
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex items-center gap-3 px-5 py-2 hover:bg-surface2/40">
      <div className="min-w-0 flex-1">
        <div className="font-mono text-[12px] font-semibold text-text-bright">
          {name}
        </div>
        <div className="text-[11px] text-muted-foreground">{desc}</div>
      </div>
      <Switch checked={enabled} onCheckedChange={onToggle} />
    </div>
  );
}

// ── Per-category block (collapsible) ─────────────────────────────────

function CategoryBlock({
  category,
  desc,
  tools,
  disabledSet,
  onToggleTool,
  onToggleCategory,
  defaultExpanded,
}: {
  category: string;
  desc: string;
  tools: Record<string, string>;
  disabledSet: Set<string>;
  onToggleTool: (tool: string) => void;
  onToggleCategory: (tools: string[], allEnabled: boolean) => void;
  defaultExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const toolNames = Object.keys(tools);
  const enabledCount = toolNames.filter((t) => !disabledSet.has(t)).length;
  const allEnabled = enabledCount === toolNames.length;

  return (
    <div className="border-b border-border last:border-b-0">
      <div className="flex items-center gap-3 bg-surface2/40 px-5 py-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          {expanded ? (
            <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
          )}
          <span className="text-[11px] font-semibold uppercase tracking-wider text-text-bright">
            {category}
          </span>
          <span className="truncate text-[11px] text-muted-foreground">
            {desc}
          </span>
        </button>
        <span className="shrink-0 tabular-nums font-mono text-[11px] text-muted-foreground">
          {enabledCount} / {toolNames.length}
        </span>
        <Switch
          checked={allEnabled}
          onCheckedChange={() => onToggleCategory(toolNames, allEnabled)}
          title={allEnabled ? "Disable all in category" : "Enable all in category"}
        />
      </div>
      {expanded &&
        toolNames.map((t) => (
          <ToolRow
            key={t}
            name={t}
            desc={tools[t]}
            enabled={!disabledSet.has(t)}
            onToggle={() => onToggleTool(t)}
          />
        ))}
    </div>
  );
}

// ── Per-MCP card ─────────────────────────────────────────────────────

function McpCard({
  meta,
  defs,
  disabled,
  onWrite,
}: {
  meta: McpMeta;
  defs: ToolDefs;
  disabled: string[];
  onWrite: (next: string[]) => Promise<void>;
}) {
  // Optimistic local set — updated immediately on toggle, then persisted
  // to config.toml via onWrite. If persistence fails we roll back.
  const [localDisabled, setLocalDisabled] = useState<string[]>(disabled);
  useEffect(() => {
    setLocalDisabled(disabled);
  }, [disabled]);

  const disabledSet = useMemo(() => new Set(localDisabled), [localDisabled]);
  const total = useMemo(() => allToolNames(defs), [defs]);
  const enabledCount = total.filter((t) => !disabledSet.has(t)).length;

  const commit = async (next: Set<string>) => {
    const prev = localDisabled;
    const nextArr = Array.from(next).sort();
    setLocalDisabled(nextArr);
    try {
      await onWrite(nextArr);
    } catch (e) {
      setLocalDisabled(prev);
      toast.error(`Save failed: ${e}`);
    }
  };

  const toggleTool = (tool: string) => {
    const next = new Set(disabledSet);
    if (next.has(tool)) next.delete(tool);
    else next.add(tool);
    void commit(next);
  };

  const toggleCategory = (tools: string[], allEnabled: boolean) => {
    const next = new Set(disabledSet);
    if (allEnabled) {
      // Everything on → turn everything off
      for (const t of tools) next.add(t);
    } else {
      for (const t of tools) next.delete(t);
    }
    void commit(next);
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-border py-3">
        <div className="flex min-w-0 items-center gap-3">
          {meta.isOs ? (
            <Server className="size-5 shrink-0 text-primary" />
          ) : (
            <img
              src={meta.iconUrl}
              alt=""
              className="size-5 shrink-0 object-contain"
            />
          )}
          <CardTitle
            className="font-mono text-sm font-bold"
            style={{ color: meta.color }}
          >
            {meta.name}
          </CardTitle>
          <Badge variant="outline" className="border-border text-muted-foreground">
            {Object.keys(defs.categories).length}{" "}
            {Object.keys(defs.categories).length === 1 ? "category" : "categories"}
          </Badge>
        </div>
        <span className="shrink-0 tabular-nums font-mono text-[11px] text-muted-foreground">
          {enabledCount} / {total.length} enabled
        </span>
      </CardHeader>
      <CardContent className="p-0">
        {Object.entries(defs.categories).map(([cat, c], idx) => (
          <CategoryBlock
            key={cat}
            category={cat}
            desc={c.desc}
            tools={c.tools}
            disabledSet={disabledSet}
            onToggleTool={toggleTool}
            onToggleCategory={toggleCategory}
            defaultExpanded={idx === 0}
          />
        ))}
      </CardContent>
    </Card>
  );
}

// ── Page ─────────────────────────────────────────────────────────────

function Tools() {
  const { config, loading, refresh } = useConfig();

  // Only show MCPs with a tool catalog generated into the bundle.
  const servers = useMemo(
    () => MCP_META.filter((m) => BUNDLE[m.key] !== undefined),
    [],
  );

  const writeDisabled = async (mcp: string, next: string[]) => {
    await setDisabledTools(mcp, next);
    // Reload so other cards (or a re-mount) see fresh state.
    refresh();
  };

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6">
      {/* Summary bar */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card px-4 py-3">
        <Wrench className="size-4 text-muted-foreground" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Tool catalog across all MCP servers
        </span>
        <div className="flex-1" />
        <Button
          size="sm"
          variant="ghost"
          onClick={refresh}
          disabled={loading}
          className="gap-1.5"
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          Reload
        </Button>
      </div>

      {/* Caveat */}
      <div className="flex items-start gap-2 rounded-md border border-border bg-surface2/50 p-3">
        <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          Toggling a tool writes the disabled list into{" "}
          <code className="rounded bg-background px-1 py-0.5 font-mono text-[11px] text-code-text">
            ~/.dcc-mcp/config.toml
          </code>
          . MCP servers reload it on each{" "}
          <code className="rounded bg-background px-1 py-0.5 font-mono text-[11px] text-code-text">
            tools/list
          </code>
          {" "}/{" "}
          <code className="rounded bg-background px-1 py-0.5 font-mono text-[11px] text-code-text">
            tools/call
          </code>
          , so changes take effect immediately — no MCP restart needed.
        </p>
      </div>

      {/* Per-MCP cards */}
      {servers.map((meta) => (
        <McpCard
          key={meta.key}
          meta={meta}
          defs={BUNDLE[meta.key]}
          disabled={config.tools[meta.key]?.disabled ?? []}
          onWrite={(next) => writeDisabled(meta.key, next)}
        />
      ))}
    </div>
  );
}

export default Tools;
