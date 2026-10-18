# Quick start

Use an absolute Git worktree root and a narrow, reviewable task. A research/review role has no owned write paths; implement/test roles require at least one `--owned-path`.

```bash
python3 skills/peer-coworkers/scripts/cowork.py init \
  --cwd "$PWD" --role implement --owned-path src \
  --goal 'Fix the specified defect and report the evidence' \
  --acceptance 'The regression reproduces before the fix and passes afterward'
```

Use the returned absolute `run` as `RUN` below. Default task files are private under `/tmp/peer-coworkers-<uid>/runs`. Task execution defaults to 600 seconds and at most two replies. Set `--model MODEL_ID` only when a particular model is wanted; otherwise the profile configuration or CLI default applies.

```bash
python3 skills/peer-coworkers/scripts/cowork.py start --run RUN
python3 skills/peer-coworkers/scripts/cowork.py screen --run RUN
python3 skills/peer-coworkers/scripts/cowork.py paste --run RUN
python3 skills/peer-coworkers/scripts/cowork.py screen --run RUN
# Only after the actual pointer is visible in the intended input field:
python3 skills/peer-coworkers/scripts/cowork.py submit --run RUN --received-confirmed
python3 skills/peer-coworkers/scripts/cowork.py wait --run RUN
```

`start` resolves proxy setup internally. The default `auto` mode calls `proxy_on` when that function exists in interactive Bash, and fails before launching if the function fails. Absence is reported and does not prevent launch. Use `start --no-proxy` to skip setup, or configure a proxy in the [JSON configuration](../config.example.json). Off mode retains inherited environment variables.

Read the reason from `wait`. `attention` means inspect the screen; `approval` means inspect the exact proposed action and existing authorization. Neither approves anything. `question` contains the worker's question. Answer or request a bounded repair using a UTF-8 message file:

```bash
python3 skills/peer-coworkers/scripts/cowork.py reply --run RUN --message-file /absolute/message.txt
```

A failed reply stays uncertain and must not be resent. A new round invalidates previous results. Once a valid result is ready:

```bash
python3 skills/peer-coworkers/scripts/cowork.py collect --run RUN
# Independently inspect the actual diff, artifacts and tests, then:
python3 skills/peer-coworkers/scripts/cowork.py accept --run RUN --evidence 'Concrete independent validation'
python3 skills/peer-coworkers/scripts/cowork.py close --run RUN --allow-active
```

`DONE` enters `awaiting_acceptance`; it does not imply acceptance. A still-running CLI requires explicit `--allow-active` to close. Keep the run directory when retaining evidence. Its default temporary storage can be removed by OS cleanup or reboot; configure `runs_dir` only after verifying worker sandbox access to that location.
