"""ric's exit codes and output are what a calling agent reads: 0 completed, 1 refused or failed, 124 timeout, 2 cannot."""
from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from unittest import mock

from helpers import Clock, FakeTmux, make_dir
from ric import cli


def ric(args, tmux=None, which=lambda name: f"/usr/bin/{name}", stdin=""):
    out, err, clock = io.StringIO(), io.StringIO(), Clock()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), mock.patch("sys.stdin", io.StringIO(stdin)):
        code = cli.main(args, tmux=tmux or FakeTmux(), which=which, sleep=clock.sleep, clock=clock)
    return code, out.getvalue(), err.getvalue()


class RunCliTest(unittest.TestCase):
    def test_a_completed_run_prints_the_session_status_tokens_screen_and_next_step(self):
        code, out, _ = ric(["run", "--workspace", str(make_dir()), "--hooks-file", str(make_dir() / "h.json"),
                            "/probe-cmd hola"])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"session: ric-probe-cmd-\d{6}")
        self.assertIn("status: completed", out)
        self.assertIn("tokens: in=14779 out=133", out)
        self.assertIn("next: ric send ric-probe-cmd-", out)

    def test_a_denied_prompt_never_starts_a_session(self):
        tmux = FakeTmux()
        code, _, err = ric(["run", "--deny", r"spec-kit\.sync-status", "/spec-kit.sync-status x"], tmux=tmux)
        self.assertEqual(code, 1)
        self.assertIn("run it in Cursor", err)
        self.assertEqual(tmux.calls, [])

    def test_timeout_exits_124(self):
        code, out, _ = ric(["run", "--workspace", str(make_dir()), "--timeout", "10", "hola"], tmux=FakeTmux(turns=[None]))
        self.assertEqual(code, 124)
        self.assertIn("status: timeout", out)

    def test_an_aborted_turn_exits_1(self):
        self.assertEqual(ric(["run", "--workspace", str(make_dir()), "hola"], tmux=FakeTmux(turns=["aborted"]))[0], 1)

    def test_without_tmux_or_cursor_agent_it_cannot(self):
        code, _, err = ric(["run", "hola"], which=lambda name: None if name == "tmux" else "/usr/bin/x")
        self.assertEqual(code, 2)
        self.assertIn("tmux", err)


class HookCliTest(unittest.TestCase):
    def test_hook_writes_to_the_run_log_and_answers_an_empty_object(self):
        log = make_dir() / "r.jsonl"
        with mock.patch.dict(os.environ, {"RUN_IN_CURSOR_LOG": str(log)}):
            code, out, _ = ric(["hook"], stdin=json.dumps({"hook_event_name": "stop", "status": "completed"}))
        self.assertEqual((code, out.strip()), (0, "{}"))
        self.assertEqual(json.loads(log.read_text(encoding="utf-8"))["event"], "stop")

    def test_hook_with_garbage_still_answers(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            self.assertEqual(ric(["hook"], stdin="not json")[:2], (0, "{}\n"))

    def test_install_hook_reports_once(self):
        path = make_dir() / "hooks.json"
        self.assertIn("added", ric(["install-hook", "--hooks-file", str(path)])[1])
        self.assertIn("already", ric(["install-hook", "--hooks-file", str(path)])[1])


if __name__ == "__main__":
    unittest.main()
