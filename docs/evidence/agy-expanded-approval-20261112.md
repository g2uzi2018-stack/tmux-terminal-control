# agy expanded command approval

2026-11-12, WSL, Python 3.12.3, tmux 3.4, reported CLI agy 1.5.3.

A complete Full Command view visually wrapped one long path onto another row. The parser counted 17 rows, while the ordinary permission card hid 12 of the command's 16 logical lines. Comparing these counts rejected the unchanged command after returning from the editor. The decision had already recorded uncertainty and sent Escape, but had sent no Enter.

The expanded approval now retains the previously observed numbered card after matching its visible command prefix. The complete reviewed command remains bound to the token. Returning from the editor must match that original card, including its preview, choices and hidden-line marker. This avoids interpreting the editor's visual line count as the command's logical line count. Tokens created without an original card retain their previous strict comparison.

The incident also exposed recovery after an explicit cancellation. The supervisor sent a recorded Escape after the uncertain attempt and later observed a different complete command card, but `wait` continued returning the old uncertain token. That specific transition now creates a fresh token. The historical attempt stays uncertain, and the submission budget keeps its original timestamp. The original card, clipped replacements and observations without a later recorded cancellation retain uncertainty.

Recorded-screen replay reproduced both failures. An isolated real tmux session replayed the menu and expanded frames through `keys`, observation and `decision`; its input log contained exactly Control-G, Escape and one Enter. A repeated decision and immediate observation of the still-visible menu sent no additional Enter. Changed return options, preview target and hidden-line count were rejected before Enter. Changes to the reviewed path or a real newline were rejected before navigation. A replay through normal `wait` produced a fresh token for the recorded post-cancellation command without terminal input.

After installation, the original supervisor obtained a fresh token for the short command through `wait`, reviewed it and received `sent=true` from the normal one-time decision. Read-only inspection of the original task record confirmed the new decision was submitted and the previous expanded decision remained uncertain. The supervisor reported that the native agy worker continued. A later native expanded-command approval remains a separate validation point.

These checks cover the approval state and terminal delivery using recorded native frames and a temporary local worker. The original active pane remained under its supervisor's control. Temporary scripts, workers and sessions were removed. Python parsing, skill validation and `git diff --check` passed. Private raw records remain local.
