# Reviewed evidence summaries

These summaries describe dated observations, not guarantees for another environment.
Raw screens, account information, absolute machine paths and temporary artifact
locations are excluded. Original reports and historical transcripts remain in the
ignored `docs/local/` directory on the machine that ran the checks.

Probe summaries retain CLI versions, sandbox arguments, per-check outcomes,
behavioral methods, submission/Escape counts, and cleanup results. Timeout,
blocked, unverified and failed outcomes are preserved. They do not enable runtime
capabilities: the tool uses the original version-bound report in user state.

The write-location summary records observed nonce-file success or refusal; a
model/tool refusal does not establish that a kernel-denied syscall occurred.
Reaper summaries retain status transitions with process IDs anonymized and omit
process command lines and host details. Review summaries retain findings and
validation limits with local paths replaced by placeholders.

To publish new evidence, inspect the original report and export only these fields.
Never copy terminal screens, credentials or raw command output into this directory.
Keep the original locally and link the reviewed summary from the dated validation
documents. Run deterministic tests separately from opt-in live CLI checks.
