"""Per-codebase server instance registry stored at ~/.dotnet-graph/registry.json."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock


def _dir() -> Path:
    d = Path.home() / ".dotnet-graph"
    d.mkdir(exist_ok=True)
    return d


def _registry_path() -> Path:
    return _dir() / "registry.json"


def _lock_path() -> Path:
    return _dir() / ".registry.lock"


def _read() -> dict[str, dict]:
    p = _registry_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(data: dict[str, dict]) -> None:
    _registry_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def register(
    root: str | None,
    db_path: str,
    transport: str,
    host: str,
    port: int,
) -> None:
    entry: dict = {
        "root": root,
        "db_path": db_path,
        "transport": transport,
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if transport == "http":
        entry["host"] = host
        entry["port"] = port
        entry["url"] = f"http://{host}:{port}/sse"

    with FileLock(str(_lock_path())):
        data = _read()
        data[db_path] = entry
        _write(data)


def deregister(db_path: str) -> None:
    try:
        with FileLock(str(_lock_path()), timeout=2):
            data = _read()
            data.pop(db_path, None)
            _write(data)
    except Exception:
        pass


def prune() -> None:
    """Remove entries whose process is no longer running."""
    with FileLock(str(_lock_path())):
        data = _read()
        live = {k: v for k, v in data.items() if _is_alive(v.get("pid", -1))}
        if len(live) != len(data):
            _write(live)


def list_instances() -> list[dict]:
    """Return all active instances, pruning dead ones first."""
    prune()
    return list(_read().values())
