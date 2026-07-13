"""Bounded in-memory log capture for the local monitoring WebUI."""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone

_MAX_RECORDS = 2000
_records: deque[dict] = deque(maxlen=_MAX_RECORDS)
_lock = threading.Lock()
_handler: logging.Handler | None = None


class _RingBufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            item = {
                "timestamp": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                item["exception"] = self.formatException(record.exc_info)
            with _lock:
                _records.append(item)
        except Exception:
            self.handleError(record)

    @staticmethod
    def formatException(exc_info) -> str:  # noqa: N802 - mirrors Formatter API
        return logging.Formatter().formatException(exc_info)


def install_log_capture() -> None:
    """Attach the WebUI capture handler to the root logger once."""
    global _handler
    if _handler is not None:
        return
    _handler = _RingBufferHandler(level=logging.DEBUG)
    logging.getLogger().addHandler(_handler)


def get_logs(*, level: str | None = None, logger: str | None = None,
             search: str | None = None, limit: int = 200) -> list[dict]:
    """Return newest matching records in chronological order."""
    level_no = logging._nameToLevel.get((level or "").upper())  # noqa: SLF001
    logger_query = (logger or "").lower()
    search_query = (search or "").lower()
    limit = max(1, min(int(limit), _MAX_RECORDS))

    with _lock:
        snapshot = list(_records)

    matches: list[dict] = []
    for item in reversed(snapshot):
        if level_no and logging._nameToLevel.get(item["level"], 0) < level_no:  # noqa: SLF001
            continue
        if logger_query and logger_query not in item["logger"].lower():
            continue
        haystack = f'{item["logger"]} {item["message"]}'.lower()
        if search_query and search_query not in haystack:
            continue
        matches.append(item)
        if len(matches) >= limit:
            break
    matches.reverse()
    return matches


def clear_logs() -> None:
    with _lock:
        _records.clear()
