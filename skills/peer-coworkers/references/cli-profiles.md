# CLI profiles and configuration

Use `python3 scripts/cowork.py doctor` to see executable availability, versions, latest probe capabilities and upgrade warnings. Availability is separate from authentication and behavioral compatibility. Use the existing login and CLI default model, or an explicit task/profile model; never silently substitute one.

Separate channel compatibility from model selection. Before first assignment, read [model selection](model-selection.md), compare suitable candidates and explicitly choose `--profile`. The inventory and dated historical machine records are discovery evidence, not current task-quality guarantees; resolve this machine's versions, paths and proxy configuration rather than copying old values.

| Profile | Launch arguments | Discovery |
| --- | --- | --- |
| codex | `--no-alt-screen --sandbox workspace-write` | `codex` |
| agy | `--sandbox` | `agy` |
| cursor | `--sandbox enabled` | `cursor-agent`, then `agent`; never the editor executable |
| opencode | compatibility only, disabled | `opencode`, only with explicit enable flag |

Configuration is JSON at `${XDG_CONFIG_HOME:-~/.config}/peer-coworkers/config.json`. `PEER_CONFIG` selects a different file. Optional keys:

- `runs_dir`: absolute directory outside the worktree. Default is private `/tmp/peer-coworkers-<uid>/runs`; verify custom locations through the worker sandbox.
- `proxy`: `mode` is auto/command/url/off. Auto calls interactive Bash's `proxy_on` when present, reports absence, and aborts launch on command failure. Command mode uses trusted local `command` Bash code. URL mode uses a credential-free HTTP(S) `url`. Start's `--proxy-url` selects URL mode; `--no-proxy` disables setup and retains inherited environment.
- `profiles.PROFILE`: absolute executable `path`, default `model`, user `approval_patterns`, positive `prompt_lines`/`cancel_lines`, and `busy_regex`. Omit explicit approval patterns to inherit a passing version-matched probe. User-supplied patterns are recognition rules, not compatibility evidence or authorization.
- `snapshot`: positive `max_files` (50000), `max_bytes` (268435456), and `max_record_bytes` (67108864). Task reads and atomic writes share the record bound; oversized updates preserve the previous readable record. Raise it for larger metadata requirements. Result/question files retain their separate 16 KiB bounds.

Tasks store actual proxy mode/command outcome/configured URL. Probe compares requested proxy variables to `/proc/PANE_PID/environ` rather than relying on tmux's environment display. It does not print inherited credentials.

`probe --profile P [--model M]` runs nine bounded interactive checks with sandbox flags retained and no approval replies. Defaults: 25 seconds per check, 240 seconds total. Reports are saved in the persistent state directory; raw terminal and nonce-file evidence stays in the private runs directory. Timeout, blocked, failed, unverified and passed are distinct. Later checks still run after a failure.

General approval regex recognition defaults to empty without explicit configuration or a passing current-version probe. Separately, task observation recognizes the complete observed agy numbered command dialog (request heading, question, all four choices, selected item and CLI footer) as an advisory `approval`, even without a matching probe. It is labeled `compatibility_verified=false`; it does not enable cancellation or authorize the command. Explicit `decision` binds a one-time allowance or denial to that exact screen and requires authorization evidence. Persistent allowances and automatic approval loops are not offered. Other layouts require inspection; configured regex recognition alone does not enable scripted decisions.

The observed agy1.4.9 two-choice file-edit card is also recognized separately from shell commands. Decisions bind the exact screen/path/diff; accepting a clipped patch or an edit outside task ownership/current control files is refused. Unrecognized layouts remain manual inspection cases. This narrow support is not a passing full CLI probe. When Git worktrees refer to metadata outside the sandbox, verify Git visibility before substantive work; an isolated clone with its own `.git` is a candidate remedy without broadening permissions.

Probe uses separately identified candidate patterns, including an eight-line region for agy's file-creation prompt. Candidate syntax alone is not a pass. Cancellation still requires a passing probe for the exact current executable/version; an upgrade disables it until retested. There are no Enter retries. Use private temporary control directories by default and verify `worker_ready` before assigning substantial work; listing models is not a launch or a write-capability test.

Dated actual compatibility records belong in repository `docs/cli-profiles.md` and `docs/local/`, not in reusable skill instructions. Fake terminal tests establish tool behavior only.
