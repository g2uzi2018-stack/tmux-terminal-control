# Contributing

Use Python 3.9+, the standard library and tmux. Keep task scheduling and Git integration with the primary agent. Contributors coordinate changes through Git and isolated worktrees; this tool does not manage multiple users.

Run `python3 -m unittest discover -s tests -v`. The default suite requires tmux and exercises actual isolated servers, raw terminal fixtures, single submissions, lease recovery, scope checks and behavioral probes without calling model services. Missing dependencies fail rather than skip. Tests own uniquely named temporary directories and exact sockets. Some outer execution sandboxes prohibit Unix sockets; run the suite in an explicitly authorized environment instead of weakening worker CLI sandboxes.

Live calls are opt-in and may incur usage:

```bash
PEER_LIVE=1 python3 -m unittest discover -s tests -p live_experiments.py -v
PEER_LIVE=1 PEER_PROFILE=cursor python3 -m unittest discover -s tests -p live_probe.py -v
```

The first command compares actual user-state and `/tmp` paths with 120-second limits and retains raw outcomes. The second runs each implemented interactive capability check; select an enabled profile with `PEER_PROFILE`. These modules are deliberately outside default `test_*.py` discovery, so there are no skipped live tests in the normal suite. Keep network, authentication, sandbox refusal, approval, timeout and successful behavior distinct. Fake TUI tests must never be described as real CLI compatibility.

For a lifecycle change, test the failure between persistence and the terminal side effect. Do not add automatic Enter retries, blanket approvals, trust bypasses, global configuration changes or broad tmux cleanup. Document commands, date, versions and concrete evidence. Protect raw private logs and keep machine-specific paths and history under `docs/local/`.

Git ignores local records except their README. Publish reviewed summaries under
`docs/evidence/`, excluding raw screens, account details and absolute machine paths.
Preserve unsuccessful outcomes and link the summary from the validation docs;
do not force-add local logs. See the [evidence policy](docs/evidence/README.md).
