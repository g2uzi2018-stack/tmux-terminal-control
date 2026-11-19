# Peer Coworkers

Run bounded coding, research, testing, and review packages through headless `codex`, `agy`, and `cursor` CLIs, with per-workspace write locking and non-invasive Git tree auditing.

Requires Linux/WSL, Python 3.9+ (standard library only), and Git.

## Install

```bash
python3 scripts/install-skill.py
python3 "${CODEX_HOME:-$HOME/.codex}/skills/peer-coworkers/scripts/cowork.py" doctor
```

The installer backs up any previous installation under `.peer-coworkers-backups/`, copies the standalone skill package without touching global CLI configuration, and preserves `LICENSE` and `NOTICE`.

## Commands

Run via `python3 skills/peer-coworkers/scripts/cowork.py`:

| Command | Behavior |
| --- | --- |
| `doctor` | Check executable paths and versions for `codex`, `agy`, and `cursor` |
| `start --cwd D --profile P [--model M] [--effort E] --task-file F [--write P]... [--name N] [--timeout S]` | Snapshot Git baseline and launch worker headlessly in the background |
| `wait --run R [--timeout S]` | Poll `run.lock` until completion or wait timeout; return result/transcript paths and diff audit |
| `send --run R --file F` | Resume the recorded session for round `N+1`, recording a per-round baseline tree |
| `log --run R [--tail N]` | Show recent readable assistant/tool output from `round-N.log` |
| `diff --run R [--round N]` | Report changed files, `outside_write_paths`, and Git HEAD/branch/index changes |
| `stop --run R` | Terminate the runner process group (`SIGTERM`, then `SIGKILL` after 5s) |

## Details

- **Scope and audit**: Omit `--write` for read-only tasks; repeatable `--write PATH` enables writable execution and enforces one active writable run per workspace via `fcntl.flock`. Audits use a temporary index and `runs/<id>/objects` without writing `.git/`. Submodule internals and `.gitignore`-ignored files are excluded.
- **Model selection**: See [model selection](skills/peer-coworkers/references/model-selection.md) and [skill guide](skills/peer-coworkers/SKILL.md).
- **Development**: See [contributing](CONTRIBUTING.md). [MIT license](LICENSE); [workflow attribution](NOTICE).
