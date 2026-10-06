from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TEMP = []


def make_dir() -> Path:
    tmp = tempfile.TemporaryDirectory()
    _TEMP.append(tmp)
    return Path(tmp.name)


class FakeTmux:
    """tmux as the measured cursor-agent session behaves: each prompt ends with the global hook's `stop` line.

    `turns` lists the stop statuses to write, one per prompt (the initial one, then each send); None writes nothing,
    like a machine without the hook. `/quit` writes sessionEnd, after `quit_enters` Enter presses.
    """

    def __init__(self, turns: Optional[List[Optional[str]]] = None, screen: str = "  OK\n", quit_enters: int = 2):
        self.calls: List[List[str]] = []
        self.turns = list(turns if turns is not None else ["completed"])
        self.screen, self.quit_enters = screen, quit_enters
        self.log: Optional[Path] = None
        self.alive, self.typed, self.enters_after_quit = False, "", 0

    def _write(self, event: dict) -> None:
        if self.log is not None:
            with self.log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event) + "\n")

    def _turn(self) -> None:
        status = self.turns.pop(0) if self.turns else None
        if status is not None:
            self._write({"event": "stop", "status": status, "model": "composer-2.5", "input_tokens": 14779,
                         "output_tokens": 133, "reason": None, "t": 1})

    def __call__(self, args: List[str]) -> subprocess.CompletedProcess:
        self.calls.append(list(args))
        out, code = "", 0
        if args[0] == "new-session":
            match = re.search(r"RUN_IN_CURSOR_LOG=(\S+) ", args[-1])
            self.log = Path(match.group(1).strip("'")) if match else None
            self.alive = True
            self._turn()
        elif args[0] == "send-keys":
            if "-l" in args:
                self.typed = args[-1]
            elif args[-1] == "Enter":
                if self.typed == "/quit":
                    self.enters_after_quit += 1
                    if self.enters_after_quit >= self.quit_enters:
                        self.alive = False
                        self._write({"event": "sessionEnd", "reason": "completed", "t": 2})
                else:
                    self._turn()
        elif args[0] == "capture-pane":
            out = self.screen
        elif args[0] == "has-session":
            code = 0 if self.alive else 1
        return subprocess.CompletedProcess(args, code, stdout=out, stderr="")


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
