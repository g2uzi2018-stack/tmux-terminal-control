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

等待共用 --poll-ms 50、--still-ms 600、--prompt-lines 4、重复 --prompt LABEL=REGEX、--busy-regex REGEX、--no-screen。LABEL 是字母数字/下划线/连字符；prompt regex 最后 N 个物理行逐行匹配，使用 ^/$ 和具体布局，排除基线相同匹配行；busy regex 命中不积累静止时间。

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

粘贴 → 等待/读屏确认接收 → 单独提交 → 确认提交。多行能力必须按目标版本/界面实测并给 --multiline-verified 证据；参数不自动开启 paste。tmux 3.5a 无查询变量。未确认提交先诊断，不补 Enter。

new 用 -f /dev/null、pane 创建前 history-limit、空 shell → remain-on-exit → respawn，@owner=tmux-tui/v1、@task、@cwd。cleanup 核对标记和精确目标，不用无范围 kill-server。

## 测试

    python3 -m unittest discover -s tests -v

每例独立 socket、系统临时目录日志，结束清理；依赖缺失报错，不能跳过。覆盖原样输入、多行、单次提交、等待、续等、输出与隔离，不改真实 CLI 沙箱/审批。完整操作规则见 [SKILL.md](skills/tmux-tui/SKILL.md)。逐项覆盖见 [test-coverage.md](docs/test-coverage.md)，本机输出见 [test-results.txt](docs/test-results.txt)。

## 已知限制与版本验收

轮询可能错过两次采样间的瞬时变化；prompt 依赖区域/具体 regex，基线相同提示再次出现保守排除，正文泛词不可靠。多行能力由调用方声明，不能检测声明失真。同一 pane 必须串行。全屏长回答可能不入历史，需目标滚动/导出；静止不是任务完成。

真实 CLI 需人工逐项检查输入、提交、多行、取消、审批、完成、隐藏思考、长回答，记录系统/WSL/tmux/CLI 版本、日期、命令/配置、证据，升级后重测。设计的 CLI 显示设置仅为候选，不承诺行为兼容。不关闭审批/沙箱。

| 对象与版本 | 环境 / 日期 | 覆盖与结论 | 证据 |
|---|---|---|---|
| tmux 3.5a / Python 3.13.5 / 假 TUI | Debian 13.7 / WSL 2，2026-10-14 | 本机 70 项自动化测试通过，0 跳过；仅假 TUI | docs/test-results.txt |
| Codex CLI 0.162.1 | Debian 13 / WSL 2，2026-10-14 | 已执行 --version；TUI 待人工验收 | docs/environment.md |
| OpenCode 2.0.28 | 同上 | 已执行 --version；TUI 待人工验收 | docs/environment.md |
| Antigravity | 同上 | WSL PATH 未安装；待验收 | docs/environment.md |

Windows/WSL 调用端退出至少一分钟后的保活待测，不用 Linux 假 TUI 通过替代，不改全局保活配置。设计偏离见 [docs/design-deviations.md](docs/design-deviations.md)。


### 假 TUI 演练

日志放系统临时目录。用会话返回的 pane ID 替换 %0，先 capture 确认启动，再 paste，核对日志/画面后 submit-and-wait。目标支持 --bracketed-paste on/off、--mode unchanged/still/animation/approval/body/quote/stale/busy/exit、接收/响应延迟和 --ignore-submit。

    logdir=$(mktemp -d)
    python3 skills/tmux-tui/scripts/session.py new --socket ai-tui-practice --task practice --cwd "$PWD" -- /usr/bin/python3 "$PWD/tests/fake_tui.py" --log "$logdir/input.jsonl" --mode approval

仅对该假 TUI 已开启的 bracketed paste 界面使用 --multiline-verified 'fake_tui/v1 paste on, verified by tests'。日志事件 raw（data_b64）、paste（text_b64）和 submit（count/text_b64）供核对，paste 不等于 submit。保留日志诊断后再 cleanup；活跃演练明确结束才加 --allow-active。

目标程序单参数时 tmux 会解释成 shell command。session.py 用 Python 的 os.execv 启动器逐项传递 argv，随后替换为目标，不把程序路径/参数拼进 shell 文本。创建成功只证明会话已建，不证明目标启动成功，必须读屏/查 pane_dead；启动失败画面保留。
