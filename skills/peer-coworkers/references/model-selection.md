# 模型选型

按任务、用户指定和当前 CLI 能力选模型。用户已升级 Google agy 订阅，适合分包时积极使用 agy。以下分工按 2026-11-19 的用户要求更新，默认使用 High 档位，具体任务可调整。小型强耦合工作由主代理直接完成。模型参数属于单个任务。

| 工作 | 默认模型 | 派工参数 |
| --- | --- | --- |
| 与负责调研的主代理商议方案 | Gemini 4 Argon High | `--profile agy --model gemini-4-argon-high` |
| Argon 与主代理未达成一致时参与方案讨论 | Claude Opus 5.5 High | `--profile agy --model claude-opus-5-5-high` |
| 按已明确的方案实现 | Gemini 4 Hydrogen High | `--profile agy --model gemini-4-hydrogen-high` |

方案讨论向 Argon 提供原始要求、调研证据和候选方案。出现分歧时，将双方理由、证据和具体争议交给 Opus 讨论，主代理结合讨论结果作出决定。实现包向 Hydrogen 交付已确定的方案、输入、写入范围和验收条件，再由主代理集成与独立验收。

以上精确 ID 已在 agy 1.5.12 的 `agy models` 目录中发现。调用前按当前目录核对，启动后在实际 TUI 核对模型和思考档位。

- 轻量检索、资料整理等任务仍可按需选用 `--profile agy --model gemini-3.8-flash-high`。
- Cursor 使用 `--profile cursor --model cursor-grok-4.6-xhigh`。在实际 TUI 的 `/model` 参数菜单核对 Extra High 和 Fast 状态。用实时目录核实精确 ID，避免根据后缀拼接参数。
- 默认标准速度，只有用户当次指定才选 Fast。Gemini Flash 是模型系列，入口没有独立 Fast 控制时记录为不适用。模型或速度无法核实时记录未知，用户指定的模型不可用时报告实际情况。

模型目录只证明发现，任务记录以实际会话和交付为准。独立审查依据具体发现与证据。
