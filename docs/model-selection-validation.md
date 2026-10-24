# 模型选型修复与验证

日期：2026-10-21，Asia/Taipei。代码基于已发布的 `037d132d7c91b7d68c8f374f8bc0836832410b55`，验证环境为 WSL Debian13 / dev。

2026-10-24 合并说明：下文保留当时的历史验证范围。本次已将 `ffabf7d` 的生命周期改进及后续审批/交付修复与模型选型规则合并；`--profile` 必填、标准速度偏好及模型参考继续保留。合并后的功能与验证见 [当前验证记录](hardening-validation.md)，不再将这些已合并功能描述为当前版本缺失。

## 改动与兼容性

首次派工需比较合理候选、说明所选和未选原因；分别确认 CLI、实际模型、思考档位与速度模式。模型能力表用于缩小候选，不固定某个品牌为主脑或低级工。独立复核优先考虑胜任的其他模型家族，最终以可复核证据验收。

`cowork.py init` 不再隐式选择 Codex，必须提供 `--profile`；旧调用需补上经选择的配置。`--model` 仍可省略，已有任务的启动、收集和关闭不受影响。

按用户偏好默认不用 Fast，只有当次明确要求才启用；不会因此排除 Gemini Flash 等模型。该偏好通过技能选型与会话核对执行，不是脚本硬封锁，也没有新增通用 Fast 或 effort 参数。不改持久的 CLI 全局设置。

入口与依据：[SKILL.md](../skills/peer-coworkers/SKILL.md)、[模型能力与选型](../skills/peer-coworkers/references/model-selection.md)、[目录快照](../skills/peer-coworkers/references/model-inventory.json)。

## 验证结果

- `python3 -m unittest discover -s tests -q`：114 项通过、0 跳过，10.897 秒。新增用例验证缺少 `--profile` 在创建任务前失败，以及 Codex / agy / Cursor 的显式 profile/model 正确保留。
- Skill Creator 的 `quick_validate.py`：通过；WSL 没有 PyYAML，改用本机已有且提供该依赖的 Windows Python 验证，未新增项目运行依赖。
- `git diff --check`：通过。技能引用及新增 Markdown 的本地链接已检查。
- 安装器将技能更新到 `/home/dev/.codex/skills/peer-coworkers` 和 Windows 的 `C:\Users\kuang\.codex\skills\peer-coworkers`；既有版本由安装器备份。安装后的文件与仓库源文件逐项校验。执行脚本仍使用 WSL，Windows 目录用于宿主发现技能，不代表原生 Windows tmux 支持。

## 证据范围与版本区别

本轮实时查询 agy 6 个模型 ID、Cursor 265 个 ID；后者包含档位、Fast 变体与历史版本，不是 265 个基础模型。Codex 仅有本地缓存中的 7 个可见模型条目。目录存在不证明额度、请求成功或复杂任务质量；本轮未重新运行在线工作包，也未做性能横测。

[首版验收](https://github.com/g2uzi2018-stack/tmux-terminal-control/blob/2c469b74d83742784d5bc0d36af8e371e995bd97/docs/peer-coworkers-acceptance.md) 的 2026-10-17 真实 CLI 记录来自另一机器/版本，继续保留为历史证据；链接固定到原发布版本，当前原始本机记录另存于忽略的 `docs/local/`。

Notion 另保留了 2026-10-18、`/home/kuang` 环境的未发布提交 `ffabf7de6ed0c484df40b8a2b6a2123dad2ec729` 记录。本轮在当前 Git 对象和 GitHub 远端均未找到该提交；其 170 项测试、内部代理处理、`doctor --probe`、`wait` / `reply` 等描述不属于本次发布。当前实际流程和参数以 [任务合同](../skills/peer-coworkers/references/task-contract.md) 为准，不能把另一环境的未发布功能算作本次已交付。
