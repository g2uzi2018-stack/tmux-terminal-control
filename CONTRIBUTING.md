# Contributing

Use Python 3.9+, the standard library and tmux. Keep task scheduling and Git integration with the primary agent. Contributors coordinate changes through Git and isolated worktrees; this tool does not manage multiple users.

The repository does not retain test code, fixtures or a test runner. Review the actual changes and evidence relevant to the requested behavior. Do not introduce smoke tests or persistent test files.

For a lifecycle change, inspect persistence ordering and terminal side effects. Do not add automatic Enter retries, blanket approvals, trust bypasses, global configuration changes or broad tmux cleanup. Document commands, date, versions and concrete evidence. Protect raw private logs and keep machine-specific paths and history under `docs/local/`.

Runtime compatibility checks remain available through `cowork.py probe`; live calls are opt-in and may incur usage. Keep network, authentication, sandbox refusal, approval, timeout and successful behavior distinct. Historical validation documents retain commands for deleted test tools as records of earlier runs.

Git ignores local records except their README. Publish reviewed summaries under
`docs/evidence/`, excluding raw screens, account details and absolute machine paths.
Preserve unsuccessful outcomes and link the summary from the validation docs;
do not force-add local logs. See the [evidence policy](docs/evidence/README.md).
