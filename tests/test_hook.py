"""The global Cursor hook writes only for a run that asked for it, and never the prompt."""
from __future__ import annotations

import json
import unittest

from helpers import make_dir
from ric import hook

PAYLOAD = {"hook_event_name": "stop", "status": "completed", "model": "composer-2.5", "input_tokens": 10,
           "output_tokens": 2, "prompt": "secreto", "conversation_id": "c1"}


class RecordTest(unittest.TestCase):
    def test_without_a_log_it_writes_nothing(self):
        d = make_dir()
        hook.record(PAYLOAD, None)
        self.assertEqual(list(d.iterdir()), [])

    def test_with_a_log_it_keeps_only_the_listed_fields(self):
        log = make_dir() / "runs" / "s.jsonl"
        hook.record(PAYLOAD, str(log), now=lambda: 7)
        [line] = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(line), {"event": "stop", "status": "completed", "model": "composer-2.5",
                                            "input_tokens": 10, "output_tokens": 2, "reason": None, "t": 7})

    def test_a_log_that_cannot_be_written_never_raises(self):
        d = make_dir()
        (d / "runs").write_text("not a dir", encoding="utf-8")
        hook.record(PAYLOAD, str(d / "runs" / "s.jsonl"))


class InstallTest(unittest.TestCase):
    def test_adds_stop_and_session_end_without_touching_other_hooks(self):
        path = make_dir() / "hooks.json"
        path.write_text(json.dumps({"version": 1, "hooks": {
            "stop": [{"command": "python3 wow hook cursor-stop"}],
            "beforeShellExecution": [{"command": "./hooks/guardrails.sh", "matcher": "git"}]}}), encoding="utf-8")
        self.assertTrue(hook.install(path, "python3 /x/ric.py hook"))
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([h["command"] for h in data["hooks"]["stop"]],
                         ["python3 wow hook cursor-stop", "python3 /x/ric.py hook"])
        self.assertEqual(data["hooks"]["sessionEnd"], [{"command": "python3 /x/ric.py hook"}])
        self.assertEqual(data["hooks"]["beforeShellExecution"][0]["matcher"], "git")
        self.assertFalse(hook.install(path, "python3 /x/ric.py hook"))
        self.assertTrue(hook.installed(path))

    def test_a_missing_file_is_created_and_reported(self):
        path = make_dir() / "cursor" / "hooks.json"
        self.assertFalse(hook.installed(path))
        self.assertTrue(hook.install(path, "python3 /x/ric.py hook"))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], 1)

    def test_another_tool_whose_name_ends_in_ric_py_is_not_ours(self):
        path = make_dir() / "hooks.json"
        path.write_text(json.dumps({"version": 1, "hooks": {
            "stop": [{"command": "python3 /y/fabric.py hook"}],
            "sessionEnd": [{"command": "python3 /y/fabric.py hook"}]}}), encoding="utf-8")
        self.assertFalse(hook.installed(path))
        self.assertTrue(hook.install(path, "python3 /x/ric.py hook"))
        self.assertTrue(hook.installed(path))


if __name__ == "__main__":
    unittest.main()
