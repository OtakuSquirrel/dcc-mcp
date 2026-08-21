// DccDaemonServer.cs — Tuanjie (团结引擎) Editor connector for the dcc-daemon.
//
// Tuanjie is Unity's Chinese fork: it scripts in C#, not an embedded CPython,
// so it CANNOT vendor plugins/common/dcc_socket_server.py like the others.
// This file is the C# equivalent of that connector: on Editor load it dials
// the daemon's DCC-register port, registers as kind "tuanjie", holds one
// connection, and serves the request frames the daemon pushes down it.
//
// (Being a fork, the engine API is still Unity's — the UnityEngine/UnityEditor
// namespaces and Application.unityVersion. Only the product name differs.)
//
// The wire protocol is identical to every other DCC (newline-delimited
// JSON, both directions):
//
// Tuanjie -> daemon (once, on connect):
//  {"type":"register","kind":"tuanjie","pid":N,"version":"...","file":"..."}
//     daemon -> Tuanjie (reply):
//         {"type":"registered","instance_id":"tuanjie-1"}
//     daemon -> Tuanjie (per request):
//     {"id":N,"command":"execute_python","params":{"code":"..."}}
//     Tuanjie -> daemon (reply, tagged by id):
//         {"id":N,"result":...} | {"id":N,"error":"...","traceback":"..."}
//
// The only engine-specific pieces:
//   * run-on-main: the UnityEditor/UnityEngine API is not thread-safe, so
//     network threads enqueue jobs that an EditorApplication.update pump
//     drains on the main thread — exactly parallel to Blender's
//     bpy.app.timers bridge and UE's slate post-tick bridge.
//   * "execute_python" carries C# source (there is no Python here); it is
//     compiled and run by DccDaemonRunner via Roslyn scripting. The daemon
//     command name is kept for one uniform protocol across all DCCs.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Runtime.ExceptionServices;
using System.Text;
using System.Threading;
using UnityEditor;
using UnityEngine;
using Debug = UnityEngine.Debug;

namespace DccDaemon
{
    [InitializeOnLoad]
    public static class DccDaemonServer
    {
        private const int DefaultRegisterPort = 18813;
        private const string Host = "127.0.0.1";
        private const double ReconnectStartSeconds = 1.0;
        private const double ReconnectMaxSeconds = 15.0;

        // Application-level keepalive. The Editor periodically writes a tiny
        // frame so a half-open connection (TCP silently dead after a domain
        // reload / crash-recovery with no RST/FIN) is detected: the next
        // heartbeat write fails, we drop the socket, and the connect loop
        // re-registers. Also lets the daemon reap registrations that went
        // silent. Interval is well under the daemon's reaper timeout.
        private const double HeartbeatIntervalSeconds = 5.0;

        // Jobs enqueued by network threads, drained on the Editor main thread.
        private static readonly ConcurrentQueue<Action> MainThreadJobs = new ConcurrentQueue<Action>();

        private static Thread _connThread;
        private static volatile bool _running;
        private static TcpClient _client;
        private static readonly object _sendLock = new object();

        public static string InstanceId { get; private set; }
        public static bool Connected { get; private set; }

        static DccDaemonServer()
        {
            // Runs whenever the Editor loads or recompiles scripts.
            EditorApplication.update += DrainMainThreadJobs;
            Start();
            // A domain reload (script recompile / play-mode toggle) tears down
            // the managed state; reconnect cleanly on the way out.
            AppDomain.CurrentDomain.DomainUnload += (_, __) => Stop();
        }

        // -- lifecycle ---------------------------------------------------

        public static void Start()
        {
            if (_running) return;
            _running = true;
            int port = ReadRegisterPort();
            _connThread = new Thread(() => ConnectLoop(port))
            {
                Name = "dcc-daemon-conn",
                IsBackground = true,
            };
            _connThread.Start();
        }

        public static void Stop()
        {
            _running = false;
            Connected = false;
            InstanceId = null;
            try { _client?.Close(); } catch { /* ignore */ }
            _client = null;
        }

        // -- main-thread bridge ------------------------------------------
        // Network threads call RunOnMain(fn) and block on an event until the
        // Editor's update pump has run the delegate on the main thread.

        private static T RunOnMain<T>(Func<T> fn)
        {
            T result = default;
            Exception error = null;
            using (var done = new ManualResetEventSlim(false))
            {
                MainThreadJobs.Enqueue(() =>
                {
                    try { result = fn(); }
                    catch (Exception e) { error = e; }
                    finally { done.Set(); }
                });
                if (!done.Wait(TimeSpan.FromSeconds(590)))
                    throw new TimeoutException("main-thread job did not complete in time");
            }
            // Rethrow preserving the ORIGINAL stack: a bare `throw error;`
            // resets it to this line, hiding where the fault actually came
            // from (verified on Tuanjie's Mono).
            if (error != null) ExceptionDispatchInfo.Capture(error).Throw();
            return result;
        }

        private static void DrainMainThreadJobs()
        {
            while (MainThreadJobs.TryDequeue(out var job))
            {
                try { job(); }
                catch (Exception e) { Debug.LogError("[dcc-daemon] main-thread job failed: " + e); }
            }
        }

        // -- connection with reconnect/backoff ---------------------------

        private static void ConnectLoop(int registerPort)
        {
            double backoff = ReconnectStartSeconds;
            while (_running)
            {
                try
                {
                    Session(registerPort);
                    backoff = ReconnectStartSeconds; // clean drop -> reset
                }
                catch (Exception)
                {
                    // connect failed / socket error — retry with backoff
                }
                if (!_running) break;
                Thread.Sleep(TimeSpan.FromSeconds(backoff));
                backoff = Math.Min(backoff * 2, ReconnectMaxSeconds);
            }
        }

        private static void Session(int registerPort)
        {
            using (var client = new TcpClient())
            {
                client.Connect(Host, registerPort);
                _client = client;
                using (var stream = client.GetStream())
                {
                    // Register — gather identity on the main thread.
                    var info = RunOnMain(GetInfo);
                    SendFrame(stream, "{\"type\":\"register\"," + info + "}");

                    // Keepalive: a background thread writes heartbeats so a
                    // half-open connection surfaces as a write error, which
                    // closes the client and unblocks the reader below.
                    var hb = new Thread(() => HeartbeatLoop(client, stream))
                    {
                        Name = "dcc-daemon-heartbeat",
                        IsBackground = true,
                    };
                    hb.Start();

                    var reader = new StreamReader(stream, new UTF8Encoding(false));
                    string line;
                    while (_running && (line = reader.ReadLine()) != null)
                    {
                        if (line.Trim().Length == 0) continue;
                        OnFrame(stream, line);
                    }
                }
            }
            Connected = false;
            InstanceId = null;
            _client = null;
        }

        private static void OnFrame(NetworkStream stream, string raw)
        {
            var frame = Json.Parse(raw);
            if (frame == null) return;

            if (frame.GetString("type") == "registered")
            {
                InstanceId = frame.GetString("instance_id");
                Connected = true;
                Debug.Log("[dcc-daemon] Tuanjie registered with daemon as " + InstanceId);
                return;
            }

            // A request frame: handle in its own thread so a long compile or a
            // wedged main thread never blocks reading the next request (e.g. a
            // health heartbeat the daemon sends concurrently).
            var worker = new Thread(() => ServeRequest(stream, frame)) { IsBackground = true };
            worker.Start();
        }

        private static void ServeRequest(NetworkStream stream, JsonValue frame)
        {
            object reqId = frame.GetRaw("id");
            string response = Handle(frame);
            // Tag the reply with the request id.
            string idField = "\"id\":" + Json.Encode(reqId);
            string body = "{" + idField + "," + response + "}";
            lock (_sendLock)
            {
                try { SendFrame(stream, body); } catch { /* connection gone */ }
            }
        }

        // -- keepalive ---------------------------------------------------

        private static void HeartbeatLoop(TcpClient client, NetworkStream stream)
        {
            // Write a heartbeat frame every interval while this connection is
            // the live one. A failed write means the link is (half-)dead:
            // close the client so the reader unblocks and we reconnect.
            while (_running && ReferenceEquals(_client, client))
            {
                Thread.Sleep(TimeSpan.FromSeconds(HeartbeatIntervalSeconds));
                if (!(_running && ReferenceEquals(_client, client))) break;
                try
                {
                    lock (_sendLock) { SendFrame(stream, "{\"type\":\"heartbeat\"}"); }
                }
                catch
                {
                    try { client.Close(); } catch { /* ignore */ }
                    break;
                }
            }
        }

        // -- request handling (runs code on the main thread) -------------

        private static string Handle(JsonValue request)
        {
            string command = request.GetString("command") ?? "";
            var parameters = request.GetObject("params");
            try
            {
                switch (command)
                {
                    case "ping":
                        // Heartbeat that touches the MAIN THREAD, so a wedged
                        // Editor fails it (the network thread would falsely pass).
                        RunOnMain(() => "pong");
                        return "\"result\":\"pong\"";
                    case "get_info":
                        return "\"result\":{" + RunOnMain(GetInfo) + "}";
                    case "execute_python":
                        string code = parameters != null ? parameters.GetString("code") : null;
                        object value = RunOnMain(() => DccDaemonRunner.Execute(code ?? ""));
                        return "\"result\":" + Json.Encode(value);
                    default:
                        return "\"error\":" + Json.Encode("unknown command: " + command);
                }
            }
            catch (Exception e)
            {
                // Report any Editor-side error to the daemon (mirrors the
                // Python connector's {"error","traceback"} shape).
                string message = e.GetType().Name + ": " + e.Message;
                return "\"error\":" + Json.Encode(message)
                    + ",\"traceback\":" + Json.Encode(e.ToString());
            }
        }

        // -- identity (runs on the main thread) --------------------------
        // Returns the interior of a JSON object (no braces), so it can be
        // spliced into both the register frame and get_info replies.

        private static string GetInfo()
        {
            string version = Application.unityVersion;
            string scene = "";
            try
            {
                var active = UnityEditor.SceneManagement.EditorSceneManager.GetActiveScene();
                scene = string.IsNullOrEmpty(active.path) ? "(unsaved)" : active.path;
            }
            catch { scene = ""; }

            int pid = Process.GetCurrentProcess().Id;
            return "\"kind\":\"tuanjie\""
                + ",\"pid\":" + pid
                + ",\"version\":" + Json.Encode(version)
                + ",\"file\":" + Json.Encode(scene);
        }

        // -- wire helpers ------------------------------------------------

        private static void SendFrame(Stream stream, string json)
        {
            byte[] bytes = new UTF8Encoding(false).GetBytes(json + "\n");
            stream.Write(bytes, 0, bytes.Length);
            stream.Flush();
        }

        // Read the daemon's DCC-register port from ~/.dcc-mcp/config.toml,
        // in lock-step with dcc_socket_server.read_register_port(). Pure
        // string scanning keeps this dependency-free inside the Editor.
        private static int ReadRegisterPort()
        {
            try
            {
                string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
                string path = Path.Combine(home, ".dcc-mcp", "config.toml");
                if (!File.Exists(path)) return DefaultRegisterPort;
                foreach (var rawLine in File.ReadAllLines(path))
                {
                    string l = rawLine.Trim();
                    if (l.StartsWith("dcc_register_port"))
                    {
                        int eq = l.IndexOf('=');
                        if (eq >= 0)
                        {
                            string rhs = l.Substring(eq + 1).Trim();
                            int hash = rhs.IndexOf('#');
                            if (hash >= 0) rhs = rhs.Substring(0, hash).Trim();
                            if (int.TryParse(rhs, out int port)) return port;
                        }
                    }
                }
            }
            catch { /* any read/parse error -> default */ }
            return DefaultRegisterPort;
        }
    }
}
