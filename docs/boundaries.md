# Scope and risk boundaries

This is a single-user coordination tool. It records contracts and ordinary changes; the CLI's own sandbox controls access. A prompt, snapshot, workspace lease or clean scope report is not a security sandbox.

Snapshots include Git-tracked and nonignored untracked files, deleted entries, symlink targets, non-UTF-8 paths and opaque special-file types. Submodules record their gitlink commit, working HEAD and porcelain-status digest without recursively hashing content. Regular-file hashes reuse metadata including size, nanosecond timestamps, inode, device and mode; metadata reuse is an optimization, not protection against hostile writers.

Content changes are checked against owned repository-relative paths. HEAD, branch and staged-index changes are checked separately. Git-ignored untracked files and paths outside the worktree are explicitly listed as exclusions in the task prompt and collection report; the primary must independently verify any relevant excluded artifacts. Runs directories must be outside the worktree. A submodule's status digest cannot establish absence of arbitrary content changes with an unchanged status representation.

Workspace leases coordinate users of the same state directory. Unrelated tools, other user accounts/state directories and unsynchronized worktree integration remain the primary's responsibility. Use separate worktrees and Git review for parallel writers. The tool does not create worktrees, commit, stage, change branches, merge, publish, or grant CLI permissions.

The primary inspects the actual requested action before any approval-related key. Keys are allowlisted, but their meaning depends on the CLI and active interface. Probe never approves prompts. A version change disables cancellation and automatic approval-pattern reuse until a fresh passing probe. Explicit user regex configuration remains a recognizer, not authorization.

Temporary run files and terminal histories can contain task content. They are private on creation, but the user must preserve required evidence before OS cleanup. Do not put secrets or material prohibited from reaching the selected CLI into a work package. Global CLI credentials, trust and model settings are not modified by installation or task commands.
