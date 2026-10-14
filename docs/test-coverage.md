# 自动化验收覆盖

来源：Notion Skill 页「自动化测试」完整要求（2026-10-14 读取）。使用 unittest，依赖缺失即失败，无 skip。每例独立 ai-tui-test-UUID socket，finally/addCleanup 使用带 -L 范围的清理；测试日志在系统临时目录。

| 设计用例 | 对应证据用例（tests/） |
|---|---|
| 末尾分号、前导 -、美元、反引号、中文、空行、末尾换行 | test_input.py 的 test_verbatim_*（每个独立 socket；含纯空行、CR、长文本） |
| 已验证多行保留全文且不提前提交 | test_fake_tui.py 的 bracketed_paste_logs_exact_bytes_and_separate_submit、p_r_prevents_early_submission_regression；test_input.py 的 blank_lines/blank_only/trailing_newline |
| 未开启或未知多行发送前拒绝 | test_input.py 的 unknown_multiline_rejected_before_any_bytes_or_buffers、disabled_multiline_rejected_before_sending |
| 粘贴与 Enter 分离、延迟期间不提交 | test_fake_tui.py 的 delayed_receiver；test_input.py 的 delayed_receive_does_not_submit_and_confirmation_is_required |
| 提交未确认不重复发送 | test_input.py 的 unconfirmed_target_submission_is_not_repeated；test_wait.py 的多个 resume 用例核对提交数始终 1 |
| 提交后一直不变不能 still | test_wait.py 的 unchanged_after_submit_never_returns_still |
| 变化后静止可 still | changed_then_quiet_returns_still |
| 持续动画 timeout | animation_without_events_returns_timeout |
| 本轮审批 prompt match=approval | new_approval_prompt_returns_match；另测 ready 标签 |
| 真实 pane 进程退出 exited / code / 最后画面 | real_exit_has_code_and_last_screen（目标是假 TUI，不是真实 AI CLI） |
| 捕获失败 error | live_pane_capture_failure_is_error、hung_capture_is_bounded_and_reported_as_error |
| pane/socket 消失不是 exited | missing_pane_is_error_not_exited、pane_disappears_while_socket_remains_is_error、socket_disappears_during_wait_is_error |
| 续等保留本轮基线与变化状态 | resume_preserves_baseline_and_observed_change、resume_detects_change_that_arrives_after_first_timeout、observed_change_survives_regex_timeout_then_resume |
| 排除旧提示和正文误匹配 | old_prompt_residual_is_excluded、resumed_old_prompt_still_excluded、body_prompt_outside_region_does_not_match、quoted_prompt_in_region_does_not_match_anchored_regex |
| 运行短于调用方 timeout、固定首行、最多一份画面 | assert_result 覆盖全部等待结果；no_screen_outputs_only_header_within_shell_timeout；精确整帧核对；pathological_regex_cannot_exceed_wait_budget |
| 可选忙碌模式 | static_busy_is_not_quiet_candidate |
| 无接收确认/错误参数不提交 | no_receipt_confirmation_is_error_before_submission、invalid_limits_or_regex_error_before_submission |
| 唯一 buffer 与失败清理隔离 | BufferIsolationTests：保留 unrelated buffer，成功/失败均只删除本次 buffer |
| 创建前 history-limit、remain-on-exit、TERM、标记 | test_session.py 的 creation_history_remain_and_metadata、history_limit_change_after_creation_does_not_apply |
| list / 自定义 TMUX_TMPDIR / 精确范围 cleanup | test_session.py 的 list_*、cleanup_*、existing_socket_cannot_be_reused_or_respawned |
| 启动失败诊断保留、argv/cwd 字面值 | failed_target_startup_keeps_diagnostics_and_exit_status、no_arguments_executable_with_spaces_is_not_shell_text、cwd_and_task_ending_semicolon_are_literal |

## 用户提供的 tmux 3.5a 回归结论

send-keys -l 的尾分号丢失（含 --）、前导 - 被当作参数以及 bracket_paste_flag 不可查询已在 3.5a 复现。history-limit 后改不生效已在真实 tmux pane 复现。

-r 与 -p -r 的多行差异使用假 TUI 的 readline 式 LF 提交规则验证：即使目标启用 bracketed paste，只用 -r 仍会触发提前提交，-p -r 保留全文且无提交。范围遵守「只通过假 TUI 测试」；没有重新运行实际 bash/readline，也不把该模型测试当成 bash 或真实 AI CLI 验收。

完整本机输出见 test-results.txt；版本/依赖见 environment.md。Skill frontmatter 另以 skill-creator quick_validate.py 校验。其 PyYAML 6.0.3 只安装到 Windows 宿主的临时开发目录，不属于项目运行或测试依赖。
