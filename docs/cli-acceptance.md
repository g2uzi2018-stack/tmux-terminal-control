# 真实 CLI 验收（2026-10-15，Asia/Taipei）

Notion 方案与 Skill 页只读，未修改。没有 git commit。没有改 tmux / WSL 全局配置，没有关闭沙箱，没有跳过或同意审批。假 TUI 的 71 项通过不记成 CLI 兼容。

## 环境

| 项 | 值 |
|---|---|
| 系统 | Debian GNU/Linux 13.7 (trixie)，x86_64 |
| WSL | WSL 2，发行版 Debian13，内核 6.18.54.1-microsoft-standard-WSL2 |
| tmux | 3.5a（/usr/bin/tmux） |
| Python | 3.13.5 |
| 代理 | `bash -ic 'proxy_on'` 输出 `Proxy ON: http://127.0.0.1:7890`。`http_proxy`、`https_proxy`、`all_proxy` 均为该地址，`NODE_USE_ENV_PROXY=1` 已导出。本机可以连上 `127.0.0.1:7890`。不记录 token |
| 工作目录 | 每个 CLI 用 `mktemp -d`，不在仓库里写 prompt |

代理变量不会留在下一条 shell。启动 `session.py` 的同一条命令里重新导出，并核对 tmux server 与 pane 的环境。第一次 Codex 启动发生在未带上这些变量的 shell，进程已退出；只删除本任务失效 socket `/tmp/tmux-1000/ai-tui-accept-codex` 后重建。重建后的 Codex、OpenCode、agy 的 server 与 pane 都有上述四项，`TERM=tmux-256color`。

等待参数固定为 `--timeout-ms 20000 --shell-timeout-ms 30000`。`still` 只作候选，完成与否按画面判断。

## 总表

| 项目 | Codex 0.162.1 | OpenCode 2.0.28 | agy 1.3.5 |
|---|---|---|---|
| 启动到可输入 | 第二次通过 | 通过 | 停在信任审批，未进入 |
| 单行粘贴可见且未提交 | 通过 | 通过（延迟后可见） | 未测 |
| 单独提交 | 通过，ready，回复 PONG | 通过，ready，回复 PONG | 未测 |
| 粘贴后立即提交 | 未卡死，回复 READY | 不做此项 | 未测 |
| 多行 | 未测，暂不支持 | 未测，暂不支持 | 未测 |
| 斜杠 / 帮助 | `/status` 通过 | Help 通过；`/thinking` 未执行 | 未测 |
| 取消 | 未知，未发 Ctrl+C | 未知，未发 Ctrl+C | 未测 |
| 长回答 | 失败，历史不完整 | 失败，历史不完整 | 未测 |
| 隐藏思考 | 可见画面无推理块；进度仍在 | 未切换；可见画面无推理块 | 未测 |
| 审批 | 未出现审批 | 未出现审批 | 出现，未同意，会话保留 |

## Codex

路径 `/home/dev/.local/bin/codex`。socket `ai-tui-accept-codex`，session `cli`，pane `%0`，cwd `/tmp/tmp.VMfF9LGMNp`。argv：

`/home/dev/.local/bin/codex -c hide_agent_reasoning=true -c show_raw_agent_reasoning=false`

命令行没有初始 prompt。

### 1. 启动画面

第一次 `session.py new` 退出码 0，当时 pane 环境没有代理变量。随后 `pane_dead=1`，`pane_dead_status=1`，画面为：

```text
Error: account/read failed during TUI bootstrap: account/read failed: workspace routing discovery timed out (code -32603
)
Pane is dead (status 1, Thu Oct 15 12:59:50 2026)
```

该画面已保留到记录完成，然后 cleanup，并在确认 server 已退出后只删除这个失效 socket，再在带代理的同一条命令里重建。

第二次 `new` 退出码 0。`pane_dead=0`，命令 `codex`，`TERM=tmux-256color`。`wait.py begin` 退出码 0：`reason=still elapsed_ms=2772 changed=1`。画面含 `OpenAI Codex (v0.162.1)`、cwd、输入提示 `› Ask Codex to do anything`，以及 `/init`、`/status`、`/permissions`、`/model`、`/review`。页脚有 `⚠ 2 warnings · f2 to view`，没有按 f2。判断：可输入。

### 2. 单行粘贴

`input.py paste` 退出码 0，`reason=pasted bytes=64`。提交前画面输入区为：

```text
› 只回复一行：PONG。不要调用工具，不要改文件。
```

原文在输入区，尚未提交。

### 3. 提交并等待

`submit-and-wait` 退出码 0：`reason=still elapsed_ms=10067 changed=1`。画面先显示该句，再显示 `• PONG`、`Worked for 5s`，输入区恢复 `› Ask Codex to do anything`。pane 仍为 `codex`。判断：ready。

### 4. 粘贴后立即提交

另一条无害短句粘贴后没有等待、没有 sleep，立刻 `submit-and-wait`。paste 退出码 0，`bytes=83`。等待退出码 0：`reason=still elapsed_ms=2278 changed=1`。画面出现 `• READY` 和 `Worked for 1s`，输入区恢复。Codex 0.162.1 / tmux 3.5a 这一次没有卡死。没有把延迟写进脚本。

### 5. 多行

`display-message` 的 `#{bracket_paste_flag}`、`#{bracketed_paste}`、`#{pane_bracketed_paste}` 都是空。当前输入界面没有标明 bracketed paste 已开启。未加 `--multiline-verified`，未发送多行，没有压成一行。结论：暂不支持。

### 6. 斜杠

空输入区粘贴 `/`（退出码 0）后出现命令菜单，未提交。滚动中见到的只读或危险项包括 `/status`、`/statusline`、`/model`、`/permissions`、`/approve`、`/ps`、`/exit`。只提交了菜单里写明 `show current session configuration and token usage` 的 `/status`。

`submit-and-wait` 退出码 0：`reason=still elapsed_ms=620 changed=1`。画面含 `OpenAI Codex (v0.162.1)`、`Model: GPT-6.1-Sol (reasoning low, summaries auto)`、`Directory: /tmp/tmp.VMfF9LGMNp`、`Permissions: Workspace (granular)`。账号已登录，邮箱不写入本文。输入区恢复。没有执行会改仓库、跑 shell 或放宽审批的命令。

粘贴 `?` 只进入输入区，没有打开快捷键帮助，已退格，未提交。

### 7. 取消

空闲画面和完成后的画面都没有给出「取消生成」且明确不是退出进程的键。未发送 Ctrl+C。结论：未知。

### 8. 长回答

单行请求约 40 行纯文字。paste 退出码 0，`bytes=193`，提交前原文在输入区并软换行。`submit-and-wait` 退出码 0：`reason=still elapsed_ms=5355 changed=1`。当前屏和 `capture-pane -p -S -60` 都从 `行11：验收` 到 `行40：验收`。`history_size=0`。`行01` 至 `行10` 不在历史里。输入区已恢复，`Worked for 4s`。生成结束，但记录不完整，不记成功。

### 9. 隐藏思考

启动参数已带上。PONG、READY 和长回答的可见区域没有推理块。`/status` 仍写 `reasoning low, summaries auto`。`Worked for` 进度仍可见。长回答前 10 行已滚出，不能据此说推理块已被消除。

## OpenCode

路径 `/home/dev/.opencode/bin/opencode`。socket `ai-tui-accept-opencode`，session `cli`，pane `%0`，cwd `/tmp/tmp.LUvXjC7WVC`。argv 只有该绝对路径。没有使用 `--auto` 或 `--prompt`。

### 1. 启动画面

`new` 退出码 0。`pane_dead=0`，命令 `opencode`，`TERM=tmux-256color`，`alternate_on=1`。`begin` 退出码 0：`reason=still elapsed_ms=1559 changed=1`。画面有 OpenCode 字样、输入提示 `Ask anything…`、`Build · Muse Spark 1.3 Free OpenCode · medium`、cwd、`ctrl+p commands`，右下角 `2.0.28`。另有 `/update to install v2.0.29`，未执行。判断：可输入。

### 2. 单行粘贴

paste 退出码 0，`bytes=64`。紧接着的 capture 仍是占位提示。随后输入区变为：

```text
┃  只回复一行：PONG。不要调用工具，不要改文件。
```

此时未提交。

### 3. 提交并等待

`submit-and-wait` 退出码 0：`reason=still elapsed_ms=3368 changed=1`。正文为 `PONG`，其下 `Build · Muse Spark 1.3 Free · 2.6s · 11.4 tok/s`。底部输入框已空。判断：ready。

### 4. 多行

格式变量为空，`alternate_on=1`。界面没有确认 bracketed paste。未发送。结论：暂不支持。

### 5. 斜杠与帮助

`keys --key C-p` 退出码 0，画面没有打开命令列表。空输入区粘贴 `/` 后出现 `Commands`，过滤内容为 `/` 时显示 `No results found`，提示 `esc`。退格清空过滤后列出部分命令，其中有 `Open settings`、`Verbosity: Medium`、`Copy session transcript`。向下滚动后列表停在 Session 一段，没有再移动。

过滤 `help` 得到唯一项 `Help`（System）。`submit-and-wait` 退出码 0：`reason=still elapsed_ms=681 changed=1`。对话框：

```text
Help                                           esc/enter
Press ctrl+p to see all available actions and commands
in any context.
```

Escape 后对话框关闭，回到空输入框。Help 记为通过。

`/thinking`：粘贴后补全行是 `/thinking     Switch model variant`，输入区是 `/thinking`，未提交。命令面板里另有 `Thinking`（Settings · Session），行上没有当前是显示还是隐藏。这和「显示/隐藏思考块的切换」不一致，已停，并退格清空，未执行。见 [design-deviations.md](design-deviations.md)。

### 6. 取消

完成后的画面没有「取消生成」键。未发送 Ctrl+C。结论：未知。

### 7. 长回答

提交前输入框内可见完整单行请求（软换行为两行）。`submit-and-wait` 退出码 0：`reason=still elapsed_ms=3820 changed=1`。当前屏与 `-S -60` 从 `行12：验收` 到 `行40：验收`。`history_size=0`，`alternate_on=1`。统计行 `Build · Muse Spark 1.3 Free · 2.9s · 87.0 tok/s`，输入框已空。`行01` 至 `行11` 不在捕获里。不记成功。

### 8. 隐藏思考

没有执行 `/thinking`，也没有改 `Verbosity: Medium`。PONG 和长回答的可见区域没有推理块。速度统计仍可见。不记成思考显示已隐藏或已消除。

## agy

路径 `/home/dev/.local/bin/agy`。`--version` 为 1.3.5。socket `ai-tui-accept-agy`，session `cli`，pane `%0`，cwd `/tmp/tmp.6th5fv2RQd`。argv 只有该绝对路径。没有使用 `--print`、`--dangerously-skip-permissions`、`--disable-slash-commands` 或 `--verbosity`。

`new` 退出码 0。`pane_dead=0`，命令 `agy`，`TERM=tmux-256color`。`begin` 退出码 0：`reason=still elapsed_ms=2663 changed=1`。画面：

```text
Accessing workspace:

/tmp/tmp.6th5fv2RQd

Do you trust the contents of this project?

Antigravity CLI requires permission to read, edit, and execute files here.

> Yes, I trust this folder
  No, exit

  ↑/↓ Navigate · enter Confirm
                                                                 Gemini 3.8 Flash · high
```

这是审批。没有按 Enter，没有选择 Yes 或 No。TUI 画面没有印出 CLI 版本号 1.3.5；状态行是模型名和 `high`。没有打开 `/settings`，没有读出或修改 verbosity，没有改 `settings.json`。

因此单行粘贴、提交、多行、斜杠、取消、长回答、隐藏思考都未测。

### 保留的会话

需要人看的是 agy 这一屏。定位：

| 项 | 值 |
|---|---|
| socket | `ai-tui-accept-agy` |
| session | `cli` |
| pane | `%0` |
| task | `accept-agy` |
| cwd | `/tmp/tmp.6th5fv2RQd` |
| 查看 | `tmux -L ai-tui-accept-agy capture-pane -p -t %0` |

Codex 与 OpenCode 已用 `session.py cleanup --allow-active` 结束，退出码都是 0，`cleaned: true`。只清理了 `ai-tui-accept-codex` / `accept-codex` 和 `ai-tui-accept-opencode` / `accept-opencode`。cleanup 之后这两个 socket 文件还在，`session.py list` 对它们报告 `no server running`，没有按前缀删除。agy 仍在，画面仍是信任审批。

## WSL 调用端退出后的保活

未测。当前环境就是 Cursor 所在的 WSL，结束这个 `wsl.exe` 会把验收进程一起杀掉。

手动步骤：另开一个调用端，执行 `bash -ic 'proxy_on'` 并确认 `Proxy ON` 与上述四个变量，再用 `session.py new` 建立会话。关掉那个 `wsl.exe`，至少 60 秒后从另一个 WSL 用 `session.py list` 和 `tmux -L SOCKET capture-pane -p -t PANE` 检查进程和画面。不要改全局保活配置。

## 第二轮（2026-10-15）

Notion 仍只读。没有 git commit，没有把 prompt 写进仓库，没有改 tmux / WSL 全局配置，没有关沙箱。没有使用 `codex exec`、`opencode --auto` / `--prompt`、`agy --print` / `--dangerously-skip-permissions` / `--mode auto`。同一 pane 串行。等待默认 `--timeout-ms 20000 --shell-timeout-ms 30000`；取消采样用 `--timeout-ms 3000`。超时只 `resume`，不补 Enter。

`keys.py` 没有 F2。本轮唯一的直接 `send-keys` 是读 Codex 警告：`tmux -L SOCKET send-keys -t %0 F2`。用过两次：`ai-tui-accept2-codex-main` 和 `ai-tui-accept2-codex-plain`。

门禁 `python3 -m unittest discover -s tests -v` 完整输出已覆盖 `docs/test-results.txt`。`Ran 71 tests in 8.466s`，`OK`，`Final socket discovery: []`。

第一轮残留：`tmux -L ai-tui-accept-codex ls` 与 `tmux -L ai-tui-accept-opencode ls` 都是 no server。`/tmp/tmux-1000/ai-tui-accept-codex` 和 `/tmp/tmux-1000/ai-tui-accept-opencode` 是 uid 1000 的 socket 文件，只删了这两个路径。`ai-tui-accept-agy` 仍有 server，保留并继续。

新会话都用一条命令启动：`bash -ic 'proxy_on && python3 skills/tmux-tui/scripts/session.py new ...'`。`proxy_on` 输出 `Proxy ON: http://127.0.0.1:7890`。目标进程用 `tr '\0' '\n' < /proc/PID/environ` 核对，都带 `http_proxy`、`https_proxy`、`all_proxy` 和 `NODE_USE_ENV_PROXY=1`。agy 保留会话的进程同样带这些变量，没有重建。

本轮同意信任的目录只有：`/tmp/tmp.6th5fv2RQd`（保留会话）、`/tmp/tmp.OdKr43tYy5`（agy 长回答）、`/tmp/tmp.mH3J1hh1sA`（agy 多行）。其它审批都拒绝或未出现。没有登录、升级或遥测同意提示。

### 第二轮总表

| 项目 | Codex 0.162.1 | OpenCode 2.0.28 | agy 1.3.5 |
|---|---|---|---|
| 多行证据 | 通过。最后模式 `ESC[?2004h`（h=1，l=0）。输入区是原文。回复是回显，不是「收到几行」 | 有证据（h=5，l=0，最后 `2004h`）。输入区是占位符 `[Pasted ~4 lines]`，全文不可见，未提交 | 通过。粘贴前 h=20，l=0，最后 `2004h`。输入区是原文。回复去跑了 `ls`，已拒绝 |
| 斜杠 | 菜单 51 条。测了 `/model`、`/permissions`、`/status`。危险项未执行 | `C-p` 打开了命令面板。斜杠菜单 10 条，方向键不滚动。测了 Help、模型列表、会话列表、View status、Thinking | 菜单 46 条。测了 `/help`、`/config`、`/model`。`/status` 不存在 |
| 取消 | 采样画面没写中断键，未发送。随后回答写完，PONG 仍可用。其它画面可见 `esc to interrupt` | 画面写 `esc interrupt`。Escape 一次后仍写到第 200 行。PONG 可用。失败 | 通过。`esc to cancel`，Escape 后停止，PONG 可用 |
| 长回答 | 通过。`--no-alt-screen` 后 `capture-pane -p -S -` 含行 01–40 | 通过。`--height 100` 的当前屏含行 01–40。`session export --sanitize` 里没有这些行 | 通过。`--height 100` 的当前屏含行 01–40 |
| 隐藏思考 | 带 `-c` 与不带 `-c` 都没有推理块。`Worked for` 仍在。第二条 warning 与 `-c` 有关 | Settings 里 Thinking 为 hide/show。两档这道题都没有推理块。hide 时一次工具回合仍有 `Thought` 行 | medium 有 Thought 行；low 没有。已改回 medium |
| 审批（写 cwd 外文件） | 探测目录在 `/tmp`。没有审批框，直接写成 `hello\n`。第三轮更正：这不是审批失效，Codex workspace 沙箱默认允许写 `/tmp` | 探测目录在 `/tmp`。没有审批框，直接写成 `hello\n`。Permissions 为 prompt。第三轮改到家目录重测 | 探测目录在 `/tmp`。没有审批框，直接写成 `hello\n`。Tool Permission 为 request-review。第三轮改到家目录重测 |

### A. agy 补完第一轮

socket `ai-tui-accept-agy`，session `cli`，pane `%0`，cwd `/tmp/tmp.6th5fv2RQd`，task `accept-agy`。进程 `/home/dev/.local/bin/agy` 自带代理。

1. 信任。capture 时选中 `> Yes, I trust this folder`。`submit-and-wait --received-confirmed` 退出码 0：`reason=still elapsed_ms=676 changed=1`。随后两条通知（verbosity 默认改为 medium、第三方模型访问变更）用 Escape 关掉。进入输入界面，页脚 `Gemini 3.8 Flash · high`，版本 1.3.5。结论：通过。信任目录是 `/tmp/tmp.6th5fv2RQd`。
2. 单行。paste 退出码 0，`bytes=64`。提交前原文在输入区。`submit-and-wait` 退出码 0：`reason=still elapsed_ms=4592 changed=1`。回复 `PONG`，输入区恢复。结论：通过。
3. `/settings` 实际命令是 `/config`。原值 Verbosity medium。只把这一项改成 low 做 F，再改回 medium。Escape 后画面有 `Exited /config`。其它设置项没有改。结论：通过。

斜杠、取消、长回答、隐藏思考、多行见下面 C–F、B。

### B. 多行

每个 CLI 单独 socket。启动 argv 是 `/bin/sh -c 'sleep 3; exec "$0" "$@"'`，CLI 绝对路径作为 `$0`。`new` 返回后 3 秒内 `pipe-pane -O -t %0 'cat >> LOG'`。判定用 python 数 `ESC[?2004h` / `ESC[?2004l`，只看最后一次。测完 `pipe-pane -t %0` 关管道，记下字节后删除 LOG。

| CLI | socket / cwd | 粘贴前日志 | 输入区 | 提交与回答 | 关管道后 | 结论 |
|---|---|---|---|---|---|---|
| agy 1.3.5 | `ai-tui-accept2-agy-multiline`，`/tmp/tmp.mH3J1hh1sA` | 1770 字节，h=20，l=0，最后 `2004h`，2026-10-15T15:39:48+08:00 | 四行原文，减号行和空行都在，未提交 | paste 退出码 0，`bytes=86`。`submit-and-wait` 退出码 0：`reason=still elapsed_ms=7674`。它去跑 `ls -la`，没有说收到几行 | 22504 字节，h=50，l=0，最后仍是 `2004h`。LOG 已删 | 粘贴通过。回答未按「收到几行」 |
| Codex 0.162.1 | `ai-tui-accept2-codex-multiline`，`/tmp/tmp.dH4MiI4rHE` | 4704 字节，h=1，l=0，最后 `2004h`，2026-10-15T15:49:13+08:00 | 四行原文，未提交 | paste 退出码 0，`bytes=86`。提交先 `still elapsed_ms=699` 且仍是 `Working (0s • esc to interrupt)`，resume 退出码 0：`still elapsed_ms=1195`。回答把四行原文回显出来 | 14207 字节，h=1，l=0。LOG 已删 | 粘贴通过。回答是回显 |
| OpenCode 2.0.28 | `ai-tui-accept2-opencode-multiline`，`/tmp/tmp.9ABzxBAUcP` | 29356 字节，h=5，l=0，最后 `2004h`，2026-10-15T16:16:57+08:00 | `[Pasted ~4 lines]`，四行原文不在画面上 | paste 退出码 0，`bytes=86`。全文不可见，没有 submit | 29543 字节，h=5，l=0。LOG 已删 | 有证据，显示为占位符，未发送 |

agy 多行提交后的审批（不是 G 的写文件）：

```text
Requesting permission for:
   ls -la
> 1. Yes, run command
  2. Yes, and always allow in this conversation for commands that start with 'ls'
  3. Yes, and always allow for commands that start with 'ls' (Persist to settings.json)
  4. No, cancel
```

移到 `> 4. No, cancel` 后单独提交。画面变为 `Ran (ls -la) failed`、`User declined the tool call`、`Interrupted · What should Antigravity CLI do instead?`。没有选 always allow。`pane_dead=0`。

### C. 斜杠

危险类都没有执行。

#### Codex

socket `ai-tui-accept2-codex-main`，cwd `/tmp/tmp.a1engputGs`。空输入粘贴 `/` 后用 Down 滚完。按首次出现，51 条：`/model` `/fast` `/ide` `/permissions` `/keymap` `/vim` `/experimental` `/approve` `/memories` `/skills` `/import` `/hooks` `/review` `/rename` `/new` `/archive` `/delete` `/resume` `/fork` `/worktree` `/init` `/compact` `/recap` `/plan` `/voice` `/goal` `/agents` `/side` `/copy` `/export` `/raw` `/tui` `/diff` `/mention` `/status` `/daemon` `/warnings` `/cd` `/pwd` `/usage` `/title` `/statusline` `/theme` `/pets` `/mcp` `/plugins` `/logout` `/exit` `/feedback` `/ps` `/stop`。第一轮见过的 `/clear`、`/subagents` 这次没出现。

按名称归类。只读：`/status` `/diff` `/pwd` `/usage` `/warnings` `/copy` `/export` `/mention` `/ps` `/review`。改本会话状态：`/model` `/fast` `/keymap` `/vim` `/experimental` `/memories` `/skills` `/rename` `/new` `/archive` `/resume` `/fork` `/worktree` `/compact` `/recap` `/plan` `/voice` `/goal` `/agents` `/side` `/raw` `/tui` `/title` `/statusline` `/theme` `/pets` `/stop`。危险：`/approve` `/init` `/delete` `/logout` `/exit` `/cd` `/hooks` `/mcp` `/plugins` `/import` `/daemon` `/ide` `/feedback`，以及确认后会改权限的 `/permissions`。

实测三条，都是打开、移动一格、Escape，没有确认新选项：

- `/model`：当前 `1 GPT-6.1-Sol`。Down 后高亮到 `2 GPT-6-Astra`。Escape 后页脚仍是 `GPT-6.1-Sol default`。列表还有 GPT-6-Sol、GPT-6-Luna、GPT-5.6-Sol、GPT-5.6-Terra、GPT-5.6-Luna。
- `/permissions`：当前 `1 Ask for approval`。Down 后高亮到 `2 Approve for me`。Escape，没有选中。其余是 Full Access、Read Only。
- 然后再 `/status`。退出码 0：`reason=still elapsed_ms=628 changed=1`。摘录：`Model: GPT-6.1-Sol (reasoning low, summaries auto)`，`Permissions: Workspace (granular)`，目录仍是该 cwd。模型和权限没变。结论：通过。

#### OpenCode

socket `ai-tui-accept2-opencode-main`，cwd `/tmp/tmp.Ae51gNk1hK`。

`keys --key C-p` 退出码 0。`begin` 退出码 0：`reason=still elapsed_ms=683 changed=1`。画面是 Commands 面板（Search、Suggested、Session）。第一轮 C-p 没反应，这一轮打开了。

PageDown / Down 滚完面板。条目：

- Suggested：Switch model（ctrl+x m）、Connect an integration、Open settings
- Session：Switch session（ctrl+x l）、New session（ctrl+x n）、Clear session、Open session or project（ctrl+o）、Close tab（ctrl+x w）、Reopen closed tab（ctrl+shift+t）、Open editor（ctrl+x e）、Manage workspaces、Ask a side question
- Agent：Switch model、Switch agent（ctrl+x a）、MCP servers、Variant cycle（ctrl+t）、Switch model variant
- Integration：Connect an integration
- System：Show release highlights、Open settings、View status（ctrl+x s）、Update OpenCode、Pair device、Restart service、Reload configuration、View debug info、Switch theme、Help、Open docs、Exit the app（ctrl+c, ctrl+d, ctrl+x q）、Toggle console、Usage statistics、Plugins
- Prompt：Queue prompt（ctrl+x enter）
- Skills：标题下没有子项
- VCS：Open diff viewer

只读：Help、Open docs、View status、View debug info、Show release highlights、Usage statistics、Open diff viewer、Switch session（只看列表）。改本会话状态：Switch model、Switch agent、Variant cycle、Switch model variant、Switch theme、Open settings、Clear session、New session、Manage workspaces、Queue prompt、Toggle console、Plugins、MCP servers。危险：Exit the app、Update OpenCode、Connect an integration、Pair device、Restart service、Reload configuration、Open editor、Open session or project。

空输入粘贴 `/`，paste 退出码 0，`bytes=1`。高亮停在 `/agents`。Down、PageDown、Up 都不滚动，画面始终这 10 条：`/agents` Switch agent，`/btw` 一次性旁路回答，`/cd` 改工作目录，`/clear` 清会话，`/connect` 连接集成，`/continue` 切换会话，`/debug` 看调试信息，`/diff` 打开 diff，`/editor` 打开编辑器，`/effort` Switch model variant。只读：`/debug` `/diff` `/btw`。改本会话状态：`/agents` `/clear` `/continue` `/editor` `/effort`。危险：`/cd` `/connect`。Escape 后输入区恢复占位符。`/thinking` 不在这 10 条里。

实测：

- Help：过滤后提交，退出码 0。对话框写 `Press ctrl+p to see all available actions and commands in any context.`，只有一个高亮 `ok`。Down 后高亮仍在 ok。Escape 关闭，页脚仍是 `Build · Muse Spark 1.3 Free OpenCode · medium`。
- 模型列表：高亮从 Cat Jam Free 移到 LongCat 2.5 Preview Free。可见模型：Cat Jam Free、LongCat 2.5 Preview Free、Space Bunny Free、MiMo-V2.6-Flash Free、Step 5 Preview Free、DeepSeek V4.1 Flash Free、● Muse Spark 1.3 Free、Nemotron 3.5 Lightning Free、Nemotron 3 Ultra Free、Big Pickle。Down 会绕回开头。Escape 后模型仍是 Muse Spark 1.3 Free。
- 会话列表：`Sessions for tmp.Ae51gNk1hK`，`No sessions available`。Down 后画面不变。Escape 关闭。页脚 hint 有 `delete ctrl+d`，没有按。
- 打开模型列表后再 View status：对话框只有 `No MCP servers`。页脚模型未变。结论：通过。

Thinking（Settings · Session）：过滤 `thinking` 后只有这一条。打开后当前值 `Thinking hide`，同一页还有 Theme opencode、Color mode system、Animations off、Sidebar auto、Scrollbar off、Markdown rendered、Tool grouping auto、Verbosity medium、Transcript images off、TPS on、New session location launch directory、Permissions prompt。底部 `←/→ change`。Down 把高亮从 Thinking 移到 Markdown，Thinking 仍显示 hide。当时没有按左右键。结论：它是 hide/show 值，不是斜杠补全里的 Switch model variant。F 里才改过这一项，并已改回 hide。

#### agy

同一保留会话。粘贴 `/` 后 PageDown 不滚动，Down 可以。46 条：`/add-dir` `/agents` `/artifact` `/btw` `/changelog` `/clear` `/codesearch` `/config` `/context` `/copy` `/credits` `/diff` `/effort` `/exit` `/feedback` `/fork` `/help` `/hooks` `/keybindings` `/logout` `/mcp` `/model` `/open` `/permissions` `/plugin` `/remote-control` `/rename` `/resume` `/rewind` `/skills` `/statusline` `/tasks` `/title` `/usage` `/voice` `/goal` `/compact` `/schedule` `/browser` `/plan` `/grill-me` `/teamwork-preview` `/learn` `/boost` `/agy-customizations` `/antigravity-guide`。没有单独的 `/status`；过滤只看到 `/statusline`。

只读：`/help` `/agents` `/artifact` `/changelog` `/context` `/credits` `/diff` `/usage` `/agy-customizations` `/antigravity-guide` `/copy`（复制到剪贴板）。改本会话状态：`/config` `/model` `/effort` `/statusline` `/rename` `/resume` `/title` `/clear` `/fork` `/rewind` `/skills`。危险：`/exit` `/logout` `/permissions` `/add-dir` `/remote-control` `/hooks` `/keybindings` `/mcp` `/plugin` `/browser` `/goal` `/compact` `/schedule` `/teamwork-preview` `/boost` `/codesearch`。

实测：

- `/help`：高亮从 `/add-dir` 移到 `/artifact`。Escape 后有 `Exited /help command`，页脚仍是 Gemini 3.8 Flash · high。
- `/config`：Verbosity 原值 medium。Left/Right 只改当前行。为 F 改到 low 后改回 medium。其它行（Agent Mode default、Sandbox Mode off、Tool Permission request-review、Non-Workspace Access off 等）没有改。
- `/model`：当前 Gemini 3.8 Flash。高亮移到 Claude Sonnet 4.6 (Thinking)。Escape 后页脚仍是 `Gemini 3.8 Flash · high`。列表里还有 Claude Opus 4.6 (Thinking)、GPT-OSS 120B (Medium)、Gemini 4 Argon。
- 没有 `/status`。用页脚核对，模型和 high 都没变。结论：通过。

### D. 取消

请求都是「写 200 行编号文字，每行一句关于 tmux 的话，不要调用工具，不要改文件」。`submit-and-wait --timeout-ms 3000 --shell-timeout-ms 30000`。

- agy，保留会话。退出码 3：`reason=timeout elapsed_ms=3000 changed=1`。画面 `Generating...` 和 `esc to cancel`。`keys --key Escape` 一次。resume 退出码 0：`reason=still elapsed_ms=682`。画面 `Interrupted · What should Antigravity CLI do instead?`，`pane_dead=0`，输入区空。随后单行 PONG 得到 `PONG`。结论：通过。这次回复里还有 `Thought for 7s, 362 tokens`。
- Codex，`ai-tui-accept2-codex-main`（备用屏）。退出码 3：`reason=timeout elapsed_ms=3000 changed=1`。画面已有 `• 1. tmux 是一个终端复用工具`，没有中断键说明。没有发 Escape 或 C-c。resume 后写到约第 95 行，输入区恢复，随后 PONG 得到 `• PONG`。`pane_dead=0`。结论：这次采样为未知。另两个会话的 Working 行写着 `esc to interrupt`（plain 会话、`--no-alt-screen` 长回答），那两轮没有拿来取消。
- OpenCode，主会话。退出码 3：`reason=timeout elapsed_ms=2992 changed=1`。页脚 `esc interrupt`。`keys --key Escape` 一次。resume 退出码 0：`reason=still elapsed_ms=621`。画面已经是第 172–200 行，没有 Interrupted。`pane_dead=0`，输入区恢复。随后「只回复 PONG」得到 `PONG`。结论：失败，Escape 没有在看到提示后停住生成。

### E. 长回答

请求都是「写 40 行，每行格式 行NN：验收，NN 从 01 到 40，不要调用工具」。

- Codex。新会话 `ai-tui-accept2-codex-long`，cwd `/tmp/tmp.tUVU2PRnm1`，argv 含 `--no-alt-screen` 和两个 `-c`。进程带代理。提交后先出现 `Working (0s • esc to interrupt)`，resume 后完成。`alternate_on=0`。`capture-pane -p -S -` 含行 01 到行 40。行 01 带前导 `•`，行 02–40 是 `行NN：验收`。方法：`--no-alt-screen` 加全历史捕获。结论：通过。
- OpenCode。`ai-tui-accept2-opencode-long`，`--height 100`，cwd `/tmp/tmp.3u5TSW2udy`。`submit-and-wait` 退出码 0：`reason=still elapsed_ms=6353`。当前屏有行 01–40。`alternate_on=1`，`history_size=0`，高度 100。同一 cwd 执行 `bash -ic 'proxy_on && opencode session list --format json'`，本轮 id `ses_ec16213bcffeNgEbK7hCdqLUGy`。`opencode session export <id> --sanitize` 退出码 0，约 2403 字节，3 条 message，正文里 `验收` 出现 0 次。导出文件已删，没有写入仓库。方法：加高 pane 后捕获当前屏。结论：屏上通过；sanitize 导出拿不到全文。
- agy。`ai-tui-accept2-agy-long`，`--height 100`，cwd `/tmp/tmp.OdKr43tYy5`，已信任该目录。`alternate_on=0`，`history_size=0`，高度 100。当前屏有行 01–40。`/copy` 提示已复制上一则回复；本机没有 wl-paste / xclip / xsel，剪贴板内容没有核对。方法：加高 pane 后捕获当前屏。结论：通过。

### F. 隐藏思考

题目都是「数列 2, 6, 12, 20, 30 的下一项是什么？只给答案和一句理由，不要调用工具。」

- Codex，带 `-c hide_agent_reasoning=true -c show_raw_agent_reasoning=false` 的 main 会话。`send-keys F2` 后：`Warnings · 1 of 2` 是 bubblewrap 不在 PATH，与 `-c` 无关；`2 of 2` 是 `command-line configuration overrides (-c, --enable, --disable, or --search) requires embedded mode`。Escape 关闭。同一题回答 `• 42。理由：…`，`Worked for 5s`，没有推理块。对照会话 `ai-tui-accept2-codex-plain`，cwd `/tmp/tmp.LCufSsYQn1`，argv 只有 codex。页脚是 `1 warning`。F2 确认只有 bubblewrap 那一条。同一题回答 `• 42。因为…`，`Worked for 4s`，也没有推理块。结论：这两边都看不到推理块；`-c` 的可见差异是多一条 embedded mode 警告。进度行仍在。
- OpenCode。C.5 确认 Thinking 是 hide/show。原值 hide。hide 时回答 `42` 和一句理由，没有 Thought 行。Right 把值改成 show（立刻捕获仍显示 hide，约 0.4 秒后才变成 show）。show 时仍是 `42` 加一句理由，没有单独推理块。Left 改回 hide 后 Escape。结论：这道题两档都没有推理块。稍后 G 的写文件回合在设置已回到 hide 时，仍出现 `+ Thought · 2.3s`。工具或进度行可见不算这项失败。
- agy。medium：`▸ Thought for 5s, 423 tokens`，然后中文 `下一项是 42`。low：没有 Thought 行，只有 `下一项是 42` 和理由。已改回 medium，画面确认后 `Exited /config`。结论：low 时这道题的 Thought 行不可见；medium 时可见。

### G. 审批

请求是在另一个 `mktemp -d` 里写 `approval-probe.txt`，内容一行 hello。目录都在 cwd 外。猜的锚定正则没有命中，因为审批框没出现。没有做「已出现的审批再用 begin 复验」，基线会排除已经在屏上的同一行。三个临时文件都已删除，目录保留。没有改权限，没有选 always allow。

- agy，保留会话，探测目录 `/tmp/tmp.vHeRvLN0rC`。`submit-and-wait --prompt-lines 40 --prompt 'approval=^Requesting permission for:$'` 退出码 0：`reason=still elapsed_ms=11833`，不是 prompt。画面 `Edited 1 file (approval-probe.txt)`。文件内容 `hello\n`。当时设置（未改）：Tool Permission request-review，Sandbox Mode off，Non-Workspace Access off。当时记成「没有审批就写了」。第三轮更正：目录在 `/tmp`，不能据此说审批失效。
- Codex，main 会话，探测目录 `/tmp/tmp.qWr8fCHAOW`。`--prompt 'approval=^[[:space:]]*(› )?[0-9]+\. (Yes|No)'` 退出码 0：`reason=still elapsed_ms=8334`。`wait.py` 对这个正则有 FutureWarning（nested set）。画面 `Ran printf 'hello\n' > …/approval-probe.txt`，并说已写入。文件内容 `hello\n`。`/status` 仍是 Workspace (granular)。第三轮更正：Codex 的 workspace 沙箱默认允许写 `/tmp`，这次写入不算审批失效。
- OpenCode，main 会话，探测目录 `/tmp/tmp.2D3J1uyved`。`--prompt 'approval=^[[:space:]]*(Allow once|Allow always|Deny|Reject|Yes, allow|No, deny)'` 同样 FutureWarning，退出码 0：`reason=still elapsed_ms=7956`。画面 `# Wrote …/approval-probe.txt` 和 `已在 … 写入 hello`。文件内容 `hello\n`。设置里看到的 Permissions 是 prompt，没有改。目录同样在 `/tmp`。家目录重测见第三轮。

agy 在多行回合里对 `ls -la` 有审批框，并且拒绝成功。那次不是这个写文件请求。

### 保留与清理

需要人看的留下：

| socket | session | pane | task | cwd | 原因 |
|---|---|---|---|---|---|
| `ai-tui-accept-agy` | `cli` | `%0` | `accept-agy` | `/tmp/tmp.6th5fv2RQd` | 第一轮保留会话。已信任该目录，verbosity 已回到 medium |
| `ai-tui-accept2-opencode-multiline` | `cli` | `%0` | `accept2-opencode-multiline` | `/tmp/tmp.9ABzxBAUcP` | 输入区仍是未提交的 `[Pasted ~4 lines]` |

其余 8 个本轮会话都用 `session.py cleanup --allow-active` 结束，退出码都是 0，`cleaned: true`。分别是 `ai-tui-accept2-codex-main` / `accept2-codex-main`、`ai-tui-accept2-codex-plain` / `accept2-codex-plain`、`ai-tui-accept2-codex-long` / `accept2-codex-long`、`ai-tui-accept2-codex-multiline` / `accept2-codex-multiline`、`ai-tui-accept2-opencode-main` / `accept2-opencode-main`、`ai-tui-accept2-opencode-long` / `accept2-opencode-long`、`ai-tui-accept2-agy-long` / `accept2-agy-long`、`ai-tui-accept2-agy-multiline` / `accept2-agy-multiline`。确认 no server 后，这 8 个路径都是 uid 1000 的 socket，已按精确路径删除。探测文件已删。目录保留：`/tmp/tmp.vHeRvLN0rC`、`/tmp/tmp.qWr8fCHAOW`、`/tmp/tmp.2D3J1uyved`，以及各 CLI 的 cwd。

WSL 保活仍然未测。

## 第三轮（2026-10-15）

Notion 只读。没有 git commit，没有改全局配置，没有关沙箱，没有改任何 CLI 的权限设置。审批都拒绝，没有选 always allow。新会话都是 `bash -ic 'proxy_on && python3 skills/tmux-tui/scripts/session.py new ...'`，并用目标进程的 `/proc/PID/environ` 核对代理。门禁 `python3 -m unittest discover -s tests -v` 覆盖写入 `docs/test-results.txt`：`Ran 71 tests in 8.404s`，`OK`。

### 0. 清理

`ai-tui-accept2-opencode-multiline` 在本轮开始时已经 no server，输入区无法再 BSpace。`keys --key BSpace` 退出码 1，`cleanup --allow-active` 退出码 1，错误都是 `no server running`。确认 no server 且 socket 属于 uid 1000 后，只删了 `/tmp/tmux-1000/ai-tui-accept2-opencode-multiline`。`ai-tui-accept-agy` 的 server 同样已经不在，socket 文件保留，没有删。

WSL 在 2026-10-15 19:40:43 重启过（当时的 `uptime -s`）。`ai-tui-accept-agy` 和 `ai-tui-accept2-opencode-multiline` 两个 server 随之消失。保活仍然未测。

### 1. 审批重测

探测目录用 `mktemp -d -p "$HOME" aitui-probe-XXXXXX`，不在 cwd，也不在 `/tmp`。请求是在该目录的 `approval-probe.txt` 写入一行 hello。`--prompt` 只用 Python re。测完删除整个探测目录。

| CLI | 第一次（不带 --prompt） | 正则 | 第二次 | 结论 |
|---|---|---|---|---|
| Codex 0.162.1 | `ai-tui-accept3-codex-approve`，cwd `/tmp/tmp.HUMQSzuiYy`，探测目录 `/home/dev/aitui-probe-9qnebp`。`submit-and-wait` 先 `still elapsed_ms=9073`，画面仍是 `Working (8s • esc to interrupt)`。resume 退出码 3：`timeout elapsed_ms=19998`。结束画面：`写入失败：…所在文件系统为只读`。文件不存在。`/status`：Permissions Workspace (granular)。`codex doctor --summary`：`sandbox restricted fs + restricted network · approval OnRequest` | 没有审批画面，写不出锚定正则 | 未做 match 验证 | 该路径未触发审批。沙箱把它表现为只读，文件没写成。doctor 显示 fs 受限且 OnRequest，但这次没有审批框，也没有写入，不记成审批失效 |
| OpenCode 2.0.28 | `ai-tui-accept3-opencode-approve`，cwd `/tmp/tmp.WB1fJoKrUU`，探测目录 `/home/dev/aitui-probe-NLRzHt`。`submit-and-wait` 退出码 0：`still elapsed_ms=11361`。画面 `# Wrote ~/aitui-probe-NLRzHt/approval-probe.txt`，文件内容 `hello\n`。设置只读打开，Permissions 仍是 prompt，没有改，Escape 关闭 | 没有审批画面 | 未做 match 验证。文件和整个探测目录已删 | 该路径未触发审批。画面只写 Permissions prompt，没有写明家目录写入本应被拦住，不升格为审批失效 |
| agy 1.3.5 | `ai-tui-accept3-agy-approve`，cwd `/tmp/tmp.75AsxAX20R`。启动时选中 `> Yes, I trust this folder`，`submit-and-wait` 退出码 0：`still elapsed_ms=686`。信任的是本轮 cwd `/tmp/tmp.75AsxAX20R`。探测目录 `/home/dev/aitui-probe-4llAcJ`。第一次提交退出码 0：`still elapsed_ms=7681`。画面：`Reason: outside workspace`，`Allow creation of this file?`，选项 1 Yes、2 always allow non-workspace、3 No, deny creation。Down 到 `> 3. No, deny creation` 后提交。结果 `User declined the tool call`。文件不存在 | `^Allow creation of this file\?$` | `submit-and-wait --prompt-lines 40` 退出码 0：`reason=prompt elapsed_ms=6818 changed=1 match=approval`。stderr 没有 FutureWarning。再次移到 3 并提交，又是 `User declined the tool call`。文件不存在。探测目录已删 | 通过。拒绝成功，没有选 always allow |

### 2. 取消

请求是写 200 行编号文字，每行一句关于 tmux 的话，不要调用工具，不要改文件。先用 `--timeout-ms 1500` 采样，看到中断提示之前不把 resume 当成结束。

- Codex，`ai-tui-accept3-codex-cancel`，cwd `/tmp/tmp.rK4GKoeEj6`。第一次 `submit-and-wait --timeout-ms 1500` 退出码 0：`still elapsed_ms=638`，画面是排队，没有中断提示。接着 `resume --timeout-ms 1500` 退出码 0：`still elapsed_ms=703`。画面 `Starting MCP servers (1/2): codex_apps (5s • esc to interrupt)`。只发一次 Escape。之后 resume 退出码 0：`still elapsed_ms=18010`。画面 `Conversation interrupted - use /feedback if something went wrong`。`pane_dead=0`。随后「只回复 PONG」得到 `• PONG`。Escape 次数：1。生成在写出 200 行之前停住。结论：通过。
- OpenCode，`ai-tui-accept3-opencode-cancel`，cwd `/tmp/tmp.vNLGzy0O27`。`submit-and-wait --timeout-ms 1500` 退出码 3：`timeout elapsed_ms=1500 changed=1`。页脚 `esc interrupt`。只发一次 Escape，立刻 `capture-pane`，没有 resume。捕获仍是 `esc interrupt` 和 `Thinking`，没有「再按一次」，所以没有发第二次。之后两次 resume 都是退出码 3、约 20 秒。最终画面是第 172–200 行，`pane_dead=0`。随后 PONG 得到 `PONG`。Escape 次数：1。生成没有停。结论：失败。

### 3. OpenCode 多行原文

`ai-tui-accept3-opencode-multiline`，cwd `/tmp/tmp.69afaFP2hk`。启动后 3 秒内接上 pipe-pane。进入输入界面时日志 27505 字节，`2004h` 5 次，`2004l` 0 次，最后是 `2004h`，2026-10-15T19:54:15+08:00。粘贴的是指令行加三行内容（减号行、空行、第四行）。paste 退出码 0，`bytes=134`。输入区是 `[Pasted ~4 lines]`，然后提交。`submit-and-wait` 退出码 0：`still elapsed_ms=8368`。回答里有 `-第二行以减号开头；`、中间空行、`第四行（上面是空行）`。指令行留在用户气泡里，没有再复述一遍。

不带 `--sanitize` 的 `session export ses_ec09600f4ffecJuimaOGRKpM7d` 退出码 0。解码后 `messages[0].text` 原样包含整段（含减号行和空行）；助手文本包含那三行（含空行）。原始 JSON 里空行是转义的 `\n\n`。x.json 已删。关管道后日志 218692 字节，h=5，l=0，最后仍是 `2004h`，LOG 已删。结论：占位符下提交后，回答和未消毒导出都逐字含有减号行和空行。

### 4. OpenCode 长回答

`ai-tui-accept3-opencode-long`，`--height 100`，cwd `/tmp/tmp.7pCuhg2I8S`。请求写 150 行 `行NNN：验收`，NNN 从 001 到 150。提交后 resume 到结束。`alternate_on=1`，`history_size=0`，高度 100。当前屏连续可见 `行062` 到 `行150`，共 89 行，看不到 001–061。

不带 `--sanitize` 的导出 `ses_ec0947724ffesU0IEagtP8f6p3` 退出码 0，7826 字节。解码后有一条字符串含 `行001：验收` 到 `行150：验收`，150 行都在。x.json 已删。结论：超过一屏的完整回答靠未消毒的 `session export`；`--height 100` 的当前屏只保留末尾大约 89 行。

### 保留与清理

本轮 7 个会话都已做完，`cleanup --allow-active` 退出码都是 0。确认 no server 后，只删了这 7 个 uid 1000 的精确 socket。没有保留新的活会话。`/tmp/tmux-1000/ai-tui-accept-agy` 仍在，server 不在。三个家目录探测目录都已删除。

WSL 保活仍然未测。

## 第四轮（2026-10-16）

Notion 仍只读。没有 git commit，没有把 prompt 写进仓库，没有改 tmux / WSL 全局配置，没有关沙箱，没有改任何 CLI 的权限设置。审批都拒绝，没有选 always allow。没有使用 `codex exec`、`opencode --auto` / `--prompt`、`agy --print` / `--dangerously-skip-permissions` / `--mode auto`。同一 pane 串行。新会话都是 `bash -ic 'proxy_on && python3 skills/tmux-tui/scripts/session.py new ...'`。`proxy_on` 退出码 0，输出 `Proxy ON: http://127.0.0.1:7890`。每个目标进程都用 `/proc/PANE_PID/environ` 核对到 `http_proxy`、`https_proxy`、`all_proxy` 和 `NODE_USE_ENV_PROXY=1`。

当天 `uptime -s` 是 `2026-10-16 10:28:56`。这是比第三轮所记 `2026-10-15 19:40:43` 更晚的一次启动。版本复测仍是 Codex 0.162.1、OpenCode 2.0.28、agy 1.3.5。Codex 画面有到 0.163.0 的更新提示，OpenCode 画面有 `/update to install v2.0.30`，都没有执行。

探测目录用 `mktemp -d -p "$HOME" aitui-probe-XXXXXX`。cwd 用 `mktemp -d`。等待默认 `--timeout-ms 20000 --shell-timeout-ms 30000`。本轮信任的目录只有 agy 的 cwd `/tmp/tmp.jDtFux7Kff`。

### 0. prune 第一轮失效 socket

`tmux -L ai-tui-accept-agy ls` 退出码 1：`no server running on /tmp/tmux-1000/ai-tui-accept-agy`。

`session.py prune --socket ai-tui-accept-agy` 退出码 0，stdout：

```json
{"socket": "ai-tui-accept-agy", "removed": true}
```

之后该路径不存在。结论：通过。

### 1. agy 的 prompt-lines

socket `ai-tui-accept4-agy-approve`，session `cli`，pane `%0`，task `accept4-agy-approve`，cwd `/tmp/tmp.jDtFux7Kff`，探测目录 `/home/dev/aitui-probe-o1mXmH`。argv 只有 `/home/dev/.local/bin/agy`。pane 7709 带上述四项代理变量。

`begin` 退出码 3：`reason=timeout elapsed_ms=19990 changed=0`。画面已经是信任提示，选中 `> Yes, I trust this folder`，目录是本轮 cwd。这是审批。用户授权信任这个 mktemp 目录后，`submit-and-wait --received-confirmed` 退出码 0：`reason=still elapsed_ms=690 changed=1`。进入输入界面，版本 1.3.5。没有再改其它设置。

粘贴「在探测目录创建 `approval-probe.txt`，内容一行 hello」。paste 退出码 0，`bytes=97`。提交前原文在输入区。

`submit-and-wait` 只带 `--prompt 'approval=^Allow creation of this file\?$'`，没有 `--prompt-lines`。退出码 0：`reason=still elapsed_ms=5354 changed=1`，不是 prompt。画面有：

```text
Allow creation of this file?
> 1. Yes, allow creation
  2. Yes, and always allow non-workspace access
  3. No, deny creation
```

页脚是 `esc to cancel` 和 `Gemini 3.8 Flash · high`。去掉末尾空行后共 28 行。该问句在第 22 行，最后 4 行是 `3. No, deny creation`、空行、导航提示、页脚。问句不在默认 4 行里。探测目录当时是空的。

两次 Down 后选中 `> 3. No, deny creation`，再 `submit-and-wait` 退出码 0：`reason=still elapsed_ms=679 changed=1`。画面 `User declined the tool call`。没有选 always allow。探测目录仍只有自身，文件不存在。

结论：失败。审批出现了，拒绝也成功，但默认 `--prompt-lines` 没有返回 `match=approval`。问句是去掉末尾空行后的倒数第 7 行。

### 2. Codex 审批

socket `ai-tui-accept4-codex-approve`，cwd `/tmp/tmp.4tyXkjoWDZ`，argv 只有 `/home/dev/.local/bin/codex`。pane 10124 带代理。`begin` 退出码 0：`reason=still elapsed_ms=6831 changed=1`。可输入。页脚 `1 warning`，没有按 f2，没有升级。

粘贴「请只运行这一条命令：curl -sI https://example.com」。paste 退出码 0，`bytes=58`。提交前输入区是这句。`submit-and-wait` 退出码 3：`reason=timeout elapsed_ms=20000 changed=1`。没有审批框。摘录：

```text
• 我会只运行这条命令。

• Failed (exit 7) curl -sI https://example.com
  └ (no output)

• 已运行该命令，没有输出。

  Worked for 16s • 10:47 AM
```

输入区已恢复。命令在画面上显示为已运行，退出码 7，没有输出。没有据此改写原因。

随后粘贴 `/status`，paste 退出码 0，`bytes=7`。`submit-and-wait` 退出码 0：`reason=still elapsed_ms=624 changed=1`。摘录：`Model: GPT-6.1-Sol (reasoning low)`，`Directory: /tmp/tmp.4tyXkjoWDZ`，`Permissions: Workspace (granular)`。账号邮箱不写入本文。

结论：未知（没有审批框，做不了 match 验证）。画面表明命令已执行并得到 exit 7。

### 3. OpenCode 审批

socket `ai-tui-accept4-opencode-approve`，cwd `/tmp/tmp.cJoKgIW558`，探测目录 `/home/dev/aitui-probe-HtDbRN`。argv 只有 `/home/dev/.opencode/bin/opencode`。pane 12158 带代理。右下角仍是 `2.0.28`。`begin` 退出码 3：`reason=timeout elapsed_ms=20000 changed=0`，画面已是可输入界面。

粘贴「请用 shell 执行 touch /home/dev/aitui-probe-HtDbRN/x」。paste 退出码 0，`bytes=80`。提交前原文在输入区。`submit-and-wait` 退出码 0：`reason=still elapsed_ms=9080 changed=1`。没有审批框。摘录：

```text
$ touch /home/dev/aitui-probe-HtDbRN/x
(no output)
已执行。
```

当时文件存在。随后删除该文件，探测目录留到收尾。本轮没有打开设置，没有改 Permissions。第三轮读到的值仍是 prompt；这里只记录又一次没有审批框就写成了文件。

结论：未知（没有审批框，做不了 match 验证）。文件曾被创建，已删除。

### 4. OpenCode 取消

socket `ai-tui-accept4-opencode-cancel`，cwd `/tmp/tmp.pskfFxYIwV`。pane 14220 带代理。粘贴「写 200 行编号文字，每行一句关于 tmux 的话，不要调用工具，不要改文件」。paste 退出码 0，`bytes=98`。提交前原文在输入区。

`submit-and-wait --timeout-ms 1500 --shell-timeout-ms 30000` 退出码 3：`reason=timeout elapsed_ms=1500 changed=1`。页脚有 `esc interrupt`。然后一次调用 `keys --key Escape --key Escape`，退出码 0，`reason=keys`。立刻 `capture-pane -p`：已经写到第 28 行附近，末行是「使用」，页脚仍是 `esc interrupt`。

`resume --timeout-ms 20000` 退出码 3：`reason=timeout elapsed_ms=20000 changed=1`。画面约在第 118 行，仍是 `esc interrupt`。再 `resume` 退出码 0：`reason=still elapsed_ms=11054 changed=1`。结尾是第 200 行，统计 `Build · Muse Spark 1.3 Free · 53.8s`，没有 Interrupted。

随后粘贴「只回复一行：PONG」。paste 退出码 0，`bytes=64`。`submit-and-wait` 退出码 0：`reason=still elapsed_ms=3086 changed=1`。回答是 `PONG`。

结论：失败。连按两次 Escape 没有停下生成，200 行写完。会话随后仍能回答 PONG。

### 5. 收尾

四个会话都 `cleanup --allow-active`，退出码都是 0，`cleaned: true`。随后 `tmux -L` 都是 no server（退出码 1）。再 `prune`，退出码都是 0，stdout 都是 `{"socket": NAME, "removed": true}`。四个 socket 文件都不在。分别是 `ai-tui-accept4-agy-approve`、`ai-tui-accept4-codex-approve`、`ai-tui-accept4-opencode-approve`、`ai-tui-accept4-opencode-cancel`。

探测目录 `/home/dev/aitui-probe-o1mXmH` 和 `/home/dev/aitui-probe-HtDbRN` 已删除。cwd 仍留在 `/tmp`：`/tmp/tmp.jDtFux7Kff`、`/tmp/tmp.4tyXkjoWDZ`、`/tmp/tmp.cJoKgIW558`、`/tmp/tmp.pskfFxYIwV`。没有保留活会话。

WSL 保活仍然未测。
