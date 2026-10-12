# run-in-cursor: referencia

> Este es el README original del repo, movido acá. Para instalarlo, la [guía simple](instalacion.md); para verlo en
> escenarios, el [showcase](showcase.md).

Una skill para Claude Code, Codex y Cursor que le manda un prompt o un slash command al agente de Cursor desde otro
agente, y deja la sesión registrada como uso real de Cursor: turnos, modelo y tokens llegan a los hooks igual que cuando
alguien escribe en Cursor.

```bash
git clone git@github.com:josefigueredo/run-in-cursor.git run-in-cursor && cd run-in-cursor && ./install.sh
python3 ~/.agents/skills/run-in-cursor/ric.py run --workspace ~/mi-repo "/spec-kit.plan specs/001-x"
```

`install.sh` sigue el layout de WayOfWork y jira-kanban (`~/.agents/skills/run-in-cursor` apunta a este repo; Claude
Code y Codex lo ven por `../../.agents/skills/run-in-cursor`) y corre `ric install-hook`.

Requisitos: `python3` 3.9 o más (solo biblioteca estándar), `tmux` y `cursor-agent` con la sesión iniciada.

## Por qué tmux y no `cursor-agent -p`

Medido el 2026-10-06 con `cursor-agent` 2026.10.01-e373342, en un proyecto de prueba con un hook que solo anotaba cada
evento:

| Cómo se lanza | Eventos que llegan |
|---|---|
| `cursor-agent -p "…"` | `sessionStart` y `sessionEnd`; ni `beforeSubmitPrompt` ni `stop` (sin turnos ni tokens) |
| `cursor-agent --trust "…"` interactivo, dentro de tmux | `sessionStart`, `beforeSubmitPrompt`, `postToolUse`, `afterAgentResponse`, `stop` (con estado y tokens) y, con `/quit`, `sessionEnd` |

Un slash command como prompt inicial se expande con sus argumentos, y con `--force` corre su shell sin pedir
aprobación. Las variables de entorno de la sesión llegan a los hooks: `ric` usa `RUN_IN_CURSOR_LOG` para que su hook
global anote solo las sesiones que lanzó, y una línea `stop` nueva en ese log marca el fin del turno.

## Comandos

| Comando | Qué hace |
|---|---|
| `ric run [--workspace D] [--model M] [--timeout S] [--deny REGEX] "<prompt>"` | Abre la sesión, espera el turno e imprime estado, tokens y pantalla |
| `ric send <sesión> [--deny REGEX] "<texto>"` | Responde en la sesión y espera el turno siguiente; `--deny` vale igual que en `run`, porque una respuesta que empieza con `/` corre como slash command |
| `ric quit <sesión>` | `/quit` (y un segundo Enter, porque el primero lo toma el autocompletado) |
| `ric install-hook` | Suma `ric hook` a `~/.cursor/hooks.json` en `stop` y `sessionEnd`, sin tocar lo demás |

Sin el hook global, `ric run` se niega de entrada (exit 2): ningún turno podría avisar que terminó. Los nombres de sesión
llevan fecha y hora (`ric-<comando>-AAAAMMDD-HHMMSS`).

Salida: 0 completado · 1 abortado, error o rechazado · 124 timeout · 2 falta `tmux` o `cursor-agent`, falta el hook global,
o un `--deny` que no es una regex válida.
Los logs quedan en `<workspace>/.run-in-cursor/runs/`, y la carpeta se agrega al `.gitignore` si el workspace es un repo.

## Desarrollar

TDD; `python3 -m unittest discover -s tests`, también con `/usr/bin/python3` (3.9). Conventional commits.
