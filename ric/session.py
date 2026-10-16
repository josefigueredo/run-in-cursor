"""An interactive cursor-agent inside a detached tmux session, driven from another agent.

Measured on 2026-10-06 with cursor-agent 2026.10.01-e373342: `cursor-agent -p` fires only sessionStart and
sessionEnd, so a turn's prompt, model and tokens never reach the hooks. The interactive mode with an initial prompt,
run in a terminal, fires them all (beforeSubmitPrompt, postToolUse, afterAgentResponse, stop and, on /quit,
sessionEnd), and a slash command as the initial prompt expands with its arguments. tmux gives it that terminal.
The session's environment reaches the hooks, so RUN_IN_CURSOR_LOG points the global hook (ric.hook) at this run's
log, and a new `stop` line there is the end of a turn.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Sequence, Callable, Iterable, List, Optional

from . import hook

POLL_S = 2
_BORDER = re.compile(r"^\s*[▄▀]+\s*$")


def _tmux(args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def denied(prompt: str, patterns: Iterable[str]) -> Optional[str]:
    for pattern in patterns:
        if re.search(pattern, prompt.strip(), re.IGNORECASE):
            return f"refused: the prompt matches {pattern!r}; run it in Cursor yourself"
    return None


def _slug(prompt: str) -> str:
    first = (prompt.strip().split() or ["prompt"])[0].lstrip("/")
    return re.sub(r"[^a-z0-9]+", "-", first.lower()).strip("-")[:30] or "prompt"


def default_stamp() -> str:
    """Date and time: a name reused at the same HH:MM:SS of another day would point at an old log."""
    return time.strftime("%Y%m%d-%H%M%S")


def log_path(workspace: Path, name: str) -> Path:
    return workspace / ".run-in-cursor" / "runs" / f"{name}.jsonl"


def _events(log: Path) -> List[dict]:
    if not log.is_file():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _stops(log: Path) -> List[dict]:
    return [e for e in _events(log) if e.get("event") == "stop"]


def _screen(name: str, tmux) -> str:
    text = tmux(["capture-pane", "-p", "-t", name]).stdout or ""
    return "\n".join(line.strip() for line in text.splitlines() if line.strip() and not _BORDER.match(line))


def _ignore(workspace: Path) -> None:
    """Keep the run logs out of the workspace's git, if it is a repo, without touching its tracked .gitignore:
    the entry goes to the repo's local info/exclude (shared by its worktrees) and only when git does not ignore it yet."""
    if not (workspace / ".git").exists():
        return
    git = ["git", "-C", str(workspace)]
    if subprocess.run(git + ["check-ignore", "-q", ".run-in-cursor/"]).returncode == 0:
        return
    found = subprocess.run(git + ["rev-parse", "--git-path", "info/exclude"], capture_output=True, text=True)
    if found.returncode != 0:
        return
    path = Path(found.stdout.strip())
    path = path if path.is_absolute() else workspace / path
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_text(text + ("" if not text or text.endswith("\n") else "\n") + ".run-in-cursor/\n", encoding="utf-8")


def _wait(name: str, log: Path, seen: int, timeout: float, tmux, sleep, clock) -> dict:
    start = clock()
    while True:
        stops = _stops(log)
        if len(stops) > seen:
            stop = stops[seen]
            return {"session": name, "log": log, "status": stop.get("status") or "completed",
                    "tokens": {"input": stop.get("input_tokens"), "output": stop.get("output_tokens")},
                    "screen": _screen(name, tmux), "warning": ""}
        if clock() - start >= timeout:
            return {"session": name, "log": log, "status": "timeout", "tokens": {}, "screen": _screen(name, tmux),
                    "warning": ""}
        sleep(POLL_S)


def _error(name: str, log: Path, status: str, warning: str) -> dict:
    return {"session": name, "log": log, "status": status, "tokens": {}, "screen": "", "warning": warning}


def run(workspace: Path, prompt: str, model: Optional[str] = None, timeout: float = 1800, tmux=_tmux,
        plugin_dirs: Sequence[str] = (),
        sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
        stamp: Callable[[], str] = default_stamp) -> dict:
    workspace = Path(workspace).resolve()
    name = f"ric-{_slug(prompt)}-{stamp()}"
    log = log_path(workspace, name)
    log.parent.mkdir(parents=True, exist_ok=True)
    _ignore(workspace)
    seen = len(_stops(log))  # a leftover log under the same name is not this run's turn
    agent = "cursor-agent --trust --force" + (f" --model {shlex.quote(model)}" if model else "")
    # cursor-agent does not load ~/.cursor/plugins/local on its own; a local plugin comes in with --plugin-dir.
    agent += "".join(f" --plugin-dir {shlex.quote(d)}" for d in plugin_dirs)
    started = tmux(["new-session", "-d", "-s", name, "-x", "200", "-y", "50", "-c", str(workspace),
                    f"RUN_IN_CURSOR_LOG={shlex.quote(str(log))} {agent} {shlex.quote(prompt)}"])
    if started.returncode != 0:
        return _error(name, log, "error", f"tmux could not start the session: {(started.stderr or '').strip()}")
    return _wait(name, log, seen, timeout, tmux, sleep, clock)


def _type(name: str, text: str, tmux) -> bool:
    """Empty the input, then type. After a follow-up turn cursor-agent leaves the sent text in its input (measured);
    without Ctrl-U the next text is appended to it. Ctrl-U on an empty input does nothing."""
    tmux(["send-keys", "-t", name, "C-u"])
    return tmux(["send-keys", "-t", name, "-l", "--", text]).returncode == 0  # `--`: a text may start with -


def send(workspace: Path, name: str, text: str, timeout: float = 1800, deny: Iterable[str] = (), tmux=_tmux,
         sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> dict:
    log = log_path(Path(workspace).resolve(), name)
    reason = denied(text, deny)  # a follow-up starting with / runs as a slash command: same deny list as run
    if reason:
        return _error(name, log, "refused", reason)
    seen = len(_stops(log))
    if not _type(name, text, tmux):
        return _error(name, log, "error", f"tmux could not type into {name}")
    tmux(["send-keys", "-t", name, "Enter"])
    return _wait(name, log, seen, timeout, tmux, sleep, clock)


def quit(workspace: Path, name: str, tmux=_tmux, sleep: Callable[[float], None] = time.sleep,
         clock: Callable[[], float] = time.monotonic, timeout: float = 15) -> bool:
    """/quit then Enter; a second Enter if the session lives on (autocomplete takes the first). True once it ended.
    A session that does not exist raises LookupError: "ended" would hide a wrong name."""
    if tmux(["has-session", "-t", name]).returncode != 0:
        raise LookupError(name)
    _type(name, "/quit", tmux)
    sleep(1)
    tmux(["send-keys", "-t", name, "Enter"])
    sleep(3)
    if tmux(["has-session", "-t", name]).returncode == 0:
        tmux(["send-keys", "-t", name, "Enter"])
    log, start = log_path(Path(workspace).resolve(), name), clock()
    while clock() - start < timeout:
        if tmux(["has-session", "-t", name]).returncode != 0:
            return True
        sleep(POLL_S)
    return any(e.get("event") == "sessionEnd" for e in _events(log))
