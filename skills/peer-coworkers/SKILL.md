---
name: peer-coworkers
description: 通过独立 CLI/TUI 工作进程进行任务分工、实现、测试与独立审查，用 tmux 保留交互并核验任务结果。适用于明确要求协作或收益清楚的可分包工作；小型强耦合工作直接完成。
---

# Peer Coworkers

主代理保留需求、接口、集成、争议裁决和最终验收。角色与模型分离：使用用户选择且可用的 CLI，不按模型名称固定分工。当前使用独立进程，经 tmux 操作；不调用旧 DeepSeek runner、原生 Luna role，也不让工作进程继续分派。

## 选择工作方式

先判断工作是否值得分包；小型或强耦合任务直接完成。需要分工时读 [协作模式](references/collaboration-modes.md)，选择实现、测试、研究或审查角色。一个工作包明确目标、依赖、可读范围、写入归属和验收证据。任务工具首版只对整个 Git worktree 建基线；需要限制读取/外发范围时，先提供只包含允许材料的独立工作区，提示词不是访问控制。

执行前读 [CLI 配置](references/cli-profiles.md) 和 [任务合同与命令](references/task-contract.md)。以 `python3 scripts/cowork.py doctor` 检查当前环境。Codex、agy、Cursor CLI 为可选活动配置；检测到可执行文件不代表登录有效或兼容验收通过。OpenCode 目前仅保留兼容入口，默认关闭；只有用户明确启用才传 `--enable-opencode`，不能把它当作失败回退。

`init --model MODEL_ID` 为单个任务绑定实际 CLI 模型，不修改 CLI 的全局默认。用户指定模型时按其要求执行，不静默替换。本机 agy 的 Gemini 3.8 Flash High 已在修复 WSL 代理域名转发后通过真实任务闭环；可显式使用 `--profile agy --model gemini-3.8-flash-high`。Claude Sonnet 4.6 也已验证，但不作为用户指定 Gemini 时的自动回退。

## 执行一个工作包

本机 WSL 启动真实工作进程（用户所说的子线程）前，先在同一次 `bash -ic` 调用中执行 `proxy_on && ... start ...`；proxy_on 失败就停止启动。此要求不调用原生子代理，也不作用于离线假 TUI 测试。具体命令见 [CLI 配置](references/cli-profiles.md)。agy 可用 `start --proxy-url` 显式传入已确认的 HTTP(S) 代理；核对实际 pane 进程环境，不根据父 shell 或 tmux show-environment 推定生效。

1. `init` 创建任务；写入角色必须列出 `--owned-path`。先 `proxy_on` 再 `start`；`start` 只启动界面，不自动输入或确认信任/权限。启动环境、cwd、账号与用户授权须相符。
2. 首次操作该 CLI/版本时，按 [终端规则](references/terminal-control.md) 核验输入界面与按键。`screen` 确认焦点就绪，再 `paste`；读屏确认任务已接收后才 `submit --received-confirmed`。多行仍须当前界面的实测证据。
3. 使用 `observe` 续等；它不重发 Enter。`prompt/still/exited/timeout` 都不是完成结论。遇到审批先核对动作和授权，不能自动全部批准；不添加跳过权限的参数。
4. 结果写入任务记录指定的 `result.json`。`collect` 校验本任务/本轮身份、六字段合同及工作区变化；无效结果不进入验收。`DONE` 只进入 `awaiting_acceptance`。
5. 主代理核对实际产物、diff 与针对性测试；必要时发起独立审查，再 `accept --evidence '实际核验结果'`。不能用格式检查、模型一致或零发现替代证据。
6. 要保留交互就交付 run/socket/pane 定位。明确结束时 `close`；活跃进程须显式 `--allow-active`，只清理本任务。需要重试时先查旧进程和副作用，建立新任务/尝试；提交不明时不能重发。

预算耗尽后停止继续输入，保留现有产物并报告未完成项；先核对是否仍在运行再决定关闭。CLI 启动、粘贴或提交失败可能留下 uncertain 状态，使用 `show`、`screen` 和底层 `session.py list` 诊断；工具不会自动回滚、重放或更换模型。

## 隔离、独立性和交付

同一工作区不并发写入，也不一边写一边对移动基线做审查。脚本按规范化 cwd 在用户状态目录共享活跃任务登记，跨 runs-dir 检查冲突；脚本外进程和不同用户状态目录仍需主代理协调。并行写入使用独立 worktree 和不重叠归属，主代理逐个集成。格式化、构建和会写缓存的测试也要计入归属；任务记录、说明和 scope 结果会明确列出快照未覆盖的忽略文件及工作区外路径，需要主代理另行核对。

独立求解与独立审查使用新 CLI 进程/会话，提供原始问题、最终产物和合同，不灌入既有结论。工作进程不会继承主对话上下文，因此要提供足够的具体信息；不传密钥、禁止外发的材料或无关历史。启动本技能不扩大用户授权，也不替代实际 CLI 的沙箱。

每工作包最多一次广泛审查、一次定向修复和一次增量复核；范围或合同变化时重新分包。高风险任务增加一次新上下文的最终检查。交付简述各工作包的角色、CLI、状态、主代理验证、剩余事项和保留会话位置。

协作设计源自用户的 [peer_coworkers](https://github.com/g2uzi2018-stack/peer_coworkers/tree/2016c9c2ec7c5f8ea16917c6c46c7c057a70c78f)，已去除旧调用身份绑定；终端实现保留 `tmux-tui/v1` 会话标记。
