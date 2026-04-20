import Dashboard from "./pages/Dashboard";

/**
 * Single-page shell: thin top bar, dashboard, footer.
 * No per-DCC routes — manager is unified (one shared port pool,
 * all DCCs mixed on one view).
 */
function App() {
  return (
    <>
      <div className="topbar">
        <span className="topbar-logo">DCC MCP MANAGER</span>
        <div className="topbar-spacer" />
      </div>
      <Dashboard />
      <div className="site-footer">DCC MCP Manager v0.1.0</div>
    </>
  );
}

export default App;
