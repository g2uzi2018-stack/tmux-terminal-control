---
name: peer-coworkers
description: 无头调用独立 CLI（codex / agy / cursor）执行边界清晰的实现、研究、测试或审查，并做 Git 树事后审计。
---

# Peer Coworkers

主代理划定目标、输入、写入范围与验收标准；小型强耦合改动直接自己做。模型与分工见 [模型选型](references/model-selection.md)。

```bash
P=scripts/cowork.py   # 已安装后为 ${CODEX_HOME:-$HOME/.codex}/skills/peer-coworkers/scripts/cowork.py
python3 "$P" doctor
python3 "$P" start --cwd "$PWD" --profile agy --model gemini-4-hydrogen-high --task-file task.md --write src [--name label]
python3 "$P" wait --run "$RUN" [--timeout 120]
python3 "$P" send --run "$RUN" --file reply.md
python3 "$P" log --run "$RUN" [--tail 50]
python3 "$P" diff --run "$RUN" [--round 1]
python3 "$P" stop --run "$RUN"
```

## 规则与边界

- **可写与只读**：有写需求时加可重复 `--write PATH`；只读调研/审查不加 `--write`（`agy`/`cursor` 靠提示词声明只读，事后由 `wait`/`diff` 确认 `changed == []`）。
- **并发写锁**：同一 `cwd` 同时最多一个可写任务，只读任务不限；冲突会报错并列出占用者。
- **交付约定**：工具在 `task.md` 末尾要求最终回复以 `DONE/PARTIAL/BLOCKED/QUESTION` 开头；`result-N.md` 只含最后一条 assistant 消息，短于 200 字时会提示查看 `transcript-N.md`。
- **任务长度**：prompt 作为单命令行参数传入（Linux 单参数上限 128 KiB）；超长上下文请写入文件并在任务中引用路径。
- **审计范围**：基线与 diff 使用临时 index + `runs/<id>/objects`，不写入仓库 `.git/`；可检出预脏文件再次修改，不包含 submodule 内部与 `.gitignore` 忽略文件。
