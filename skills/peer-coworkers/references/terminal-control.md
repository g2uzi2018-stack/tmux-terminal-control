# Terminal operations

Prefer task-bound `cowork.py term screen/history/status/paste/submit/wait/keys --run RUN`. These commands resolve the recorded socket and pane and retain task state and audit rules. History uses `capture-pane -p -S -`; the current viewport is not the whole answer.

The lower-level scripts are included as ordinary files for terminal diagnostics. Use explicit simple `ai-tui-...` socket names and `%NUMBER` pane IDs. A separate socket and marked session belong to each work package. The owner marker is `peer-coworkers/v2`, with task and cwd markers checked before cleanup.

```text
session.py new --task TASK --cwd ABS -- /absolute/program arg ...
session.py list
session.py cleanup --socket SOCKET --session cli --task TASK [--allow-active]
session.py prune --socket SOCKET
input.py paste --socket SOCKET --pane %0 [--multiline-verified EVIDENCE]
input.py keys --socket SOCKET --pane %0 --key Escape
input.py submit --socket SOCKET --pane %0 --received-confirmed
```

UTF-8 paste comes through stdin. It loads a unique buffer and uses `paste-buffer -p -r -d`, never adds Enter, and cleans only that buffer on failure. Any LF/CR requires actual target/version/interface multiline evidence before sending. A collapsed paste widget alone does not prove literal receipt. Do not transform text into shell code or flatten multiline content.

Observe focus, paste, read the actual input, submit once, then observe the result. The submit key set is Enter/C-j/C-m; the general key allowlist excludes these. Other keys include Escape, Tab, navigation/editing keys and permitted control keys. Key meanings depend on the active UI. Do not assume Ctrl+C cancels generation without exiting.

```text
wait.py submit-and-wait --socket SOCKET --pane %0 --received-confirmed --timeout-ms 20000 --shell-timeout-ms 30000
wait.py begin --socket SOCKET --pane %0 --timeout-ms 20000 --shell-timeout-ms 30000
wait.py resume --socket SOCKET --pane %0 --timeout-ms 20000 --shell-timeout-ms 30000
```

Lower-level wait stores its baseline in pane options. Begin establishes a new observation without submission; resume preserves the current round and never resends Enter. Options include `--poll-ms`, `--still-ms`, `--prompt-lines`, repeated `--prompt LABEL=REGEX`, `--busy-regex`, `--no-screen`. Regex searches share the deadline; invalid/warning-producing expressions fail before submission. Prompt patterns apply line by line to the last physical rows after removing trailing blank rows, with old full-baseline matches excluded. Busy patterns suppress quiet-screen candidates.

The first output line is `reason=prompt|still|exited|timeout|error elapsed_ms=N changed=0|1`, optionally with `match=LABEL` or numeric `exit_code=N`; afterward comes at most one screen. Exit codes: events 0, timeout 3, error 1. A pane can close its PTY before tmux reaps its exit status; status queries retry within a short bounded window. On Linux, a proven zombie may be re-notified to its exact owned tmux parent so native wait status can be published; generic sockets and live children are excluded. Signal exits may have no numeric code. Missing panes and capture failures remain errors.

Cleanup requires exact owner/task/cwd markers; active sessions require explicit authorization through `--allow-active`. Prune accepts one exact owned socket and removes it only after ConnectionRefused and unchanged inode checks. Live sockets, unknown owners, arbitrary names and broad cleanup are refused. Never clean by prefix or use an unscoped server-kill command.

The task-level wait adds validated current-round result/question events and 120 ms JSON stability. Only result validation starts task acceptance; still/prompt/attention/exit are not completion claims. All approval-related interactions require reading the exact action and existing user authorization. Tests or probes never approve on behalf of the user.
