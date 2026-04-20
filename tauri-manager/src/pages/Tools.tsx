import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Wrench, Server } from "lucide-react";
import { DCCS } from "@/dcc-meta";

/**
 * Tools page — per-MCP-server tool catalog with enable/disable toggles.
 *
 * Phase 3b: structural scaffolding. Each MCP server gets a card showing
 * "Coming in Phase 3d" — actual tool loading needs Python-side endpoints
 * or a bundled tool_defs.json per MCP.
 */

const MCP_SERVERS = [
  ...DCCS.map((d) => ({
    key: d.key,
    name: `${d.key}-mcp`,
    label: d.label,
    color: d.color,
    iconUrl: d.iconUrl,
    isOs: false,
  })),
  {
    key: "os" as const,
    name: "os-mcp",
    label: "OS Tools",
    color: "#6366f1",
    iconUrl: "",
    isOs: true,
  },
];

function Tools() {
  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6">
      {/* Summary bar */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card px-4 py-3">
        <Wrench className="size-4 text-muted-foreground" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Tool catalog across all MCP servers
        </span>
        <div className="flex-1" />
        <span className="text-[11px] text-muted-foreground">
          Changes take effect immediately
        </span>
      </div>

      {/* Per-MCP-server cards */}
      {MCP_SERVERS.map((srv) => (
        <Card key={srv.key}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-border py-3">
            <div className="flex items-center gap-3">
              {srv.isOs ? (
                <Server className="size-5 text-primary" />
              ) : (
                <img
                  src={srv.iconUrl}
                  alt=""
                  className="size-5 shrink-0 object-contain"
                />
              )}
              <CardTitle
                className="font-mono text-sm font-bold"
                style={{ color: srv.color }}
              >
                {srv.name}
              </CardTitle>
              <Badge
                variant="outline"
                className="border-border text-muted-foreground"
              >
                Coming in Phase 3d
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span className="tabular-nums">— / —</span>
              <Switch disabled />
            </div>
          </CardHeader>
          <CardContent className="py-8 text-center text-[12px] text-muted-foreground">
            Tool list loading requires a Python-side tool_defs JSON
            endpoint. The catalog UI is scaffolded here; wiring happens
            next phase.
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default Tools;
