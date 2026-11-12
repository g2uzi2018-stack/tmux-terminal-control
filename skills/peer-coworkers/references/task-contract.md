# Work package and handoff

Give the worker the goal, known inputs, expected artifact, and acceptance criteria. List writable workspace paths with repeatable `--owned-path` or omit them for a read-only workspace. Every worker can write its current handoff. The CLI sandbox controls access. The primary checks changes in tracked and nonignored untracked files, HEAD, branch and index. Inspect relevant ignored or external artifacts separately.

Multiple read-only packages may share a workspace. Startup serializes the lease check and session creation, waiting up to 30 seconds for the workspace lock. Wait for each `start` command to finish, including a command that returns a process/session handle while still running. After a lock timeout, inspect `show`. Retry `start` only when that attempt failed before launch and the task is still `prepared` without a recorded session or lease. A `launch_uncertain` task requires inspection of its exact session and lease before recovery.

Read the task from the private `prompt.txt`. Deliver one UTF-8 Markdown file at the requested path (up to 1 MiB). Start it with `DONE`, `PARTIAL`, `BLOCKED`, or `QUESTION` on its own line, then explain the outcome and give evidence, remaining work or the question as appropriate. Publish the finished file in one write or rename its exact `.tmp` file. A finished review can be `DONE` with findings requiring changes. State the assessment in the report.

Use `reply --message-file FILE` to answer or refine a task. It sends one pointer after checking literal receipt and allocates a fresh handoff path. Previous handoffs stay readable at their original paths. Wait for a handoff from existing feedback before sending more. Queue visibility is advisory. If the earlier work must stop before the feedback takes effect, close or use verified cancellation and create a fresh task.

Work defaults to 2700 seconds from first submission, with a separate 300-second startup budget and up to 300 seconds of grace for observed approvals. Feedback keeps the original budget. An uncertain submit or reply is resolved only when the tool finds a valid handoff at the current path. Inspect uncertainty without repeating input.

`wait` reports the handoff path, which you can read directly. `collect` checks the workspace scope. For `DONE`, independently inspect the report and real artifacts before `accept --evidence TEXT`. Acceptance checks the collected handoff bytes and workspace again. `close` needs `--allow-active` for a live CLI. To abandon an unaccepted `DONE`, use `--discard-unaccepted` explicitly.

Closed runs from older releases remain readable via `show` and `collect`. Use their original tool version for any legacy run still in progress.
