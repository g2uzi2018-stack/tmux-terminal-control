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

The task-level wait adds validated current-round result/question/ready events and 120 ms final-result stability. Only result validation starts task acceptance; still/prompt/attention/exit are not completion claims. For `approval`, inspect the exact action and existing authorization, then use `cowork.py decision --run RUN --approval-id ID --screen-sha256 HASH --decision allow-once|deny --evidence TEXT` for a supported agy command or file-edit menu. The token/hash come from observation, not a guessed screen. Navigation and the single submission are audited together; do not replace this with raw arrows and Enter. An uncertain attempt cannot be rearmed by footer changes. Other menus remain manual inspection cases. Tests or probes never approve on behalf of the user.

File-edit cards report `path`, `diff`, `diff_sha256` and `diff_fully_visible`. Inspect these before a one-time acceptance. The visible additions/deletions must match the header counts; clipped/hidden patches cannot be accepted through `decision`. The task's owned paths and permitted current control files are rechecked before acceptance, including symlink resolution. `terminal-events.json` saves bounded observations, pre-decision screens and the final screen before closing so a stalled edit can be diagnosed later.

If a long patch scrolls `Pending edit` or the file header entirely out of the viewport, the strict recognizer may return timeout instead of approval. Inspect `screen`/`history` and the full diff manually; never infer permission from a quiet/busy footer. Diagnostic history or final screen capture errors are reported but do not prevent observation or exact-session cleanup.

If the command body is collapsed, use the observed `C-g` expansion key and `wait` again. Only a fully visible Full Command section supplies an expanded-review token. After explicit review, `decision` backs out with Escape without editing permissions, confirms the numbered menu, and performs the single one-time/deny selection. It refuses hidden content or a changed prefix; do not press Enter inside the editable permission editor.
