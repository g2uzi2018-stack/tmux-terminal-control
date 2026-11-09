# Quick start

Run from a Git workspace with Python 3.9+ and tmux. Set the actual CLI profile and model for the package.

```bash
peer=skills/peer-coworkers/scripts/cowork.py
python3 "$peer" init --cwd "$PWD" --profile codex --owned-path src \
  --goal 'Fix the specified defect and report the evidence' \
  --acceptance 'Show the relevant before-and-after behavior'
```

Use the returned path as `RUN`. Omit `--owned-path` for a read-only workspace. The worker can still write its handoff. The default work budget is 45 minutes (2700 seconds) from first submit. Startup has 300 seconds, and observed approval waits receive up to 300 seconds of grace.

```bash
python3 "$peer" start --run "$RUN"
python3 "$peer" screen --run "$RUN"
python3 "$peer" paste --run "$RUN"
python3 "$peer" screen --run "$RUN"
# Confirm the exact task pointer is in the input field.
python3 "$peer" submit --run "$RUN" --received-confirmed
python3 "$peer" wait --run "$RUN"
```

Handle startup trust or a concrete approval only after inspection and under existing authorization. See [terminal interactions](../skills/peer-coworkers/references/terminal-control.md).

Read the Markdown handoff path returned by `wait`. Answer a question or request changes with `reply --run "$RUN" --message-file FILE`. Feedback gets a new handoff path, with earlier handoffs kept in the private run directory.

```bash
python3 "$peer" collect --run "$RUN"
# Independently review the handoff and actual workspace artifacts.
python3 "$peer" accept --run "$RUN" --evidence 'Concrete independent validation' &&
  python3 "$peer" close --run "$RUN" --allow-active
```

An unaccepted `DONE` requires acceptance or explicit abandonment with `close --discard-unaccepted`. Keep any run evidence you need before temporary storage is cleaned.
