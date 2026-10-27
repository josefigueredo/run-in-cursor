---
name: run-in-cursor
description: Use when the user asks to run something in Cursor from here ("corré esto en Cursor", "mandale a Cursor", send a prompt or a slash command such as /spec-kit.plan to Cursor's agent) and the session must count as real Cursor usage, with its turns, model and tokens reaching Cursor's hooks. Not for work this agent can do itself.
compatibility: Requires python3 3.9+ (standard library only), tmux and a logged-in cursor-agent on PATH; running a prompt opens a real Cursor session and spends Cursor usage. ric install-hook adds a hook to ~/.cursor/hooks.json.
---

# run-in-cursor

Drive Cursor's agent from here: `ric` starts an interactive `cursor-agent` inside a detached tmux session, waits for
the turn to end, and shows you the screen. Every Cursor hook fires (sessionStart, beforeSubmitPrompt, postToolUse,
afterAgentResponse, stop, sessionEnd), exactly as when the user types in Cursor, so any telemetry built on those hooks
records the session.

```bash
python3 ~/.agents/skills/run-in-cursor/ric.py <run|send|keys|quit|install-hook> ...
```

## Steps

1. **Once per machine:** `ric install-hook` (the installer already ran it). It adds `ric hook` to `~/.cursor/hooks.json`
   on stop and sessionEnd, next to whatever is there; it writes only for sessions `ric` started.
2. **Run:** `ric run --workspace <repo> "<prompt or /command args>"` (add `--model` only if the user named one). Pass
   `--deny <regex>` for any command the user keeps for themselves: `ric` refuses to send a text that matches it
   (a pattern that starts with `-` goes as `--deny=<regex>`). To load a local Cursor plugin, pass
   `--plugin-dir <dir>` (repeatable): cursor-agent does not read `~/.cursor/plugins/local` by itself. Wait for it: it
   returns when the turn ends.
3. **Read the result:** exit 0 completed, 1 aborted, error or refused, 124 timeout, 2 tmux, cursor-agent or the
   global hook missing (`ric install-hook`).
   Show the user the screen it printed, not your guess of it.
4. **If Cursor asks something:** answer with `ric send <session> "<reply>" --workspace <repo>`; each reply is another
   recorded turn; pass the same `--deny` as the run. Ask the user when the answer is theirs to give.
   If it asks with a menu (options with `›` and `[ ]`), text does not answer it: press keys with
   `ric keys <session> Down Space Enter --workspace <repo>`. Each key waits 3 s (`--pause`), because keys sent in one
   burst were dropped (measured); read the screen it prints before the next key, and add `--wait` on the last one
   to wait for the turn.
5. **Always end with** `ric quit <session> --workspace <repo>`, so Cursor sends sessionEnd.

## Rules

- Never `cursor-agent -p`: print mode fires no turn hooks (measured), so nothing records the turns or the tokens.
- `--force` is on: Cursor runs shell commands without asking. Anything that publishes (push, Jira writes, deploys)
  stays with the user: deny it with `--deny`, or hand them the command for Cursor.
- `--deny` checks only the text you send, never the commands Cursor runs afterwards: do not tell the user it blocked
  anything Cursor might do. It also checks your own words, so naming the file you want protected ("do not overwrite
  X") gets the run refused; leave it unnamed and verify yourself (hash before and after).
- A timeout leaves the session alive: `tmux attach -t <session>` shows it; then `ric quit`.
