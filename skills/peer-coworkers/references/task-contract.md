# Bounded task contract

Scripts are relative to this skill. Entry point: `python3 scripts/cowork.py`.

`init --cwd ABS_GIT_ROOT --goal TEXT --role ROLE --profile PROFILE --acceptance TEXT` creates a private run directory. Roles are implement/test/review/research. Write roles require repeatable `--owned-path`; read-only roles have no owned paths. Select the requested profile/model explicitly. Arguments include `--model`, `--budget-seconds` (600), `--startup-budget-seconds` (300), `--approval-budget-seconds` (300; zero disables grace), `--max-replies` (2), `--runs-dir`, explicit `--enable-opencode`.

`--profile` is mandatory; choose it using [model selection](model-selection.md) rather than inheriting an implicit Codex default. `--model` binds only this task; when omitted, preserve the profile or CLI default. Use an exact current CLI model ID, at most 200 characters; bracketed parameter expressions are unsupported. There is no generic `--effort` or Fast switch. Default to standard speed unless explicitly requested otherwise and verify any separate session setting. Record actual model/effort/speed and unknown values in the primary's work record, not as extra result-envelope fields. Never silently substitute a requested model or alter global settings.

The normal flow is `init → start → screen → paste → screen → submit --received-confirmed → wait → collect → accept --evidence TEXT → close`. All commands after init take `--run RUN`. Start supports `--no-proxy` or `--proxy-url URL` and records the current executable version and matching-probe warnings. Wait defaults to 25 seconds and returns one of `worker_ready/result_ready/question/approval/exited/attention/timeout/budget_exhausted`. Observe resumes the lower terminal observation without Enter. Neither quiet output nor exit implies a completed task.

New tasks have a separate startup budget. Work time starts immediately before the first submission (including an uncertain submission), never resets on reply, and excludes at most the configured grace for observed approval waiting. Unobserved time is not retrospectively classified. Approval waiting cannot extend execution indefinitely. `show`, `submit`, `observe` and `wait` return budget details. Older records without `budget_origin=submission` retain their launch-based deadline.

Workers read the entire private `prompt.txt`, then first atomically publish `ready.json` with exactly `task_id`, `attempt_id`, current integer `round`, and `STATUS: "READY"`. This proves control-file access before substantive work. `wait` reports `worker_ready` once per round; stale/invalid/symlink receipts do not count. A valid final result can supersede the receipt. If writing is refused, workers stop and report the restriction in the terminal; the primary inspects access instead of waiting through the whole budget. Workers save owned drafts early, execute only their bounded contract, and publish current-round JSON atomically: write a temporary file in the run directory and rename it to the named control file. They may write owned artifacts, result/question/ready control files and the current-round `report_path`, including atomic temporary files. They do not edit `task.json`, prompts, replies, old archives or prior-round reports, delegate, commit, stage, change branches or CLI permissions.

Prefer direct file tools. If those cannot atomically rename, permit a narrow local command that only publishes this run's control files, under ordinary CLI approval. A blanket shell ban can conflict with the publication contract; do not ask a worker to satisfy both when its tools lack rename support.

For a recognized agy command dialog, `wait` returns `approval_id`, `screen_sha256`, exact command and allowed decisions under `approval`. Inspect the action and existing authorization, then call `decision --run RUN --approval-id ID --screen-sha256 HASH --decision allow-once|deny --evidence TEXT`. The command rechecks the whole screen, selects only the one-time or deny option, persists uncertainty before navigation, confirms the changed selection, and submits once. A changed screen, unsupported layout, blank evidence or previously attempted decision is refused. Recognition is advisory and does not certify CLI compatibility or grant authorization. Uncertain decisions require inspection, never an Enter retry. Replies are refused while a known approval is waiting/uncertain.

The observed agy two-choice `Pending edit` / `Accept this file edit?` card uses the same `decision` flow. Its `agy_file_edit` dialog includes the absolute `path`, visible `diff`, `diff_sha256`, change counts and `diff_fully_visible`. Acceptance requires all changed lines to be visible and the resolved target to belong to an owned path or this run's ready/result/question JSON (including their `.tmp` files). Read-only roles may accept only those control files. Git metadata and old archives are not allowed targets. Incomplete diffs offer denial only; inspect the full diff manually rather than guessing an approval. File acceptance selects option1; rejection selects option2. Neither enables accept-edits or a persistent permission.

Each wait returns `terminal_events_path`. The private `terminal-events.json` retains at most16 distinct recent observations, each with task/attempt/round, timestamp, reason and at most32 KiB of screen text (explicitly marked when clipped). Decisions and the final screen before closing are also saved. This is local diagnostic evidence, not a completion signal. Only observed approval time earns bounded grace; observe promptly instead of treating unobserved waits as model computation.

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

Exact fields only. STATUS is DONE/PARTIAL/BLOCKED and describes the assigned work package. Each other handoff field is an array of up to 12 nonblank strings, each at most 2000 characters. Compact handoff JSON must fit 8192 bytes, measured with Python `json.dumps(handoff, ensure_ascii=False, separators=(',', ':')).encode('utf-8')`; the complete file must fit 16384 bytes. DONE requires no unfinished assigned work; PARTIAL/BLOCKED require concrete unfinished assigned work. Duplicate fields, stale IDs/rounds, boolean rounds, nonregular files and symlinks are rejected. Strict validation still applies to wait, collect and accept.

New review tasks (`result_contract_version=2` in `task.json`) require one additional top-level field, `"review_verdict": "PASS"`, `"CHANGES_REQUESTED"` or `"INCONCLUSIVE"`. Other roles retain exactly the envelope above. Legacy tasks without this contract version retain their original schema, including on reply. The six handoff fields remain unchanged.

A review can be `STATUS=DONE`, `review_verdict=CHANGES_REQUESTED`, `REMAINING_WORK=[]`: the assigned review is finished, but the reviewed code needs fixes. Put findings in RESULT and risks in RISKS. REMAINING_WORK lists unfinished review steps, not unassigned implementation fixes. `accept` on a review explicitly returns `accepted_subject=review_report` and its verdict (UNSPECIFIED for legacy reviews); it does not approve delivery of the reviewed code. A PASS verdict still requires independent primary validation.

For long reports, every role on a new task may atomically publish UTF-8 text to the run's `report.round<N>.md` (`report_path` in the current prompt/reply), using `report.round<N>.md.tmp` as its temporary file. Limit: 1 MiB. Keep the result envelope short and reference this path in EVIDENCE; do not truncate JSON or silently drop findings to meet the envelope limit. Collection automatically returns the report's path, byte count and SHA-256 if present. Acceptance rechecks that digest, including additions/deletions since collection. Reports remain in their original round; a reply grants only the new round's report path. The recognized file-edit approval permits only the current report and its `.tmp` alongside existing control-file targets.

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

`reply --message-file F` accepts a regular no-follow UTF-8 file up to 32 KiB. Prior regular control files need not be valid: oversized files, malformed JSON/UTF-8, duplicate keys, stale identities and invalid handoffs all remain correctable. It checks archive/reply-name collisions and unsafe file types before advancing state, persists `reply_uncertain`, increments round, and renames prior files unchanged to `result.round<N>.json`, `question.round<N>.json` and `ready.round<N>.json`. No truncation, JSON rewriting or unbounded reads occur. Bounded validation of the archived bytes supplies per-file validity/diagnostics in the intervention record and new reply; it never prevents correction. Symlinks, FIFOs and directories require inspection and are refused without following/reading them.

Reply then writes private `reply-<N>.md` with the current schema, byte limits, report path and correction message, pastes a short pointer, verifies literal screen receipt, then sends exactly one Enter. Archive/write/paste/receipt/submit failures after uncertainty is persisted are not retried; inspect the durable state. Existing archives are preserved. Max replies defaults to two; exceeding it requires a new task. Replies still require a live open task, available work budget and no waiting/uncertain approval; they never bypass permission menus or reset the budget. The current task/attempt/round must match in wait, collect and accept.

`collect` checks owned-path drift plus HEAD/branch/index changes. DONE awaits independent acceptance. `accept` rechecks both current result and current artifacts; evidence must describe actual independent validation. Snapshots exclude Git-ignored untracked files and paths outside the worktree; these exclusions appear in the prompt and collection report for independent inspection. Scope checks are contracts, not access controls.

`close [--allow-active]` verifies exact session identity and releases its persistent lease. A confirmed missing session reports `session_gone=true`. Unconfirmed launch records cannot be reclaimed automatically. `reap` reports active/gone/unknown leases; unknown records require `reap --task ID --force`. Locks retry briefly; lock contention leaves sessions intact.
