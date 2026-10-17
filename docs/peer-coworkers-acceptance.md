# Peer Coworkers 首版验收

日期：2026-10-17，Asia/Taipei。运行环境：WSL 2、Python 3.12.3、tmux 3.4、Codex CLI 0.163.0、agy 1.4.0、Cursor CLI 2026.10.16-e3cb207。初轮沿用 CLI 已有模型；后续通过任务参数显式绑定模型，未修改全局模型或推理档；不调用旧 DeepSeek runner 或原生 Luna role。

## 自动化验证

`python3 -m unittest discover -s tests -v`：112 项通过，0 跳过，18.598 秒。保留原有 80 项并增加 32 项编排/安装测试。完整输出见 [peer-coworkers-test-results.txt](peer-coworkers-test-results.txt)。

新增测试覆盖任务与 attempt 绑定、严格结果字段/大小/重复键、PARTIAL/BLOCKED 合同、符号链接/FIFO 拒绝、dirty 文件同状态变更、归属与路径逃逸、真实暂存变化与正常索引缓存刷新、超时与提交确认、提交失败后不重发、真实 tmux 单次提交至验收与清理、关闭锁争用及登记释放失败的重试、跨运行目录冲突、范围排除声明、OpenCode 不执行，以及安装物化与更新备份。

代理增量新增 3 项：显式代理变量实际进入 tmux pane 且父环境恢复；启动异常时也恢复父环境；不含有效 HTTP(S) 端点或带凭据/路径的代理在启动前被拒绝，任务保持 prepared。

Cursor 增量新增 3 项：优先解析 cursor-agent、缺失时回退 agent、两者缺失时拒绝并且不启动编辑器 cursor；doctor 的启用配置探测也覆盖 Cursor，OpenCode 仍不执行。

模型增量新增 3 项：显式模型绑定任务说明/记录并进入结构化启动 argv；不传模型时保留 CLI 默认；无效模型 ID 在创建任务前拒绝。没有配置自动模型回退。

tmux 3.4 的两项实测差异已处理：会话检查先把精确名称解析为 session ID；启动失败测试等待退出状态发布，避免 pane_dead 已可见但 pane_dead_status 尚为空的竞态。

## 真实 CLI 演练

初轮 run 目录位于 `/tmp/peer-coworkers-live-20261017/`，显式代理增量位于 `/tmp/peer-coworkers-proxy-live-20261017/`，不保存凭据；活跃会话均在结束后精确清理。临时目录中的结果是本机诊断证据，不能保证跨系统清理长期留存；本文件记录关键结论。

| 工作包 | 实际操作与结果 |
|---|---|
| Codex 输入探测 `task-ca98a845ed4b41e796e817433f10b88f` | 长说明显示为粘贴占位符；未提交，关闭该会话。随后把 paste 改为可读屏确认的短指令，让进程读取独立 prompt.txt |
| Codex 独立审查 `task-37d9715986b84f43a3e4ffff02aa5dbb` | 完整跑通启动、读屏、粘贴、单次提交、续等、result.json、collect、主代理 accept 和 close。工作区变化为空，Git HEAD/branch/index 无变化；返回两项可复现边界 |
| agy 默认网络 `task-d148498e5b71478487f08c1b440a5ee8` | 自动恢复已有登录，关闭更新说明提示后可输入；单次提交返回 API 地区限制，没有结果文件，关闭会话 |
| agy 现有代理复测 `task-6c46bbb3f7584046b3689a007b826974` | 在现有 proxy_on 配置下新建会话，依然返回同一地区错误，没有结果文件，关闭会话；没有自动换模型或回退 OpenCode |
| Codex 临时实现 `task-7c28821b9f64417a8bb027f2771e250a` | 仅允许新增一个临时 Python 文件，完成 normalize_tags 的空白过滤、casefold 去重、顺序保持和类型检查；工作进程报告实际断言通过，主代理另做 12 个用例全部通过 |
| 安装包 Codex 定向复核 `task-416593f8e9c44ce483988888035bb7e4` | 使用安装后物化的独立包跑通任务闭环，确认共享登记与排除范围声明符合合同，并发现关闭流程遇到登记锁争用时无法重试释放的 P2 问题 |
| agy 显式代理 `task-c954237c0eb34923896bf6ebefefea72` | 按用户要求先 proxy_on，再用 --proxy-url http://127.0.0.1:17890 创建新 server/pane；六个代理环境变量及实际 TCP 连接均核验到该入口；单次提交仍返回相同 API 地区限制，无结果文件，关闭并 prune 本任务 socket |
| agy / Claude 完整闭环 `task-f1cc85bc0ccc4929b83a11784cd48f5e` | init 显式选择 claude-sonnet-4-6，按代理要求启动；读取任务后返回含 AGY_CLAUDE_WORKER_OK 与 323 的本轮结果，collect 检查通过；主代理独立验算并核对无工作区/Git 状态变更后 accept、close、prune |
| agy / Gemini 修复后闭环 `task-6589ff584d1c4fce82afb04d66f5dbe1` | 原生 Linux agy、Gemini 3.8 Flash High，proxy_on 后显式 17890；结果含 AGY_GEMINI_WORKER_OK 与 667，collect 核对工作区/Git 零变化；主代理独立验算、accept、close、prune 均通过 |
| Cursor CLI 完整闭环 `task-52823954b5d648ad8f39107d250502e0` | 使用安装包的 cursor 配置，cursor-agent --sandbox enabled，界面为 Auto；proxy_on 后显式 17890，六个代理变量已核对；单次提交后读 prompt.txt、写 result.json，含 CURSOR_WORKER_OK 与 391；主代理独立验算、检查工作区/Git 零变化，accept、close、prune 均通过 |

临时实现的 collect 报告唯一变更为 `tests/_peer_coworkers_probe_a7c91d.py`，无归属违规与 Git 状态变更。主代理验收并关闭会话后删除该演练文件，未混入正式功能。

审查提出的两项边界已处理：跨 runs-dir 的同一工作区调用现使用用户状态目录中的共享登记和锁，并增加回归测试；未跟踪且被 Git 忽略的文件继续排除，但任务记录、工作说明及 collect 结果均明确携带 scope_check_exclusions，主代理须另行核对有关产物。该检查不承担沙箱、外部写者或恶意本地篡改防护。

定向复核发现的 P2 已修复：close 在清理前获取共享锁，锁争用不终止会话；登记删除失败后，已关闭任务仍可再次 close 释放登记。主代理用真实 tmux 会话分别验证锁争用和模拟 unlink 失败后的重试。另复现并修复了普通 git status 更新 index 缓存造成误报的问题，改为比较暂存条目；正常刷新可收集，真正 git add 改变暂存内容仍被拒绝。以上修复包含在首版 103 项通过结果中；本轮代理增量后完整测试扩展为 106 项，修复后没有再增加一轮模型审查。

代理复测调用的是用户已有 `proxy_on`，实际控制持久的 WSL 透明代理，复测时状态为 on/Global；未切换 Windows 代理节点。调用前未采样该全局代理的原状态，因此不能声称网络设置前后完全一致。这一轮尚未解决地区错误；后续域名转发修复见下文。未替用户重新登录或更改 CLI 账号。

用户随后明确要求把 proxy_on 加入启动前提示，并尝试为 agy 指定代理。本次增量已写入两个技能的终端说明及 README；新增 start --proxy-url，在创建独立 tmux server 的同一调用内设置 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY 和小写变量，恢复主调用环境并保留工作进程变量。真实 agy 1.4.0 的 `/proc/PANE_PID/environ` 与 `ss -tnp` 均确认显式本地代理已接入，但服务端仍拒绝当前地区。此证据不能进一步确定是出口 IP、账号地区还是其他服务策略；未自动切换代理节点或模型。

进一步排障通过单变量对照确认：同账号同代理的 Claude 请求成功，Gemini 默认后端仍报 400；临时切换 Gemini 后端只改成 429，没有作为修复持久化。此阶段通过上表 agy / Claude 闭环，Gemini 的恢复随后单独完成。

Gemini 最终修复：Windows 官方 CLI 与同模型成功，Linux CLI 经保留域名的转发路径成功，回到原路径再次失败。已更新本机 WSL 代理生成器，删除 mixed 入口提前 IPv4 解析，并为透明流量恢复 Antigravity API 的同名域名目的地址；配置验证、服务重载通过。原 17890 显式代理、无代理变量的透明代理以及不传 --model 的默认 Gemini High 均成功。上表真实 Gemini 技能工作包也已验收。未改账号、默认后端或 Windows 节点。完整对照、备份与回滚见 [agy-wsl-diagnosis.md](agy-wsl-diagnosis.md)。

## 尚未验收

Cursor 的多行输入、审批与取消行为，以及其他 CLI 新版本的逐字接收、审批匹配、取消生成、Windows 调用端退出后的保活、自动创建与集成 worktree、多写入流端到端，以及原生 Windows 安装均未作为本次通过项。OpenCode 仅有关闭默认入口及禁止默认执行的测试，没有本次在线验收。

Cursor 本轮使用默认 Auto 路由，没有指定底层模型，不能据此确定其实际模型 ID。这里只验收 Cursor CLI 作为独立工作进程；技能安装器默认仍安装到 Codex 的技能目录。当前基础模型 ID 的 --model 传递有测试，带方括号参数的 Cursor 模型表达式尚未接入本任务合同。
