import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { DCCS } from "@/dcc-meta";
import { FolderPlus, Package, Puzzle, Info } from "lucide-react";

/**
 * Install page — two sub-sections.
 *
 * Phase 3b: UI scaffolding only. All buttons are inert placeholders;
 * Phase 3c will wire them to Rust commands for plugin install + project
 * MCP setup.
 */
function Install() {
  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6">
      {/* Sub-section 1: DCC plugin install */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-border py-3">
          <div className="flex items-center gap-2">
            <Puzzle className="size-4 text-muted-foreground" />
            <CardTitle className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Install Plugin into DCC
            </CardTitle>
          </div>
          <Button variant="ghost" size="sm" disabled>
            Rescan
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          <p className="px-5 pt-4 text-[12px] text-muted-foreground">
            Installs the MCP plugin (Blender addon / Houdini packages entry
            / etc.) into each detected DCC version's user pref directory.
          </p>
          <ul className="mt-2 min-h-[120px]">
            {DCCS.map((d, i) => (
              <li
                key={d.key}
                className={`flex items-center gap-4 px-5 py-4 ${
                  i > 0 ? "border-t border-border" : ""
                }`}
              >
                <img
                  src={d.iconUrl}
                  alt=""
                  className="size-8 shrink-0 object-contain"
                />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-text-bright">
                    {d.label}
                  </div>
                  <div className="font-mono text-[10px] text-muted-foreground">
                    No versions detected yet
                  </div>
                </div>
                <Badge
                  variant="outline"
                  className="border-border text-muted-foreground"
                >
                  Not installed
                </Badge>
                <Button size="sm" variant="outline" disabled>
                  Detect & Install
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {/* Sub-section 2: Project MCP setup */}
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
              Opens a folder picker, then lets you select which MCP servers
              to include.
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
