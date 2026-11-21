# 模型选型

按任务、用户指定和当前 CLI 能力选模型，积极使用已有 agy/Cursor 额度；默认 High、标准速度，小型强耦合工作由主代理直接完成。模型参数仅作用于单个任务。

| 工作 | 默认模型 | 派工参数 |
| --- | --- | --- |
| 与负责调研的主代理商议方案 | Gemini 4 Argon High | `--profile agy --model gemini-4-argon-high` |
| Argon 额度不足或不可用时接替方案商议 | Gemini 4 Neon High | `--profile agy --model gemini-4-neon-high` |
| 重要方案的独立意见 | Grok 4.7 High | `--profile cursor --model grok-4.7-high` |
| 方案存在实质分歧时参与讨论 | Claude Opus 5.5 High | `--profile agy --model claude-opus-5-5-high` |
| 按已明确的方案实现 | Gemini 4 Hydrogen High | `--profile agy --model gemini-4-hydrogen-high` |
| 边界清楚的日常实现（可选） | Composer 2.5 | `--profile cursor --model composer-2.5` |

优先由 Argon 与主代理商议，不可用时由主代理切换 Neon 并说明；重要方案另请 Grok 基于原始要求、调研证据与候选方案独立提出意见，再比较分歧，必要时请 Opus，主代理裁决。实现交付已定方案、写入范围与验收条件，由主代理集成验收；不为凑模型额外派工。

调用前用 `agy models` / `cursor-agent models` 核对精确 ID，并在 `round-N.log` 的 init 事件核对实际模型；不根据后缀拼接参数。

- 轻量检索、资料整理可按需选用 `--profile agy --model gemini-3.8-flash-high`。
- Cursor 优先使用 Grok/Composer；同一模型换入口不算异构意见。`cursor-grok-4.6-xhigh` 仅显式备用，不静默替换用户指定模型。
- Fast 仅用户当次指定时启用；Flash 是模型系列。实际模型或速度无法核实时记录未知。

用途参考 [Cursor 官方说明](https://prod.cursor.com/help/models-and-usage/available-models)，不视为本地能力排名；目录列出不代表调用成功，验收以实际日志、产物和证据为准。
