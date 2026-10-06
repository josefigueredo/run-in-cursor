"""The global Cursor hook (`ric hook`, on stop and sessionEnd in ~/.cursor/hooks.json).

Cursor runs global hooks in every project. This one writes only when the session was started by `ric run`, which
sets RUN_IN_CURSOR_LOG; in any other session it does nothing. It keeps the event, status, model and token counts,
never the prompt or the files, answers `{}` and never fails: a hook that breaks would surface in every turn.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Optional

EVENTS = ("stop", "sessionEnd")
KEEP = ("status", "model", "input_tokens", "output_tokens", "reason")


def record(payload: dict, log: Optional[str], now: Callable[[], float] = time.time) -> None:
    if not log:
        return
    entry = {"event": payload.get("hook_event_name"), **{k: payload.get(k) for k in KEEP}, "t": round(now())}
    try:
        path = Path(log)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _ours(entry: dict) -> bool:
    return "ric.py" in str(entry.get("command", "")) and str(entry.get("command", "")).endswith(" hook")


def installed(path: Path) -> bool:
    hooks = _load(path).get("hooks") or {}
    return all(any(_ours(e) for e in hooks.get(event) or []) for event in EVENTS)


def install(path: Path, command: str) -> bool:
    """Add `command` to stop and sessionEnd as a union with what is there. True when the file changed."""
    data = _load(path) or {"version": 1}
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    changed = False
    for event in EVENTS:
        entries = hooks.setdefault(event, [])
        if not any(_ours(e) for e in entries):
            entries.append({"command": command})
            changed = True
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed
