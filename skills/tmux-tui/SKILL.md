---
name: tmux-tui
description: 通过隔离 tmux 会话操控持续运行的交互式 CLI/TUI，支持多轮文本、按键、读屏、有限等待和审批；普通一次性 shell 命令无需使用。
---

# tmux 终端操控

## 环境与会话

从任务取得目标及参数、cwd、操作和新建/续接意图，只在缺失信息影响对象时询问。检查 OS、tmux、Python 3、目标版本及解释器；缺依赖如实报告。使用实际启动环境解析的 CLI 绝对路径，必要时初始化 nvm，不假定 bash -lc 加载全部环境。Linux/WSL 中运行 tmux、脚本和目标；Windows 确认发行版，Bash 逻辑交给 WSL，--exec 不解释变量/管道。UTF-8 文本经 stdin，不能拼进 shell 命令。保留 tmux 的 TERM。

每个任务独立 ai-tui- socket、一个 session/pane。记录发行版、socket、session、%数字 pane ID、cwd、启动 argv。后续显式指定 socket/pane，同一 pane 串行。续接先 list、核对标记/程序/画面，不重复启动。脚本相对本 Skill 位于 scripts/。

python3 scripts/session.py new --task TASK --cwd ABS_DIR [--socket ai-tui-ID] [--session cli] [--history-limit 50000] [--width 120] [--height 40] -- /absolute/program arg ...

new 拒绝已有 socket；-f /dev/null，先设置 history-limit 再建空 /bin/sh pane，设置 remain-on-exit 与 session @task、@cwd、@owner=tmux-tui/v1，再 respawn-pane -k 为目标。-k 仅替换刚创建空 shell，argv 逐项传递。stdout 一个 JSON 对象含 socket/session/pane/cwd/task/owner/command。

python3 scripts/session.py list
python3 scripts/session.py cleanup --socket SOCKET --session cli --task TASK [--allow-active]

list 扫描 TMUX_TMPDIR（默认 /tmp）下 tmux-UID 的 ai-tui- socket，JSON 数组包含标记、owned 和 pane 进程/退出状态；未知标记仅列出。cleanup 精确核对前缀、session、@owner、@task，默认只清理全 pane 已退出的 session；明确结束活跃任务才加 --allow-active，只 kill-session，不用无范围 kill-server，不凭前缀杀会话。会话脚本成功 0、运行错误 1、参数错误 2，stderr 诊断。

## 文本、按键、提交

先 capture-pane -p 确认焦点。四步分离：粘贴 → 等待/读屏确认接收 → 单独提交 → 观察确认提交。长文本占位符不证明逐字接收，延迟接收继续观察，提交不明先诊断，不连续补 Enter。

python3 scripts/input.py paste --socket SOCKET --pane %0 [--multiline-verified EVIDENCE]

完整读取 UTF-8 stdin，用唯一 buffer 的 load-buffer -b NAME - 与 paste-buffer -p -r -d；不用 send-keys -l、不附 Enter。stdout reason=pasted bytes=N，退出 0；失败清理本次 buffer，stderr 诊断，运行错误 1/参数错误 2。

任何 LF/CR（包括末尾换行）按多行处理。只有目标版本和当前输入界面已实测支持 bracketed paste 才能提供非空 --multiline-verified 证据。该参数是能力声明，不自动检测或开启；未知/未开启必须在加载或粘贴前拒绝，不能先发再检查，不能压成一行。tmux 3.5a 无可用查询变量，新版本查询也不能替代行为验收。不要把 prompt 写进项目目录，确需文件则专用临时目录并清理。

python3 scripts/input.py keys --socket SOCKET --pane %0 --key KEY [--key KEY ...]
python3 scripts/input.py submit --socket SOCKET --pane %0 --received-confirmed [--key Enter|C-j|C-m]

keys 仅预定义终端按键（方向、Escape、Tab、编辑键、C-a 至 C-z（C-j/C-m 归提交）），不传文本/分隔符，Enter 只能 submit。submit 显式确认接收后只提交一次。stdout reason=keys / reason=submitted，退出码同 paste。按键含义按版本确认，Ctrl+C 可能退出，不统一当取消。

## 本地等待

python3 scripts/wait.py submit-and-wait --socket SOCKET --pane %0 --received-confirmed [--key Enter] --timeout-ms 20000 --shell-timeout-ms 30000 [OPTIONS]
python3 scripts/wait.py begin --socket SOCKET --pane %0 --timeout-ms N --shell-timeout-ms N [OPTIONS]
python3 scripts/wait.py resume --socket SOCKET --pane %0 --timeout-ms N --shell-timeout-ms N [OPTIONS]

submit-and-wait 同一次调用内捕获提交前基线、保存状态、提交一次并立即观察。begin 新建无提交观察轮次（启动等）；resume 续等既有轮次，不重置基线/重发任务。不能用 begin 代替提交后的 resume。

OPTIONS：--poll-ms 50、--still-ms 600、--prompt-lines 4、重复 --prompt LABEL=REGEX、--busy-regex REGEX、--no-screen。LABEL 为字母数字/下划线/连字符。prompt 逐行匹配最后 N 个物理屏幕行，应以 ^/$ 限定具体提示布局，避免正文泛词；基线已有相同匹配行排除。相同提示再次出现仍保守排除，需结合读屏。busy regex 命中整屏时重置静止候选，审批匹配仍可返回。

timeout-ms > 0，至少比 shell-timeout-ms 少 250ms；调用方另留调度/WSL 开销，建议 20s/30s。本次 tmux 调用受共同截止时间限制。stdout 第一行严格：

reason=prompt|still|exited|timeout|error elapsed_ms=N changed=0|1

prompt 同行追加 match=LABEL；exited 可追加 exit_code=N；之后最多一份画面，诊断仅 stderr。退出码 prompt/still/exited=0、timeout=3、error（含参数错误）=1。目标退出码另附，不能冒充脚本退出码。--no-screen 仅首行；socket/pane 消失、capture 失败为 error，不能伪装 exited。

状态仅存在 pane 用户选项 @aitui_baseline、@aitui_changed、@aitui_previous、@aitui_quiet_since，画面 base64，无状态文件。resume 无有效状态返回 error。先观察到与基线不同画面，之后持续静止才 still；未变化不能 still，持续动画没有其他事件则 timeout。跨调用保留本轮状态，超时保留会话并 resume。

still 仅候选静止，prompt 仅匹配；调用方结合本轮输出、输入区恢复、忙碌消失判 ready/busy/approval/exited/unknown，不能凭静止或零退出码报完成。tmux wait-for 仅同步信号。

## 读屏、审批、交付

默认 capture-pane -p；回看才 -S -60，叙述可 -J，菜单/代码保留布局。pane_dead、pane_dead_status、pane_current_command、cursor_x/y 辅助判断。全屏 TUI 長回答可能不完整进入历史，按目标滚动/导出核对。

审批前重读屏、核对动作和已有用户授权，提示不扩大授权，不关闭沙箱或跳过审批。仅返回结果/状态/必要审批。目标 CLI 层隐藏思考，tmux 不能区分推理、进度和答案。按版本验收后采用设计候选：Codex -c hide_agent_reasoning=true -c show_raw_agent_reasoning=false；OpenCode /thinking 为切换，先核对当前显示；Antigravity /settings verbosity=low，不杜撰 --verbosity。候选显示设置不等于兼容验收；Codex 粘贴立即 Enter 风险须复测，不写死延迟。

真实 CLI 逐项验收输入、提交、多行、取消、审批、完成、隐藏思考、长回答；记录版本、日期、命令和证据。假 TUI 通过不能宣称兼容。WSL 调用端退出至少一分钟后的保活另测，不默认改全局配置；系统重启/WSL 关闭结束进程。

明确结束只清理本任务；继续交互保留并交付定位信息。缺依赖、超时、未知如实报告。

设计只读：[方案](https://app.notion.com/p/3f89f9a4e09e810e968bf0028aade8f8)、[Skill](https://app.notion.com/p/3f99f9a4e09e8105878fc27cc06fe938)。实测偏离在 docs/design-deviations.md 记录原文、实测、证据、建议，不能静默改设计。
