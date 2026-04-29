import { useState, useCallback, useEffect } from "react";
import { toast } from "sonner";
import {
  Copy,
  RefreshCw,
  Radio,
  Hash,
  Activity,
  CircleSlash,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

import { DCCS, DCC_MAP } from "@/dcc-meta";
import type { DccMeta } from "@/dcc-meta";
import type { DccInstance } from "@/types";
import { invoke, isTauri } from "@/lib/tauri";
import { useConfig } from "@/lib/config";

/** Stats shown in the action bar. */
function Stat({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="size-3.5 text-muted-foreground" />
      <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="tabular-nums font-mono text-sm font-bold text-text-bright">
        {value}
      </span>
    </div>
  );
}

/** A single Manual Start row — click the code block to copy. */
function ManualStartRow({
  dcc,
  nextPort,
  loading,
}: {
  dcc: DccMeta;
  nextPort: number | null;
  loading: boolean;
}) {
  const snippet =
    nextPort !== null && dcc.manualSnippet ? dcc.manualSnippet(nextPort) : "";

  const copy = async () => {
    if (!snippet) return;
    try {
      await navigator.clipboard.writeText(snippet);
      toast.success(`Copied: ${dcc.label} start (port ${nextPort})`, {
        description: "Paste into the DCC's Python console.",
      });
    } catch (e) {
      toast.error(`Copy failed: ${e}`);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <span
        className="w-20 shrink-0 text-[11px] font-bold uppercase tracking-wider"
        style={{ color: dcc.color }}
      >
        {dcc.label}
      </span>
      {loading ? (
        <Skeleton className="h-8 flex-1" />
      ) : (
        <button
          type="button"
          onClick={copy}
          className="group flex min-w-0 flex-1 items-center gap-2 overflow-hidden rounded-md border border-border bg-background px-3 py-1.5 text-left font-mono text-[11px] text-code-text transition-colors hover:border-muted-foreground hover:bg-surface2"
        >
          <span className="flex-1 truncate">{snippet}</span>
          <Copy className="size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        </button>
      )}
    </div>
  );
}

/** A running DCC instance row. */
function InstanceItem({ inst }: { inst: DccInstance }) {
  const meta = DCC_MAP[inst.dcc_type];
  const color = meta?.color ?? "var(--primary)";
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className="flex flex-col gap-1 border-b border-border px-5 py-3 last:border-0 transition-colors hover:bg-surface2/60"
    >
      <div className="flex items-center gap-3">
        <span
          className="size-2 shrink-0 rounded-full"
          style={{ background: color }}
        />
        <span className="tabular-nums font-mono text-sm font-bold text-text-bright">
          :{inst.port}
        </span>
        <span
          className="rounded border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider"
          style={{ color, borderColor: color }}
        >
          {inst.dcc_type}
        </span>
        <div className="ml-auto flex items-center gap-3 font-mono text-[11px] text-muted-foreground">
          <span className="tabular-nums">pid {inst.pid}</span>
          {inst.window_title && (
            <span className="max-w-[14rem] truncate" title={inst.window_title}>
              {inst.window_title}
            </span>
          )}
        </div>
      </div>
      {inst.exe_path && (
        <div className="pl-5 font-mono text-[10px] text-muted-foreground/80">
          {inst.exe_path}
        </div>
      )}
    </motion.li>
  );
}

function Dashboard() {
  const { config } = useConfig();
  const portMin = config.ports.min;
  const portMax = config.ports.max;

  const [instances, setInstances] = useState<DccInstance[]>([]);
  const [nextPort, setNextPort] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastScan, setLastScan] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, freePort] = await Promise.all([
        invoke<DccInstance[]>(
          "list_dcc_instances",
          { portMin, portMax },
          [],
        ),
        invoke<number | null>(
          "next_free_port",
          { portMin, portMax },
          portMin,
        ),
      ]);
      setInstances(list);
      setNextPort(freePort);
      setLastScan(new Date());
    } catch (e) {
      setError(String(e));
      toast.error(`Scan failed: ${e}`);
    } finally {
      setLoading(false);
    }
  }, [portMin, portMax]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const manualDccs = DCCS.filter((d) => d.manualSnippet);

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6">
      {/* Action bar */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card px-4 py-3">
        <Button
          size="sm"
          onClick={refresh}
          disabled={loading}
          className="min-w-[96px] gap-1.5"
        >
          <RefreshCw
            className={`size-3.5 ${loading ? "animate-spin" : ""}`}
          />
          {loading ? "Scanning" : "Refresh"}
        </Button>
        <Separator orientation="vertical" className="!h-5" />
        <Stat
          icon={Radio}
          label="Instances"
          value={loading ? "—" : instances.length}
        />
        <Stat
          icon={Hash}
          label="Range"
          value={`${portMin}–${portMax}`}
        />
        <Stat
          icon={Activity}
          label="Next Free"
          value={nextPort !== null ? `:${nextPort}` : "—"}
        />
        {lastScan && (
          <span className="ml-auto tabular-nums font-mono text-[11px] text-muted-foreground">
            {lastScan.toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Manual Start */}
      <Card>
        <CardHeader className="flex flex-row items-center gap-4 space-y-0 border-b border-border py-3">
          <CardTitle className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
            Manual Start
          </CardTitle>
          <span className="text-[11px] text-muted-foreground">
            Paste into the DCC's Python console · refresh after each use
          </span>
        </CardHeader>
        <CardContent className="space-y-2 p-4">
          {manualDccs.map((d) => (
            <ManualStartRow
              key={d.key}
              dcc={d}
              nextPort={nextPort}
              loading={loading}
            />
          ))}
        </CardContent>
      </Card>

      {/* Running Instances */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-border py-3">
          <CardTitle className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
            Running Instances
          </CardTitle>
          <span className="tabular-nums font-mono text-[11px] text-muted-foreground">
            {loading ? "—" : `${instances.length} found`}
          </span>
        </CardHeader>
        <CardContent className="p-0">
          <ul className="min-h-[120px]">
            {loading ? (
              <li className="space-y-2 p-5">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </li>
            ) : error ? (
              <li className="flex flex-col items-center gap-2 py-10 text-sm text-destructive">
                <CircleSlash className="size-5" />
                {error}
              </li>
            ) : instances.length === 0 ? (
              <li className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
                <CircleSlash className="size-5" />
                <span>
                  No DCC instances detected on ports {portMin}–{portMax}
                </span>
                {!isTauri() && (
                  <span className="text-[11px] text-muted-foreground/70">
                    (running in browser preview — no scan available)
                  </span>
                )}
              </li>
            ) : (
              <AnimatePresence mode="popLayout" initial={false}>
                {instances.map((i) => (
                  <InstanceItem key={i.port} inst={i} />
                ))}
              </AnimatePresence>
            )}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

export default Dashboard;
