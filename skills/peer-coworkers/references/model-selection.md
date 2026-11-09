# 模型选型

按任务、用户指定和当前 CLI 能力选模型。用户偏好优先使用 agy 的 Gemini 3.8 Flash High，跨模型家族深审可选 Cursor Grok 4.6 Extra High。模型参数属于单个任务。

- agy 使用 `--profile agy --model gemini-3.8-flash-high`，在实际 TUI 核对 Gemini 3.8 Flash 和 high。Gemini Flash 是模型系列。当前入口没有独立 Fast 控制时记录为不适用。
- Cursor 使用 `--profile cursor --model cursor-grok-4.6-xhigh`。在实际 TUI 的 `/model` 参数菜单核对 Extra High 和 Fast 状态。用实时目录核实精确 ID，避免根据后缀拼接参数。
- 默认标准速度，只有用户当次指定才选 Fast。模型或速度无法核实时记录未知，用户指定的模型不可用时报告实际情况。

模型目录只证明发现，任务记录以实际会话和交付为准。独立审查依据具体发现与证据。
