"""RPyC adapter tests — Houdini path via an in-process RPyC slave.

Houdini is reached over RPyC (its hot-pluggable ``hrpyc`` server). We
cannot run Houdini in CI, but we can run a real ``rpyc.classic`` slave on
a Houdini-range port and exercise the full adapter path: adapter
selection, teleported execute_python, get_info, and remote-error
propagation. The slave has no ``hou`` module, which mirrors the adapter's
graceful degradation (kind still reported as "houdini").
"""

from __future__ import annotations

import threading
import time

import pytest

from dcc_daemon.core import DaemonCore
from dcc_daemon.transport import DCCError, adapter_for_port

_HOUDINI_TEST_PORT = 18877  # inside the houdini range (18811-18899)


@pytest.fixture
def rpyc_slave():
    """Start a real RPyC classic slave on a Houdini-range port."""
    from rpyc.core.service import SlaveService
    from rpyc.utils.server import ThreadedServer

    server = ThreadedServer(
        SlaveService,
        port=_HOUDINI_TEST_PORT,
        protocol_config={"allow_all_attrs": True, "allow_public_attrs": True},
    )
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    time.sleep(0.5)
    yield DaemonCore(), _HOUDINI_TEST_PORT
    server.close()


def test_houdini_port_selects_rpyc():
    assert type(adapter_for_port(_HOUDINI_TEST_PORT)).__name__ == "RpycAdapter"


def test_rpyc_execute_python(rpyc_slave):
    core, port = rpyc_slave
    assert core.execute_python(port, "result = 6 * 7") == {"port": port, "result": 42}


def test_rpyc_execute_multiline_and_imports(rpyc_slave):
    core, port = rpyc_slave
    out = core.execute_python(port, "import math\nresult = round(math.pi, 2)")
    assert out["result"] == 3.14


def test_rpyc_result_none(rpyc_slave):
    core, port = rpyc_slave
    assert core.execute_python(port, "x = 1") == {"port": port, "result": None}


def test_rpyc_get_info_kind(rpyc_slave):
    core, port = rpyc_slave
    info = core.get_info(port)
    assert info["kind"] == "houdini"
    assert "pid" in info


def test_rpyc_error_propagation(rpyc_slave):
    core, port = rpyc_slave
    with pytest.raises(DCCError) as ei:
        core.execute_python(port, "raise ValueError('boom')")
    assert "boom" in str(ei.value)
    assert ei.value.traceback


def test_rpyc_non_jsonable_result_reprs(rpyc_slave):
    core, port = rpyc_slave
    out = core.execute_python(port, "result = object()")
    assert isinstance(out["result"], str)
    assert "object" in out["result"]


def test_rpyc_health_verdict(rpyc_slave):
    core, port = rpyc_slave
    verdict = core.health(port)["verdict"]
    # Slave answers the protocol ping, so it is at least reachable; on a
    # headless CI host with no window the verdict is healthy or busy.
    assert verdict in {"healthy", "busy", "no_protocol"}
