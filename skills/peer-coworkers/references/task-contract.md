# 任务合同与命令

以下路径相对统一技能根目录。`cowork.py` 只处理一个工作包的交互和验收状态，不是后台调度服务，不自动运行测试、批准权限、创建 worktree 或集成改动。

## 最小闭环

```bash
python3 scripts/cowork.py doctor
python3 scripts/cowork.py init --cwd /absolute/git/worktree --role implement --profile codex --goal '实现具体目标' --owned-path src/example.py --acceptance '指定针对性测试通过'
# 使用 init 返回的绝对 run 目录替换 RUN；它不是 shell 环境变量。
bash -ic 'proxy_on && python3 /home/kuang/.codex/skills/peer-coworkers/scripts/cowork.py start --run RUN'
python3 scripts/cowork.py screen --run RUN
python3 scripts/cowork.py paste --run RUN
python3 scripts/cowork.py screen --run RUN
# 主代理确认输入确已接收，再提交一次：
python3 scripts/cowork.py submit --run RUN --received-confirmed
python3 scripts/cowork.py observe --run RUN
# 工作进程已停止工作、结果文件写完，才取结果：
python3 scripts/cowork.py collect --run RUN
# 主代理检查产物并完成独立验证后，记录实际证据：
python3 scripts/cowork.py accept --run RUN --evidence '已核对具体 diff；实际执行的测试及结果'
python3 scripts/cowork.py close --run RUN --allow-active
```

`init` 默认 Codex，支持 `--profile agy` 和 `--profile cursor`。Cursor 配置启动 `cursor-agent`，缺失时尝试 `agent`，不会启动编辑器命令 `cursor`。OpenCode 需要用户先明确启用，再附 `--profile opencode --enable-opencode`。`--role review/research` 禁止拥有写入路径，`implement/test` 必须提供至少一个 `--owned-path`。归属相对 Git worktree 根，不允许 `..`、绝对路径或 `.git`；`.` 表示整个工作区，慎按任务实际范围使用。首版允许读取整个工作区，不提供文件读取隔离。

`init --model MODEL_ID` 可显式绑定本任务模型，写入 task.json 和任务说明，启动时作为 `--model MODEL_ID` argv 传递；不提供则沿用 CLI 默认，不修改用户持久模型配置。模型 ID 最多 200 字符，使用 CLI 实际列出的标识符。当前机器的 Gemini 3.8 Flash High 已通过真实任务验收，可显式使用 `--profile agy --model gemini-3.8-flash-high`；不静默替换用户指定的模型。

本机真实进程启动前先执行 `proxy_on`；函数只在交互 Bash 中可用。`start --proxy-url http://127.0.0.1:17890` 可为 agy 显式指定本机已确认的代理，代理变量只在新建任务的 server/pane 中保留，不改变 CLI 的账号、模型或审批。完整环境约定见 [CLI 配置](cli-profiles.md)。

`--budget-seconds` 默认 600，从启动算起；等待默认 20 秒/次，`--timeout-ms` 最多 20000。预算到期不再输入或等待，不自动杀进程；仍可读屏、收集已有结果和精确关闭。`observe` 仅续等已提交轮次。`show` 查看状态与定位信息，不打印完整基线。所有命令成功为 0，错误为 1（argparse 用法错误为 2）；终端的 timeout/still 等包含在 JSON 的 observation 字段，不等于任务状态或完成。

## 文件与结果

运行目录默认 `${XDG_STATE_HOME:-$HOME/.local/state}/peer-coworkers/task-UUID/`，可用 `init --runs-dir /absolute/path` 指定，必须在工作区外。目录中 `task.json` 是主代理记录，`prompt.txt` 是工作包说明，`result.json` 是工作进程结果。`paste` 只发送读取 prompt.txt 的短指令，便于读屏核对；工作进程须读取完整说明再执行，不能仅凭短指令猜测任务。创建目录为 0700，主代理创建的记录与提示为 0600；不存密钥。运行记录留存供诊断，由用户或主代理在不再需要时清理；它不是跨重启恢复进程的保证。

结果文件严格为一个 UTF-8 JSON 对象，不含 Markdown 或其他文本，字段如下：

```json
{
  "task_id": "init 生成的 task-UUID",
  "attempt_id": "init 生成的 UUID",
  "handoff": {
    "STATUS": "DONE",
    "RESULT": ["实际结果"],
    "EVIDENCE": ["可定位的文件、命令或观察"],
    "VALIDATION": ["确实执行的验证与结果"],
    "REMAINING_WORK": [],
    "RISKS": []
  }
}
```

STATUS 只能为 DONE、PARTIAL、BLOCKED。DONE 必须无剩余工作；另两者须列出具体未完成项。每数组最多 12 项，每项 1–2000 字符且不能全空白，六字段对象紧凑 UTF-8 最多 8 KiB，整个原始文件最多 16 KiB。拒绝重复字段、额外字段、错任务/轮次、符号链接、非普通文件、非 UTF-8 与截断内容。

工具在启动前建立工作区基线：Git tracked 与未忽略 untracked 的路径、文件模式和内容摘要，以及 HEAD、branch、暂存条目。`collect` 检查从基线以来变化是否都在归属内，禁止修改 Git HEAD/branch/暂存内容。暂存比较使用 `git ls-files --stage -z`，不把普通 git status 刷新的 index 元数据缓存当作暂存操作。主代理不能在工作包活动期间修改相同基线；原本 dirty 文件会保留，并按启动时内容比较，归属仍需主代理核对。最多 10000 文件、64 MiB；更大项目需调整工作区，不静默跳过。

这是可信单用户环境的范围漂移检查，不是沙箱：未检测 ignored 文件、外部写入、读取或数据外发，也不抵抗本地恶意修改任务记录。`scope_check_exclusions` 在任务记录、提示与收集结果中明确列出未覆盖的类别；相关产物须由主代理另行核对，不能把空 scope_violations 扩大解释为全盘无变化。实际 CLI 权限与数据范围仍须单独核对。所有结果均由主代理核实；被允许路径中的改动也可能错误。

## 状态与失败处理

正常流程为 prepared → started → pasted → running → awaiting_acceptance → accepted。PARTIAL/BLOCKED 分别进入 partial/blocked。`accept` 要求本轮 DONE、主代理非空验证证据，并再次确认结果和工作区自 collect 后没有变化。

启动、粘贴、提交在副作用之前先写入 launch_uncertain/paste_uncertain/submit_uncertain；中断或错误后不会自动重试。`show` 和 `screen` 诊断现有任务，底层 `session.py list` 可定位尚未返回 pane 的启动。提交不明时不补 Enter；发现本轮有效结果可从 submit_uncertain 收集，仍须验收。确需重试则先核对旧进程/产物，关闭旧任务并新建任务，避免重复副作用。

任务按规范化 cwd 在 `${XDG_STATE_HOME:-$HOME/.local/state}/peer-coworkers/workspaces/` 共享活跃登记，跨不同 runs-dir 检查工作区冲突：只读任务可共存，有写入角色时同一 cwd 的其他任务必须先关闭；独立 worktree 可分别执行。工具外进程和不同用户状态目录不受此检查覆盖。工作进程完成后仍可能停在交互界面，因此 accepted/partial/blocked 不自动释放该工作区，需 close；close 后释放自己的登记。登记指向缺失/损坏任务时拒绝新启动，须先人工核对遗留进程与记录，不自动抢占。

`close` 先获取工作区登记锁，再核对 owner/task/cwd/pane 并精确清理；锁竞争时保留会话，稍后重试。默认拒绝活跃进程，显式 `--allow-active` 只用于已决定结束的本任务。尚未验收的活动任务关闭后记为 cancelled，已有 accepted/partial/blocked 状态保留；已关闭但登记删除失败时，再次 close 会继续释放自己的登记。它终止会话，不证明所有脱离会话的后代均已退出。失效 socket 只在确认拒绝连接后使用底层 prune；不扫描删除。
