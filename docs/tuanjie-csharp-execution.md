# Tuanjie (团结引擎): C# execution and the traps we hit

Status: **implemented and verified on a live Editor** (Tuanjie 2022.3.62t12,
Tuanjie Editor 1.10.0).

Tuanjie is Unity's Chinese fork. It is the one DCC with no embedded CPython,
so `execute_python` carries **C# source** for it. This note records what
actually broke, the root cause of each failure, and why the code looks the way
it does — several of these look like arbitrary complexity until you know the
failure they prevent.

## Identifying Tuanjie (and not confusing it with Unity)

| | Value |
|---|---|
| Executable | `C:\Program Files\Tuanjie\Hub\Editor\<ver>\Editor\Tuanjie.exe` |
| Editor log | `%LOCALAPPDATA%\Tuanjie\Editor\Editor.log` (**not** `.../Unity/Editor/`) |
| Project marker | `m_TuanjieEditorVersion:` in `ProjectSettings/ProjectVersion.txt` |
| Version string | `2022.3.62t12` — the `t` is the Tuanjie build, vs Unity's `f` |

`m_TuanjieEditorVersion` is the reliable discriminator: a stock Unity project
never has that line. `TuanjieInstaller._is_tuanjie_project` **requires** it, so
adding a Unity installer later cannot cross-claim projects.

Being a fork, Tuanjie still uses Unity's API surface — the `UnityEngine` /
`UnityEditor` namespaces, `Application.unityVersion`, `com.unity.*` UPM
packages, and the `"unity": "2020.3"` field in `package.json`. **Only the
product name is Tuanjie.** When renaming things, that is the line to hold:
rename the product, keep the engine API.

## The headline bug: Roslyn *scripting* cannot load its own output

Symptom: every snippet, however trivial, failed with

```
NotImplementedException: The method or operation is not implemented.
```

That message is the default text of `new NotImplementedException()` — the
signature of a **Mono stub**. The stack (once we could see it, see below)
pinned it exactly:

```
at Microsoft.CodeAnalysis.Scripting.Hosting.CoreAssemblyLoaderImpl.LoadFromStream(Stream, Stream)
at InteractiveAssemblyLoader.LoadAssemblyFromStream(...)
at ScriptBuilder.Build[T](...)          <- compilation already SUCCEEDED here
at CSharpScript.RunAsync(...)
```

`CoreAssemblyLoaderImpl` is Roslyn's **.NET Core** hosting path; it wants
`AssemblyLoadContext`. Tuanjie runs Mono, where that implementation is a stub.
So Roslyn scripting compiled correctly and then died loading its own output.

Two facts that made this confusing before we had the stack:

- **Compilation genuinely works.** Sending invalid C# returned a proper
  `CompilationErrorException: (3,9): error CS8652 ...`. Roslyn was loaded and
  functioning — only the loader was missing.
- **A standalone repro under the same Mono succeeded.** Running the identical
  reflection code under `MonoBleedingEdge/bin/mono.exe` returned `2`, because
  outside the Editor Roslyn selected `DesktopAssemblyLoaderImpl` instead.

### The fix: compile ourselves, emit to a *file*

`DccDaemonRunner` does not use `Microsoft.CodeAnalysis.CSharp.Scripting` at
all. It wraps the snippet, compiles with plain `CSharpCompilation`, emits to a
temp DLL, and `Assembly.LoadFrom`s it:

```
snippet -> BuildSource()            wrap as DccDynamicSnippet.Run() body
        -> CSharpSyntaxTree.ParseText
        -> CSharpCompilation.Create(refs = every loaded assembly with a file)
        -> Emit(FileStream)          %TEMP%\dcc-daemon\DccDynamic_<pid>_<n>.dll
        -> Assembly.LoadFrom(path)   the point: a real FILE, never a Stream
        -> Run() via reflection
```

**Do not "simplify" this back to `CSharpScript.RunAsync`.** It will look
cleaner, compile fine, and fail on every call.

We deliberately do **not** write a `.cs` into the project and let the Editor
compile it: that triggers an asset import and a domain reload, which would tear
down the very connection serving the request.

### Roslyn 3.7 API quirks (bundled version, reached by reflection)

Tuanjie ships Roslyn **3.7** in `Editor/Data/MonoBleedingEdge/lib/mono/4.5/`
(`Microsoft.CodeAnalysis*.dll`, plus `System.Collections.Immutable` 1.2.3 and
`System.Reflection.Metadata` 1.4.3 — self-consistent, no version conflict, and
nothing shadowing them in `Editor/Data/Managed`). All access is reflective so
we take no compile-time dependency on assemblies whose versions shift per
Editor build. Three things bit us:

- **No `Emit(string path)`.** Roslyn 3.7 exposes only `Emit(Stream, ...)`
  overloads; the path-taking convenience came later. Emit into a `FileStream`.
- **`CSharpCompilationOptions`' constructor has a long optional tail** that
  shifts between versions. `Activator.CreateInstance(type, outputKind)` throws
  `MissingMethodException`. Bind `outputKind` **by parameter name** and let the
  rest take their declared defaults.
- **`Type.GetType("...")` returns null** for types in assemblies pulled in via
  `Assembly.LoadFrom` (load-context isolation). Search
  `AppDomain.CurrentDomain.GetAssemblies()` instead.

Also: the Editor does not load Roslyn into its AppDomain by default (it shells
out to a compiler process for project scripts), so `LoadCodeAnalysis()` loads
the DLLs by path — **dependencies first** (`Immutable`, `Metadata`, then
`CodeAnalysis`, then `CodeAnalysis.CSharp`), or resolution from the LoadFrom
context can fail.

### Consequences of the design, worth knowing

- **Every call is a fresh assembly**, so nothing carries over between calls —
  no shared locals. Scene/asset changes persist (they live in the Editor);
  variables do not. Batch related work into one call.
- **The snippet is a method body**, not a script. Statements are fine at top
  level; `using` directives and type declarations are not.
- **`result` must be assigned.** It is pre-declared as `object` and returned.
  A bare trailing expression does *not* come back (unlike Python). This was
  previously mis-documented as working either way — it never did.
- **Temp DLLs accumulate** in `%TEMP%\dcc-daemon\`. A loaded assembly is locked
  and cannot be deleted until a domain reload, so we leave them (a few KB
  each). Only failed compiles are cleaned up. Sweeping the directory on
  `beforeAssemblyReload` would fix this properly — not done yet.
- **Names are pid-scoped** (`DccDynamic_<pid>_<n>`). Several Editors can be
  registered at once; a shared name means the second Editor cannot overwrite
  the first one's locked file.

## Trap: Hotreload means your connector edits do not take effect

Tuanjie defaults to **Hotreload** — it recompiles *without* reloading the
managed domain. The Editor log says so plainly:

```
Scripting: domain reloads=0, compile time=1984 ms
Hotreload: 6.795ms
```

This cost us a full debugging round: we edited the connector to print a stack
trace, waited for the recompile, re-ran, and saw **no diagnostic output** — the
old assembly was still live. The tell is a timestamp comparison:

```bash
ls -la Library/ScriptAssemblies/DccDaemon.Editor.dll   # 13:35
ls -la Packages/com.dcc-mcp.tuanjie/DccDaemonRunner.cs # 13:46  <- source newer
```

**After changing connector C#, force a real domain reload** (restart the
Editor, or right-click → Reimport the package) and verify the DLL timestamp
moved. Otherwise you are testing the previous build and will draw wrong
conclusions.

## Trap: `throw ex;` destroys the stack trace

This one silently invalidates all downstream diagnosis, so it is worth stating
precisely. Verified on Tuanjie's own Mono with `[MethodImpl(NoInlining)]`
frames:

```
bare `throw e;`                        -> only the rethrow site; Deep/Middle frames GONE
ExceptionDispatchInfo.Capture(e).Throw() -> Deep/Middle frames preserved
```

The connector had three bare rethrows on the error path
(`DccDaemonServer.RunOnMain`, and two in `DccDaemonRunner`). With them, the
traceback pointed at our own rethrow line instead of the Mono stub — the fix
below would have surfaced a useless stack. All three now use
`ExceptionDispatchInfo`.

The Python connectors need no equivalent change: `raise` preserves frames via
`__traceback__` chaining, so `traceback.format_exc()` already shows the deep
frame. **The asymmetry is C#-only.**

## Trap: FastMCP renders only `str(exc)`

The connector sent `{"error", "traceback"}` and `HubError` carried
`.traceback` — but nothing read it. FastMCP 3.2.4 (`server.py:1263`) does:

```python
raise ToolError(f"Error calling tool {name!r}: {e}") from e
```

`str(exc)` only. The DCC-side stack trace was constructed, transmitted, stored
on the exception, and then dropped one layer from the agent.

`execute_python` now catches `DCCError` and folds `.traceback` into a
`ToolError`. `ToolError` is a `FastMCPError`, which FastMCP re-raises verbatim
— so it also survives `mask_error_details` (settable via
`FASTMCP_MASK_ERROR_DETAILS`, so the default cannot be relied on).

Separately, `hub.py` now logs DCC-side faults at the one choke point every DCC
and command passes through. FastMCP's own `logger.exception` does **not**
propagate to root, so before this a DCC failure left no trace in the WebUI's
`/api/logs` at all.

## Verification techniques that paid off

Two throwaway tools were worth more than the time they cost, because the
Editor's edit→reload→test cycle is slow and (per the Hotreload trap) can lie.

**1. Standalone Mono probe.** Drive the same reflective Roslyn calls under the
Editor's own `mono.exe`, outside the Editor. This is how the emit-to-file path
was proven (returning `2`) before any connector code was written, and how the
`Emit(string)` and options-constructor quirks were found — in seconds per
iteration instead of minutes.

**2. Compile-check against the Editor's own response file.** The Editor writes
`Library/Bee/artifacts/*.dag/DccDaemon.Editor.rsp` with the exact reference set
for our asmdef. Rewriting its `-out`/`-refout` to a temp path and its source
paths to the repo working copy type-checks connector edits with the real
Roslyn `csc` and real engine assemblies, without touching the project.

Hand-rolling the reference list instead does **not** work — you hit the
`netstandard` vs `mscorlib` duplicate-type conflict (`CS0433`/`CS0518`). Use
the Editor's rsp. Mono's legacy `mcs` is also not a substitute: it cannot parse
modern C# (`default` literal, type patterns) and errors out.

Guard that script: if the rsp no longer contains the expected source path,
**fail loudly**. A silent no-op replacement once made it compile the installed
copy instead of the edits under test, and reported success.

## Verified working

Against a live Editor, after the fix:

| Check | Result |
|---|---|
| `result = 1 + 1` | `2` |
| Default imports unqualified | `EditorSceneManager`, `Dictionary`, LINQ all in scope |
| Scene mutation | primitive created, `Rigidbody` added, `mass` set |
| Persistence across calls | object found by a later, separate call |
| Runtime exception | stack contains `DccDynamicSnippet.Run()` |
| Compile error | `(line 3) error CS1002` — renumbered to the agent's own lines |
| WebUI | fault appears in `/api/logs` |

The compile-error line offset is `Imports.Length + 3` (one `using` per import,
the class header, the method header, the `result` declaration). It was
initially `+ 4` and reported every error one line early — if the wrapper in
`BuildSource` changes, re-derive this.
