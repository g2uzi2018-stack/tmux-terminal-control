# CLI profiles and configuration

Use `cowork.py doctor` to check executables and versions. `probe --profile PROFILE` runs live capability checks when needed. Executable discovery, account access and task success are separate observations.

| Profile | Default launch |
| --- | --- |
| codex | `codex --no-alt-screen --sandbox workspace-write` |
| agy | `agy --sandbox` |
| cursor | `cursor-agent --sandbox enabled` (also discovers `agent`) |
| opencode | Compatibility profile, requires `--enable-opencode` |

Cursor uses a task-private copy of `cli-config.json` via `CURSOR_CONFIG_DIR`. The copy preserves existing settings and permissions while task model selection can persist inside that copy. Use the current CLI's exact model ID. Cursor also accepts a parameter expression when supported by the current CLI and model.

Optional JSON configuration lives at `${XDG_CONFIG_HOME:-~/.config}/peer-coworkers/config.json` or `PEER_CONFIG`.

- `runs_dir` sets private storage outside the workspace. Default is `/tmp/peer-coworkers-<uid>/runs`. Verify sandbox access when changing the location.
- `proxy.mode` is auto, command, url, or off. Auto uses an available interactive Bash `proxy_on`; command mode uses trusted local Bash code; URL mode takes a credential-free HTTP(S) endpoint. `start --no-proxy` keeps the inherited environment without setup.
- `profiles.PROFILE` accepts `path`, `model`, `approval_patterns`, `prompt_lines`, `cancel_lines` and `busy_regex`. Explicit patterns report possible prompts. Without configuration, a matching passing probe can supply patterns. Built-in observed cards have separate recognition.
- `snapshot` limits are `max_files` (50000), `max_bytes` (268435456) and `max_record_bytes` (67108864).

Use an isolated clone with its own Git metadata if a CLI sandbox cannot read a linked worktree's metadata.
