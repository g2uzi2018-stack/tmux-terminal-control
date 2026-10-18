# Bounded task contract

Scripts are relative to this skill. Entry point: `python3 scripts/cowork.py`.

`init --cwd ABS_GIT_ROOT --goal TEXT --role ROLE --acceptance TEXT` creates a private run directory. Roles are implement/test/review/research. Write roles require repeatable `--owned-path`; read-only roles have no owned paths. Optional arguments: `--profile`, `--model`, `--budget-seconds` (600), `--max-replies` (2), `--runs-dir`, explicit `--enable-opencode`.

The normal flow is `init → start → screen → paste → screen → submit --received-confirmed → wait → collect → accept --evidence TEXT → close`. All commands after init take `--run RUN`. Start supports `--no-proxy` or `--proxy-url URL`. Wait defaults to 25 seconds and returns one of `result_ready/question/approval/exited/attention/timeout`. Observe resumes the lower terminal observation without Enter. Neither quiet output nor exit implies a completed task.

Workers read the entire private `prompt.txt`, execute only their bounded contract, and publish current-round JSON atomically: write a temporary file in the run directory and rename it to the named control file. They may write owned artifacts and result/question control files, including atomic temporary files. They do not edit `task.json`, prompts, replies or old archives, delegate, commit, stage, change branches or CLI permissions.

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
