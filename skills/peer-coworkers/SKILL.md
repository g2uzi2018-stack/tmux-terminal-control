---
name: peer-coworkers
description: 通过 tmux 向独立 CLI 分派有明确交付物的实现、研究、测试或审查，并由主代理独立验收。适用于能清楚划分范围的工作包。
---

# Peer Coworkers

主代理划定目标、输入、写入范围和验收条件，负责集成与验收。适合拆分时积极使用 peer。小型强耦合改动直接完成，多路写入用隔离工作区。工作进程自行完成分配给它的工作。独立审查以原始要求和实际产物为输入。

先用 `python3 scripts/cowork.py doctor` 核对 CLI，再按 [模型选型](references/model-selection.md) 选择 `--profile` 和需要绑定的 `--model`。模型、思考档和速度在实际会话中核对。

1. `init` 指定工作区根目录、目标及验收条件。有工作区写入需求时给 `--owned-path`。
2. `start` 后检查 `screen`，用 `paste` 放入任务说明的指针。确认输入框收到指针后，`submit --received-confirmed` 一次。启动信任与任务提交是独立操作。
3. `wait` 观察当前交付路径及终端。检查具体权限请求，再按已有授权处理。看 [终端交互](references/terminal-control.md)。
4. 读取 Markdown 交付。`reply --message-file` 可答疑或提出修改，工具为新交付分配独立路径。提交不明时用 `wait` 或 `collect` 查实际交付。
5. `collect` 检查范围后，独立审阅交付和实际产物，再 `accept --evidence`、`close`。保留会话时给出 run、socket 和 pane。

各命令使用同一 `--run`。交付格式、反馈和收尾见 [任务说明](references/task-contract.md)，启动配置见 [CLI 配置](references/cli-profiles.md)。
