# CLI 配置

首版面向 Linux/WSL，tmux、Python 和目标 CLI 在同一环境。`cowork.py doctor` 只查路径和已启用 CLI 的版本，不读取凭据或替用户登录。

## 本机启动前的代理要求

根据用户要求，本机每次启动真实 CLI 工作进程前必须先执行 `proxy_on`。它是交互 Bash 的函数，需用 `bash -ic`；`&&` 保证开启失败时不继续启动。`start` 本身不自动修改系统代理，也不会替用户创建代理函数。其他机器须使用当地已确认的网络配置，不能照抄端口。

```bash
# RUN 替换为 init 返回的绝对目录；下面路径为本机安装位置。
bash -ic 'proxy_on && python3 /home/kuang/.codex/skills/peer-coworkers/scripts/cowork.py start --run RUN'
# agy 显式代理示例（本机已确认监听的 WSL mixed 入口）：
bash -ic 'proxy_on && python3 /home/kuang/.codex/skills/peer-coworkers/scripts/cowork.py start --run RUN --proxy-url http://127.0.0.1:17890'
```

本机 `proxy_on` 开启持久的 WSL 透明代理并清除 shell 中的旧代理变量，不会自动 export HTTP_PROXY。`--proxy-url` 在创建本任务 tmux server 时显式设置大小写两套 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY，保留已有 NO_PROXY 并补充本地回环地址；创建完成或失败后恢复调用脚本环境，工作进程继续保留自己的变量。任务记录保留无凭据的代理端点用于复现。暂只接受不含用户名、密码、查询或路径的 HTTP(S) 端点。

agy 1.4.0 的 `--help` 未列出独立代理开关；本地二进制包含 HTTP_PROXY/HTTPS_PROXY 变量处理。是否实际生效要读取 `/proc/PANE_PID/environ` 中对应的变量再做真实请求，不能只凭这些字符串断定代理解决了 API 地区限制。不要输出完整环境、代理密码或登录凭据。

| 配置 | 默认启动参数 | 当前边界 |
|---|---|---|
| `codex` | `--no-alt-screen --sandbox workspace-write` | 使用已有登录及模型配置，不指定 Luna 或新 provider；保留当前审批策略 |
| `agy` | `--sandbox` | 使用已有登录及模型配置；目录信任提示需有该目录的明确授权，不能自动确认 |
| `cursor` | `--sandbox enabled` | 优先 `cursor-agent`，否则 `agent`；使用已有登录和模型，不调用编辑器 `cursor`，不自动确认信任 |
| `opencode` | 无 | 兼容候选，默认关闭，未购买/未做本次在线验收；仅用户明确启用时使用 |

2026-10-17 当前机器读取到 Codex 0.163.0、agy 1.4.0、Cursor CLI 2026.10.16-e3cb207、tmux 3.4、Python 3.12.3。版本探测不证明所有交互能力有效。旧项目在另一环境的 0.162.1/1.3.5/2.0.28 验收仍可参考，升级后须实测；不把旧结果自动升级为当前保证。

本次 Codex 已跑通只读审查与限定文件写入任务。agy / Gemini 3.8 Flash High 在修复本机 WSL 代理后，已完成真实 tmux 任务的读取、结果文件、collect、主代理 accept、close 与精确 socket 清理；Claude Sonnet 4.6 也已通过同类闭环。OpenCode 未启动。
通过 PATH 解析绝对路径；必要的代理环境必须在创建 tmux server 的同一调用中设置，核对目标进程环境，不能只依赖交互 shell 的函数。不要打印完整环境或凭据。启动参数不包含跳过审批或自动接受全部权限的开关；仅在 init 显式选择模型时传入 --model。

每次适配至少核验：界面就绪、接收输入、单次提交、结果文件或完整输出、任务结束、取消行为和精确清理。多行能力另按 terminal-control.md 验证；模板是单行 JSON 任务说明，原字段中的换行保留为 JSON 字符串转义，不将用户粘贴文本自行折成一行。

## 本机 agy / Gemini 的网络修复

2026-10-17，Windows 桌面版 2.24.0 与官方 Windows CLI 1.4.0 均确认同账号、同模型可用。Linux 原生 CLI 1.4.0 经原 WSL mixed 入口报地区错误，但经保留域名的转发路径成功；切回原路径再次失败。实际修复位于本机 `/usr/local/lib/wsl-proxy/wsl_proxy_common.py` 的配置生成器：

- 去掉 mixed-in / Global 的强制 IPv4 resolve，让 Windows 上游按原域名处理显式代理请求。
- 对 Global 模式下 TUN 的 TCP 443 读取 TLS 握手中公开的域名；仅当匹配 `daily-cloudcode-pa.googleapis.com` 时，将目的地址恢复为该域名交给原 Windows 上游。没有解密 TLS 或记录认证信息。

配置检查与服务重载通过；原端口 `17890` 的显式代理、清除代理变量后的纯透明路径均已获得 Gemini 成功答案。配置生成器已持久更新，后续 proxy_on 不会覆盖回旧规则。没有替换账号、模型、默认后端或 Windows 节点。全局默认模型未更改，工作包可用 `init --profile agy --model gemini-3.8-flash-high ...` 显式确认模型。

`proxy_on` 仍为每次真实工作进程启动前的本机要求；技能继续推荐显式 `--proxy-url http://127.0.0.1:17890`，保留可复现的任务记录。日常交互终端也可先 proxy_on 再直接 agy。上述系统配置是本机排障修复，不是技能安装时的自动操作；其他机器不要直接套用本机代理端口。

早期 Claude 成功、Gemini 地区错误、临时生产后端 429 都是修复前的诊断结果。生产后端覆盖从未持久化，也不需要作为当前启动配置。不能仅凭地区错误文案断定服务端账号资格问题，应先对照实际域名、DNS 和转发路径。

真实 Gemini 任务 `task-6589ff584d1c4fce82afb04d66f5dbe1` 的界面确认 Gemini 3.8 Flash High；六个代理变量匹配 17890；结果包含 AGY_GEMINI_WORKER_OK 与 667。主代理核对 task/attempt、独立验算 23×29、检查工作区与 Git 状态零变化后接受，随后关闭并 prune 精确 socket。此结果验证当前任务通道，不扩大为所有审批、多行和取消行为均已验收。

OpenCode 当前没有在线调用记录，默认版本探测也不执行它。即使显式打开兼容入口，也仍需要实际确认启动参数、身份、输入、取消和结果提取；不能仅凭可执行文件存在宣称支持通过。

## Cursor Agent CLI

使用 `init --profile cursor`。本机 `agent` 和 `cursor-agent` 指向同一官方 CLI；优先选择 cursor-agent，便于与其他软件的通用 agent 命令区分。仅有 agent 时，应核对它确实为 Cursor CLI。默认开启 sandbox，保留已有审批，不传 --force/--yolo、--approve-mcps 或 --trust；不改变持久模型。--model 只接受当前合同允许的基础模型 ID，不支持带方括号的参数化模型表达式。

[官方安装说明](https://cursor.com/docs/cli/installation)使用 agent 命令；[参数说明](https://cursor.com/docs/cli/reference/parameters)列出 --model 与 --sandbox enabled。不要将 CLI 可用性扩大为原生 Windows 上的 tmux 控制已支持；统一技能仍在 Linux/WSL 中运行。

本机真实验收：Cursor CLI 2026.10.16-e3cb207，默认 Auto，任务 task-52823954b5d648ad8f39107d250502e0。安装包经 tmux 启动，读屏确认完整短指令后只提交一次；工作进程读取 prompt.txt、写 result.json，返回 CURSOR_WORKER_OK 与 17×23=391。collect 验证身份和零工作区/Git 变化，主代理独立验算后 accept、close、prune。实际 pane 六个代理变量均为 17890；没有 --force/--yolo 或 --trust。Auto 的底层模型没有确认；多行、审批框识别和取消生成仍需单独验收。
