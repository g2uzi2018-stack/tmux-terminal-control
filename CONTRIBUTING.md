# Contributing

Use Linux/WSL, Python 3.9+ (standard library only), and Git. Keep task orchestration and Git integration with the primary agent.

## Maintenance Constraints

1. **500-line script cap**: Keep the total line count across repository Python scripts at or below 500 lines; delete or simplify before adding code.
2. **No redundant persisted state**: Derive status from live locks and filesystem artifacts (`run.lock`, `rounds[N]`, `result-N.md`) rather than storing a mutable state machine.
3. **Report, do not block**: Audit differences (`outside_write_paths`, `head_moved`, `branch_changed`, `index_changed`) are reported for primary review; the only hard block is the per-workspace write lock (`workspace.lock`).
4. **No committed test reports or evidence dumps**: Verify changes with real CLI scenarios (read-only, writable with out-of-scope detection, and follow-up `send`), not committed test harnesses or evidence logs.
5. **Justify every new parameter**: Any new CLI flag must document the specific, real failure mode it prevents.
