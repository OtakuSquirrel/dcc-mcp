"""Exercise Windows restarts only against disposable checkout processes."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _powershell(command: str, *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=cwd, capture_output=True, text=True, timeout=40,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def test_restart_process_matcher_is_scoped_to_checkout():
    python = r"C:\work\DCC project's checkout\.venv\Scripts\python.exe"
    entry = r"C:\work\DCC project's checkout\.venv\Scripts\dcc-mcp.exe"
    cases = [
        (f'"{python}" -m dcc_mcp --log-level INFO', True),
        (f'"{python.upper()}" -m dcc_mcp', True),
        (f'"{python}" "{entry}" --log-level INFO', True),
        (f'"{entry}" --log-level INFO', True),
        (f'"{python}" -m dcc_mcp_extra', False),
        (f'"{python}" -c "print(123)"', False),
        (f'"{entry}.bak"', False),
        (f'cmd.exe /c "{entry}"', False),
        (r'"C:\other\.venv\Scripts\python.exe" -m dcc_mcp', False),
        (None, False),
    ]
    payload = json.dumps({"python": python, "entry": entry, "commands": [c[0] for c in cases]})
    result = _powershell(
        f". {_quote(REPO_ROOT / 'scripts/restart-daemon.ps1')}\n"
        f"$data = ConvertFrom-Json @'\n{payload}\n'@\n"
        "$results = @($data.commands | ForEach-Object {\n"
        "  Test-DccDaemonCommandLine -CommandLine $_ -PythonPath $data.python -EntryPoint $data.entry\n"
        "})\n$results | ConvertTo-Json -Compress"
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [expected for _, expected in cases]


def _free_ports() -> tuple[int, int]:
    with socket.socket() as first, socket.socket() as second:
        first.bind(("127.0.0.1", 0))
        second.bind(("127.0.0.1", 0))
        return first.getsockname()[1], second.getsockname()[1]


@pytest.fixture
def checkout(tmp_path: Path) -> tuple[Path, int]:
    root = tmp_path / "checkout with spaces"
    root.mkdir()
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(root / ".venv")],
        check=True, capture_output=True, timeout=30,
    )
    (root / "scripts").mkdir()
    shutil.copy2(REPO_ROOT / "start-daemon.bat", root)
    shutil.copy2(REPO_ROOT / "scripts/restart-daemon.ps1", root / "scripts")
    package = root / "dcc_mcp"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    http_port, register_port = _free_ports()
    (package / "config.py").write_text(
        f'def http_bind(): return ("127.0.0.1", {http_port})\n'
        f'def register_bind(): return ("127.0.0.1", {register_port})\n',
        encoding="utf-8",
    )
    (package / "__main__.py").write_text(
        "import os, socket\n"
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "from . import config\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200)\n"
        "        self.end_headers()\n"
        "        self.wfile.write(str(os.getpid()).encode())\n"
        "registration = socket.socket()\n"
        "registration.bind(config.register_bind())\n"
        "registration.listen()\n"
        "HTTPServer(config.http_bind(), Handler).serve_forever()\n",
        encoding="utf-8",
    )
    return root, http_port


def _wait_for_daemon(port: int, *, old_pid: int | None = None) -> int:
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/", timeout=.5) as response:
                pid = int(response.read())
                if pid != old_pid:
                    return pid
        except (URLError, OSError):
            pass
        time.sleep(.1)
    pytest.fail("Disposable daemon did not become ready")


def _stop_checkout(root: Path):
    # This helper only ever receives pytest's disposable checkout path.
    script = root / "scripts/restart-daemon.ps1"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(script)],
        cwd=root, capture_output=True, text=True, timeout=40,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("relative_old_process", [False, True])
def test_double_launch_replaces_previous_daemon(
    checkout: tuple[Path, int], relative_old_process: bool,
):
    root, port = checkout
    launchers = []
    current_pid = None
    batch = root / "start-daemon.bat"
    batch_source = batch.read_text()
    with (root / "launch.log").open("w") as log:
        try:
            for attempt in range(2):
                source = batch_source
                if attempt == 0 and relative_old_process:
                    source = source.replace('"%~dp0.venv\\Scripts\\python.exe"', '".venv\\Scripts\\python.exe"')
                batch.write_text(source)
                previous = current_pid
                launchers.append(subprocess.Popen(
                    ["cmd.exe", "/d", "/c", str(root / "start-daemon.bat")],
                    cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                ))
                current_pid = _wait_for_daemon(port, old_pid=previous)
            assert current_pid != previous
            launchers[0].wait(timeout=5)
        finally:
            _stop_checkout(root)
            for launcher in launchers:
                launcher.wait(timeout=5)
    assert "Stopping previous dcc-mcp" in (root / "launch.log").read_text()


def test_foreign_port_owner_is_not_stopped(checkout: tuple[Path, int]):
    root, port = checkout
    with socket.socket() as foreign_listener:
        foreign_listener.bind(("127.0.0.1", port))
        foreign_listener.listen()
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(root / "scripts/restart-daemon.ps1")],
            cwd=root, capture_output=True, text=True, timeout=40,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert result.returncode == 1
        assert "It was not stopped" in result.stdout
        assert foreign_listener.getsockname()[1] == port
