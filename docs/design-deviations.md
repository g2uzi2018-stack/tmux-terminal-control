# 设计偏离记录

只读来源：[方案](https://app.notion.com/p/3f89f9a4e09e810e968bf0028aade8f8)、[Skill](https://app.notion.com/p/3f99f9a4e09e8105878fc27cc06fe938)，完整读取于 2026-10-14。Notion 未修改。

2026-10-14 的实现核对没有发现经实测确认的 Notion 描述冲突。具体接口退出码、保守能力声明、pane 选项 base64 编码、静止默认时间属于设计预留给实现的细化；不改变架构/权限/行为要求。2026-10-15 真实验收新增一条 OpenCode `/thinking` 冲突，见文末。

## 实测核对（无偏离）

| 原文或用户补充结论 | 实测现象 | 证据 | 建议 |
|---|---|---|---|
| 「tmux 3.5a 没有可用的 bracketed paste 格式查询变量」 | 格式展开为空；运行层不依赖该变量 | test_input.py：test_tmux_35a_has_no_paste_format_query | 保持按 CLI 版本/输入界面声明多行能力 |
| 「在创建 pane 前设置 history-limit」 | pane 建前 777，建后改全局 999，该 pane 仍为 777 | test_session.py：test_history_limit_change_after_creation_does_not_apply | 保持创建前设置 |
| 「跨多次等待保留同一轮基线及已观察变化状态」 | 超时续等保留基线；changed=1；提交数仍为 1 | test_wait.py 的 resume_* / observed_change_survives_regex_timeout_then_resume | 保持 pane 用户选项，不增状态文件 |
| 「pane/socket 消失或捕获失败返回 error」 | 消失、主动捕获失败、挂起捕获均返回 error | test_wait.py 的对应用例 | 保持 error 与 exited 分离 |

2026-10-14 当时没有真实 CLI 交互证据，缺少证据没有写成兼容结论。-r/-p/-r 回归仅在假 TUI 中复现 LF 行为，实际 bash/readline 未重验；见 test-coverage.md。2026-10-15 真实验收见 [cli-acceptance.md](cli-acceptance.md)。

## 2026-10-15 真实验收

Notion 方案与 Skill 页于 2026-10-15 再次只读，未修改 Notion。除下表一行外，本次实测没有新的原文冲突。未测项目（agy 信任审批之后、多行、取消、WSL 保活）不算冲突。

| 原文 | 实测 | 证据 | 建议 |
|---|---|---|---|
| Skill 页「AI CLI 的显示设置」：OpenCode 使用 `/thinking` 将思考块切换为隐藏；它是切换命令，不要在已经隐藏时盲目重复执行 | OpenCode 2.0.28 空输入区粘贴 `/thinking` 后，补全行写的是 `Switch model variant`。第二轮斜杠菜单没有 `/thinking`，`/effort` 的说明是 Switch model variant。命令面板的 `Thinking`（Settings · Session）打开后当前值是 `hide`，Right 一次后变为 `show`，Left 可改回 `hide`。底部写着 `←/→ change`。同一页没有把 hide/show 列成菜单。这道数列题在 hide 和 show 下都没有单独推理块 | 第一轮：输入区 `/thinking`，上一行 `Switch model variant`。第二轮：设置行 `● Thinking hide`，随后 `● Thinking show`，再恢复为 hide。见 cli-acceptance.md 第二轮 C.5 与 F | 斜杠 `/thinking` 或 `/effort` 仍不要当成隐藏开关。要改显示时打开 Settings · Session 的 Thinking，先读当前是 hide 还是 show，用左右键改，用完改回。改完要再读屏，值不会立刻重画。已合入 SKILL.md（2026-10-16） |

## 第三轮建议补进 Skill 的规则

这些是验收里暴露、当时 Skill 还没写明的操作规则。2026-10-15 写这一节时 SKILL.md 没有改。2026-10-16 已把下表建议写入 SKILL.md，原记录保留。

| 原文 | 实测 | 证据 | 建议 |
|---|---|---|---|
| Skill「全屏 TUI 长回答可能不完整进入历史，按目标滚动/导出核对」 | Codex 默认备用屏 `history_size=0`，40 行答案在当前屏和短回看里会丢开头。`--no-alt-screen` 之后 `alternate_on=0`，`capture-pane -p -S -` 含行 01–40 | cli-acceptance.md 第二轮 E | Codex 要核对长输出时，启动加 `--no-alt-screen`，再用 `capture-pane -p -S -`。不要把默认备用屏的当前屏当成全文。已合入 SKILL.md（2026-10-16） |
| Skill 候选「Codex -c hide_agent_reasoning=true -c show_raw_agent_reasoning=false」 | 带这两个 `-c` 的会话 F2 第二条警告是 command-line configuration overrides 要求 embedded mode。不带 `-c` 的对照会话只有 bubblewrap 那一条警告 | 第二轮 F：`Warnings · 2 of 2` 与 plain 会话 `Warnings · 1 of 1` | 使用这两个 `-c` 时预期多一条 embedded mode 警告。它说明进程没有走共享后台服务器，不要当成推理已隐藏的证据。已合入 SKILL.md（2026-10-16） |
| Skill 候选「Antigravity /settings verbosity=low，不杜撰 --verbosity」 | agy 1.3.5 没有单独的 `/settings` 命令，菜单项是 `/config`（说明里也叫 settings）。Verbosity 原值 medium；改成 low 后同一道题不再出现 `Thought for …` 行；改回 medium 后该行又出现 | 第二轮 A/F：`Exited /config`，medium 有 `▸ Thought for 5s, 423 tokens`，low 没有 | 改 agy 思考显示用 `/config`，只动 Verbosity。`verbosity=low` 用于隐藏 Thought 行。不要发明 `--verbosity`。已合入 SKILL.md（2026-10-16） |
| Skill 候选「OpenCode /thinking 为切换」 | 隐藏思考的控件在命令面板 Settings · Session 的 Thinking，取值 hide/show，用左右键改。斜杠 `/thinking` 不是这个开关 | 第二轮 C.5 与 F，见上表 | Skill 写成：OpenCode 隐藏思考打开 Settings · Session 的 Thinking，先读 hide 或 show，再改，用完改回。已合入 SKILL.md（2026-10-16） |
| Skill 的 `--prompt LABEL=REGEX` 由 Python `re.compile` 编译，按物理行匹配 | `[[:space:]]` 这类 POSIX 字符类会让 `re.compile` 打出 FutureWarning，第二轮 Codex 和 OpenCode 的审批正则都出现了。第三轮 agy 用 `^Allow creation of this file\?$`，stderr 为空，并返回 `reason=prompt match=approval` | 第二轮 G 的 FutureWarning；第三轮 agy 第二次 `submit-and-wait` 退出码 0 | `--prompt` 写 Python re：用 `\s`、`\d`，锚定 `^...$`。出现 FutureWarning 就改正则，不要把那次等待当成匹配成功。已合入 SKILL.md（2026-10-16）：会触发警告的正则现在直接按参数错误拒绝，退出码 1，不提交 |
| Skill「多行能力必须按目标版本/界面实测」。第二轮多行正文没有自带「不要调用工具」 | agy 收到多行验收正文后去跑 `ls`。OpenCode 把多行收成 `[Pasted ~4 lines]`。第三轮在正文前加了「原样复述下面三行内容，不要调用工具，不要改文件」，回答复述了减号行、空行和第四行，没有调用工具 | 第二轮 B 的 agy `ls -la` 审批；第三轮 OpenCode 多行画面与未消毒导出 | 多行探测文本第一行写明要原样复述、不要调用工具、不要改文件。占位符先照实记录，再决定是否提交。已合入 SKILL.md（2026-10-16） |
