---
name: peer-coworkers
description: 通过独立 CLI/TUI 工作进程执行有界实现、测试、研究或审查，用 tmux 保留交互，由主代理核验结果。仅在用户明确要求协作或适合分包时使用；小型强耦合工作直接完成。
---

# Peer Coworkers

主代理负责需求、分包、接口、集成和最终验收。先判断是否需要协作；角色与 CLI/模型分离，不按模型名称固定分工。工作进程不得继续分派。多写入流使用独立 worktree，通过 Git 串行集成；工具只管理一个工作包的生命周期。

选择模式时读 [协作模式](references/collaboration-modes.md)。调用前读 [任务合同](references/task-contract.md) 和 [CLI 配置](references/cli-profiles.md)，运行 `python3 scripts/cowork.py doctor` 核对当前环境。存在可执行文件不代表已登录或兼容。不要自动换模型、启用默认关闭的 profile 或改变 CLI 权限。

1. 明确目标、角色、归属路径与可验证的验收条件，用 `init` 建立工作包。合同与范围检查不是沙箱；需要限制读取或外发时，先准备只包含允许材料的隔离环境。
2. `start` 内置代理准备，默认自动探测交互 Bash 中的代理函数；用 `--no-proxy` 跳过准备。启动本身不粘贴、不提交、不确认信任。通过 `screen` 检查界面，再 `paste`；确认短指针实际接收后，`submit --received-confirmed` 一次。
3. 用 `wait` 观察结果、问题、审批、退出、注意提示或超时。静止不是完成，提示不是授权。审批前核对具体动作与已有用户授权；不自动全部批准。按键与多行操作见 [终端规则](references/terminal-control.md)。
4. 有效问题或定向修复通过 `reply --message-file` 回答；每次递增 round 并归档旧结果，默认最多两次。粘贴、提交或回复不明时保留 uncertain 状态，先诊断，不能重发 Enter。取消只在当前版本有通过的 probe 时发送一次 Escape，否则明确关闭。
5. `collect` 校验本任务、attempt、round、六字段合同与范围。DONE 仅进入待验收；主代理独立检查实际产物、diff 和针对性测试，再 `accept --evidence`。需要独立审查时提供原始要求与最终产物，避免灌入实现者自评。
6. 保留交互时交付 run/socket/pane；明确结束时 `close`，活跃进程需 `--allow-active`。会话已消失时释放租约；未确认启动或损坏记录先 `reap` 检查，再决定是否对精确 task 强制回收。

执行预算耗尽后停止新输入，仍可读屏、等待、收集、取消或关闭。交付说明角色、CLI、状态、主代理验证、剩余事项和保留会话位置。范围检查明确排除 Git 忽略的未跟踪文件和工作区外路径；主代理另行核对有关产物。不得将假 TUI 通过写成真实 CLI 兼容。
