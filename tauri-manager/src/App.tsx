import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LayoutDashboard, Package, Wrench } from "lucide-react";
import { isTauri } from "@/lib/tauri";
import Dashboard from "./pages/Dashboard";
import Install from "./pages/Install";
import Tools from "./pages/Tools";

type TabKey = "dashboard" | "install" | "tools";

function App() {
  const [tab, setTab] = useState<TabKey>("dashboard");

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Top bar */}
      <header className="flex h-14 shrink-0 items-center gap-4 border-b border-border bg-card px-6">
        <div className="flex items-center gap-2">
          <div className="size-6 rounded-md bg-primary/15 ring-1 ring-primary/30" />
          <span className="text-sm font-bold tracking-tight text-primary">
            DCC MCP Manager
          </span>
        </div>
        {!isTauri() && (
          <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-warning">
            Preview mode
          </span>
        )}
        <div className="flex-1" />
      </header>

      {/* Tabs (also control the main content area) */}
      <Tabs
        value={tab}
        onValueChange={(v) => setTab(v as TabKey)}
        className="flex flex-1 flex-col"
      >
        <div className="border-b border-border bg-card px-6">
          <TabsList
            variant="line"
            className="h-12 gap-0 bg-transparent p-0"
          >
            <TabsTrigger
              value="dashboard"
              className="h-12 gap-2 px-4 font-medium text-muted-foreground hover:text-foreground data-[state=active]:text-primary! after:bottom-0! after:bg-primary"
            >
              <LayoutDashboard className="size-4" />
              Dashboard
            </TabsTrigger>
            <TabsTrigger
              value="install"
              className="h-12 gap-2 px-4 font-medium text-muted-foreground hover:text-foreground data-[state=active]:text-primary! after:bottom-0! after:bg-primary"
            >
              <Package className="size-4" />
              Install
            </TabsTrigger>
            <TabsTrigger
              value="tools"
              className="h-12 gap-2 px-4 font-medium text-muted-foreground hover:text-foreground data-[state=active]:text-primary! after:bottom-0! after:bg-primary"
            >
              <Wrench className="size-4" />
              Tools
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Content area */}
        <main className="flex-1 overflow-auto">
          <TabsContent value="dashboard" className="m-0">
            <Dashboard />
          </TabsContent>
          <TabsContent value="install" className="m-0">
            <Install />
          </TabsContent>
          <TabsContent value="tools" className="m-0">
            <Tools />
          </TabsContent>
        </main>
      </Tabs>

      {/* Footer */}
      <footer className="shrink-0 border-t border-border px-6 py-3 text-center text-[11px] text-muted-foreground">
        DCC MCP Manager v0.1.0
      </footer>
    </div>
  );
}

export default App;
