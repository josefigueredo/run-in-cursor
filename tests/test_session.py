"""ric drives an interactive cursor-agent in tmux, the one way measured to fire every Cursor hook."""
from __future__ import annotations

import subprocess
import unittest

from helpers import Clock, FakeTmux, make_dir
from ric import session


def run(tmux, workspace=None, clock=None, **kw):
    clock = clock or Clock()
    return session.run(workspace or make_dir(), kw.pop("prompt", "/probe-cmd hola"), tmux=tmux, sleep=clock.sleep,
                       clock=clock, stamp=lambda: "101500", **kw)


class Taken(FakeTmux):
    """A tmux server where some session names already exist."""

    def __init__(self, names, **kw):
        super().__init__(**kw)
        self.names = set(names)

    def __call__(self, args):
        if args[0] == "new-session" and args[args.index("-s") + 1] in self.names:
            self.calls.append(list(args))
            return subprocess.CompletedProcess(args, 1, stdout="", stderr=f"duplicate session: {args[args.index('-s') + 1]}")
        return super().__call__(args)


class DeniedTest(unittest.TestCase):
    def test_a_matching_pattern_refuses_whatever_the_case_or_spacing(self):
        for prompt in ("/spec-kit.sync-status specs/x", "   /SPEC-KIT.SYNC-STATUS"):
            self.assertIn("run it in Cursor", session.denied(prompt, [r"spec-kit\.sync-status"]))
        self.assertIsNone(session.denied("/spec-kit.plan", [r"spec-kit\.sync-status"]))


class RunTest(unittest.TestCase):
    def test_launches_interactive_cursor_agent_in_a_detached_session(self):
        ws, tmux = make_dir().resolve(), FakeTmux()
        result = run(tmux, ws, model="composer-2.5")
        log = ws / ".run-in-cursor" / "runs" / "ric-probe-cmd-101500.jsonl"
        self.assertEqual(tmux.calls[0], [
            "new-session", "-d", "-s", "ric-probe-cmd-101500", "-x", "200", "-y", "50", "-c", str(ws),
            f"RUN_IN_CURSOR_LOG={log} cursor-agent --trust --force --model composer-2.5 '/probe-cmd hola'"])
        self.assertEqual((result["session"], result["status"], result["log"]), ("ric-probe-cmd-101500", "completed", log))
        self.assertEqual(result["tokens"], {"input": 14779, "output": 133})
        self.assertEqual(result["screen"], "OK")

    def test_loads_each_local_plugin_dir(self):
        # cursor-agent does not read ~/.cursor/plugins/local by itself (measured 2026-10-13, 2026.10.01-e373342);
        # --plugin-dir loads one plugin directory and can be repeated.
        tmux = FakeTmux()
        run(tmux, plugin_dirs=["/p/pdlc", "/p/with space"])
        agent = tmux.calls[0][-1].split("cursor-agent", 1)[1]
        self.assertIn("--plugin-dir /p/pdlc --plugin-dir '/p/with space'", agent)

    def test_never_print_mode(self):
        tmux = FakeTmux()
        run(tmux, model="composer-2.5")
        agent = tmux.calls[0][-1].split("cursor-agent", 1)[1]  # tmux's own `capture-pane -p` is not cursor-agent's
        self.assertFalse({"-p", "--print"} & set(agent.split()), agent)

    def test_no_stop_line_ends_in_timeout(self):
        clock = Clock()
        result = run(FakeTmux(turns=[None]), clock=clock, timeout=30)
        self.assertEqual(result["status"], "timeout")
        self.assertGreaterEqual(clock.now, 30)

    def test_the_screen_drops_blank_and_border_lines(self):
        result = run(FakeTmux(screen="\n ▄▄▄▄\n  OK\n ▀▀▀▀\n  → Add a follow-up\n"))
        self.assertEqual(result["screen"], "OK\n→ Add a follow-up")

    def test_a_stale_log_with_the_same_name_is_not_a_finished_turn(self):
        # Review I2: a leftover log of an earlier run must not read as this run's stop line.
        ws, clock = make_dir(), Clock()
        old = session.log_path(ws.resolve(), "ric-probe-cmd-101500")
        old.parent.mkdir(parents=True)
        old.write_text('{"event": "stop", "status": "completed", "input_tokens": 1, "output_tokens": 1}\n', encoding="utf-8")
        result = run(FakeTmux(turns=[None]), ws, clock=clock, timeout=10)
        self.assertEqual(result["status"], "timeout")

    def test_a_failed_launch_is_an_error_right_away(self):
        class Refusing(FakeTmux):
            def __call__(self, args):
                done = super().__call__(args)
                return done.__class__(args, 1, stdout="", stderr="no server running") if args[0] == "new-session" else done
        clock = Clock()
        result = run(Refusing(turns=[None]), clock=clock)
        self.assertEqual((result["status"], clock.now), ("error", 0))
        self.assertIn("no server running", result["warning"])

    def test_a_taken_name_gets_the_next_free_suffix(self):
        # Measured 2026-10-21: two runs launched in the same second with the same first word got the same name, and
        # the second one failed with "duplicate session". tmux new-session is atomic, so retrying is race-free.
        ws = make_dir().resolve()
        tmux = Taken({"ric-probe-cmd-101500", "ric-probe-cmd-101500-2"})
        result = run(tmux, ws)
        log = ws / ".run-in-cursor" / "runs" / "ric-probe-cmd-101500-3.jsonl"
        self.assertEqual((result["session"], result["status"], result["log"]), ("ric-probe-cmd-101500-3", "completed", log))
        launches = [c for c in tmux.calls if c[0] == "new-session"]
        self.assertEqual([c[c.index("-s") + 1] for c in launches],
                         ["ric-probe-cmd-101500", "ric-probe-cmd-101500-2", "ric-probe-cmd-101500-3"])
        self.assertIn(f"RUN_IN_CURSOR_LOG={log} ", launches[-1][-1])

    def test_a_name_taken_too_many_times_is_an_error(self):
        names = {"ric-probe-cmd-101500"} | {f"ric-probe-cmd-101500-{n}" for n in range(2, 100)}
        result = run(Taken(names, turns=[None]))
        self.assertEqual(result["status"], "error")
        self.assertIn("duplicate session", result["warning"])

    def test_session_names_carry_the_date(self):
        self.assertRegex(session.default_stamp(), r"^\d{8}-\d{6}$")

    def test_the_run_folder_is_ignored_locally_without_touching_gitignore(self):
        # Measured 2026-10-16: writing .run-in-cursor/ into the tracked .gitignore left a diff in every feature branch.
        ws = make_dir()
        subprocess.run(["git", "init", "-q", str(ws)], check=True)
        (ws / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        run(FakeTmux(), ws)
        run(FakeTmux(), ws)
        self.assertEqual((ws / ".gitignore").read_text(encoding="utf-8"), "node_modules/\n")
        self.assertEqual(subprocess.run(["git", "-C", str(ws), "check-ignore", "-q", ".run-in-cursor/"]).returncode, 0)
        exclude = (ws / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertEqual(exclude.splitlines().count(".run-in-cursor/"), 1)

    def test_a_run_folder_already_ignored_adds_nothing(self):
        ws = make_dir()
        subprocess.run(["git", "init", "-q", str(ws)], check=True)
        (ws / ".gitignore").write_text(".run-in-cursor/\n", encoding="utf-8")
        exclude = ws / ".git" / "info" / "exclude"
        before = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        run(FakeTmux(), ws)
        after = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        self.assertEqual(after, before)

    def test_in_a_worktree_the_run_folder_is_ignored_through_the_shared_exclude(self):
        main = make_dir()
        git = ["git", "-C", str(main), "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(["git", "init", "-q", str(main)], check=True)
        (main / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        subprocess.run(git + ["add", "."], check=True)
        subprocess.run(git + ["commit", "-qm", "init"], check=True)
        ws = make_dir() / "wt"
        subprocess.run(git + ["worktree", "add", "-q", str(ws)], check=True)
        run(FakeTmux(), ws)
        self.assertEqual((ws / ".gitignore").read_text(encoding="utf-8"), "node_modules/\n")
        self.assertEqual(subprocess.run(["git", "-C", str(ws), "status", "--porcelain"], capture_output=True,
                                        text=True).stdout, "")


class SendQuitTest(unittest.TestCase):
    def test_send_and_quit_clear_the_input_first(self):
        # Measured: after a follow-up turn cursor-agent leaves the sent text in its input; typing /quit then made
        # "<last message>/quit" a new prompt instead of quitting. Ctrl-U empties the input and is harmless when empty.
        ws, tmux, clock = make_dir(), FakeTmux(turns=["completed", "completed"]), Clock()
        name = run(tmux, ws, clock=clock)["session"]
        session.send(ws, name, "seguí", tmux=tmux, sleep=clock.sleep, clock=clock)
        session.quit(ws, name, tmux=tmux, sleep=clock.sleep, clock=clock)
        typed = [c for c in tmux.calls if c[0] == "send-keys"]
        for text in ("seguí", "/quit"):
            at = typed.index(["send-keys", "-t", name, "-l", "--", text])
            self.assertEqual(typed[at - 1], ["send-keys", "-t", name, "C-u"], text)

    def test_send_waits_for_the_next_turn_only(self):
        ws, tmux, clock = make_dir(), FakeTmux(turns=["completed", "aborted"]), Clock()
        first = run(tmux, ws, clock=clock)
        second = session.send(ws, first["session"], "sí, seguí", tmux=tmux, sleep=clock.sleep, clock=clock)
        self.assertEqual(second["status"], "aborted")
        self.assertIn(["send-keys", "-t", first["session"], "-l", "--", "sí, seguí"], tmux.calls)

    def test_a_reply_that_starts_with_a_dash_is_typed_literally(self):
        # Review I4: `send-keys -l -foo` fails with "unknown flag"; `--` ends tmux's options.
        ws, tmux, clock = make_dir(), FakeTmux(turns=["completed", "completed"]), Clock()
        name = run(tmux, ws, clock=clock)["session"]
        session.send(ws, name, "-1", tmux=tmux, sleep=clock.sleep, clock=clock)
        self.assertIn(["send-keys", "-t", name, "-l", "--", "-1"], tmux.calls)

    def test_send_refuses_a_denied_text(self):
        # Review I3: a follow-up starting with / runs as a slash command, so send needs the same deny list.
        ws, tmux, clock = make_dir(), FakeTmux(turns=["completed"]), Clock()
        name = run(tmux, ws, clock=clock)["session"]
        result = session.send(ws, name, "/spec-kit.sync-status x", deny=[r"spec-kit\.sync-status"], tmux=tmux,
                              sleep=clock.sleep, clock=clock)
        self.assertEqual(result["status"], "refused")
        self.assertNotIn("/spec-kit.sync-status x", [c[-1] for c in tmux.calls])

    def test_quit_on_a_session_that_does_not_exist_says_so(self):
        # Minor 7: every tmux error was ignored and has-session != 0 read as "ended".
        tmux, clock = FakeTmux(), Clock()
        with self.assertRaises(LookupError):
            session.quit(make_dir(), "ric-nope-20261006-101500", tmux=tmux, sleep=clock.sleep, clock=clock)
        self.assertEqual([c[0] for c in tmux.calls], ["has-session"])

    def test_quit_presses_enter_again_when_autocomplete_takes_the_first(self):
        ws, tmux, clock = make_dir(), FakeTmux(quit_enters=2), Clock()
        name = run(tmux, ws, clock=clock)["session"]
        self.assertTrue(session.quit(ws, name, tmux=tmux, sleep=clock.sleep, clock=clock))
        enters = [c for c in tmux.calls if c[:3] == ["send-keys", "-t", name] and c[-1] == "Enter"]
        self.assertEqual(len(enters), 2)
        self.assertIn(["send-keys", "-t", name, "-l", "--", "/quit"], tmux.calls)


if __name__ == "__main__":
    unittest.main()


class KeysTest(unittest.TestCase):
    """Cursor's question menus take keys, not text. Measured 2026-10-21: keys sent in one burst were mostly dropped;
    one key every 3 s landed every time."""

    def _alive(self, ws, name="ric-x-1"):
        tmux = FakeTmux()
        tmux.alive = True
        tmux.log = session.log_path(ws.resolve(), name)
        tmux.log.parent.mkdir(parents=True, exist_ok=True)
        return tmux

    def test_presses_each_key_on_its_own_with_a_pause_and_shows_the_screen(self):
        ws, clock = make_dir(), Clock()
        tmux = self._alive(ws)
        result = session.keys(ws, "ric-x-1", ["Down", "Space", "Enter"], pause=3, tmux=tmux, sleep=clock.sleep,
                              clock=clock)
        pressed = [c for c in tmux.calls if c[0] == "send-keys"]
        self.assertEqual(pressed, [["send-keys", "-t", "ric-x-1", k] for k in ("Down", "Space", "Enter")])
        self.assertEqual((result["status"], result["screen"]), ("sent", "OK"))
        self.assertGreaterEqual(clock.now, 9)  # between keys and before reading the screen

    def test_the_default_pause_is_the_measured_one(self):
        self.assertEqual(session.KEY_PAUSE_S, 3)

    def test_with_wait_it_returns_the_next_turn(self):
        ws, clock = make_dir(), Clock()
        result = session.keys(ws, "ric-x-1", ["Enter"], wait=True, tmux=self._alive(ws), sleep=clock.sleep,
                              clock=clock)
        self.assertEqual((result["status"], result["tokens"]), ("completed", {"input": 14779, "output": 133}))

    def test_an_unknown_key_is_refused_before_pressing_anything(self):
        ws = make_dir()
        tmux = self._alive(ws)
        with self.assertRaises(ValueError):
            session.keys(ws, "ric-x-1", ["Down", "hola"], tmux=tmux, sleep=Clock().sleep, clock=Clock())
        self.assertFalse([c for c in tmux.calls if c[0] == "send-keys"])

    def test_a_session_that_does_not_exist_raises(self):
        with self.assertRaises(LookupError):
            session.keys(make_dir(), "ric-nope-1", ["Enter"], tmux=FakeTmux(), sleep=Clock().sleep, clock=Clock())
