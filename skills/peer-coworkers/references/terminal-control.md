# Terminal interactions

Use `screen` for the current pane, `term history` for scrollback, and `wait` for handoffs, approvals and terminal events. Paste only after checking the input focus, and verify literal receipt before submitting. A quiet pane or an exit calls for inspection.

For a recognized startup trust card, verify the exact directory and authority to trust it. Use `trust --screen-sha256 HASH --evidence TEXT` with the current hash from `screen`. This sends the displayed trust key once.

When `wait` reports `approval`, review the current action and use `decision --approval-id ID --decision allow-once|deny --evidence TEXT` under existing authorization. The token binds the recognized card, including command or file path, contents and selection. Screen changes outside the card can leave that token valid. An unsupported card calls for inspection. Persistent grants are unavailable.

- On an agy Read card, review the exact canonical file path. On an edit/create card, read the whole diff and check the target. For a clipped diff use `inspect-diff --approval-id ID`, review the returned card and use its new token. A still-clipped card can only be denied.
- Expand a clipped agy command with `keys --key C-g` when the card offers that key. Read the entire Full Command section and call `wait` for the expanded card. A paginated section is incomplete. The decision returns to the numbered menu before acting.
- On a recognized Cursor shell card, review the whole bottom command. The one-time decision uses the displayed `y`; denial uses Escape.

Feedback can queue behind the active turn. When Cursor shows the exact submitted follow-up and `wait` returns `reply_steer`, `steer --steer-id ID --evidence TEXT` can steer that item once. The recognized activity spinner and token count may change while the queue and reply bytes stay bound. Wait for the resulting handoff.

For an uncertain send, inspect the recorded state, current screen and handoff. Avoid replaying input. `cancel` requires a passing cancellation probe for the current executable and version. For low-level diagnostics the packaged `session.py`, `input.py` and `wait.py` support `--help`; use the recorded socket and pane only.
