# Peer Coworkers

Run a bounded work package through an independent CLI in an isolated tmux session. The primary agent chooses work, inspects changes and tests, and accepts the result. The tool manages one task at a time; it does not schedule a team or merge worktrees.

Requires Linux/WSL, Python 3.9+, Git and tmux. Uses only the Python standard library. Install the single standalone skill:

```bash
python3 scripts/install-skill.py
python3 "${CODEX_HOME:-$HOME/.codex}/skills/peer-coworkers/scripts/cowork.py" doctor
```

The installer copies ordinary files, backs up an existing installation, preserves CLI configuration, and prints a SHA-256 fingerprint for the installed package. It only reports an old sibling skill directory; removal of an existing user installation is manual. Native Windows execution is not supported; run the scripts and CLI together inside WSL.

Codex, agy and Cursor Agent CLI have sandbox-preserving launch profiles. OpenCode requires explicit opt-in and is never a fallback. Executable availability does not establish authentication or compatibility.

Choose the profile and requested model for each work package. Verify model, reasoning effort and speed in the active session. See [model selection](skills/peer-coworkers/references/model-selection.md).

Start with the [quick start](docs/quick-start.md). See the [command reference](docs/commands.md), [state machine](docs/state-machine.md), [scope and risk boundaries](docs/boundaries.md), [configuration example](config.example.json), and [contribution guide](CONTRIBUTING.md).

Workers deliver a Markdown handoff for implementation, research, testing or review. Feedback assigns a new handoff path and keeps earlier files available. See the [work package contract](skills/peer-coworkers/references/task-contract.md).

The repository does not retain test source code or fixtures. Runtime compatibility probes remain available through the `probe` command and are opt-in. Historical results and limitations are dated in [hardening validation](docs/hardening-validation.md) and [CLI profiles](docs/cli-profiles.md). [Reviewed evidence summaries](docs/evidence/README.md) are committed; raw screens and machine-specific history stay in ignored [local records](docs/local/README.md).

[MIT license](LICENSE). Workflow attribution: [NOTICE](NOTICE).
