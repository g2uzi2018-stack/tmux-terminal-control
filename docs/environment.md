# 环境检查（2026-10-14，Asia/Taipei）

WSL 2 Debian13、用户 dev；Debian GNU/Linux 13.7 (trixie)，内核 6.18.54.1-microsoft-standard-WSL2 x86_64。

初检 tmux / Python 3 未安装；apt-get install tmux python3 后复检：

| 工具 | 路径 | 实际结果 |
|---|---|---|
| tmux | /usr/bin/tmux | tmux -V → tmux 3.5a（包 3.5a-3） |
| Python | /usr/bin/python3 | python3 --version → Python 3.13.5 |
| Bash | /usr/bin/bash | GNU bash 5.2.37 |
| Codex | /home/dev/.local/bin/codex | 2026-10-15 `--version` → codex-cli 0.162.1 |
| OpenCode | /home/dev/.opencode/bin/opencode | 2026-10-15 `--version` → opencode v2.0.28 |
| agy（Antigravity CLI） | /home/dev/.local/bin/agy | 2026-10-15 `--version` → 1.3.5。2026-10-14 `command -v antigravity` 无结果；验收用 `agy` |
| 本次 proxy_on | 当前交互 shell 的函数，不是可执行文件 | 成功。输出 `Proxy ON: http://127.0.0.1:7890`。`http_proxy`、`https_proxy`、`all_proxy` 均为该地址，`NODE_USE_ENV_PROXY=1` 已导出。验收用的 tmux server 在此之后启动，pane 环境已核对含这四项 |

直接 wsl --exec 的 PATH 未含 ~/.local/bin / ~/.opencode/bin，不能因此说 CLI 未安装。启动用实际解析的绝对路径及环境。2026-10-14 只检查版本；2026-10-15 与 2026-10-16 的 TUI 验收见 [cli-acceptance.md](cli-acceptance.md)。2026-10-16 复测版本未变：Codex 0.162.1、OpenCode 2.0.28、agy 1.3.5。画面里的 Codex 0.163.0 与 OpenCode 2.0.30 更新提示没有执行。当天 `uptime -s` 为 `2026-10-16 10:28:56`。

这条只记本机环境，不写进 SKILL.md。当前工具里的 shell 不会把上一条命令的导出变量留给下一条。`proxy_on` 必须和 `session.py new` 写在同一条 `bash -ic 'proxy_on && python3 ... session.py new ...'` 里。核对目标进程本身：`tr '\0' '\n' < /proc/PID/environ | grep -i -E '^(https?|all)_proxy=|NODE_USE_ENV_PROXY'`。只看 `tmux show-environment` 不够。第一轮第一次 Codex 启动没带上这些变量，进程退出，画面是：

```text
Error: account/read failed during TUI bootstrap: account/read failed: workspace routing discovery timed out (code -32603)
```

仓库初始无提交/无 Git author 配置。自动化提交命令级 author 为 Codex <codex@localhost>，不改全局身份。
