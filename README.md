# tmux-terminal-control

隔离 tmux 会话的终端操控工具：Agent Skill、Python 标准库辅助脚本、假 TUI 和 unittest。只读设计：[方案](https://app.notion.com/p/3f89f9a4e09e810e968bf0028aade8f8)、[Skill](https://app.notion.com/p/3f99f9a4e09e8105878fc27cc06fe938)。

## 安装

Linux/WSL 安装 Python 3 和 tmux（基准 3.5a），Debian 可 sudo apt-get install tmux python3，无 pip 依赖。整个 skills/tmux-tui 目录可安装至宿主的 skills 目录。脚本、tmux、目标处于同一环境，保留 TERM。Windows 从 wsl -d YOUR_DISTRO --cd /absolute/repo --exec python3 ... 调用；UTF-8 文本通过 stdin，不拼进命令字符串。CLI 用绝对路径，注意登录 Bash 与 --exec PATH 差异，见 [环境](docs/environment.md)。

## 接口（从仓库根目录调用）

| 脚本 / 子命令 | 参数与行为 | stdout / 退出码 |
|---|---|---|
| skills/tmux-tui/scripts/input.py paste | --socket、--pane；UTF-8 stdin，LF/CR 要求 --multiline-verified EVIDENCE，否则发送前拒绝；唯一 buffer、load-buffer + paste-buffer -p -r -d | reason=pasted bytes=N；成功 0、错误 1、参数错误 2 |
| input.py keys | --socket、--pane、重复 --key；预定义按键，Enter 禁用 | reason=keys；同上 |
| input.py submit | --socket、--pane、--received-confirmed；--key Enter/C-j/C-m（默认 Enter），只提交一次 | reason=submitted；同上 |
| skills/tmux-tui/scripts/wait.py submit-and-wait | --socket、--pane、--received-confirmed、--timeout-ms、--shell-timeout-ms；先基线后提交/观察，--key Enter/C-j/C-m | 0 prompt/still/exited、3 timeout、1 error/参数错误 |
| wait.py begin / resume | 同等待参数，begin 建无提交轮次，resume 续等、不重发 | 同上 |
| skills/tmux-tui/scripts/session.py new | --task、--cwd 必填；--socket 默认唯一 ai-tui- 名、--session cli、--history-limit 50000、--width 120、--height 40，-- 后绝对程序路径及 argv | JSON 对象含 socket/session/pane/cwd/task/owner/command；0/1/2 |
| session.py list | 扫描 TMUX_TMPDIR（默认 /tmp）下 tmux-UID 的 ai-tui- sockets，含 owned、任务和进程状态 | JSON 数组；0/1/2 |
| session.py cleanup | --socket、--session、--task；默认只清理已退出，明确结束活跃任务用 --allow-active | JSON 对象；0/1/2 |
| session.py prune | --socket 一个精确 ai-tui- 名称；只删除已确认 ConnectionRefused 的当前用户 socket，不能替代 cleanup | JSON 对象 `{"socket","removed":true}`；0/1/2 |

等待共用 --poll-ms 50、--still-ms 600、--prompt-lines 4、重复 --prompt LABEL=REGEX、--busy-regex REGEX、--no-screen。LABEL 是字母数字/下划线/连字符。--prompt-lines 从最后一个非空行往上数 N 个物理行，中间空行照常计数，末尾全是空白行时区域为空。--prompt 与 --busy-regex 使用 Python re；会触发警告的正则按参数错误处理，退出码 1，不提交。prompt 在这 N 行上逐行匹配，使用 ^/$ 和具体布局，用整个基线排除旧提示；busy regex 命中不积累静止时间。

第一行严格 reason=prompt|still|exited|timeout|error elapsed_ms=N changed=0|1；prompt 追加 match=LABEL，exited 可追加 exit_code=N。之后最多一份画面，stderr 诊断。所有 tmux 调用受共同截止时间限制，timeout-ms 必须至少比 shell-timeout-ms 短 250ms，建议 20s/30s，额外留 WSL 开销。

轮次只存 pane @aitui_baseline、@aitui_changed、@aitui_previous、@aitui_quiet_since，无状态文件；resume 要求已有有效状态。先看到基线变化后静止才 still；still/prompt 不是完成证明。socket/pane/capture 消失返回 error。

## 用法

    python3 skills/tmux-tui/scripts/session.py new --socket ai-tui-demo --task demo --cwd "$PWD" -- /absolute/cli
    printf '%s' '用户文本;' | python3 skills/tmux-tui/scripts/input.py paste --socket ai-tui-demo --pane %0
    tmux -L ai-tui-demo capture-pane -p -t %0
    # 确认已接收，调用方 Shell 超时 30 秒，才提交：
    python3 skills/tmux-tui/scripts/wait.py submit-and-wait --socket ai-tui-demo --pane %0 --received-confirmed --timeout-ms 20000 --shell-timeout-ms 30000 --prompt 'approval=^APPROVAL: .+$' --busy-regex '^BUSY'
    # 超时后续等，不重发 Enter：
    python3 skills/tmux-tui/scripts/wait.py resume --socket ai-tui-demo --pane %0 --timeout-ms 20000 --shell-timeout-ms 30000
    python3 skills/tmux-tui/scripts/session.py list
    python3 skills/tmux-tui/scripts/session.py cleanup --socket ai-tui-demo --session cli --task demo
    # 确认 no server 后，才可删除这一个失效 socket：
    python3 skills/tmux-tui/scripts/session.py prune --socket ai-tui-demo

粘贴 → 等待/读屏确认接收 → 单独提交 → 确认提交。多行能力必须按目标版本/界面实测并给 --multiline-verified 证据；参数不自动开启 paste。tmux 3.5a 无查询变量。未确认提交先诊断，不补 Enter。

new 用 -f /dev/null、pane 创建前 history-limit、空 shell → remain-on-exit → respawn，@owner=tmux-tui/v1、@task、@cwd。cleanup 核对标记和精确目标，不用无范围 kill-server。

## 测试

    python3 -m unittest discover -s tests -v

每例独立 socket、系统临时目录日志，结束清理；依赖缺失报错，不能跳过。覆盖原样输入、多行、单次提交、等待、续等、输出与隔离，不改真实 CLI 沙箱/审批。完整操作规则见 [SKILL.md](skills/tmux-tui/SKILL.md)。逐项覆盖见 [test-coverage.md](docs/test-coverage.md)，本机输出见 [test-results.txt](docs/test-results.txt)。

## 已知限制与版本验收

轮询可能错过两次采样间的瞬时变化；prompt 依赖区域/具体 regex，基线相同提示再次出现保守排除，正文泛词不可靠。多行能力由调用方声明，不能检测声明失真。同一 pane 必须串行。服务器退出后可能残留失效 socket，list 会报告 error。prune 只删除一个已确认 ConnectionRefused 的精确名称，不凭前缀删除不明端点，也不能替代 cleanup。测试只删除自己创建的精确 UUID 端点。长回答用该版本已验收的捕获或导出；静止不是任务完成。没出现审批框不等于操作被禁止。

真实 CLI 需人工逐项检查输入、提交、多行、取消、审批、完成、隐藏思考、长回答，记录系统/WSL/tmux/CLI 版本、日期、命令/配置、证据，升级后重测。下表是四轮之后的最终结论。不关闭审批/沙箱。

| 对象与版本 | 环境 / 日期 | 覆盖与结论 | 证据 |
|---|---|---|---|
| 假 TUI / tmux 3.5a / Python 3.13.5 | Debian 13.7 / WSL 2，2026-10-16 | 自动化 80 项通过、0 跳过。只说明假 TUI，不是真实 CLI 兼容 | docs/test-results.txt |
| Codex CLI 0.162.1 | 同上，tmux 3.5a | 可输入。单行提交得到 PONG。粘贴后立刻 Enter 未卡死，结论只限这一组合。多行输入区显示原文。`esc to interrupt` 时按一次 Escape 能停。长回答用 `--no-alt-screen` 加 `capture-pane -p -S -`。两个 `-c` 没有隐藏效果，并多一条 embedded mode 警告。家目录写入没有审批框，文件未创建。`curl -sI https://example.com` 没有审批框，画面为 Failed (exit 7)、无输出。`/status` 为 Workspace (granular)。保活未测 | docs/cli-acceptance.md |
| OpenCode 2.0.28 | 同上 | 可输入。单行提交得到 PONG。多行只显示 `[Pasted ~N lines]`，提交后未消毒导出含原文。一次 Escape，以及一次调用连发两次 Escape，生成都没有停。长回答用未消毒的 `session export`；高度 100 装不下 150 行。Thinking 用命令面板里的 hide/show。第三轮 Permissions=prompt 时没有审批框就写了家目录文件；第四轮 touch 探测文件同样没有审批框，文件已创建。保活未测 | docs/cli-acceptance.md |
| agy 1.3.5 | 同上 | 信任目录提示属于审批，明确授权后可输入。多行输入区显示原文。`esc to cancel` 时按一次 Escape 能停。40 行答案用加高 pane 能看到。Thought 行用 `/config` 的 Verbosity low 隐藏，用完改回。创建工作区外文件会弹出 `Allow creation of this file?`，锚定正则 `^Allow creation of this file\?$`。第三轮 `--prompt-lines 40` 返回 match。第四轮默认 4 行时该行是去掉末尾空行后的倒数第 7 行，返回 still；拒绝后文件不存在。保活未测 | docs/cli-acceptance.md |

Windows/WSL 调用端退出至少一分钟后的保活待测，不用 Linux 假 TUI 通过替代，不改全局保活配置。设计偏离见 [docs/design-deviations.md](docs/design-deviations.md)。

### 待办

1. agy 审批的提示区域：1.3.5 的审批问句在去掉末尾空行后的倒数第 7 行，默认 --prompt-lines 4 返回 still。待用 --prompt-lines 8 复测；通过后同步更新 SKILL.md 和 Notion Skill 页里的「待验证」。
2. WSL 保活：Windows 调用端的 wsl.exe 退出至少一分钟后，会话是否仍在，待人工测试。2026-10-15 19:40:43 WSL 重启时，已有会话全部消失，符合「WSL 关闭会结束进程」。
3. 已确认不可用或无法验证，不再补测，升级后复测：
   - OpenCode 2.0.28：Escape（一次，或一次调用连发两次）不能取消生成。
   - Codex 0.162.1：四轮都没有出现审批框，审批匹配无法验证。
   - OpenCode 2.0.28：Permissions=prompt 时没有审批框就写了工作区外文件。这是目标 CLI 的行为，不是本工具的问题。


### 假 TUI 演练

日志放系统临时目录。用会话返回的 pane ID 替换 %0，先 capture 确认启动，再 paste，核对日志/画面后 submit-and-wait。目标支持 --bracketed-paste on/off、--mode unchanged/still/animation/approval/body/quote/stale/busy/exit、接收/响应延迟和 --ignore-submit。

    logdir=$(mktemp -d)
    python3 skills/tmux-tui/scripts/session.py new --socket ai-tui-practice --task practice --cwd "$PWD" -- /usr/bin/python3 "$PWD/tests/fake_tui.py" --log "$logdir/input.jsonl" --mode approval

仅对该假 TUI 已开启的 bracketed paste 界面使用 --multiline-verified 'fake_tui/v1 paste on, verified by tests'。日志事件 raw（data_b64）、paste（text_b64）和 submit（count/text_b64）供核对，paste 不等于 submit。保留日志诊断后再 cleanup；活跃演练明确结束才加 --allow-active。

目标程序单参数时 tmux 会解释成 shell command。session.py 用 Python 的 os.execv 启动器逐项传递 argv，随后替换为目标，不把程序路径/参数拼进 shell 文本。创建成功只证明会话已建，不证明目标启动成功，必须读屏/查 pane_dead；启动失败画面保留。
