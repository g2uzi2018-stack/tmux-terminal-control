# 设计偏离记录

只读来源：[方案](https://app.notion.com/p/3f89f9a4e09e810e968bf0028aade8f8)、[Skill](https://app.notion.com/p/3f99f9a4e09e8105878fc27cc06fe938)，完整读取于 2026-10-14。Notion 未修改。

本次实现没有发现经实测确认的 Notion 描述冲突，因此无设计偏离条目。具体接口退出码、保守能力声明、pane 选项 base64 编码、静止默认时间属于设计预留给实现的细化；不改变架构/权限/行为要求。

## 实测核对（无偏离）

| 原文或用户补充结论 | 实测现象 | 证据 | 建议 |
|---|---|---|---|
| 「tmux 3.5a 没有可用的 bracketed paste 格式查询变量」 | 格式展开为空；运行层不依赖该变量 | test_input.py：test_tmux_35a_has_no_paste_format_query | 保持按 CLI 版本/输入界面声明多行能力 |
| 「在创建 pane 前设置 history-limit」 | pane 建前 777，建后改全局 999，该 pane 仍为 777 | test_session.py：test_history_limit_change_after_creation_does_not_apply | 保持创建前设置 |
| 「跨多次等待保留同一轮基线及已观察变化状态」 | 超时续等保留基线；changed=1；提交数仍为 1 | test_wait.py 的 resume_* / observed_change_survives_regex_timeout_then_resume | 保持 pane 用户选项，不增状态文件 |
| 「pane/socket 消失或捕获失败返回 error」 | 消失、主动捕获失败、挂起捕获均返回 error | test_wait.py 的对应用例 | 保持 error 与 exited 分离 |

没有验证的真实 CLI 显示参数/交互行为仍为待验收，不能将缺少证据写成冲突或兼容结论。-r/-p/-r 回归仅在假 TUI 中复现 LF 行为，实际 bash/readline 未重验（遵守本次测试范围）；见 test-coverage.md。

如后续真实验收发现差异，按「原文、实测现象、证据、建议修改」追加，不静默改设计。
