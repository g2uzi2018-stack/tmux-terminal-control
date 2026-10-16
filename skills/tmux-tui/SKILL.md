---
name: tmux-tui
description: 通过隔离 tmux 会话操控持续运行的交互式 CLI/TUI，支持多轮文本、按键、读屏、有限等待和审批；普通一次性 shell 命令无需使用。
---

# tmux 终端操控

## 环境与会话

从任务取得目标及参数、cwd、操作和新建/续接意图，只在缺失信息影响对象时询问。检查 OS、tmux、Python 3、目标版本及解释器；缺依赖如实报告。使用实际启动环境解析的 CLI 绝对路径，必要时初始化 nvm，不假定 bash -lc 加载全部环境。Linux/WSL 中运行 tmux、脚本和目标；Windows 确认发行版，Bash 逻辑交给 WSL，--exec 不解释变量/管道。UTF-8 文本经 stdin，不能拼进 shell 命令。保留 tmux 的 TERM。目标需要代理或其他环境变量时，在启动 tmux server 的同一条命令里导出，再用该 pane 进程的 /proc/PANE_PID/environ 核对；只看 tmux show-environment 不够。具体开关和地址不写在这里。

每个任务独立 ai-tui- socket、一个 session/pane。记录发行版、socket、session、%数字 pane ID、cwd、启动 argv。后续显式指定 socket/pane，同一 pane 串行。续接先 list、核对标记/程序/画面，不重复启动。脚本相对本 Skill 位于 scripts/。

python3 scripts/session.py new --task TASK --cwd ABS_DIR [--socket ai-tui-ID] [--session cli] [--history-limit 50000] [--width 120] [--height 40] -- /absolute/program arg ...

new 拒绝已有 socket；-f /dev/null，先设置 history-limit 再建空 /bin/sh pane，设置 remain-on-exit 与 session @task、@cwd、@owner=tmux-tui/v1，再 respawn-pane -k 为目标。-k 仅替换刚创建空 shell，argv 逐项传递。stdout 一个 JSON 对象含 socket/session/pane/cwd/task/owner/command。

python3 scripts/session.py list
python3 scripts/session.py cleanup --socket SOCKET --session cli --task TASK [--allow-active]
python3 scripts/session.py prune --socket SOCKET

list 扫描 TMUX_TMPDIR（默认 /tmp）下 tmux-UID 的 ai-tui- socket，JSON 数组包含标记、owned 和 pane 进程/退出状态；未知标记仅列出。cleanup 精确核对前缀、session、@owner、@task，默认只清理全 pane 已退出的 session；明确结束活跃任务才加 --allow-active，只 kill-session，不用无范围 kill-server，不凭前缀杀会话。prune 只处理一个精确 ai-tui- 名称，路径固定为上述目录下的这个名字，不扫描、不通配。lstat 必须是当前用户拥有的 socket；用 AF_UNIX connect，只有 ConnectionRefusedError 才算失效。能连上就报错并改用 cleanup，其他 OSError 不删除。删除前再 lstat，inode 不变才 unlink。stdout 为 {"socket","removed":true}。prune 不能替代 cleanup。会话脚本成功 0、运行错误 1、参数错误 2，stderr 诊断。

## 文本、按键、提交

先 capture-pane -p 确认焦点。四步分离：粘贴 → 等待/读屏确认接收 → 单独提交 → 观察确认提交。长文本占位符不证明逐字接收，延迟接收继续观察，提交不明先诊断，不连续补 Enter。

python3 scripts/input.py paste --socket SOCKET --pane %0 [--multiline-verified EVIDENCE]

完整读取 UTF-8 stdin，用唯一 buffer 的 load-buffer -b NAME - 与 paste-buffer -p -r -d；不用 send-keys -l、不附 Enter。stdout reason=pasted bytes=N，退出 0；失败清理本次 buffer，stderr 诊断，运行错误 1/参数错误 2。

任何 LF/CR（包括末尾换行）按多行处理。只有目标版本和当前输入界面已实测支持 bracketed paste 才能提供非空 --multiline-verified 证据。该参数是能力声明，不自动检测或开启；未知/未开启必须在加载或粘贴前拒绝，不能先发再检查，不能压成一行。tmux 3.5a 无可用查询变量，新版本查询也不能替代行为验收。证据做法：用 /bin/sh -c 'sleep N; exec "$0" "$@"' 包一层启动，sleep 期间接上 pipe-pane -O；在原始输出里找最后一次 ESC[?2004h 或 ESC[?2004l，最后是 2004h 才算证据。测完关掉管道并删除日志。探测文本第一行写「原样复述，不要调用工具，不要改文件」。已验收于 Codex 0.162.1、agy 1.3.5：输入区显示原文。已验收于 OpenCode 2.0.28：只显示 [Pasted ~N lines]，提交后用不带 --sanitize 的 session export 核对原文。升级后复测。不要把 prompt 写进项目目录，确需文件则专用临时目录并清理。

python3 scripts/input.py keys --socket SOCKET --pane %0 --key KEY [--key KEY ...]
python3 scripts/input.py submit --socket SOCKET --pane %0 --received-confirmed [--key Enter|C-j|C-m]

keys 仅预定义终端按键（方向、Escape、Tab、编辑键、C-a 至 C-z（C-j/C-m 归提交）），不传文本/分隔符，Enter 只能 submit。submit 显式确认接收后只提交一次。stdout reason=keys / reason=submitted，退出码同 paste。按键含义按版本确认。不要统一用 Ctrl+C 当取消，它可能退出进程。已验收于 Codex 0.162.1：画面出现 esc to interrupt 时按一次 Escape。已验收于 agy 1.3.5：画面出现 esc to cancel 时按一次 Escape。已验收于 OpenCode 2.0.28：画面出现 esc interrupt 后，一次 keys 调用连发两次 Escape，生成没有停，随后写完。升级后复测。

## 本地等待

python3 scripts/wait.py submit-and-wait --socket SOCKET --pane %0 --received-confirmed [--key Enter] --timeout-ms 20000 --shell-timeout-ms 30000 [OPTIONS]
python3 scripts/wait.py begin --socket SOCKET --pane %0 --timeout-ms N --shell-timeout-ms N [OPTIONS]
python3 scripts/wait.py resume --socket SOCKET --pane %0 --timeout-ms N --shell-timeout-ms N [OPTIONS]

submit-and-wait 同一次调用内捕获提交前基线、保存状态、提交一次并立即观察。begin 新建无提交观察轮次（启动等）；resume 续等既有轮次，不重置基线/重发任务。不能用 begin 代替提交后的 resume。

OPTIONS：--poll-ms 50、--still-ms 600、--prompt-lines 4、重复 --prompt LABEL=REGEX、--busy-regex REGEX、--no-screen。LABEL 为字母数字/下划线/连字符。--prompt-lines 从最后一个非空行往上数 N 个物理行；中间空行照常计数，只有去掉末尾空白行后没有剩余行时区域才为空。prompt 在这 N 行上逐行匹配，应以 ^/$ 限定具体提示布局，避免正文泛词。旧提示用整个基线排除，不是只用这 N 行；相同提示再次出现仍保守排除，需结合读屏。--prompt 与 --busy-regex 使用 Python re。编译时出现 Warning（含 POSIX 字符类的 FutureWarning）与 re.error 一样按参数错误处理：reason=error，退出码 1，不提交。busy regex 命中整屏时重置静止候选，审批匹配仍可返回。

timeout-ms > 0，至少比 shell-timeout-ms 少 250ms；调用方另留调度/WSL 开销，建议 20s/30s。本次 tmux 调用受共同截止时间限制。stdout 第一行严格：

reason=prompt|still|exited|timeout|error elapsed_ms=N changed=0|1

prompt 同行追加 match=LABEL；exited 可追加 exit_code=N；之后最多一份画面，诊断仅 stderr。退出码 prompt/still/exited=0、timeout=3、error（含参数错误）=1。目标退出码另附，不能冒充脚本退出码。--no-screen 仅首行；socket/pane 消失、capture 失败为 error，不能伪装 exited。

状态仅存在 pane 用户选项 @aitui_baseline、@aitui_changed、@aitui_previous、@aitui_quiet_since，画面 base64，无状态文件。resume 无有效状态返回 error。先观察到与基线不同画面，之后持续静止才 still；未变化不能 still，持续动画没有其他事件则 timeout。跨调用保留本轮状态，超时保留会话并 resume。

still 仅候选静止，prompt 仅匹配；调用方结合本轮输出、输入区恢复、忙碌消失判 ready/busy/approval/exited/unknown，不能凭静止或零退出码报完成。tmux wait-for 仅同步信号。

## 读屏、审批、交付

默认 capture-pane -p；回看才 -S -60，叙述可 -J，菜单/代码保留布局。pane_dead、pane_dead_status、pane_current_command、cursor_x/y 辅助判断。长回答不要把当前屏当成全文。已验收于 Codex 0.162.1：启动加 --no-alt-screen，再用 capture-pane -p -S -。已验收于 OpenCode 2.0.28：用 opencode session export ID，不要加 --sanitize（它会遮掉正文）；导出放临时目录，用完删除。加高 pane 只对装得下一屏的回答有效；同一版本实测 150 行装不进高度 100 的当前屏。升级后复测。

审批前重读屏、核对动作和已有用户授权，提示不扩大授权，不关闭沙箱或跳过审批。没出现审批框不等于操作被禁止，执行后要核对实际结果。探测路径不要放 /tmp，很多沙箱默认允许写 /tmp。agy 首次启动的信任目录提示属于审批，只有用户明确授权该目录才能确认。已验收于 agy 1.3.5：创建工作区外文件的锚定正则是 ^Allow creation of this file\?$。第三轮加 --prompt-lines 40 时返回 match=approval。第四轮只用这条正则、不加 --prompt-lines，该行是去掉末尾空行后的倒数第 7 行，返回 still；拒绝后文件不存在。已验收于 Codex 0.162.1：请求 curl -sI https://example.com 没有审批框，画面为 Failed (exit 7)、无输出，模型称已运行；/status 为 Workspace (granular)。已验收于 OpenCode 2.0.28：第三轮 Permissions=prompt 时没有审批框就往工作区外写了文件；第四轮 touch 家目录探测文件同样没有审批框，文件被创建。记成事实，不推断原因。仅返回结果/状态/必要审批。

目标 CLI 的思考显示按版本操作，用完改回。tmux 不能区分推理、进度和答案。已验收于 Codex 0.162.1：两个 -c（hide_agent_reasoning=true 与 show_raw_agent_reasoning=false）会多一条 embedded mode 警告，没有看到隐藏效果，不要当成隐藏做法。已验收于 OpenCode 2.0.28：命令面板（C-p）打开 Settings · Session 的 Thinking，取值 hide/show，用左右键改，用完改回；斜杠 /thinking 是 Switch model variant，不是这个开关。已验收于 agy 1.3.5：用 /config 改 Verbosity，low 会隐藏 Thought 行，用完改回。升级后复测。Codex 粘贴后立刻 Enter 卡死（issue #28167）在 Codex 0.162.1 / tmux 3.5a 没有复现，结论只限这个组合，不写死延迟。

真实 CLI 逐项验收输入、提交、多行、取消、审批、完成、隐藏思考、长回答；记录版本、日期、命令和证据。假 TUI 通过不能宣称兼容。WSL 调用端退出至少一分钟后的保活另测，不默认改全局配置；系统重启/WSL 关闭结束进程。server 消失后可能留下 socket 文件，只对已经确认 ConnectionRefused 的精确名称使用 prune。

明确结束只清理本任务；继续交互保留并交付定位信息。缺依赖、超时、未知如实报告。

设计只读：[方案](https://app.notion.com/p/3f89f9a4e09e810e968bf0028aade8f8)、[Skill](https://app.notion.com/p/3f99f9a4e09e8105878fc27cc06fe938)。实测偏离在 docs/design-deviations.md 记录原文、实测、证据、建议，不能静默改设计。
