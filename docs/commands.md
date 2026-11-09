# Command reference

Run commands through `python3 skills/peer-coworkers/scripts/cowork.py`. Successful observations return JSON, including timeouts. Command errors exit 1 and argument errors exit 2.

| Command | Arguments and behavior |
| --- | --- |
| `doctor` | Report installed versions and stored capabilities. `--probe --profile P [--no-proxy]` additionally runs live checks. |
| `init` | `--cwd ABS --profile P --goal TEXT --acceptance TEXT`. Repeat acceptance and `--owned-path` as needed. Optional `--role LABEL`, `--model ID`, `--runs-dir DIR`, and `--enable-opencode`. Time limits in seconds are `--budget-seconds` (2700), `--startup-budget-seconds` (300) and `--approval-budget-seconds` (300 grace, 0 disables). |
| `start` | `--run RUN [--no-proxy \| --proxy-url URL]`. Start one exact marked tmux session and take a workspace lease. |
| `show`, `screen` | `--run RUN`. View task metadata or the current pane and screen hash. |
| `trust` | `--run RUN --screen-sha256 HASH --evidence TEXT`. Confirm the observed startup trust card once. |
| `paste`, `submit` | `--run RUN`. Paste the pointer, inspect its receipt, then use `submit --received-confirmed` once. |
| `wait` | `--run RUN [--timeout-ms N]` (25 seconds by default). Reports a result, question, approval, queued reply, exit, attention, expired budget or timeout. `observe` resumes the lower-level terminal observation. |
| `decision`, `inspect-diff` | `--run RUN --approval-id ID`. Decision also takes `--decision allow-once\|deny --evidence TEXT`. Inspect-diff opens the agy viewer and returns a fresh approval token. |
| `reply`, `steer` | `--run RUN`. Reply takes `--message-file FILE` (UTF-8, up to 32 KiB). Cursor steer takes `--steer-id ID --evidence TEXT` for the observed queued item. |
| `collect`, `accept` | `--run RUN`. Collect checks current handoff and Git scope. Accept rechecks the collected bytes and workspace and requires `--evidence TEXT`. |
| `close` | `--run RUN [--allow-active] [--discard-unaccepted]`. Releases the exact session and lease. |
| `keys`, `cancel` | `--run RUN`. Keys accepts repeatable `--key K` from the allowlist, which excludes submit keys. Cancel sends one Escape with a passing current cancellation probe. |
| `reap` | Report leases and reclaim confirmed gone sessions. Unknown records require exact `--task ID --force` for removal. |
| `probe` | `--profile P [--model ID] [--cwd ABS] [--timeout-ms N] [--budget-seconds N]`. Runs real CLI checks with 25 seconds per check and 240 seconds total by default. May incur usage. |
| `term` | `screen`, `history`, `status`, `paste`, `submit`, `wait`, or `keys`, with the same `--run RUN` and command options. |

See [CLI configuration](../skills/peer-coworkers/references/cli-profiles.md) and [terminal interactions](../skills/peer-coworkers/references/terminal-control.md).
