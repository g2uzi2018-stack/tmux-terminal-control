# Local records (not committed)

Keep raw CLI screens, account information, absolute machine paths, probe artifacts,
proxy patches and historical investigation transcripts here. Git ignores this
directory's contents except this README. Existing local files are preserved.
Do not force-add raw logs to a commit.

Reviewed summaries belong in [public evidence](../evidence/README.md). Those JSON
files retain versions, dates, sandbox arguments, capability outcomes, submission
counts and cleanup results, but exclude raw screens, account details and artifact
paths. Summaries are deliberately not substitutes for the local raw evidence.

Live experiment modules write raw reports here; they require explicit invocation
with `PEER_LIVE=1`. A real CLI timeout, blocked approval or failed check remains
that outcome in the public summary. A successful harness is not a claim that all
capabilities passed. Default tests do not rewrite these evidence records.

Machine-specific history does not establish compatibility on other systems.
Historical material remains available in local files and prior Git commits.
