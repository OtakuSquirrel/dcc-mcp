// DccDaemonRunner.cs — executes C# sent through the daemon's execute_python
// channel, inside the Tuanjie Editor on the main thread.
//
// Every other DCC runs the `code` string as Python in its embedded CPython.
// Tuanjie has no Python, so here `code` is C# source. It is wrapped in a
// static method, compiled with Roslyn, emitted to a temp DLL, loaded, and
// invoked. Return a value the way Python does: assign to `result`.
//
// Example agent code (C#, not Python):
//     var go = new GameObject("Cube");
//     go.AddComponent<UnityEngine.MeshFilter>();
//     result = go.name;     // -> "Cube" returned to the agent
//
// WHY NOT Roslyn *scripting* (CSharpScript.RunAsync)? It is the obvious fit
// and it does compile correctly here — but it loads the compiled script via
// Microsoft.CodeAnalysis.Scripting.Hosting.CoreAssemblyLoaderImpl
// .LoadFromStream, which under Tuanjie's Mono is a NotImplementedException
// stub (Roslyn picks its .NET Core hosting path, which wants
// AssemblyLoadContext). Every snippet failed with "The method or operation is
// not implemented." AFTER compiling successfully. Emitting to a real FILE and
// using Assembly.LoadFrom sidesteps that loader entirely.
//
// The compile is deliberately NOT routed through the Editor's own script
// compiler: writing a .cs into the project would trigger an asset import and
// a domain reload, which would tear down this very connection.
//
// UnityEngine, UnityEditor and common namespaces are imported by default so
// short snippets "just work". If Roslyn is unavailable in a given Editor
// version, Execute throws a clear error the daemon relays upward.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.ExceptionServices;

namespace DccDaemon
{
    public static class DccDaemonRunner
    {
        // Namespaces made available to every snippet, mirroring how bpy/hou
        // are already in scope for the Python DCCs.
        private static readonly string[] Imports =
        {
            "System",
            "System.Linq",
            "System.Collections",
            "System.Collections.Generic",
            "UnityEngine",
            "UnityEditor",
            "UnityEngine.SceneManagement",
            "UnityEditor.SceneManagement",
        };

        private const string WrapperType = "DccDynamicSnippet";
        private const string WrapperMethod = "Run";

        // Lines the wrapper adds above the user's first line: one `using` per
        // import, the class header, the method header, and the `result`
        // declaration. Diagnostics are shifted by this so the agent sees ITS
        // OWN line numbers.
        private static readonly int WrapperLineOffset = Imports.Length + 3;

        // Roslyn is reached purely by reflection — no compile-time dependency
        // on Microsoft.CodeAnalysis, whose assembly names/versions vary by
        // Editor build.
        private static bool _probed;
        private static Type _syntaxTreeType;    // CSharpSyntaxTree
        private static Type _compilationType;  // CSharpCompilation
        private static Type _metadataRefType;  // MetadataReference
        private static object _compileOptions; // CSharpCompilationOptions (DLL)
        private static Array _references;      // MetadataReference[]
        private static int _counter;
        private static readonly int _processId =
            System.Diagnostics.Process.GetCurrentProcess().Id;

        public static object Execute(string code)
        {
            EnsureRoslyn();

            string source = BuildSource(code ?? "");
            object tree = ParseTree(source);

            _counter++;
            // Scope the name by process id: several Editors can be registered
            // at once, and a loaded DLL stays locked, so a shared name would
            // make the second Editor fail to overwrite the first one's file.
            string name = "DccDynamic_" + _processId + "_" + _counter;
            object compilation = CreateCompilation(name, tree);

            // Emit into a real file: Assembly.LoadFrom works, LoadFromStream
            // does not (see the header note).
            string dll = Path.Combine(Path.GetTempPath(), "dcc-daemon", name + ".dll");
            Directory.CreateDirectory(Path.GetDirectoryName(dll));

            object emitResult;
            using (var stream = new FileStream(dll, FileMode.Create, FileAccess.Write))
                emitResult = Emit(compilation, stream);

            bool ok = (bool)emitResult.GetType().GetProperty("Success").GetValue(emitResult);
            if (!ok)
            {
                TryDelete(dll);
                throw new InvalidOperationException(
                    "C# compilation failed:\n" + string.Join("\n", CompileErrors(emitResult)));
            }

            Assembly assembly = Assembly.LoadFrom(dll);
            MethodInfo entry = assembly.GetType(WrapperType).GetMethod(
                WrapperMethod, BindingFlags.Public | BindingFlags.Static);
            try
            {
                return entry.Invoke(null, null);
            }
            catch (TargetInvocationException tie)
            {
                // Capture/Throw, not `throw inner`: a bare rethrow resets
                // StackTrace to this line, hiding where the snippet actually
                // failed (verified on Tuanjie's Mono).
                ExceptionDispatchInfo.Capture(tie.InnerException ?? tie).Throw();
                throw; // unreachable; satisfies the compiler
            }
            // The temp DLL is intentionally left on disk: it is loaded into
            // this AppDomain and cannot be deleted until a domain reload.
        }

        // Wrap the snippet as the body of a static method returning object.
        // `result` is pre-declared and returned, so assigning to it is the
        // whole contract — exactly as `result` works for the Python DCCs.
        private static string BuildSource(string code)
        {
            var text = new System.Text.StringBuilder();
            foreach (var ns in Imports)
                text.AppendLine("using " + ns + ";");
            text.AppendLine("public static class " + WrapperType + " {");
            text.AppendLine("  public static object " + WrapperMethod + "() {");
            text.AppendLine("    object result = null;");
            text.AppendLine(code);
            text.AppendLine("    return result;");
            text.AppendLine("  }");
            text.AppendLine("}");
            return text.ToString();
        }

        // -- error reporting ---------------------------------------------

        private static IEnumerable<string> CompileErrors(object emitResult)
        {
            var diagnostics = (System.Collections.IEnumerable)
                emitResult.GetType().GetProperty("Diagnostics").GetValue(emitResult);
            foreach (var diagnostic in diagnostics)
            {
                var severity = diagnostic.GetType().GetProperty("Severity")?.GetValue(diagnostic);
                if (severity == null || severity.ToString() != "Error")
                    continue;
                // Diagnostic.ToString() leads with its own "(line,col): "
                // against the WRAPPED source; strip it so the agent is not
                // shown two conflicting line numbers.
                string message = diagnostic.ToString();
                int colon = message.IndexOf("): ", StringComparison.Ordinal);
                if (message.StartsWith("(", StringComparison.Ordinal) && colon > 0)
                    message = message.Substring(colon + 3);
                yield return "(line " + UserLine(diagnostic) + ") " + message;
            }
        }

        // Translate a diagnostic's line back into the agent's own numbering.
        private static string UserLine(object diagnostic)
        {
            try
            {
                object location = diagnostic.GetType().GetProperty("Location").GetValue(diagnostic);
                object span = location.GetType().GetMethod("GetLineSpan", Type.EmptyTypes)
                    .Invoke(location, null);
                object start = span.GetType().GetProperty("StartLinePosition").GetValue(span);
                int line = (int)start.GetType().GetProperty("Line").GetValue(start);
                return Math.Max(1, line + 1 - WrapperLineOffset).ToString();
            }
            catch
            {
                return "?";
            }
        }

        // -- reflective Roslyn calls -------------------------------------

        private static object ParseTree(string source)
        {
            MethodInfo parse = _syntaxTreeType
                .GetMethods(BindingFlags.Public | BindingFlags.Static)
                .Where(m => m.Name == "ParseText" && m.GetParameters().Length >= 1 &&
                       m.GetParameters()[0].ParameterType == typeof(string))
                .OrderBy(m => m.GetParameters().Length)
                .First();
            return parse.Invoke(null, Defaults(parse.GetParameters(), source));
        }

        private static object CreateCompilation(string name, object tree)
        {
            MethodInfo create = _compilationType
                .GetMethods(BindingFlags.Public | BindingFlags.Static)
                .First(m => m.Name == "Create" && m.GetParameters().Length == 4);
            Array trees = Array.CreateInstance(tree.GetType(), 1);
            trees.SetValue(tree, 0);
            return create.Invoke(null, new object[] { name, trees, _references, _compileOptions });
        }

        private static object Emit(object compilation, Stream stream)
        {
            // Roslyn 3.7 exposes only Emit(Stream, ...) — no Emit(string).
            MethodInfo emit = compilation.GetType().GetMethods()
                .Where(m => m.Name == "Emit" && m.GetParameters().Length >= 1 &&
                       m.GetParameters()[0].ParameterType == typeof(Stream))
                .OrderBy(m => m.GetParameters().Length)
                .First();
            return emit.Invoke(compilation, Defaults(emit.GetParameters(), stream));
        }

        // Build an argument array for `parameters`, setting the first to
        // `first` and letting every other take its declared default (or a
        // zeroed value type). Roslyn's signatures vary across versions, so we
        // never hard-code an arity.
        private static object[] Defaults(ParameterInfo[] parameters, object first)
        {
            var args = new object[parameters.Length];
            for (int i = 0; i < parameters.Length; i++)
            {
                if (parameters[i].HasDefaultValue)
                    args[i] = parameters[i].DefaultValue;
                else
                    args[i] = parameters[i].ParameterType.IsValueType
                        ? Activator.CreateInstance(parameters[i].ParameterType)
                        : null;
            }
            if (args.Length > 0)
                args[0] = first;
            return args;
        }

        private static void TryDelete(string path)
        {
            try { File.Delete(path); } catch { /* best effort */ }
        }

        // -- one-time setup ----------------------------------------------

        private static void EnsureRoslyn()
        {
            if (_probed)
            {
                if (_compilationType == null)
                    throw new NotSupportedException(
                        "Roslyn (Microsoft.CodeAnalysis.CSharp) is unavailable in this " +
                        "Editor; cannot execute code sent through execute_python.");
                return;
            }
            _probed = true;

            if (!LoadCodeAnalysis())
                return; // leave _compilationType null -> clear error above

            var assemblies = AppDomain.CurrentDomain.GetAssemblies();
            _syntaxTreeType = FindType(assemblies, "Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree");
            _compilationType = FindType(assemblies, "Microsoft.CodeAnalysis.CSharp.CSharpCompilation");
            _metadataRefType = FindType(assemblies, "Microsoft.CodeAnalysis.MetadataReference");
            Type optionsType = FindType(assemblies, "Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions");
            Type outputKindType = FindType(assemblies, "Microsoft.CodeAnalysis.OutputKind");
            if (_syntaxTreeType == null || _compilationType == null ||
                _metadataRefType == null || optionsType == null || outputKindType == null)
            {
                _compilationType = null;
                return;
            }

            _compileOptions = BuildCompileOptions(optionsType, outputKindType);
            _references = BuildReferences();
        }

        // CSharpCompilationOptions' constructor takes a long optional tail
        // that shifts between versions; bind outputKind by NAME and let the
        // rest default.
        private static object BuildCompileOptions(Type optionsType, Type outputKindType)
        {
            ConstructorInfo ctor = optionsType.GetConstructors()
                .OrderByDescending(c => c.GetParameters().Length)
                .First();
            ParameterInfo[] parameters = ctor.GetParameters();
            var args = new object[parameters.Length];
            for (int i = 0; i < parameters.Length; i++)
            {
                if (parameters[i].Name == "outputKind")
                    args[i] = Enum.Parse(outputKindType, "DynamicallyLinkedLibrary");
                else if (parameters[i].HasDefaultValue)
                    args[i] = parameters[i].DefaultValue;
                else
                    args[i] = parameters[i].ParameterType.IsValueType
                        ? Activator.CreateInstance(parameters[i].ParameterType)
                        : null;
            }
            return ctor.Invoke(args);
        }

        // Reference every loaded assembly that has a real file on disk, so a
        // snippet can touch anything the Editor itself can.
        private static Array BuildReferences()
        {
            MethodInfo fromFile = _metadataRefType
                .GetMethods(BindingFlags.Public | BindingFlags.Static)
                .First(m => m.Name == "CreateFromFile" && m.GetParameters().Length >= 1 &&
                       m.GetParameters()[0].ParameterType == typeof(string));

            var references = new List<object>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                if (assembly.IsDynamic)
                    continue;
                string location;
                try { location = assembly.Location; }
                catch { continue; }
                if (string.IsNullOrEmpty(location) || !File.Exists(location))
                    continue;
                if (!seen.Add(location))
                    continue;
                try { references.Add(fromFile.Invoke(null, Defaults(fromFile.GetParameters(), location))); }
                catch { /* skip anything Roslyn refuses to read */ }
            }

            Array typed = Array.CreateInstance(_metadataRefType, references.Count);
            for (int i = 0; i < references.Count; i++)
                typed.SetValue(references[i], i);
            return typed;
        }

        private static Type FindType(Assembly[] assemblies, string fullName)
        {
            return assemblies.Select(a => a.GetType(fullName)).FirstOrDefault(t => t != null);
        }

        // The Editor ships Roslyn inside its bundled Mono
        // (Editor/Data/MonoBleedingEdge/lib/mono/4.5) but does NOT load it
        // into the Editor AppDomain by default -- it only shells out to a
        // compiler process for project scripts, so GetAssemblies() never sees
        // CSharpCompilation. Look among loaded assemblies first; if absent,
        // load the DLLs by path from the Editor's Mono folder (always present
        // in the install -- no Visual Studio or extra package required).
        private static bool LoadCodeAnalysis()
        {
            const string probe = "Microsoft.CodeAnalysis.CSharp.CSharpCompilation";
            if (AppDomain.CurrentDomain.GetAssemblies().Any(a => a.GetType(probe) != null))
                return true;

            string data = UnityEditor.EditorApplication.applicationContentsPath;
            string[] monoDirs =
            {
                Path.Combine(data, "MonoBleedingEdge", "lib", "mono", "4.5"),
                Path.Combine(data, "MonoBleedingEdge", "lib", "mono", "msbuild", "Current", "bin", "Roslyn"),
            };
            // Order matters: the dependencies must load before Roslyn itself,
            // or resolving them from the LoadFrom context can fail.
            string[] dllNames =
            {
                "System.Collections.Immutable.dll",
                "System.Reflection.Metadata.dll",
                "Microsoft.CodeAnalysis.dll",
                "Microsoft.CodeAnalysis.CSharp.dll",
            };
            foreach (var dir in monoDirs)
            {
                if (!Directory.Exists(dir))
                    continue;
                foreach (var name in dllNames)
                {
                    string dll = Path.Combine(dir, name);
                    if (!File.Exists(dll))
                        continue;
                    try { Assembly.LoadFrom(dll); }
                    catch { /* try the next candidate */ }
                }
                if (AppDomain.CurrentDomain.GetAssemblies().Any(a => a.GetType(probe) != null))
                    return true;
            }
            return false;
        }
    }
}
