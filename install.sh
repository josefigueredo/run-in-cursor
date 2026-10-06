#!/usr/bin/env bash
# Install the run-in-cursor skill for Claude Code, Codex and Cursor.
#   ./install.sh
# Shared layout (same as WayOfWork): ~/.agents/skills/run-in-cursor points at this repo, and
# ~/.claude/skills/run-in-cursor and ~/.codex/skills/run-in-cursor point at ../../.agents/skills/run-in-cursor.
# Cursor reads ~/.agents/skills natively. Re-running is safe. A real directory with the skill's name is never
# replaced: the script stops with exit 1.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="run-in-cursor"
case "${1:-}" in
  -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
  "") ;;
  *) echo "unknown argument: $1" >&2; exit 2 ;;
esac

link() {  # link <target> <path>: create or refresh a symlink, never replace a real file or directory
  if [ -e "$2" ] && [ ! -L "$2" ]; then
    echo "refusing to replace $2: it is not a symlink; move it away and re-run" >&2
    return 1
  fi
  mkdir -p "$(dirname "$2")"
  ln -sfn "$1" "$2"
}

status=0
link "$REPO" "$HOME/.agents/skills/$NAME" || exit 1
for host in .claude .codex; do
  link "../../.agents/skills/$NAME" "$HOME/$host/skills/$NAME" || status=1
done
command -v python3 >/dev/null || { echo "note: python3 is not on PATH; ric needs it" >&2; status=1; }
command -v tmux >/dev/null || { echo "note: tmux is not on PATH; ric needs it (brew install tmux)" >&2; status=1; }
command -v cursor-agent >/dev/null || { echo "note: cursor-agent is not on PATH; ric needs it" >&2; status=1; }
python3 "$REPO/ric.py" install-hook || status=1
echo "skill: $NAME (Claude Code, Codex, Cursor) -> $REPO"
exit "$status"
