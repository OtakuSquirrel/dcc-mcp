# Tuanjie 团结引擎 — driving it with `execute_python` (C#, not Python)

Load this when the target `kind` is `tuanjie`. Tuanjie is Unity's Chinese
fork, and like Unity it has **no embedded Python interpreter** — it scripts in
C#. The daemon keeps the same `execute_python` channel for uniformity, but the
`code` you send is **C# source**, compiled and run inside the Editor by the
connector. `UnityEngine`, `UnityEditor`, and common namespaces are already
imported (being a fork, Tuanjie still uses Unity's namespaces).

## Execution model

- Code runs on the Editor's **main thread** (the connector marshals it through
  an `EditorApplication.update` pump), so `UnityEngine`/`UnityEditor` calls are
  safe and synchronous.
- Your snippet becomes the **body of a static method**: it is wrapped, compiled
  with Roslyn into a temporary DLL, loaded, and invoked. So statements are fine
  at top level, but a `using` directive or a type declaration is not — declare
  local types inside the snippet only if you nest them in a method you define.
- Return a value the same way as every other DCC: **assign to `result`**. It is
  pre-declared as `object`, so `result = 42;` works. Unlike Python, a bare
  trailing expression does *not* come back — the assignment is the contract.
- Default imports: `System`, `System.Linq`, `System.Collections`,
  `System.Collections.Generic`, `UnityEngine`, `UnityEditor`,
  `UnityEngine.SceneManagement`, `UnityEditor.SceneManagement` — all already in
  scope, so `GameObject`, `Vector3`, `Dictionary`, `EditorSceneManager`, and
  LINQ work unqualified. Fully-qualify anything outside those.
- `result` must be JSON-safe. Return names, ids, counts, coordinate tuples —
  not raw `UnityEngine.Object` references (they come back as their string form).
- Every call compiles a fresh assembly, so **nothing carries over between
  calls** — no shared locals. Scene/asset changes persist (they live in the
  Editor), local variables do not. Batch related work into one call.
- This is **Editor** context: `UnityEditor` APIs (menus, asset database,
  scene management) are available; runtime-only PlayMode behavior is not the
  target unless you explicitly enter Play Mode.
- **Errors are precise.** Compile failures come back per-line, renumbered to
  *your* snippet's lines. Runtime exceptions come back with the full C# stack
  trace, with your code appearing as `DccDynamicSnippet.Run()`.

## Minimal patterns

Scene summary (default imports are in scope — no qualification needed):
```csharp
var scene = EditorSceneManager.GetActiveScene();
var roots = scene.GetRootGameObjects();
result = new Dictionary<string, object> {
    { "scene", scene.path },
    { "root_count", roots.Length },
    { "sample", roots.Take(10).Select(g => g.name).ToArray() },
};
```

Create a primitive and capture its name:
```csharp
var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
go.name = "Widget";
go.transform.position = new Vector3(0, 1.5f, 0);
result = go.name;
```

Add a component and read state back:
```csharp
var go = GameObject.Find("Widget");
var rb = go.AddComponent<Rigidbody>();
rb.mass = 2.5f;
result = rb.mass;   // -> 2.5
```

List assets by type via the AssetDatabase:
```csharp
var guids = AssetDatabase.FindAssets("t:Material");
result = guids.Select(g => AssetDatabase.GUIDToAssetPath(g)).ToArray();
```

## Traps that actually bite

- **It's C#, not Python.** No `bpy`-style snippets. Statements end with `;`;
  types are static; use `var`. Only an explicit `result = ...;` comes back.
- **Return plain data.** `UnityEngine.Object` subclasses aren't
  JSON-serializable — return `.name`, `.GetInstanceID()`, asset path strings,
  or `Dictionary`/array/tuple of primitives.
- **Hot reload vs domain reload.** Tuanjie defaults to **Hotreload**: it
  recompiles *without* reloading the managed domain (the Editor log shows
  `domain reloads=0`). So editing the connector's own C# does **not** take
  effect until you force a real domain reload — restart the Editor, or
  right-click → Reimport the package. Entering Play Mode or a genuine
  recompile *does* reload the domain, which briefly drops and re-establishes
  the connection; retry once it reconnects.
- **Editor vs runtime.** `UnityEditor.*` only exists in the Editor. Don't rely
  on it inside code intended for a built player.
- **Undo/serialization.** Direct edits may not be marked dirty; call
  `UnityEditor.EditorUtility.SetDirty(obj)` (and save the scene) if a change
  must persist.
- **Roslyn availability.** Execution needs the Editor's Roslyn assemblies
  (`Microsoft.CodeAnalysis.CSharp`, shipped in the Editor's bundled Mono). If
  they're missing, `execute_python` returns a clear error rather than silently
  doing nothing.
- **Not Roslyn *scripting*.** Worth knowing if you read the connector: the
  obvious `CSharpScript.RunAsync` path compiles fine but then dies in
  `CoreAssemblyLoaderImpl.LoadFromStream`, a `NotImplementedException` stub
  under Tuanjie's Mono. The connector therefore emits to a temp DLL and uses
  `Assembly.LoadFrom` instead. Don't "simplify" it back.

## Screenshot

`screenshot(instance_id)` captures the Editor's **Windows application
window** (via the registered process id), not an in-engine game/scene-view
render. For non-visual verification, read scene/object state back via
`execute_python`.

## Why Tuanjie uses a C# connector (context)

Other DCCs vendor a shared Python connector; Tuanjie can't, so it ships an
equivalent **C# connector** as an embedded Editor package
(`Packages/com.dcc-mcp.tuanjie/`). It speaks the exact same registration
protocol (dials the daemon, registers as `tuanjie`, receives an
`instance_id`) — mirroring how the mainstream Unity MCP servers put a C#
bridge inside the Editor and talk to it over a socket. From your side it is
identical to every other DCC: `execute_python` with a value in `result`.
