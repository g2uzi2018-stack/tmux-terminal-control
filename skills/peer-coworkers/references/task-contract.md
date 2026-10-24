# Bounded task contract

Scripts are relative to this skill. Entry point: `python3 scripts/cowork.py`.

`init --cwd ABS_GIT_ROOT --goal TEXT --role ROLE --profile PROFILE --acceptance TEXT` creates a private run directory. Roles are implement/test/review/research. Write roles require repeatable `--owned-path`; read-only roles have no owned paths. Select the requested profile/model explicitly. Arguments include `--model`, `--budget-seconds` (600), `--startup-budget-seconds` (300), `--approval-budget-seconds` (300; zero disables grace), `--max-replies` (2), `--runs-dir`, explicit `--enable-opencode`.

`--profile` is mandatory; choose it using [model selection](model-selection.md) rather than inheriting an implicit Codex default. `--model` binds only this task; when omitted, preserve the profile or CLI default. Use an exact current CLI model ID, at most 200 characters; bracketed parameter expressions are unsupported. There is no generic `--effort` or Fast switch. Default to standard speed unless explicitly requested otherwise and verify any separate session setting. Record actual model/effort/speed and unknown values in the primary's work record, not as extra result-envelope fields. Never silently substitute a requested model or alter global settings.

The normal flow is `init → start → screen → paste → screen → submit --received-confirmed → wait → collect → accept --evidence TEXT → close`. All commands after init take `--run RUN`. Start supports `--no-proxy` or `--proxy-url URL` and records the current executable version and matching-probe warnings. Wait defaults to 25 seconds and returns one of `worker_ready/result_ready/question/approval/exited/attention/timeout/budget_exhausted`. Observe resumes the lower terminal observation without Enter. Neither quiet output nor exit implies a completed task.

New tasks have a separate startup budget. Work time starts immediately before the first submission (including an uncertain submission), never resets on reply, and excludes at most the configured grace for observed approval waiting. Unobserved time is not retrospectively classified. Approval waiting cannot extend execution indefinitely. `show`, `submit`, `observe` and `wait` return budget details. Older records without `budget_origin=submission` retain their launch-based deadline.

Workers read the entire private `prompt.txt`, then first atomically publish `ready.json` with exactly `task_id`, `attempt_id`, current integer `round`, and `STATUS: "READY"`. This proves control-file access before substantive work. `wait` reports `worker_ready` once per round; stale/invalid/symlink receipts do not count. A valid final result can supersede the receipt. If writing is refused, workers stop and report the restriction in the terminal; the primary inspects access instead of waiting through the whole budget. Workers save owned drafts early, execute only their bounded contract, and publish current-round JSON atomically: write a temporary file in the run directory and rename it to the named control file. They may write owned artifacts and result/question/ready control files, including atomic temporary files. They do not edit `task.json`, prompts, replies or old archives, delegate, commit, stage, change branches or CLI permissions.

Prefer direct file tools. If those cannot atomically rename, permit a narrow local command that only publishes this run's control files, under ordinary CLI approval. A blanket shell ban can conflict with the publication contract; do not ask a worker to satisfy both when its tools lack rename support.

For a recognized agy command dialog, `wait` returns `approval_id`, `screen_sha256`, exact command and allowed decisions under `approval`. Inspect the action and existing authorization, then call `decision --run RUN --approval-id ID --screen-sha256 HASH --decision allow-once|deny --evidence TEXT`. The command rechecks the whole screen, selects only the one-time or deny option, persists uncertainty before navigation, confirms the changed selection, and submits once. A changed screen, unsupported layout, blank evidence or previously attempted decision is refused. Recognition is advisory and does not certify CLI compatibility or grant authorization. Uncertain decisions require inspection, never an Enter retry. Replies are refused while a known approval is waiting/uncertain.

Collapsed commands (`command_fully_visible=false`) cannot be allowed. For the observed menu, `keys --run RUN --key C-g` opens the full command editor without approving or editing it; then `wait` returns a new token/hash for that complete expanded screen. Read the entire command and call `decision` with the new token. It returns to the numbered menu with Escape, checks the visible command prefix, verifies selection, and sends the sole Enter there. If the full command is still clipped/scrolled, inspection remains manual and scripted allowance is refused. Never confirm the editable permission field with Enter as a shortcut.

Result envelope, with actual IDs from the task:

```json
{
  "task_id": "TASK",
  "attempt_id": "ATTEMPT",
  "round": 0,
  "handoff": {
    "STATUS": "DONE",
    "RESULT": [],
    "EVIDENCE": [],
    "VALIDATION": [],
    "REMAINING_WORK": [],
    "RISKS": []
  }
}
```

Exact fields only. STATUS is DONE/PARTIAL/BLOCKED. Each other handoff field is an array of up to 12 nonblank strings, each at most 2000 characters. Compact handoff JSON must fit 8 KiB and the complete file must fit 16 KiB. DONE requires no remaining work; PARTIAL/BLOCKED require concrete remaining work. Duplicate fields, stale IDs/rounds, boolean rounds, nonregular files and symlinks are rejected.

For a question, atomically publish `question.json` in the run directory:

```json
{
  "task_id": "TASK",
  "attempt_id": "ATTEMPT",
  "round": 0,
  "QUESTION": "Which interface should this change use?",
  "OPTIONS": ["A", "B"],
  "BLOCKING": true
}
```

Question files use the same 16 KiB/no-duplicate/no-symlink rules. QUESTION is nonblank and at most 2000 characters; OPTIONS has the same per-array/string limits as the handoff; BLOCKING is boolean. Wait returns the validated question and records `awaiting_reply`, while preserving an existing `cancelling` state. Cancellation delivery is recorded independently of mutable task state, so a leftover question cannot cause another Escape in the same round.

`reply --message-file F` accepts a regular no-follow UTF-8 file up to 32 KiB. It persists `reply_uncertain`, increments round, archives prior control files as `result.round<N>.json` and `question.round<N>.json`, writes private `reply-<N>.md` with the new contract, pastes a short pointer, verifies literal screen receipt, then sends exactly one Enter. Failure at any stage is not retried. Max replies defaults to two; exceeding it requires a new task. The current task/attempt/round must match in wait, collect and accept.

`collect` checks owned-path drift plus HEAD/branch/index changes. DONE awaits independent acceptance. `accept` rechecks both current result and current artifacts; evidence must describe actual independent validation. Snapshots exclude Git-ignored untracked files and paths outside the worktree; these exclusions appear in the prompt and collection report for independent inspection. Scope checks are contracts, not access controls.

`close [--allow-active]` verifies exact session identity and releases its persistent lease. A confirmed missing session reports `session_gone=true`. Unconfirmed launch records cannot be reclaimed automatically. `reap` reports active/gone/unknown leases; unknown records require `reap --task ID --force`. Locks retry briefly; lock contention leaves sessions intact.
