# Hardening validation — 2026-10-18

The latest precommit suite passed **170 tests in 53.577 seconds, zero skips**, independently run by the primary agent with `python3 -m unittest discover -s tests`. [Full output](test-results.txt). This includes all 113 tests present at the WP0 handoff, migrated to the single skill, plus the hardening regressions. The implementation handoff had passed 166 cases before independent review and the repairs below. Implementation and review used separate peer CLI processes; worker CLI permissions were preserved.

## Installation, updated CLI and publication

At the user's request, `python3 scripts/install-skill.py` installed the new skill
into the default user skill directory and backed up the previous installation.
All 22 source package files match the installed files; there are no symlinks and
the installed `cowork.py --help` exits 0. The installer preserved and reported the
legacy sibling directory. [Installation checks](install-validation.json).

The installed entry point ran `probe --profile agy --timeout-ms 90000
--budget-seconds 540` against **agy 1.4.2**, retaining `--sandbox` and automatic
proxy setup. Paste, single-line, multiline, 150-line history and precise cleanup
passed. Readiness was unverified because literal input was not visible; no Enter
was sent in that check. Cancellation, approval recognition and atomic result
writing encountered human permission gates and remained blocked; no approval or
Escape was sent. Every check cleaned up without errors. [Updated probe summary](evidence/probe-agy-1.4.2.json).

The installed doctor now matches the current agy executable/version and its new
report, so the old upgrade warning is resolved. It still withholds cancellation
and approval capabilities because those checks did not pass. [Updated doctor](evidence/doctor-after-install.json).

Raw CLI screens, account details, machine paths and historical transcripts remain
on the local machine in ignored `docs/local/`; only its README is committed.
Reviewed field-limited summaries are committed under `docs/evidence/`, and public
documentation links to those summaries. Process IDs in reaper summaries are
anonymized. The raw files were preserved. [Evidence policy](evidence/README.md).

## Independent review and repairs

A fresh read-only CLI process reviewed the plan and final source. Its collected scope report had no changed paths. It independently reproduced two P1 defects: a 10,000-file task became unreadable after collection exceeded the old 4 MiB task-record cap, and observing a leftover question reset cancellation state and permitted another Escape. [Original review evidence](evidence/independent-review.json).

Task record reads and atomic writes now share a configurable `snapshot.max_record_bytes` limit (64 MiB by default). An oversized update fails before replacement, preserving the previous readable task. A real 10,000-file prepare/collect/reload/accept regression and a configured write-limit/recovery regression pass. Result and question bounds remain 16 KiB.

Question observation preserves `cancelling`; cancellation also checks its persisted current-round intervention, independently of the mutable state. The real-tmux regression observes a leftover question, reloads the task, deliberately changes its state, calls cancel again, and proves only one Escape was sent.

The primary also reproduced stale proxy inheritance after a successful proxy command unset its environment variables. Command environment capture now represents removals explicitly, launch applies both sets and removals, and probe compares absent variables correctly. A real-pane regression proves all eight inherited proxy variables are absent in the worker and restored in the parent after launch. Default status tests no longer rewrite repository evidence files.

The targeted repair run passed 111 tests in 23.742 seconds; the subsequent complete run passed all 170. A new temporary standalone install still contained all 16 modules, no symlinks, and an installed entry point whose `--help` exited 0. Previously recorded real-CLI limitations below remain applicable.

A second fresh CLI process performed the bounded incremental review and confirmed no remaining defect in these repairs. It independently passed the large-record tests, real Bash removal capture, restoration on exception, persisted cancellation fencing after state changes, and probe absence comparison; its repository scope report was empty. It correctly delivered PARTIAL because its sandbox denied six real-tmux tests. [Incremental review](evidence/incremental-review.json).

The primary closed that environment gap with a separate permitted real-tmux run: `PYTHONPATH=tests python3 -m unittest -v test_config.ConfigTests.test_proxy_command_removals_reach_real_pane_and_parent_is_restored test_interactions.InteractionTests.test_question_cannot_rearm_single_attempt_cancellation test_status.RealReaperTests`. **All six tests passed in 16.455 seconds**. [Named test output](review-recheck.txt). The direct-launch check observed 17 pending native statuses and 17 exact-server notifications, followed by all 40 correct native exit codes. All three peer CLI sessions were closed and their precise stale sockets pruned; their private run records remain available for diagnosis.

| Package | Implementation and targeted evidence |
| --- | --- |
| WP0 | Preserved and completed the initial uncommitted module split. Removed the old skill and materialized all scripts. `cowork.py` parses/dispatches; lifecycle logic is in `tasks.py`, alongside records, leases, snapshots, configuration, results, observations, interactions and probes. Original 113 tests passed before continuing. |
| WP1 | Short-retry locks, confirmed-dead close/reap/start recovery, conservative corrupt/missing/unconfirmed leases, identity checks before cleanup. Nine focused real-tmux lease tests passed, including a live empty server whose socket must not be pruned. |
| WP2 | Opaque submodules, surrogate-escaped paths, FIFO/socket type records, stat-based regular-file hash reuse, configurable file/byte caps and adjustment errors. Tests cover init/collect/accept with a dirty submodule and non-UTF-8 path, special files, changed content and caching. The 1501-file benchmark measured 0.0400 s full and 0.0299 s cached; no performance threshold is asserted. |
| WP3 | Current-round JSON events, a 120 ms stability window, question/approval/exit/attention/timeout observations, bounded regex and version queries, shared observe patterns. Tests include half-written and duplicate JSON, stale rounds, remaining question files and disappeared sessions. |
| WP4 | Audited keys, one-Escape cancellation with verified capability gating, reply uncertainty before side effects, literal receipt before one Enter, private reply files, round archives and max-reply enforcement. Real tmux fixtures verify successful replies, failed submission without replay, questions, supported cancellation and observation without a second Escape. |
| WP5 | Bounded JSON configuration, model binding, auto/command/url/off proxy modes, CLI flag precedence and failure-before-launch. Tests exercise missing config/function, real command success/failure, actual pane proxy environment, and configurable limits. |
| WP6 | All nine probe checks execute behavior independently. Negative fixtures reject prompt echo, partial long output, a false interrupted label and a forged heartbeat. Actual heartbeat identity/progress, response tokens, nonce-file content, all 150 lines and same-server cleanup are required. Doctor compares executable/version and disables stale capabilities; corrupted reports only warn. |
| WP7 | README split into quick start, commands, states and boundaries; concise skill and generic references; local history moved under `docs/local/`; MIT license, attribution, example configuration and contribution guidance added. |

The outer execution sandbox rejects tmux Unix socket operations with `Operation not permitted`. Real tmux tests therefore used separately approved outer execution; worker CLI sandbox flags were retained. Missing dependencies are failures. Opt-in live modules are outside default discovery, so the default suite contains no skipped live tests.

## WP0 sandbox experiment

Command: `PEER_LIVE=1 python3 -m unittest discover -s tests -p live_experiments.py -v`. Each attempt had a **120-second** limit. Actual unique paths under the user state directory (outside both cwd and `/tmp`) were compared with `/tmp` paths. Codex 0.163.0 used `exec --sandbox workspace-write --ephemeral`; Cursor 2026.10.16-e3cb207 used `--sandbox enabled --print`. Both refused/rejected the state target and both wrote the expected unpredictable nonce under `/tmp`. No approvals were answered. These are observed refusals/tool rejections, not proof that both reached a kernel-denied syscall. [Reviewed outcome summary](evidence/wp0-sandbox-experiment.json).

Default runs therefore use private `/tmp/peer-coworkers-<uid>/runs`. Leases and reports remain in persistent user state. Temporary evidence can be removed by OS cleanup/reboot; a custom run directory requires fresh worker-sandbox verification. Noninteractive writing does not establish interactive approval behavior.

## Exit-status investigation

The final fix obtains **actual native tmux exit status**, rather than inventing a value for a closed pane. In the initial 80-case failed-launch reproduction, 20 panes closed their PTYs without a published numeric status. Further `/proc` observations showed exited zombie children still parented by their exact tmux servers. An exec-start gate did not eliminate this and was removed. [Original observations](evidence/reaper-diagnosis-before.json), [failed gated investigation](evidence/reaper-diagnosis-gated.json).

Independent main-agent evidence also reproduced missing status in 2 of 40 direct new-session launches with remain-on-exit set before creation and no respawn. Respawn is therefore not required to trigger the issue. A focused regression now launches Python directly in 40 fresh sessions, with no placeholder, respawn or wait-for gate. In that run, 10 native statuses were still missing after 500 ms; exactly 10 verified-zombie notifications were sent, and all 40 subsequently exposed native exit code 1. The eight focused status tests passed in 12.650 seconds. [Focused direct-launch proof](evidence/reaper-direct-launch-focused.json); the [latest full-suite direct-launch samples](evidence/reaper-direct-launch.json) are retained separately. The final full-suite run independently observed 12 pending native statuses and 12 exact-server notifications; again all 40 native statuses were 1. No CLI compatibility retests were added for this follow-up.

The status helper retries briefly. When status is still missing, it verifies an `ai-tui-` target, both process owners, zombie state, the exact child-to-server parent relation and tmux process identity, then sends that server one `SIGCHLD` notification per status call. It never signals the worker or a generic socket. This asks tmux to reap its own already-exited child and publish the real status. tmux's [format callbacks](https://github.com/tmux/tmux/blob/3.4/format.c) distinguish PTY closure from a ready wait status; its [SIGCHLD handler](https://github.com/tmux/tmux/blob/3.4/server.c) publishes the outcome returned by `waitpid`.

The same command, `python3 -m unittest discover -s tests -p reaper_diagnosis.py -v`, now passed all 80 cases in 19.848 seconds, with native exit code 1 and the real interpreter error in every case. [Reviewed final status transitions](evidence/reaper-diagnosis.json). Default tests additionally repeat 40 direct new-session launches, 20 failed launches and 90 ordinary exits, check the native numeric result, and ensure generic sockets/live children are never notified. The original failed-start assertion still checks tmux's native status equals 1 after observation. Signal exits retain no invented numeric code; pending outcomes remain bounded observations.

## Actual CLI probes and remaining limits

Five actual interactive probe runs were recorded: Cursor initial/retest, agy initial/longer retest, and Codex. Commands and per-capability outcomes are in [CLI profiles](cli-profiles.md). The longer Codex and agy runs allowed 90 seconds per check, 540 total. Later checks ran despite earlier failures. No approval was sent and each check submitted at most once.

Codex passed input, multiline, nonce writing, 150-line recovery and exact cleanup. Escape interrupted the conversation while a background tool remained active, so cancellation was not enabled. No approval prompt appeared for the refused state-directory write. Cursor passed actual cancellation and approval recognition; its initial multiline result passed but its latest computation was wrong and timed out. agy passed the eight-line file prompt and longer output recovery; command approvals blocked cancellation and result writing and were left unanswered. These limitations are preserved, not converted into passes.

Before the installed retest above, `doctor` observed **agy 1.4.2** while the probe was for **1.4.0**. It warned that the upgrade had not been retested and did not reuse that version's capabilities. [Historical doctor output](evidence/doctor.json). Codex and Cursor reports matched their reported versions; OpenCode was not executed.

## Install and static checks

A standalone install in a private temporary directory contained zero symlinks, all 16 modules, LICENSE and NOTICE; installed `cowork.py --help` exited 0. [Install evidence](install-validation.json). Installer tests also verified recoverable replacement and preservation/notice for an old sibling installation. The user's live installation was subsequently updated as recorded above.

`python3 -m compileall -q skills tests`, `git diff --check`, and source-tree symlink inspection passed after the final changes. Personal paths, the previous local proxy port and proxy-wrapper commands are confined to `docs/local/`. The legacy directory name remains only in the required installer preservation notice and its regression test; there is no old runtime skill or session marker.

Scope checking remains a contract, not a sandbox. Ignored Python caches and paths outside the worktree are excluded. The primary must independently verify relevant excluded artifacts, including the state-directory reports and private `/tmp` evidence paths recorded in the live JSON. Historical local documents are evidence, not current installation instructions.
