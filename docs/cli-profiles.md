# CLI evidence — 2026-10-18

These are actual CLI runs with sandbox flags retained. Results are limited to this environment, executable/version, model and settings. Reviewed report summaries retain launch arguments, date, per-check outcomes and methods, submission counts and cleanup outcomes. Raw screens, account information and machine paths remain in ignored local records; see the [evidence policy](evidence/README.md).

| Capability | Codex 0.163.0 | Cursor Agent 2026.10.16-e3cb207 | agy 1.4.0 (historical) | agy 1.4.2 (installed retest) |
| --- | --- | --- | --- | --- |
| Readiness | Passed | Passed | Passed on longer retest | Unverified: literal input not visible; no Enter sent |
| Unicode/metacharacter paste | Passed | Passed | Passed | Passed |
| Single-line computed response | Passed | Passed | Passed | Passed |
| Multiline | Passed | Passed initial run; later run gave an incorrect computed second token and timed out | Passed | Passed |
| One-Escape cancellation | Unverified: conversation interrupted while a background terminal remained active | Passed: heartbeat process stopped and an explicit cancelled tool row appeared | Blocked on command approval before heartbeat execution; no Escape sent | Blocked on human permission gate; no Escape sent |
| Approval recognition | No prompt: sandbox refused the write; recognition attempt timed out | Passed actual file-write prompt with 8 physical lines; no approval sent | Passed actual file-creation prompt with 8 physical lines; no approval sent | Blocked on human gate; candidate recognizer not verified |
| Atomic nonce result | Passed | Passed retest; initial attempt timed out | Blocked on command approval; left unanswered | Blocked on human permission gate; left unanswered |
| Full 150-line history | Passed | Passed | Passed with 90-second limit; initial shorter attempt timed out | Passed |
| Exact cleanup | Passed | Passed | Passed | Passed |

Commands: `PEER_LIVE=1 PEER_PROFILE=PROFILE python3 -m unittest discover -s tests -p live_probe.py -v`, selecting each profile. Cursor's initial/retest and agy's initial runs used 25 seconds per check, 240 total. Codex and agy's longer retest used 90 seconds per check, 540 total; cleanup/diagnostic reads have separate bounded overhead. A successful harness means all outcomes were recorded and exact cleanup succeeded; it does not mean every capability passed.

Reports: [Codex](evidence/probe-codex.json), [Cursor initial](evidence/probe-cursor-initial.json), [Cursor retest](evidence/probe-cursor.json), [agy initial](evidence/probe-agy-initial.json), [agy longer retest](evidence/probe-agy.json). Do not replace unsuccessful outcomes with inferred passes. The latest matching report is authoritative even when an earlier run passed a capability.

After installing the new skill with `python3 scripts/install-skill.py`, the installed
entry point ran `probe --profile agy --timeout-ms 90000 --budget-seconds 540`.
The [agy 1.4.2 report](evidence/probe-agy-1.4.2.json) records all nine checks,
sandbox-preserving `agy --sandbox`, automatic proxy setup, and successful precise
cleanup for every check. No approval was answered. Five capabilities passed;
readiness is unverified and three permission-dependent checks are blocked.

Cursor's captured approval region says `Write to this file?`; the initial empty recognizer did not match it. The candidate came from that actual screen and passed a separate live probe. Its cancellation pattern likewise came from an actual cancelled command row and passed only when the heartbeat process was proven stopped. Normal commands inherit patterns only from a passing report matching executable and version. Approval recognition covers the observed file prompts; other menus can still require manual screen inspection.

Codex's interrupted conversation retained a background tool process, so the heartbeat check correctly did not enable cancellation. agy's command permission menus were not approved; cancellation and atomic writing remain unverified through this interactive probe. These are external capability limitations, not fictitious successes from quiet screens.

The WP0 write-location experiment used Codex `exec --sandbox workspace-write --ephemeral` and Cursor `--sandbox enabled --print`, with 120 seconds each, comparing real user-state paths outside both cwd and `/tmp` against `/tmp`. Both refused/rejected the state target and wrote the unpredictable nonce under `/tmp`. This justifies default run placement; it does not establish that an interactive CLI will approve writing there. Evidence: [WP0 JSON](evidence/wp0-sandbox-experiment.json).

Default tests use fake peers and raw-terminal fixtures inside real tmux. All nine probe checks execute there, including an actual heartbeat child, process identity/progress checks and an eight-line approval region. Negative fixtures reject an echoed prompt, a 149-line answer, an interruption label with a running child, and a forged heartbeat naming an unrelated process. Those are tool regressions, not real CLI compatibility results.

The earlier doctor correctly warned about agy 1.4.2 against a 1.4.0 report;
see the [historical doctor summary](evidence/doctor.json). After the installed
retest, [doctor matches agy 1.4.2](evidence/doctor-after-install.json) and no longer
reports an upgrade mismatch. Cancellation and approval recognition remain disabled
because those current-version checks did not pass. No CLI update command was run.
