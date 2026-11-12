# Concurrent startup lock recovery

2026-11-11, WSL, Python 3.12.3, tmux 3.4. The reported native worker was agy 1.5.3.

Two read-only packages used the same workspace. The first `start` took 11.56 seconds. The second began 1.22 seconds after the first and failed after 3.33 seconds, while the first was still starting. The failed package remained `prepared` without a session or workspace lease. Inspecting it with `screen` raised `KeyError: socket`.

Holding the workspace lock reproduced the two-second `BlockingIOError` timeout. Read-only packages are compatible with each other, but startup holds the registry lock across snapshot and session creation. That startup wait now allows 30 seconds. A timeout identifies the operation lock and directs the caller to inspect task state. Terminal commands require a confirmed socket, session and pane and otherwise report the current task state.

Focused verification used temporary Git workspaces and an executable that remained idle in real tmux sessions. Two concurrent `cowork.py start --run RUN` processes both completed after a deliberately held 3.5-second workspace lock. Both read-only leases were live. Repeated startup was rejected, and a writer still conflicted with the readers. A shortened lock timeout left another package prepared without launch effects, and the same package started after release. `screen` on a prepared package and session inspection after an unconfirmed launch returned explicit errors before terminal access.

The reporting supervisor separately retried the original prepared agy package after the initial startup finished and it started successfully. This observation predates installation of the patch. The targeted verification establishes local lock and terminal lifecycle behavior. Native agy task delivery continues under the reporting supervisor.

All temporary workers, scripts and workspaces were removed, and the temporary leases and tmux sessions were closed. Python parsing, skill validation and `git diff --check` passed. Raw timing and validation records remain local.
