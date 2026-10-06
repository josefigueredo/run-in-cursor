---
name: run-in-cursor
description: Use when the user asks to run something in Cursor from here ("corré esto en Cursor", "mandale a Cursor", send a prompt or a slash command such as /spec-kit.plan to Cursor's agent) and the session must count as real Cursor usage, with its turns, model and tokens reaching Cursor's hooks. Not for work this agent can do itself.
---

# run-in-cursor

Drive Cursor's agent from here: `ric` starts an interactive `cursor-agent` inside a detached tmux session, waits for
the turn to end, and shows you the screen. Every Cursor hook fires (sessionStart, beforeSubmitPrompt, postToolUse,
afterAgentResponse, stop, sessionEnd), exactly as when the user types in Cursor, so any telemetry built on those hooks
records the session.

```bash
python3 ~/.agents/skills/run-in-cursor/ric.py <run|send|quit|install-hook> ...
```

## Steps

1. **Once per machine:** `ric install-hook` (the installer already ran it). It adds `ric hook` to `~/.cursor/hooks.json`
   on stop and sessionEnd, next to whatever is there; it writes only for sessions `ric` started.
2. **Run:** `ric run --workspace <repo> "<prompt or /command args>"` (add `--model` only if the user named one). Pass
   `--deny <regex>` for any command the user keeps for themselves. Wait for it: it returns when the turn ends.
3. **Read the result:** exit 0 completed, 1 aborted, error or refused, 124 timeout, 2 tmux or cursor-agent missing.
   Show the user the screen it printed, not your guess of it.
4. **If Cursor asks something:** answer with `ric send <session> "<reply>" --workspace <repo>`; each reply is another
   recorded turn. Ask the user when the answer is theirs to give.
5. **Always end with** `ric quit <session> --workspace <repo>`, so Cursor sends sessionEnd.

## Rules

- Never `cursor-agent -p`: print mode fires no turn hooks (measured), so nothing records the turns or the tokens.
- `--force` is on: Cursor runs shell commands without asking. Anything that publishes (push, Jira writes, deploys)
  stays with the user: deny it with `--deny`, or hand them the command for Cursor.
- A timeout leaves the session alive: `tmux attach -t <session>` shows it; then `ric quit`.
