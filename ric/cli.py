"""ric: run | send | keys | quit | install-hook | hook. Never `cursor-agent -p`: print mode fires no turn hooks."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

from . import hook, session

OK, FAILED, CANNOT, TIMEOUT = 0, 1, 2, 124
HOOKS_FILE = Path.home() / ".cursor" / "hooks.json"
ENTRY = Path(__file__).resolve().parent.parent / "ric.py"


def _print(result: dict, workspace: Path) -> int:
    print(f"session: {result['session']}")
    print(f"status: {result['status']}")
    tokens = result.get("tokens") or {}
    if tokens.get("input") is not None:
        print(f"tokens: in={tokens['input']} out={tokens['output']}")
    if result.get("warning"):
        sys.stderr.write(f"warning: {result['warning']}\n")
    print(f"log: {result['log']}")
    print("--- screen ---")
    print(result["screen"])
    print("--- end ---")
    name = result["session"]
    print(f'next: ric send {name} "<reply>" --workspace {workspace}  |  ric quit {name} --workspace {workspace}')
    return {"completed": OK, "sent": OK, "timeout": TIMEOUT}.get(result["status"], FAILED)


def main(argv: Optional[List[str]] = None, tmux=session._tmux, which: Callable = shutil.which,
         sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> int:
    parser = argparse.ArgumentParser(prog="ric", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="start an interactive cursor-agent session with this prompt and wait for its turn")
    run.add_argument("prompt")
    send = sub.add_parser("send", help="answer in a running session and wait for the next turn")
    send.add_argument("session")
    send.add_argument("text")
    keys = sub.add_parser("keys", help="press keys one at a time in a running session, for Cursor's question menus")
    keys.add_argument("session")
    keys.add_argument("keys", nargs="+", metavar="KEY", help=" ".join(sorted(session.KEYS)))
    keys.add_argument("--pause", type=float, default=session.KEY_PAUSE_S, help="seconds after each key")
    keys.add_argument("--wait", action="store_true", help="wait for the next turn instead of returning the screen")
    quit_ = sub.add_parser("quit", help="leave a session (/quit), so Cursor sends sessionEnd")
    quit_.add_argument("session")
    for p in (run, send, keys, quit_):
        p.add_argument("--workspace", default=".")
    for p in (run, send, keys):
        p.add_argument("--timeout", type=float, default=1800)
    run.add_argument("--model", default=None)
    run.add_argument("--plugin-dir", action="append", default=[], dest="plugin_dirs",
                     help="load a local Cursor plugin directory (repeatable)")
    for p in (run, send):
        p.add_argument("--deny", action="append", default=[], help="regex; a matching text is refused (repeatable)")
    for p in (run, sub.add_parser("install-hook", help="add ric's hook to Cursor's global hooks.json")):
        p.add_argument("--hooks-file", default=str(HOOKS_FILE))
    sub.add_parser("hook", help="called by Cursor on stop and sessionEnd")
    args = parser.parse_args(argv)

    if args.cmd == "hook":  # inside Cursor's loop: always answer, never fail
        try:
            hook.record(json.loads(sys.stdin.read() or "{}"), os.environ.get("RUN_IN_CURSOR_LOG"))
        except Exception:  # noqa: BLE001
            pass
        print("{}")
        return OK
    if args.cmd == "install-hook":
        changed = hook.install(Path(args.hooks_file).expanduser(), f"{sys.executable} {ENTRY} hook")
        print(f"{args.hooks_file}: {'hook added on stop and sessionEnd' if changed else 'hook already present'}")
        return OK
    for tool in ("tmux", "cursor-agent"):
        if which(tool) is None:
            sys.stderr.write(f"ric: {tool} is not on PATH\n")
            return CANNOT
    workspace = Path(args.workspace).resolve()
    if args.cmd == "quit":
        try:
            ended = session.quit(workspace, args.session, tmux=tmux, sleep=sleep, clock=clock)
        except LookupError:
            print(f"{args.session}: no such session (tmux ls lists the running ones)")
            return FAILED
        print(f"{args.session}: {'ended' if ended else 'still running; check it with tmux attach -t ' + args.session}")
        return OK if ended else FAILED
    if args.cmd == "keys":
        try:
            return _print(session.keys(workspace, args.session, args.keys, pause=args.pause, wait=args.wait,
                                       timeout=args.timeout, tmux=tmux, sleep=sleep, clock=clock), workspace)
        except ValueError as exc:
            sys.stderr.write(f"ric: {exc}\n")
            return CANNOT
        except LookupError:
            print(f"{args.session}: no such session (tmux ls lists the running ones)")
            return FAILED
    for pattern in args.deny:
        try:
            re.compile(pattern)
        except re.error as exc:
            sys.stderr.write(f"ric: invalid --deny {pattern!r}: {exc}\n")
            return CANNOT
    text = args.text if args.cmd == "send" else args.prompt
    reason = session.denied(text, args.deny)
    if reason:
        sys.stderr.write(f"ric: {reason}\n")
        return FAILED
    if args.cmd == "send":
        return _print(session.send(workspace, args.session, args.text, timeout=args.timeout, tmux=tmux, sleep=sleep,
                                   clock=clock), workspace)
    if not hook.installed(Path(args.hooks_file).expanduser()):
        # Without the hook no turn ever reports its end: refuse now instead of waiting out the whole timeout.
        sys.stderr.write(f'ric: the global hook is missing from {args.hooks_file}: run "ric install-hook" first\n')
        return CANNOT
    return _print(session.run(workspace, args.prompt, model=args.model, timeout=args.timeout, tmux=tmux, sleep=sleep,
                              plugin_dirs=[str(Path(d).expanduser()) for d in args.plugin_dirs],
                              clock=clock), workspace)
